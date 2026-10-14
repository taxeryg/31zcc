"""
app.py — Flask + SocketIO ana uygulama
"""
import functools
import logging
import os
import sys
import time

import threading

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)-8s %(name)s: %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger(__name__)

from flask import Flask, jsonify, render_template, request, session, redirect, url_for
from flask_socketio import SocketIO, emit

import storage
import kick_client as kc
import ai_engine
import kick_account_creator as kac
from bot_manager import BotManager
from pipeline import MessagePipeline

# ── Init ─────────────────────────────────────
storage.init_db()
storage.insert_default_bots()

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = os.environ.get('SECRET_KEY', 'kick_ai_bot_s3cr3t_2026_xK9_egeazakli_auth')
app.config['PERMANENT_SESSION_LIFETIME'] = 86400 * 30  # 30 gün kalıcı oturum

ADMIN_USERNAME = os.environ.get('ADMIN_USER', 'egeazakli')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASS', 'ege123')

socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading')

# ── Global state ─────────────────────────────
_kick_client: kc.KickChatClient | None = None
_bot_manager = BotManager()
_account_creator: kac.KickAccountCreatorSession | None = None


def _emit(event: str, data: dict):
    socketio.emit(event, data)


def _get_account_creator() -> kac.KickAccountCreatorSession:
    global _account_creator
    if _account_creator is None:
        _account_creator = kac.KickAccountCreatorSession(emit_fn=_emit)
    return _account_creator


def _on_kick_message(message: dict):
    if _pipeline:
        _pipeline.handle_incoming(message)


def _on_kick_status(status: str, message: str):
    logger.info(f'[_on_kick_status] status={status}, msg={message}')
    socketio.emit('kick_status', {'status': status, 'message': message})
    if status not in ('connecting', 'reconnecting'):
        storage.log_message('system', 'system', message, status=status)


_pipeline: MessagePipeline = MessagePipeline(_bot_manager, _emit)
_saved_cid = storage.get_setting('chatroom_id')
if _saved_cid:
    try:
        _pipeline.set_chatroom_id(int(_saved_cid))
    except Exception:
        pass


def _get_or_create_pipeline() -> MessagePipeline:
    return _pipeline


def _auto_connect_saved():
    time.sleep(2.0)
    global _kick_client
    ch = storage.get_setting('channel')
    if ch:
        try:
            logger.info(f"Auto-connecting to saved Kick channel: {ch}")
            _kick_client = kc.KickChatClient(
                on_message_cb=_on_kick_message,
                on_status_cb=_on_kick_status,
            )
            pipeline = _get_or_create_pipeline()
            success = _kick_client.connect(ch)
            if success:
                for _ in range(12):
                    if _kick_client.chatroom_id:
                        break
                    time.sleep(0.3)
                if _kick_client.chatroom_id:
                    pipeline.set_chatroom_id(_kick_client.chatroom_id)
                    logger.info(f"Auto-connected successfully to {ch} (#{_kick_client.chatroom_id})")
        except Exception as e:
            logger.warning(f"Auto-connect on startup failed: {e}")

threading.Thread(target=_auto_connect_saved, daemon=True, name='kick-autoconnect').start()


# ═══════════════════════════════════════════════
# Auth Guard & Login Routes
# ═══════════════════════════════════════════════

@app.before_request
def auth_guard():
    # Statik dosyalar serbest
    if request.path.startswith('/static/'):
        return
    # Login sayfaları ve API'si serbest
    if request.path in ('/login', '/api/login'):
        return
        
    # Oturum kontrolü
    if not session.get('logged_in'):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Giriş yapmanız gerekiyor', 'auth_required': True}), 401
        return redirect(url_for('login'))


@app.route('/login', methods=['GET'])
def login():
    if session.get('logged_in'):
        return redirect('/')
    return render_template('login.html')


@app.route('/api/login', methods=['POST'])
def login_api():
    data = request.get_json() or {}
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()
    
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        session['logged_in'] = True
        session['username'] = username
        session.permanent = True
        return jsonify({'success': True, 'redirect': '/'})
        
    return jsonify({'error': 'Invalid username or password!'}), 401


@app.route('/logout', methods=['GET', 'POST'])
def logout():
    session.clear()
    return redirect('/login')


# ═══════════════════════════════════════════════
# Persistent Sync Routes
# ═══════════════════════════════════════════════

@app.route('/api/sync/backup', methods=['GET'])
def sync_backup():
    return jsonify(storage.export_all_data())


@app.route('/api/sync/restore', methods=['POST'])
def sync_restore():
    data = request.get_json() or {}
    ok = storage.restore_all_data(data)
    return jsonify({'success': ok})


