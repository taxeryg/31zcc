"""
pipeline.py — Mesaj işleme pipeline'ı
Kick mesajı → spam filtre → AI seç → yanıt üret → Kick'e gönder → dashboard'a bildir
"""
import threading
import time
import logging
import random
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
    # Check dynamic blacklist from DB
    try:
        banned_from_db = storage.get_banned_words()
        for bw in banned_from_db:
            if bw in tl:
                return False
    except Exception:
        pass
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

        self._last_activity_time = time.time()

        # Background processor
        self._proc_thread = threading.Thread(
            target=self._processor_loop, daemon=True, name='pipeline'
        )
        self._proc_thread.start()

        # Background idle chatter (ölü chat canlandırıcı & bot paslaşması)
        self._idle_thread = threading.Thread(
            target=self._idle_chatter_loop, daemon=True, name='idle-chatter'
        )
        self._idle_thread.start()

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

        self._last_activity_time = time.time()
        # Emit raw chat message to dashboard
        self._safe_emit('chat_message', {**message, 'msg_type': 'user'})

        # Is this one of our own bots? Add to history but don't re-process
        if username in self._bot_usernames:
            self._add_history({**message, 'type': 'bot', 'bot_name': username})
            return

        # Madde 28: Raid algılandığında otomatik karşılama
        if message.get('type') == 'raid':
            self.bot_manager.trigger_hype(self.chatroom_id, count=5, custom_content="HOŞ GELDİNİZ! 🎉")
            return

        # Madde 29: Poll algılandığında reaksiyon
        if message.get('type') == 'poll':
            self.bot_manager.trigger_hype(self.chatroom_id, count=3, custom_content="anket açıldı basalım")
            return

        # Madde 67: Kategori / Başlık Değişimi Reaksiyonu
        if message.get('type') == 'category_change':
            category_reaction = random.choice(["oyun değişti beyler", "yeni oyun sarar", "kategori değişti hayırlı olsun", "hadi bakalım"])
            self.bot_manager.send_message(self.bot_manager.get_pool_account() or {'id': 1, 'name': 'MertBot'}, self.chatroom_id, category_reaction)
            return

        # Madde 57: Yayına yeni katılanı ("hg kanka") karşılama dedektörü
        existing_mem = storage.get_user_memory(username)
        if not existing_mem and random.random() < 0.20:
            logger.info(f"[Yeni İzleyici Dedektörü] {username} ilk defa yazdı, hoş geldin karşılaması hazırlanıyor.")
            welcome_msg = random.choice(["as hg kanka", "hg kanka aramıza", "hoş geldin reis", "hg"])
            threading.Thread(target=lambda: (time.sleep(random.uniform(2.0, 4.5)), self.bot_manager.send_message(self.bot_manager.get_pool_account() or {'id': 1, 'name': 'MertBot'}, self.chatroom_id, welcome_msg)), daemon=True).start()

        # Madde 3: Chat Hızı (Spike) & Klip Algılayıcı (10 saniyede 15+ mesaj)
        self._recent_timestamps = getattr(self, '_recent_timestamps', deque(maxlen=30))
        now = time.time()
        self._recent_timestamps.append(now)
        if len(self._recent_timestamps) >= 15 and (now - self._recent_timestamps[0]) < 8.0:
            logger.info("[Spike / Klip Algılayıcı] Chat akışı 5x fırladı, otomatik reaksiyon basılıyor!")
            self._recent_timestamps.clear()
            self.bot_manager.trigger_hype(self.chatroom_id, count=4, custom_content=random.choice(["KLİP ALIN", "OHA", "NE OLDU LAN", "GG", "W"]))

        # Spam / flood filter — same content within 5 s
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
    # Autonomous Idle Chatter Loop (with Night Sleep Mode)
    # ──────────────────────────────────────────

    def _idle_chatter_loop(self):
        """If chat is idle for 90-180 seconds, send an organic chat-starter or banter."""
        import random
        from datetime import datetime
        while True:
            try:
                time.sleep(30)
                if not self.enabled or not self.chatroom_id:
                    continue

                # Madde 83: Gece Uyku Modu (04:00 - 09:00 arası botların %80'i uyur)
                current_hour = datetime.now().hour
                if 4 <= current_hour < 9:
                    if random.random() < 0.80:
                        # Gece saatlerinde sessiz kal
                        continue

                idle_duration = time.time() - self._last_activity_time
                # Chat idle threshold: 90 - 180 seconds
                if idle_duration > random.randint(90, 180):
                    bots = storage.get_bots()
                    enabled_bots = [b for b in bots if b.get('enabled')]
                    if not enabled_bots:
                        continue

                    # Select random bot
                    bot = random.choice(enabled_bots)
                    if self.bot_manager.is_on_cooldown(bot['id']):
                        continue

                    # Get AI token
                    token_id = bot.get('ai_token_id') or storage.get_first_ai_token_id()
                    api_key, base_url, model = storage.get_ai_token_raw(token_id)
                    if not api_key:
                        continue

                    # Build prompt for conversation starter
                    prompt_starter = {
                        'username': 'chat_starter',
                        'content': 'Chat sessizleşti, ortaya samimi, kısa ve doğal bir şey yaz veya soru sor.'
                    }
                    resp, err = ai_engine.generate_response(
                        bot, list(self._chat_history), prompt_starter,
                        api_key, base_url, model
                    )
                    if err == 'rate_limit':
                        logger.warning("[AI Throttle] AI Rate limit hit in idle loop, cooling down 60s...")
                        time.sleep(60)
                        continue

                    if resp and not err and _is_safe(resp):
                        ok, detail = self.bot_manager.send_message(bot, self.chatroom_id, resp)
                        if ok:
                            self._last_activity_time = time.time()
                            bot_msg = {
                                'id': f'bot_{time.time()}',
                                'username': bot['name'],
                                'content': resp,
                                'type': 'bot',
                                'bot_name': bot['name'],
                                'msg_type': 'bot',
                            }
                            self._add_history(bot_msg)
                            self._safe_emit('chat_message', bot_msg)
                            storage.log_message('bot', bot['name'], resp, bot_name=bot['name'],
                                                analysis='[Idle Chatter / Konuşma Başlatıcı]', status='sent')
            except Exception as e:
                logger.error(f'Idle chatter error: {e}')

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
            saved_cid = storage.get_setting('chatroom_id')
            if saved_cid:
                try:
                    self.chatroom_id = int(saved_cid)
                except Exception:
                    pass

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

        # 1. Update User Memory Store
        storage.update_user_memory(message.get('username'), topic=message.get('content')[:50])
        user_mem = storage.get_user_memory(message.get('username'))

        # 2. Chat Sentiment Detection (Hype vs Normal)
        content_lower = message['content'].lower()
        sentiment = 'neutral'
        if any(h in content_lower for h in ('oha', 'woow', 'letss go', 'w', 'omg', 'gg', 'helal', 'adamsın', 'lan')):
            sentiment = 'hype'
        elif any(t in content_lower for t in ('çöp', 'bot', 'rezil', 'yuh', 'satılık')):
            sentiment = 'toxic'

        # Madde 53: Futbol/Derbi Gündemi kontrolü
        is_derby = any(fb in content_lower for fb in ('maç', 'derbi', 'gs', 'fb', 'bjk', 'ts', 'gol', 'ofsayt', 'hakem'))

        # Madde 77: Bölgesel Dil / Ağız Adaptasyonu (Botun karakterine veya rastgele havuzuna göre)
        dialect = None
        if random.random() < 0.15:
            dialect = random.choice(['ege', 'karadeniz'])

        # Generate AI response with sentiment, derby, and regional dialect
        history_snapshot = list(self._chat_history)[:-1]  # exclude last (current msg)
        response, error = ai_engine.generate_response(
            selected, history_snapshot, message, api_key, base_url, model,
            sentiment=sentiment, user_mem=user_mem,
            regional_dialect=dialect, is_derby_day=is_derby
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

        # 3. Anti-Duplicate Filter (son 10 mesajla aynı kalıpta olmasın)
        recent_bot_responses = [m.get('content', '').lower().strip() for m in list(self._chat_history)[-10:] if m.get('type') == 'bot']
        if response.lower().strip() in recent_bot_responses:
            logger.info(f"Anti-duplicate triggered for '{response}', modifying...")
            response = f"{response} valla"

        # Safety check
        if not _is_safe(response):
            logger.warning(f'Unsafe response from {selected["name"]}: {response[:40]}')
            return

        # 4. Human Typing Delay & Slow Mode Adaptor
        typing_delay = min(max(len(response) * 0.12, 1.2), 4.5)
        time.sleep(typing_delay)

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

            # Madde 79: Kick oto-moduna veya banına takılan hesaba 5 dk sessizlik (cooldown) cezası
            if 'moderation' in str(detail).lower() or 'timeout' in str(detail).lower() or 'blocked' in str(detail).lower():
                logger.warning(f"[Oto-Mod Koruması] {selected['name']} moderasyon cezası aldı, 5 dakika (300s) dinlenmeye alınıyor...")
                self.bot_manager._set_cooldown(selected['id'], 300)

            # Discord Red Alert Webhook (Kritik Uyarı)
            webhook_url = storage.get_setting('discord_webhook_url')
            if webhook_url and ('banned' in str(detail).lower() or 'authenticated' in str(detail).lower()):
                try:
                    import requests as _req
                    _req.post(webhook_url, json={
                        "username": "KickBot Emergency Guard",
                        "embeds": [{
                            "title": "🚨 Kick Bot Gönderim Hatası!",
                            "description": f"**Bot:** `{selected['name']}`\n**Hata:** `{str(detail)[:150]}`",
                            "color": 15158332,
                            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                        }]
                    }, timeout=5)
                except Exception:
                    pass
