"""
pipeline.py — Mesaj işleme pipeline'ı
Kick mesajı → spam filtre → AI seç → yanıt üret → Kick'e gönder → dashboard'a bildir
"""
import threading
import time
import logging
from collections import deque

import storage
import ai_engine

logger = logging.getLogger(__name__)

# Words that trigger moderation block
_BLOCKED_PATTERNS = [
    'nigger', 'faggot', 'kıç', 'göt', 'sik', 'amk', 'orospu', 'piç',
]


def _is_safe(text: str) -> bool:
    tl = text.lower()
    for p in _BLOCKED_PATTERNS:
        if p in tl:
            return False
    return True


class MessagePipeline:
    def __init__(self, bot_manager, emit_fn=None):
        self.bot_manager = bot_manager
        self.emit = emit_fn            # socketio emit function
        self.chatroom_id = None
        self.enabled = True

        self._chat_history: deque = deque(maxlen=100)
        self._recent_contents: dict[str, float] = {}   # content → last_seen_ts
        self._queue: deque = deque()
        self._lock = threading.Lock()
        self._bot_usernames: set[str] = set()          # lowercase bot usernames to skip
        self._refresh_bot_names()

        # Background processor
        self._proc_thread = threading.Thread(
            target=self._processor_loop, daemon=True, name='pipeline'
        )
        self._proc_thread.start()

    # ──────────────────────────────────────────
    # Public
    # ──────────────────────────────────────────

    def set_chatroom_id(self, chatroom_id):
        self.chatroom_id = chatroom_id

    def handle_incoming(self, message: dict):
        """Entry point called by KickChatClient for each chat message."""
        if not self.enabled:
            return

        username = (message.get('username') or '').lower()
        content = (message.get('content') or '').strip()
        if not content:
            return

        # Emit raw chat message to dashboard
        self._safe_emit('chat_message', {**message, 'msg_type': 'user'})

        # Is this one of our own bots? Add to history but don't re-process
        if username in self._bot_usernames:
            self._add_history({**message, 'type': 'bot', 'bot_name': username})
            return

        # Spam / flood filter — same content within 5 s
        now = time.time()
        last = self._recent_contents.get(content, 0)
        if now - last < 5:
            return
        self._recent_contents[content] = now

        user_msg = {**message, 'type': 'user'}
        self._add_history(user_msg)

        with self._lock:
            self._queue.append(user_msg)

    def refresh_bot_names(self):
        self._refresh_bot_names()

    # ──────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────

    def _refresh_bot_names(self):
        bots = storage.get_bots()
        self._bot_usernames = {b['name'].lower() for b in bots}

    def _add_history(self, msg: dict):
        self._chat_history.append(msg)

    def _safe_emit(self, event: str, data: dict):
        if self.emit:
            try:
                self.emit(event, data)
            except Exception as e:
                logger.debug(f'emit error: {e}')

    # ──────────────────────────────────────────
    # Processor loop
    # ──────────────────────────────────────────

    def _processor_loop(self):
        while True:
            try:
                with self._lock:
                    msg = self._queue.popleft() if self._queue else None
                if msg:
                    self._process(msg)
                else:
                    time.sleep(0.4)
            except Exception as e:
                logger.error(f'Pipeline processor error: {e}')
                time.sleep(1)

    def _process(self, message: dict):
        if not self.chatroom_id:
            return

        bots = storage.get_bots()
        enabled_bots = [b for b in bots if b.get('enabled')]
        if not enabled_bots:
            return

        # Build cooldown & daily maps
        cooldowns = {
            b['id']: self.bot_manager.get_cooldown_remaining(b['id'])
            for b in enabled_bots
        }
        daily = {
            b['id']: self.bot_manager.get_daily_count(b['id'])
            for b in enabled_bots
        }

        # Select bot
        selected = ai_engine.select_bot(
            enabled_bots, message['content'], cooldowns, daily
        )

        if not selected:
            storage.log_message(
                'user', message['username'], message['content'],
                status='skipped', analysis='Uygun bot yok / cooldown / limit'
            )
            return

        # Resolve AI token
        token_id = selected.get('ai_token_id') or storage.get_first_ai_token_id()
        if not token_id:
            storage.log_message(
                'user', message['username'], message['content'],
                bot_name=selected['name'], status='error',
                error_msg='AI token atanmamış'
            )
            return

        api_key, base_url, model = storage.get_ai_token_raw(token_id)
        if not api_key:
            storage.log_message(
                'user', message['username'], message['content'],
                bot_name=selected['name'], status='error',
                error_msg='API key çözülemedi'
            )
            return

        # Notify dashboard: generating
        self._safe_emit('pipeline_status', {
            'status': 'generating',
            'bot': selected['name'],
            'trigger': message['content'][:60],
        })

        # Generate AI response
        history_snapshot = list(self._chat_history)[:-1]  # exclude last (current msg)
        response, error = ai_engine.generate_response(
            selected, history_snapshot, message, api_key, base_url, model
        )

        if error:
            storage.log_message(
                'user', message['username'], message['content'],
                bot_name=selected['name'], status='error',
                analysis=f'{selected["name"]} seçildi', error_msg=error
            )
            self._safe_emit('pipeline_status', {'status': 'error', 'bot': selected['name'], 'error': error})
            return

        if not response:
            return

        # Safety check
        if not _is_safe(response):
            logger.warning(f'Unsafe response from {selected["name"]}: {response[:40]}')
            return

        # Send to Kick
        success, detail = self.bot_manager.send_message(selected, self.chatroom_id, response)
        status = 'sent' if success else 'error'

        analysis = (
            f'{selected["name"]} → {message["username"]}: '
            f'"{message["content"][:30]}"'
        )
        storage.log_message(
            'bot', selected['name'], response,
            bot_name=selected['name'], analysis=analysis,
            status=status, error_msg=None if success else detail
        )

        if success:
            bot_msg = {
                'id': f'bot_{time.time()}',
                'username': selected['name'],
                'content': response,
                'type': 'bot',
                'bot_name': selected['name'],
                'msg_type': 'bot',
            }
            self._add_history(bot_msg)
            self._safe_emit('chat_message', bot_msg)
            self._safe_emit('pipeline_status', {
                'status': 'sent',
                'bot': selected['name'],
                'message': response,
                'in_reply_to': message['content'][:40],
            })
        else:
            self._safe_emit('pipeline_status', {
                'status': 'send_error',
                'bot': selected['name'],
                'error': detail[:80],
            })