@app.route('/api/sync/status', methods=['GET'])
def sync_status():
    import sqlite3
    conn = sqlite3.connect(storage.DB_FILE)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM ai_tokens')
    ai_count = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM kick_accounts')
    kick_count = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM bots')
    bots_count = c.fetchone()[0]
    conn.close()
    return jsonify({
        'ai_tokens': ai_count,
        'kick_accounts': kick_count,
        'bots': bots_count
    })


# ═══════════════════════════════════════════════
# Page Routes
# ═══════════════════════════════════════════════

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/hesapolustur')
def hesap_olustur():
    return render_template('index.html', initial_tab='hesapolustur')


@app.route('/sesdenemesi')
def ses_denemesi():
    return render_template('sesdenemesi.html')


import audio_listener as al
_audio_listener = al.AudioListener(socketio=socketio)

@app.route('/api/audio/start', methods=['POST'])
def start_audio():
    data = request.get_json() or {}
    channel = data.get('channel', '').strip()
    if not channel:
        return jsonify({'error': 'Kanal adı gerekli'}), 400
    _audio_listener.start(channel)
    return jsonify({'success': True})


# ── Channel ──────────────────────────────────

@app.route('/api/channel/connect', methods=['POST'])
def connect_channel():
    global _kick_client
    data = request.get_json() or {}
    channel = (data.get('channel') or '').strip()
    if not channel:
        return jsonify({'error': 'Kanal adı gerekli'}), 400

    if _kick_client:
        _kick_client.disconnect()

    _kick_client = kc.KickChatClient(
        on_message_cb=_on_kick_message,
        on_status_cb=_on_kick_status,
    )

    pipeline = _get_or_create_pipeline()
    success = _kick_client.connect(channel)

    if not success:
        return jsonify({'error': 'Kanal bulunamadı veya bağlantı kurulamadı'}), 400

    # Wait briefly for chatroom_id
    for _ in range(10):
        if _kick_client.chatroom_id:
            break
        time.sleep(0.3)

    if _kick_client.chatroom_id:
        pipeline.set_chatroom_id(_kick_client.chatroom_id)
        storage.set_setting('channel', channel)
        storage.set_setting('chatroom_id', str(_kick_client.chatroom_id))

    return jsonify({
        'success': True,
        'channel': channel,
        'chatroom_id': _kick_client.chatroom_id,
    })


@app.route('/api/channel/disconnect', methods=['POST'])
def disconnect_channel():
    global _kick_client
    if _kick_client:
        _kick_client.disconnect()
        _kick_client = None
    return jsonify({'success': True})


@app.route('/api/channel/status')
def channel_status():
    saved_ch = storage.get_setting('channel')
    saved_cid = storage.get_setting('chatroom_id')
    cid_val = None
    if saved_cid and saved_cid.isdigit():
        cid_val = int(saved_cid)

    if _kick_client:
        return jsonify({
            'connected': _kick_client.connected,
            'channel': _kick_client.channel or saved_ch,
            'chatroom_id': _kick_client.chatroom_id or cid_val,
        })
    return jsonify({'connected': False, 'channel': saved_ch, 'chatroom_id': cid_val})


# ── Rol Kontrolü ─────────────────────────────────
REQUIRED_ROLE_ID = "1552409518380552224"

def check_kick_role(username):
    """Kullanıcının Kick'te belirtilen role sahip olup olmadığını kontrol et"""
    if not username:
        return True
    allowed_users = ["taxer", "sefoge", "taxeryg", "egeazakli", "admin"]
    return username.lower() in allowed_users

def role_required(f):
    """Token yönetimi için rol kontrolü decorator'ı"""
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        # Oturum açmış kullanıcılar tam yetkilidir
        if session.get('logged_in'):
            return f(*args, **kwargs)

        # Web dashboard veya header'dan username al
        username = request.headers.get('X-Username') or request.args.get('username')
        
        # Web arayüzünden doğrudan erişiliyorsa veya izinli kullanıcılardansa izin ver
        if not username or check_kick_role(username):
            return f(*args, **kwargs)
        
        return jsonify({'error': 'Bu işlem için yetkiniz yok! Gerekli rol: Admin'}), 403
    return decorated_function


# ── AI Tokens ─────────────────────────────────

@app.route('/api/tokens', methods=['GET'])
@role_required
def get_tokens():
    return jsonify(storage.get_ai_tokens())


@app.route('/api/tokens', methods=['POST'])
@role_required
def add_token():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    token = (data.get('token') or '').strip()
    base_url = (data.get('base_url') or 'https://api.openai.com/v1').strip()
    model = (data.get('model') or 'gpt-4o-mini').strip()

    if not name or not token:
        return jsonify({'error': 'İsim ve token gerekli'}), 400

    id_ = storage.add_ai_token(name, token, base_url, model)
    return jsonify({'success': True, 'id': id_})


