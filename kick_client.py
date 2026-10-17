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
# Proxy Management
# ──────────────────────────────────────────────

_PROXIES_CACHE = []
_PROXY_INDEX = 0
_PROXY_LOCK = threading.Lock()

def load_proxies_list():
    global _PROXIES_CACHE
    import os
    candidates = ['proxies.txt', 'discordbot/proxies.txt']
    loaded = []
    for p in candidates:
        if os.path.exists(p):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            parts = line.split(':')
                            if len(parts) == 4:
                                ip, port, u, pwd = parts
                                loaded.append(f'http://{u}:{pwd}@{ip}:{port}')
                            elif len(parts) == 2:
                                ip, port = parts
                                loaded.append(f'http://{ip}:{port}')
            except Exception as e:
                logger.warning(f'Error reading proxy file {p}: {e}')
    _PROXIES_CACHE = loaded
    return _PROXIES_CACHE

def get_next_proxy(priority_low_latency: bool = False):
    """
    Proxy Hızına Göre Yük Dengeleme (Madde 81) & Residential/Datacenter Ayrımı (Madde 82).
    Düşük pingli (<200ms) proxy'lere reaksiyon/hype için öncelik verir.
    """
    global _PROXY_INDEX
    with _PROXY_LOCK:
        if not _PROXIES_CACHE:
            load_proxies_list()
        if not _PROXIES_CACHE:
            return None

        # Check DB for best scored proxies if low latency requested
        import storage
        try:
            stats = storage.get_proxy_stats()
            alive_fast = [s['proxy'] for s in stats if s.get('is_alive') and 0 < s.get('latency_ms', 9999) < 250]
            if priority_low_latency and alive_fast:
                proxy_url = random.choice(alive_fast)
                return {'http': proxy_url, 'https': proxy_url}
        except Exception:
            pass

        proxy_url = _PROXIES_CACHE[_PROXY_INDEX % len(_PROXIES_CACHE)]
        _PROXY_INDEX += 1
        return {'http': proxy_url, 'https': proxy_url}


# ──────────────────────────────────────────────
# Send Message (with Proxy & Direct Fallback)
# ──────────────────────────────────────────────

def send_kick_message(chatroom_id, content: str, bearer_token: str, use_proxy: bool = True):
    """
    Send a message to Kick chat with Proxy scoring, Auto-brake on 429, and Direct Fallback.
    Returns (success: bool, response_text: str)
    """
    import storage
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

    # Helper for followers only auto-bypass
    def _check_and_bypass_followers_only(resp_status, resp_text):
        if resp_status == 400 and 'FOLLOWERS_ONLY_ERROR' in resp_text:
            channel_slug = storage.get_setting('channel')
            if channel_slug:
                try:
                    logger.info(f"[Auto-Bypass] Channel is followers-only! Auto-following {channel_slug}...")
                    follow_url = f'https://kick.com/api/v2/channels/{channel_slug}/follow'
                    follow_headers = {**_HEADERS, 'Authorization': f'Bearer {token}'}
                    requests.post(follow_url, headers=follow_headers, timeout=5)
                    time.sleep(1.0)
                    retry_resp = requests.post(url, json=payload, headers=headers, timeout=7)
                    if retry_resp.status_code in (200, 201):
                        return True, retry_resp.text
                except Exception as fe:
                    logger.warning(f"Auto-follow bypass error: {fe}")
        return False, resp_text

    # 1. Try with proxy if enabled
    if use_proxy:
        proxies = get_next_proxy()
        if proxies:
            proxy_addr = proxies.get('http', '')
            t0 = time.time()
            try:
                resp = requests.post(url, json=payload, headers=headers, proxies=proxies, timeout=7)
                latency = (time.time() - t0) * 1000
                if resp.status_code in (200, 201):
                    storage.record_proxy_result(proxy_addr, True, latency)
                    return True, resp.text
                elif resp.status_code == 429:
                    logger.warning("[Auto-Brake] 429 Rate limit hit on proxy, cooling down 3s...")
                    time.sleep(3.0)
                    storage.record_proxy_result(proxy_addr, False, latency)
                else:
                    bypassed, byp_resp = _check_and_bypass_followers_only(resp.status_code, resp.text)
                    if bypassed:
                        storage.record_proxy_result(proxy_addr, True, latency)
                        return True, byp_resp
                    storage.record_proxy_result(proxy_addr, False, latency)
            except Exception as pe:
                storage.record_proxy_result(proxy_addr, False, 9999)
                logger.debug(f'Proxy attempt failed ({pe}), falling back to direct connection...')

    # 2. Direct fallback (kendi IP'si üzerinden çalışma garantisi)
    try:
        t0 = time.time()
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        if resp.status_code == 429:
            logger.warning("[Auto-Brake] 429 Rate limit on Direct IP, sleeping 2.5s...")
            time.sleep(2.5)
        if resp.status_code in (200, 201):
            return True, resp.text
        bypassed, byp_resp = _check_and_bypass_followers_only(resp.status_code, resp.text)
        if bypassed:
            return True, byp_resp
        return False, resp.text
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

            elif 'StreamHostEvent' in event:
                # Madde 28: Raid Karşılama
                logger.info(f"Raid detected! Data: {data}")
                if self.on_message_cb:
                    self.on_message_cb({'type': 'raid', 'content': 'Raid geldi!', 'username': 'KickRaid'})

            elif 'PollUpdateEvent' in event:
                # Madde 29: Anket / Poll Algılayıcı
                logger.info(f"Poll update event: {data}")
                if self.on_message_cb:
                    self.on_message_cb({'type': 'poll', 'content': 'Anket açıldı!', 'username': 'KickPoll'})

            elif 'ChannelUpdatedEvent' in event or 'StreamUpdateEvent' in event:
                # Madde 67: Kategori / Yayın başlığı değişimi algılayıcı
                logger.info(f"[Kategori/Başlık Değişimi] Event: {event}, Data: {data}")
                if self.on_message_cb:
                    self.on_message_cb({'type': 'category_change', 'content': 'Yayın başlığı veya kategorisi güncellendi!', 'username': 'KickSystem'})

            elif 'ChatroomUpdatedEvent' in event:
                # Madde 5 & 14: Slow Mode & Sub-Only Mode tespiti
                logger.info(f"Chatroom settings updated: {data}")

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
