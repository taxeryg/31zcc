"""
kick_client.py — Kick Pusher WebSocket bağlantısı + mesaj gönderme
"""
import json
import threading
import time
import logging
import requests
import websocket

logger = logging.getLogger(__name__)

KICK_APP_KEY = '34bf7a0ff419a2a775b9'
KICK_CLUSTER = 'us2'

def get_pusher_credentials(channel_id=None):
    """Dynamically fetch current Pusher app_key and cluster from Kick API, with fallback."""
    global KICK_APP_KEY, KICK_CLUSTER
    try:
        cid = channel_id or 668
        url = f'https://web.kick.com/api/v1/realtime/channels/{cid}/chat/connection'
        headers = {
            'Referer': 'https://kick.com',
            'Origin': 'https://kick.com',
            'Accept': 'application/json',
            'x-app-platform': 'web',
            'Content-Type': 'application/json',
            'User-Agent': _HEADERS['User-Agent'],
        }
        body = {
            'client': {'id': '68b6dbe3-a5fe-48b9-9e97-61938f004681', 'type': 'web'},
            'capabilities': {'accepted_providers': [{'provider': 'pusher'}]}
        }
        resp = requests.post(url, headers=headers, json=body, timeout=5)
        if resp.status_code == 200:
            conns = resp.json().get('data', {}).get('connections', [])
            for c in conns:
                if c.get('provider') == 'pusher':
                    creds = c.get('credentials', {})
                    if creds.get('app_key'):
                        KICK_APP_KEY = creds['app_key']
                        KICK_CLUSTER = creds.get('cluster', 'us2')
                        logger.info(f"Updated Kick Pusher credentials: key={KICK_APP_KEY}, cluster={KICK_CLUSTER}")
                        return KICK_APP_KEY, KICK_CLUSTER
    except Exception as e:
        logger.warning(f"Could not fetch dynamic Pusher credentials: {e}")
    return KICK_APP_KEY, KICK_CLUSTER

def get_kick_ws_url(channel_id=None):
    key, cluster = get_pusher_credentials(channel_id)
    return (
        f'wss://ws-{cluster}.pusher.com/app/{key}'
        '?protocol=7&client=js&version=7.6.0&flash=false'
    )

KICK_WS_URL = (
    f'wss://ws-{KICK_CLUSTER}.pusher.com/app/{KICK_APP_KEY}'
    '?protocol=7&client=js&version=7.6.0&flash=false'
)
KICK_API_BASE = 'https://kick.com/api/v2'

_HEADERS = {
    'Accept': 'application/json',
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
}


# ──────────────────────────────────────────────
# Channel Info
# ──────────────────────────────────────────────