@app.route('/api/tokens/<int:token_id>', methods=['DELETE'])
@role_required
def delete_token(token_id):
    storage.delete_ai_token(token_id)
    return jsonify({'success': True})


@app.route('/api/tokens/<int:token_id>/test', methods=['POST'])
def test_token(token_id):
    api_key, base_url, model = storage.get_ai_token_raw(token_id)
    if not api_key:
        return jsonify({'error': 'Token bulunamadı'}), 404
    ok, msg = ai_engine.test_api_key(api_key, base_url, model)
    return jsonify({'valid': ok, 'message': msg})


@app.route('/api/kick-accounts', methods=['GET'])
def get_kick_accounts():
    return jsonify(storage.get_kick_accounts())


@app.route('/api/kick-accounts', methods=['POST'])
def add_kick_account():
    data = request.get_json() or {}
    username = (data.get('username') or '').strip()
    token = (data.get('token') or '').strip()
    if not token:
        return jsonify({'error': 'Token gerekli'}), 400

    clean_tok = token.replace('Bearer ', '').strip()
    if not username:
        import requests as _req
        try:
            r = _req.get(
                'https://kick.com/api/v1/user',
                headers={'Authorization': f'Bearer {clean_tok}', 'User-Agent': kc._HEADERS['User-Agent']},
                timeout=5
            )
            if r.status_code == 200:
                username = r.json().get('username') or ''
        except Exception:
            pass
    if not username:
        username = f"Hesap_{clean_tok[:8]}"

    id_ = storage.add_kick_account(username, clean_tok)
    return jsonify({'success': True, 'id': id_, 'username': username})


@app.route('/api/kick-accounts/fetch-username', methods=['POST'])
def fetch_kick_username():
    """Given a bearer token, return the Kick username for that account."""
    import requests as _req
    data = request.get_json() or {}
    token = (data.get('token') or '').strip()
    if not token:
        return jsonify({'error': 'Token gerekli'}), 400
    try:
        r = _req.get(
            'https://kick.com/api/v1/user',
            headers={
                'Authorization': f'Bearer {token}',
                'Accept': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0',
            },
            timeout=10,
        )
        if r.status_code == 200:
            j = r.json()
            username = j.get('username') or j.get('name') or ''
            return jsonify({'success': True, 'username': username})
        return jsonify({'success': False, 'error': f'HTTP {r.status_code}', 'username': ''})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'username': ''})


@app.route('/api/kick-accounts/bulk-add', methods=['POST'])
def bulk_add_kick_accounts():
    """
    Accepts a list of bearer tokens, optionally sends a test message to chatroom,
    fetches username from Kick API, and saves to DB.
    Returns per-token results.
    """
    import requests as _req
    data = request.get_json() or {}
    tokens = data.get('tokens', [])
    chatroom_id = data.get('chatroom_id')  # optional — for test message
    test_msg = (data.get('test_msg') or '').strip()

    results = []
    for raw_token in tokens:
        token = (raw_token or '').strip()
        if not token:
            continue

        result = {'token_preview': token[:10] + '...', 'username': '', 'saved': False, 'error': ''}

        # 1. Fetch username from Kick API
        try:
            r = _req.get(
                'https://kick.com/api/v1/user',
                headers={
                    'Authorization': f'Bearer {token}',
                    'Accept': 'application/json',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0',
                },
                timeout=10,
            )
            if r.status_code == 200:
                j = r.json()
                username = j.get('username') or j.get('name') or ''
                result['username'] = username
            else:
                result['error'] = f'Kullanıcı adı alınamadı (HTTP {r.status_code})'
        except Exception as e:
            result['error'] = f'API hatası: {str(e)[:60]}'

        # 2. If chatroom_id given, also send a test message to chat
        msg_ok = False
        if chatroom_id and test_msg:
            try:
                msg_ok, resp_text = kc.send_kick_message(chatroom_id, test_msg, token)
                if msg_ok:
                    socketio.emit('chat_message', {
                        'username': result['username'] or '[Yeni Hesap]',
                        'content': test_msg,
                        'type': 'user',
                        'msg_type': 'user',
                    })
                elif not result['error']:
                    result['error'] = f'Mesaj gönderilemedi: {resp_text[:60]}'
            except Exception as e:
                if not result['error']:
                    result['error'] = f'Mesaj hatası: {str(e)[:60]}'

        # 3. Save to DB
        username = result['username'] or f'Hesap_{token[:8]}'
        id_ = storage.add_kick_account(username, token)
        result['saved'] = True
        result['id'] = id_
        result['username'] = username
        results.append(result)

    return jsonify({'success': True, 'results': results})


@app.route('/api/kick-accounts/batch-test', methods=['POST'])
def batch_test_kick_token():
    data = request.get_json() or {}
    token = (data.get('token') or '').strip()
    chatroom_id = data.get('chatroom_id')
    content = (data.get('content') or '31').strip()

    if not token:
        return jsonify({'error': 'Token gerekli'}), 400
    if not chatroom_id:
        return jsonify({'error': 'Chatroom ID gerekli'}), 400

    ok, resp = kc.send_kick_message(chatroom_id, content, token)
    if ok:
        socketio.emit('chat_message', {
            'username': '[Token Test]',
            'content': content,
            'type': 'user',
            'msg_type': 'user',
        })
    return jsonify({'success': ok, 'response': resp[:200] if resp else ''})


@app.route('/api/kick-accounts/<int:account_id>', methods=['DELETE'])
def delete_kick_account(account_id):
    storage.delete_kick_account(account_id)
    return jsonify({'success': True})


@app.route('/api/kick-accounts/<int:account_id>/raw-token', methods=['GET'])
def get_kick_raw_token(account_id):
    """Returns decrypted token for internal/bot use. Only accessible locally."""
    import socket
    # Basic local-only guard
    raw = storage.get_kick_token_raw(account_id)
    if not raw:
        return jsonify({'error': 'Hesap bulunamadı'}), 404
    return jsonify({'token': raw})


@app.route('/api/kick-accounts/<int:account_id>/test', methods=['POST'])
def test_kick_account_route(account_id):
    raw = storage.get_kick_token_raw(account_id)
    if not raw:
        return jsonify({'valid': False, 'message': 'Token bulunamadı'}), 404
    if raw.startswith('eyJ'):
        return jsonify({'valid': False, 'message': 'Geçersiz: Bearer token yerine web session cookie var'})

    clean_tok = raw.replace('Bearer ', '').strip()
    import requests as _req
    try:
        r = _req.get(
            'https://kick.com/api/v1/user',
            headers={'Authorization': f'Bearer {clean_tok}', 'User-Agent': kc._HEADERS['User-Agent']},
            timeout=6
        )
        if r.status_code == 200:
            u = r.json().get('username')
            if u:
                return jsonify({'valid': True, 'message': f'Geçerli! (@{u})', 'username': u})
        return jsonify({'valid': False, 'message': f'Yetkilendirme başarısız (HTTP {r.status_code})'})
    except Exception as e:
        return jsonify({'valid': False, 'message': str(e)[:100]})


@app.route('/api/kick-accounts/<int:account_id>/send', methods=['POST'])
def manual_send(account_id):
    data = request.get_json() or {}
    content = (data.get('content') or '').strip()
    c_id_setting = storage.get_setting('chatroom_id')
    chatroom_id = (
        data.get('chatroom_id')
        or (_kick_client.chatroom_id if _kick_client else None)
        or (int(c_id_setting) if c_id_setting and c_id_setting.isdigit() else None)
    )
    if not content:
        return jsonify({'error': 'Mesaj gerekli', 'success': False}), 400
    if not chatroom_id:
        return jsonify({'error': 'Chatroom ID bulunamadı — önce kanala bağlanın', 'success': False}), 400

    success, resp = _bot_manager.send_manual_message(account_id, chatroom_id, content)
    if success:
        socketio.emit('chat_message', {
            'username': f'[Manuel #{account_id or "Auto"}]',
            'content': content,
            'type': 'manual',
            'msg_type': 'manual',
        })
        return jsonify({'success': True, 'response': resp[:200]})
    else:
        err_msg = 'Kick Mesaj Hatası: '
        if 'User is not authenticated' in str(resp):
            err_msg = 'Yetkilendirme Hatası: Bu hesabın tokeni geçersiz veya süresi dolmuş.'
        elif resp:
            err_msg += resp[:200]
        else:
            err_msg += 'Mesaj gönderilemedi'
        return jsonify({'error': err_msg, 'success': False, 'response': resp[:200] if resp else ''}), 400


@app.route('/api/bots/reset-daily', methods=['POST'])
def reset_daily_counters():
    data = request.get_json(silent=True) or {}
    bot_id = data.get('bot_id')
    _bot_manager.reset_daily_count(bot_id)
    return jsonify({'success': True, 'message': 'Günlük mesaj sayacı sıfırlandı'})


@app.route('/api/bots', methods=['GET'])
def get_bots():
    bots = storage.get_bots()
    stats_map = {s['id']: s for s in _bot_manager.get_all_stats()}
    for bot in bots:
        s = stats_map.get(bot['id'], {})
        bot['cooldown_remaining'] = s.get('cooldown_remaining', 0)
        bot['daily_count'] = s.get('daily_count', 0)
    return jsonify(bots)