def get_channel_info(channel_input: str):
    """Returns (chatroom_id, slug) or (None, None) on failure."""
    channel_input = str(channel_input).strip()
    if channel_input.isdigit():
        return int(channel_input), f"id:{channel_input}"

    try:
        url = f'{KICK_API_BASE}/channels/{channel_input}'
        resp = requests.get(url, headers=_HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            chatroom_id = data.get('chatroom', {}).get('id')
            slug = data.get('slug', channel_input)
            return chatroom_id, slug
        logger.warning(f'Channel info status {resp.status_code} for {channel_input}')
    except Exception as e:
        logger.error(f'get_channel_info error: {e}')
    return None, None


# ──────────────────────────────────────────────
# Send Message
# ──────────────────────────────────────────────

def send_kick_message(chatroom_id, content: str, bearer_token: str):
    """
    Send a message to Kick chat.
    Returns (success: bool, response_text: str)
    """
    token = bearer_token.strip()
    if token.startswith("Bearer "):
        token = token[7:].strip()
    url = f'{KICK_API_BASE}/messages/send/{chatroom_id}'
    headers = {
        **_HEADERS,
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }
    payload = {'content': content, 'type': 'message'}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        ok = resp.status_code in (200, 201)
        return ok, resp.text
    except Exception as e:
        logger.error(f'send_kick_message error: {e}')
        return False, str(e)


# ──────────────────────────────────────────────
# WebSocket Client
# ──────────────────────────────────────────────

class KickChatClient:
    def __init__(self, on_message_cb=None, on_status_cb=None):
        self.on_message_cb = on_message_cb
        self.on_status_cb = on_status_cb

        self.ws = None
        self.channel: str | None = None
        self.chatroom_id = None
        self.connected = False
        self.running = False
        self._thread: threading.Thread | None = None
        self._reconnect_delay = 2
        self._max_reconnect_delay = 60

    # ── Public ──────────────────────────────

    def connect(self, channel_name: str) -> bool:
        if self.running:
            self.disconnect()
            time.sleep(0.5)

        chatroom_id, _ = get_channel_info(channel_name)
        if not chatroom_id:
            self._status('error', f'Kanal bulunamadı: {channel_name}')
            return False

        self.channel = channel_name
        self.chatroom_id = chatroom_id
        self.running = True
        self._reconnect_delay = 2
        self._status('connecting', f'Bağlanıyor → {channel_name}…')

        self._thread = threading.Thread(target=self._run_loop, daemon=True, name='kick-ws')
        self._thread.start()
        return True

    def disconnect(self):
        self.running = False
        self.connected = False
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
        self._status('disconnected', 'Bağlantı kesildi')

    # ── Internal loop ────────────────────────

    def _run_loop(self):
        import traceback
        while self.running:
            try:
                ws_url = get_kick_ws_url(self.chatroom_id)
                self.ws = websocket.WebSocketApp(
                    ws_url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                import ssl
                self.ws.run_forever(sslopt={'cert_reqs': ssl.CERT_NONE})
            except Exception as e:
                print(f'WS loop exception: {e}', flush=True)
                traceback.print_exc()
                logger.error(f'WS loop error: {e}')

            if not self.running:
                break

            time.sleep(self._reconnect_delay)
            self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)

    # ── WS callbacks ─────────────────────────

    def _on_open(self, ws):
        print('Kick WS opened', flush=True)
        logger.info('Kick WS opened')

    def _on_message(self, ws, raw: str):
        try:
            print(f'Kick WS msg: {raw[:120]}', flush=True)
            data = json.loads(raw)
            event = data.get('event', '')

            if event == 'pusher:error':
                err_data = data.get('data', {})
                if isinstance(err_data, str):
                    try: err_data = json.loads(err_data)
                    except: pass
                code = err_data.get('code') if isinstance(err_data, dict) else None
                if code == 4001:
                    logger.warning("Pusher 4001 error, refreshing credentials...")
                    get_pusher_credentials(self.chatroom_id)

            elif event == 'pusher:connection_established':
                self.connected = True
                self._status('connected', f'Bağlandı ✓  {self.channel} (#{self.chatroom_id})')
                ws.send(json.dumps({
                    'event': 'pusher:subscribe',
                    'data': {'channel': f'chatrooms.{self.chatroom_id}.v2'}
                }))

            elif event == 'pusher_internal:subscription_succeeded':
                self.connected = True
                self._reconnect_delay = 2
                self._status('connected', f'Abone Olundu ✓  {self.channel} (#{self.chatroom_id})')

            elif 'ChatMessageEvent' in event or 'ChatMessageSent' in event:
                raw_d = data.get('data', '{}')
                if isinstance(raw_d, str):
                    try:
                        msg_data = json.loads(raw_d)
                    except Exception:
                        msg_data = {}
                elif isinstance(raw_d, dict):
                    msg_data = raw_d
                else:
                    msg_data = {}
                self._handle_chat(msg_data)

            elif event == 'pusher:ping':
                ws.send(json.dumps({'event': 'pusher:pong', 'data': {}}))

        except Exception as e:
            print(f'_on_message parse error: {e}', flush=True)
            logger.error(f'_on_message parse error: {e}')

    def _on_error(self, ws, error):
        print(f'Kick WS error: {error}', flush=True)
        logger.error(f'Kick WS error: {error}')
        self.connected = False
        self._status('error', f'WS Hatası: {error}')

    def _on_close(self, ws, code, msg):
        print(f'Kick WS closed: {code} {msg}', flush=True)
        logger.info(f'Kick WS closed: {code} {msg}')
        self.connected = False

    # ── Helpers ──────────────────────────────

    def _handle_chat(self, msg_data: dict):
        try:
            sender = msg_data.get('sender', {})
            message = {
                'id': msg_data.get('id', ''),
                'username': sender.get('username', 'unknown'),
                'content': msg_data.get('content', ''),
                'sender': sender,
                'type': 'user',
            }
            if self.on_message_cb:
                self.on_message_cb(message)
        except Exception as e:
            logger.error(f'_handle_chat error: {e}')

    def _status(self, status: str, message: str):
        if self.on_status_cb:
            try:
                self.on_status_cb(status, message)
            except Exception:
                pass