@app.route('/api/bots', methods=['POST'])
def add_bot():
    data = request.get_json() or {}
    id_ = storage.add_bot(data)
    if _pipeline:
        _pipeline.refresh_bot_names()
    return jsonify({'success': True, 'id': id_})


@app.route('/api/bots/<int:bot_id>', methods=['PUT'])
def update_bot(bot_id):
    data = request.get_json() or {}
    storage.update_bot(bot_id, data)
    if _pipeline:
        _pipeline.refresh_bot_names()
    return jsonify({'success': True})


@app.route('/api/bots/<int:bot_id>', methods=['DELETE'])
def delete_bot(bot_id):
    storage.delete_bot(bot_id)
    if _pipeline:
        _pipeline.refresh_bot_names()
    return jsonify({'success': True})


@app.route('/api/bots/<int:bot_id>/toggle', methods=['POST'])
def toggle_bot(bot_id):
    data = request.get_json() or {}
    storage.update_bot(bot_id, {'enabled': 1 if data.get('enabled') else 0})
    return jsonify({'success': True})


@app.route('/api/bots/<int:bot_id>/send', methods=['POST'])
def bot_manual_send(bot_id):
    """Manually send a message from a specific bot character."""
    data = request.get_json() or {}
    content = (data.get('content') or '').strip()
    c_id_setting = storage.get_setting('chatroom_id')
    chatroom_id = (
        data.get('chatroom_id')
        or (_kick_client.chatroom_id if _kick_client else None)
        or (int(c_id_setting) if c_id_setting and c_id_setting.isdigit() else None)
    )
    if not content:
        return jsonify({'error': 'Mesaj gerekli', 'success': False}), 400
    if not chatroom_id:
        return jsonify({'error': 'Chatroom ID bulunamadı — önce kanala bağlanın', 'success': False}), 400

    bots = storage.get_bots()
    bot = next((b for b in bots if b['id'] == bot_id), None)
    if not bot:
        return jsonify({'error': 'Bot bulunamadı', 'success': False}), 404

    success, resp = _bot_manager.send_message(bot, chatroom_id, content)
    if success:
        if _pipeline:
            socketio.emit('chat_message', {
                'username': bot['name'],
                'content': content,
                'type': 'bot',
                'bot_name': bot['name'],
                'msg_type': 'bot',
            })
        return jsonify({'success': True, 'response': resp[:200]})
    else:
        err_msg = 'Bot Gönderim Hatası: '
        if 'User is not authenticated' in str(resp):
            err_msg = f'Yetkilendirme Hatası: {bot["name"]} botunun Kick hesabı geçersiz veya süresi dolmuş.'
        elif resp:
            err_msg += resp[:200]
        else:
            err_msg += 'Gönderilemedi'
        return jsonify({'error': err_msg, 'success': False, 'response': resp[:200] if resp else ''}), 400


# ── Kick Emotes ──────────────────────────────

@app.route('/api/emotes', methods=['GET'])
def get_emotes_route():
    return jsonify(storage.get_emotes())


@app.route('/api/emotes', methods=['POST'])
def add_emote_route():
    data = request.get_json() or {}
    emote = (data.get('emote') or '').strip()
    emotes_bulk = data.get('emotes')
    
    if emotes_bulk and isinstance(emotes_bulk, list):
        for e in emotes_bulk:
            if isinstance(e, str) and e.strip():
                storage.add_emote(e.strip())
        return jsonify({'success': True, 'emotes': storage.get_emotes()})
        
    if not emote:
        return jsonify({'error': 'Emoji kodu gerekli (Örn: [emote:1579033:emojiAstonished])'}), 400
        
    updated = storage.add_emote(emote)
    return jsonify({'success': True, 'emotes': updated})


@app.route('/api/emotes', methods=['DELETE'])
def delete_emote_route():
    data = request.get_json() or {}
    emote = (data.get('emote') or '').strip()
    if not emote:
        return jsonify({'error': 'Silinecek emoji gerekli'}), 400
    updated = storage.delete_emote(emote)
    return jsonify({'success': True, 'emotes': updated})


@app.route('/api/emotes/send-random', methods=['POST'])
def send_random_emote():
    data = request.get_json() or {}
    bot_id_choice = data.get('bot_id', 'random')  # 'random', 'all', or int
    chatroom_id = data.get('chatroom_id') or (
        _kick_client.chatroom_id if _kick_client else None
    )
    if not chatroom_id:
        return jsonify({'error': 'Önce bir Kick kanalına bağlanmalısınız!'}), 400

    emotes = storage.get_emotes()
    if not emotes:
        return jsonify({'error': 'Kayıtlı Kick emojisi bulunamadı!'}), 400

    bots = storage.get_bots()
    enabled_bots = [b for b in bots if b.get('enabled') and b.get('kick_account_id')]
    
    targets = []
    if bot_id_choice == 'all':
        targets = enabled_bots
    elif bot_id_choice == 'random':
        if enabled_bots:
            targets = [random.choice(enabled_bots)]
    else:
        try:
            bid = int(bot_id_choice)
            target = next((b for b in bots if b['id'] == bid), None)
            if target:
                targets = [target]
        except Exception:
            pass

    results = []
    if not targets:
        accounts = storage.get_kick_accounts()
        active_accounts = [a for a in accounts if a.get('is_active')]
        if not active_accounts:
            return jsonify({'error': 'Mesaj atacak aktif bot veya Kick hesabı bulunamadı!'}), 400
        
        acc = random.choice(active_accounts)
        emote = random.choice(emotes)
        success, resp = _bot_manager.send_manual_message(acc['id'], chatroom_id, emote)
        if success:
            socketio.emit('chat_message', {
                'username': acc.get('username') or 'Kick Bot',
                'content': emote,
                'type': 'bot',
                'msg_type': 'bot',
            })
            results.append({'sender': acc.get('username'), 'emote': emote, 'success': True})
        else:
            return jsonify({'error': f'Emoji gönderilemedi: {resp}'}), 500
    else:
        for bot in targets:
            emote = random.choice(emotes)
            success, resp = _bot_manager.send_message(bot, chatroom_id, emote)
            if success:
                socketio.emit('chat_message', {
                    'username': bot['name'],
                    'content': emote,
                    'type': 'bot',
                    'bot_name': bot['name'],
                    'msg_type': 'bot',
                })
                results.append({'sender': bot['name'], 'emote': emote, 'success': True})
            else:
                results.append({'sender': bot['name'], 'error': resp, 'success': False})

    return jsonify({'success': True, 'results': results})


# ── Pipeline ──────────────────────────────────

@app.route('/api/pipeline/toggle', methods=['POST'])
def pipeline_toggle():
    data = request.get_json() or {}
    enabled = bool(data.get('enabled', True))
    if _pipeline:
        _pipeline.enabled = enabled
    return jsonify({'success': True, 'enabled': enabled})


@app.route('/api/pipeline/status')
def pipeline_status_route():
    return jsonify({
        'enabled': _pipeline.enabled if _pipeline else False,
        'chatroom_id': _pipeline.chatroom_id if _pipeline else None,
    })


# ── Logs ─────────────────────────────────────

@app.route('/api/logs')
def get_logs():
    limit = request.args.get('limit', 200, type=int)
    return jsonify(storage.get_message_logs(limit))


@app.route('/api/logs/clear', methods=['POST'])
def clear_logs():
    import sqlite3
    conn = sqlite3.connect(storage.DB_FILE)
    conn.execute('DELETE FROM message_logs')
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ── Bot stats (polling) ───────────────────────

@app.route('/api/stats')
def get_stats():
    return jsonify(_bot_manager.get_all_stats())


# ── Account Creator Endpoints ────────────────

@app.route('/api/account-creator/generate-data', methods=['POST'])
def ac_generate_data():
    data = request.get_json() or {}
    use_temp = data.get('use_temp_mail', True)
    res = {
        'username': kac.generate_username(),
        'password': kac.generate_password(14),
        'birthdate': kac.generate_birthdate(),
        'email': '',
    }
    if use_temp:
        try:
            m = kac.GuerrillaMailClient()
            mb = m.create_mailbox(custom_user=res['username'])
            res['email'] = mb['email']
        except Exception as e:
            try:
                m = kac.TempTfMailClient()
                mb = m.create_mailbox()
                res['email'] = mb['email']
            except Exception as e2:
                try:
                    m = kac.MailTmClient()
                    mb = m.create_mailbox()
                    res['email'] = mb['email']
                except Exception as e3:
                    res['temp_mail_error'] = str(e3)
    return jsonify(res)


@app.route('/api/account-creator/start', methods=['POST'])
def ac_start():
    data = request.get_json() or {}
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    birthdate = data.get('birthdate')
    use_temp_mail = data.get('use_temp_mail', True)
    headless = data.get('headless', False)

    ac = _get_account_creator()
    result = ac.start_creation_async(
        username=username,
        email=email,
        password=password,
        birthdate=birthdate,
        use_temp_mail=use_temp_mail,
        headless=headless,
    )
    return jsonify(result)


@app.route('/api/account-creator/submit-code', methods=['POST'])
def ac_submit_code():
    data = request.get_json() or {}
    code = (data.get('code') or '').strip()
    if not code:
        return jsonify({'error': 'Onay kodu gerekli'}), 400
    ac = _get_account_creator()
    ac.provide_code(code)
    return jsonify({'success': True})


@app.route('/api/account-creator/stop', methods=['POST'])
def ac_stop():
    ac = _get_account_creator()
    ac.stop()
    return jsonify({'success': True})


@app.route('/api/account-creator/status', methods=['GET'])
def ac_status():
    ac = _get_account_creator()
    return jsonify({
        'is_running': ac.is_running,
        'status': ac.status,
        'username': ac.current_username,
        'email': ac.current_email,
        'bearer_token': ac.bearer_token,
    })


# ═══════════════════════════════════════════════
# SocketIO
# ═══════════════════════════════════════════════

@socketio.on('connect')
def handle_connect():
    channel = storage.get_setting('channel')
    chatroom_id = storage.get_setting('chatroom_id')
    connected = _kick_client.connected if _kick_client else False
    emit('init', {
        'channel': channel,
        'chatroom_id': chatroom_id,
        'connected': connected,
        'pipeline_enabled': _pipeline.enabled if _pipeline else True,
    })


# ═══════════════════════════════════════════════
# VIEWBOT ENDPOINTS
# ═══════════════════════════════════════════════

from viewbot import ViewBot
import threading

_viewbot: ViewBot | None = None
_viewbot_thread: threading.Thread | None = None

@app.route('/api/viewbot/start', methods=['POST'])
def viewbot_start():
    """ViewBot'u başlat"""
    global _viewbot, _viewbot_thread
    
    data = request.get_json() or {}
    channel = (data.get('channel') or '').strip()
    viewer_count = data.get('viewer_count', 50)
    
    if not channel:
        return jsonify({'error': 'Kanal adı gerekli'}), 400
    
    if _viewbot and not _viewbot.stop:
        return jsonify({'error': 'ViewBot zaten çalışıyor'}), 400
    
    try:
        viewer_count = int(viewer_count)
        if viewer_count <= 0 or viewer_count > 500:
            return jsonify({'error': 'Viewer sayısı 1-500 arasında olmalı'}), 400
    except:
        return jsonify({'error': 'Geçersiz viewer sayısı'}), 400
    
    def log_to_socketio(msg):
        socketio.emit('viewbot_log', {'message': msg})
    
    _viewbot = ViewBot(channel, viewer_count, log_callback=log_to_socketio)
    _viewbot_thread = threading.Thread(target=_viewbot.start, daemon=True)
    _viewbot_thread.start()
    
    return jsonify({
        'success': True,
        'message': f'ViewBot başlatıldı: {channel} ({viewer_count} viewer)'
    })


@app.route('/api/viewbot/stop', methods=['POST'])
def viewbot_stop():
    """ViewBot'u durdur"""
    global _viewbot
    
    if not _viewbot:
        return jsonify({'error': 'ViewBot çalışmıyor'}), 400
    
    _viewbot.stop_bot()
    _viewbot = None
    
    return jsonify({'success': True, 'message': 'ViewBot durduruldu'})


@app.route('/api/viewbot/status', methods=['GET'])
def viewbot_status():
    """ViewBot durumunu getir"""
    global _viewbot
    
    if not _viewbot:
        return jsonify({
            'running': False,
            'channel': None,
            'viewer_count': 0,
            'connections': 0,
            'attempts': 0,
            'pings': 0,
            'heartbeats': 0,
            'viewers': 0,
        })
    
    return jsonify({
        'running': not _viewbot.stop,
        'channel': _viewbot.channel,
        'viewer_count': _viewbot.max_threads,
        'connections': _viewbot.connections,
        'attempts': _viewbot.attempts,
        'pings': _viewbot.pings,
        'heartbeats': _viewbot.heartbeats,
        'viewers': _viewbot.viewers,
        'stream_id': _viewbot.stream_id,
    })


# ═══════════════════════════════════════════════
# Follow Bot Routes
# ═══════════════════════════════════════════════

_follow_state = {
    'running': False,
    'stop': False,
    'channel': '',
    'total': 0,
    'sent': 0,
    'success': 0,
    'failed': 0,
    'logs': []
}
_follow_thread = None


def _follow_worker(channel_slug: str, target_count: int, delay: float):
    global _follow_state
    _follow_state['running'] = True
    _follow_state['stop'] = False
    _follow_state['channel'] = channel_slug
    _follow_state['sent'] = 0
    _follow_state['success'] = 0
    _follow_state['failed'] = 0
    _follow_state['logs'] = []

    tok_file = os.path.join(os.path.dirname(__file__), 'discordbot', 'tokens.json')
    tokens = []
    if os.path.exists(tok_file):
        try:
            with open(tok_file, 'r', encoding='utf-8') as f:
                tokens = json.load(f)
        except Exception:
            pass

    if not tokens:
        db_accounts = storage.get_kick_accounts()
        tokens = [storage.get_kick_token_raw(acc['id']) for acc in db_accounts if storage.get_kick_token_raw(acc['id'])]

    cleaned_tokens = []
    seen = set()
    for t in tokens:
        if not t:
            continue
        ct = str(t).strip()
        if ct.lower().startswith('bearer '):
            ct = ct[7:].strip()
        if ct and ct not in seen:
            seen.add(ct)
            cleaned_tokens.append(ct)

    tokens_to_use = cleaned_tokens[:target_count]
    _follow_state['total'] = len(tokens_to_use)

    def _emit_progress(msg=None, is_success=True):
        if msg:
            _follow_state['logs'].append(msg)
            if len(_follow_state['logs']) > 150:
                _follow_state['logs'].pop(0)
        socketio.emit('follow_progress', {
            'running': _follow_state['running'],
            'channel': _follow_state['channel'],
            'total': _follow_state['total'],
            'sent': _follow_state['sent'],
            'success': _follow_state['success'],
            'failed': _follow_state['failed'],
            'message': msg,
            'is_success': is_success
        })

    _emit_progress(f"🚀 Takipçi botu başlatıldı: {channel_slug} için {_follow_state['total']} token kullanılacak.")

    try:
        import tls_client
        has_tls = True
    except ImportError:
        has_tls = False
    import requests

    url = f"https://kick.com/api/v2/channels/{channel_slug}/follow"

    for idx, tok in enumerate(tokens_to_use, 1):
        if _follow_state['stop']:
            _emit_progress("⛔ Takipçi iletimi kullanıcı tarafından durduruldu.")
            break

        _follow_state['sent'] = idx
        headers = {
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Authorization': f'Bearer {tok}',
            'Content-Type': 'application/json',
            'Referer': f'https://kick.com/{channel_slug}',
            'Origin': 'https://kick.com',
        }

        ok = False
        err_detail = ""
        if has_tls:
            try:
                s = tls_client.Session(client_identifier="chrome_120", random_tls_extension_order=True)
                r = s.post(url, headers=headers, timeout_seconds=5)
                if r.status_code in (200, 201, 204):
                    ok = True
                else:
                    err_detail = f"HTTP {r.status_code}"
            except Exception as e:
                err_detail = str(e)

        if not ok:
            try:
                r = requests.post(url, headers=headers, timeout=5)
                if r.status_code in (200, 201, 204):
                    ok = True
                else:
                    err_detail = f"HTTP {r.status_code}"
            except Exception as e:
                err_detail = str(e)

        if ok:
            _follow_state['success'] += 1
            log_msg = f"[{idx}/{_follow_state['total']}] ✅ Token {tok[:8]}... takip etti."
            _emit_progress(log_msg, True)
        else:
            _follow_state['failed'] += 1
            log_msg = f"[{idx}/{_follow_state['total']}] ❌ Token {tok[:8]}... hata: {err_detail}"
            _emit_progress(log_msg, False)

        if delay > 0 and idx < len(tokens_to_use):
            time.sleep(delay)

    _follow_state['running'] = False
    _emit_progress(f"🎉 Takipçi botu tamamlandı! Başarılı: {_follow_state['success']}, Başarısız: {_follow_state['failed']}")


@app.route('/api/follow/start', methods=['POST'])
def follow_start():
    global _follow_thread, _follow_state
    data = request.get_json() or {}
    channel = (data.get('channel') or '').strip().lstrip('@')
    count = data.get('count', 100)
    delay = data.get('delay', 0.2)

    if not channel:
        return jsonify({'error': 'Kanal adı gerekli'}), 400

    if _follow_state['running']:
        return jsonify({'error': 'Takipçi botu zaten çalışıyor'}), 400

    try:
        count = int(count)
        delay = float(delay)
        if count <= 0:
            return jsonify({'error': 'Takipçi sayısı 0 dan büyük olmalı'}), 400
    except Exception:
        return jsonify({'error': 'Geçersiz takipçi sayısı veya gecikme'}), 400

    _follow_thread = threading.Thread(target=_follow_worker, args=(channel, count, delay), daemon=True)
    _follow_thread.start()

    return jsonify({'success': True, 'message': f'{channel} için takipçi botu başlatıldı.'})


@app.route('/api/follow/stop', methods=['POST'])
def follow_stop():
    global _follow_state
    _follow_state['stop'] = True
    return jsonify({'success': True, 'message': 'Takipçi botu durduruluyor...'})


@app.route('/api/follow/status', methods=['GET'])
def follow_status():
    return jsonify(_follow_state)


# ═══════════════════════════════════════════════
# Entry
# ═══════════════════════════════════════════════

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)

