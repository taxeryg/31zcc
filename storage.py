"""
storage.py — SQLite + Fernet şifreli token yönetimi
"""
import json
import sqlite3
import os
import logging
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.environ.get('DB_FILE', os.path.join(_ROOT_DIR, 'botdash.db'))
BACKUP_FILE = os.environ.get('BACKUP_FILE', os.path.join(_ROOT_DIR, 'persistent_storage.json'))
_KEY_FILE = os.path.join(_ROOT_DIR, '.secret_key')

DEFAULT_FERNET_KEY = b'pO8o1qW7CmLzWfbh-NZ1ZP-QJBXanmRWMl4MpWNcQvU='


def _get_or_create_fernet():
    env_key = os.environ.get('FERNET_KEY')
    if env_key:
        try:
            return Fernet(env_key.encode() if isinstance(env_key, str) else env_key)
        except Exception:
            pass
    if os.path.exists(_KEY_FILE):
        try:
            with open(_KEY_FILE, 'rb') as f:
                key = f.read().strip()
                if key:
                    return Fernet(key)
        except Exception:
            pass
    # Sabit anahtar: sunucu yeniden başlasa bile şifre çözümü asla bozulmaz
    return Fernet(DEFAULT_FERNET_KEY)


_cipher = _get_or_create_fernet()


def encrypt(text: str) -> str:
    if not text:
        return ''
    return _cipher.encrypt(text.encode()).decode()


def decrypt(enc: str) -> str:
    if not enc:
        return ''
    try:
        return _cipher.decrypt(enc.encode()).decode()
    except Exception:
        return ''


def mask_token(token: str) -> str:
    if not token or len(token) < 8:
        return '****'
    return '****...' + token[-6:]


# ──────────────────────────────────────────────
# DB Init
# ──────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS key_settings (
        owner_key TEXT NOT NULL,
        key TEXT NOT NULL,
        value TEXT,
        PRIMARY KEY (owner_key, key)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS ai_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        token_enc TEXT NOT NULL,
        base_url TEXT DEFAULT 'https://api.openai.com/v1',
        model TEXT DEFAULT 'gpt-4o-mini',
        owner_key TEXT DEFAULT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS kick_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        token_enc TEXT NOT NULL,
        owner_key TEXT DEFAULT NULL,
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS bots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        personality TEXT DEFAULT '',
        style TEXT DEFAULT '',
        interests TEXT DEFAULT '',
        enabled INTEGER DEFAULT 1,
        response_chance REAL DEFAULT 0.35,
        min_delay INTEGER DEFAULT 8,
        max_delay INTEGER DEFAULT 45,
        daily_limit INTEGER DEFAULT 50,
        ai_token_id INTEGER,
        kick_account_id INTEGER,
        system_prompt TEXT DEFAULT '',
        owner_key TEXT DEFAULT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS message_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        msg_type TEXT,
        username TEXT,
        content TEXT,
        bot_name TEXT,
        analysis TEXT,
        status TEXT,
        error_msg TEXT,
        owner_key TEXT DEFAULT NULL,
        timestamp TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS license_keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key_code TEXT UNIQUE NOT NULL,
        duration_hours INTEGER NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        activated_at TEXT,
        expires_at TEXT,
        bound_ip TEXT,
        bound_hwid TEXT,
        is_active INTEGER DEFAULT 1,
        created_by TEXT DEFAULT 'discord'
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS user_memory (
        username TEXT PRIMARY KEY,
        first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
        last_seen TEXT DEFAULT CURRENT_TIMESTAMP,
        message_count INTEGER DEFAULT 1,
        last_topic TEXT,
        sentiment TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS banned_words (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        word TEXT UNIQUE NOT NULL,
        reason TEXT DEFAULT 'kick_automod',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS proxy_stats (
        proxy TEXT PRIMARY KEY,
        success_count INTEGER DEFAULT 0,
        fail_count INTEGER DEFAULT 0,
        latency_ms REAL DEFAULT 0,
        last_tested TEXT,
        is_alive INTEGER DEFAULT 1
    )''')

    conn.commit()

    # Otomatik geri yükleme: Eğer DB yeni oluşmuşsa ve persistent_storage.json varsa geri yükle
    if os.path.exists(BACKUP_FILE):
        try:
            c.execute('SELECT COUNT(*) FROM ai_tokens')
            token_count = c.fetchone()[0]
            c.execute('SELECT COUNT(*) FROM kick_accounts')
            account_count = c.fetchone()[0]
            if token_count == 0 and account_count == 0:
                with open(BACKUP_FILE, 'r', encoding='utf-8') as f:
                    saved_data = json.load(f)
                conn.close()
                restore_all_data(saved_data)
                return
        except Exception as e:
            logger.error(f'Auto-restore error: {e}')

    conn.close()


# ──────────────────────────────────────────────
# Settings (Multi-Tenant with Key-Scope)
# ──────────────────────────────────────────────

def get_setting(key, default=None, owner_key=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if owner_key:
        c.execute('SELECT value FROM key_settings WHERE owner_key=? AND key=?', (owner_key, key))
        row = c.fetchone()
        if row:
            conn.close()
            return row[0]
    c.execute('SELECT value FROM settings WHERE key=?', (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default


def set_setting(key, value, owner_key=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if owner_key:
        c.execute('INSERT OR REPLACE INTO key_settings (owner_key, key, value) VALUES (?,?,?)', (owner_key, key, value))
    else:
        c.execute('INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)', (key, value))
    conn.commit()
    conn.close()
    save_backup_file()


# ──────────────────────────────────────────────
# AI Tokens (Multi-Tenant with Key-Scope)
# ──────────────────────────────────────────────

def add_ai_token(name, token, base_url, model, owner_key=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO ai_tokens (name,token_enc,base_url,model,owner_key) VALUES (?,?,?,?,?)',
              (name, encrypt(token), base_url, model, owner_key))
    id_ = c.lastrowid
    conn.commit()
    conn.close()
    save_backup_file()
    return id_


def get_ai_tokens(owner_key=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if owner_key:
        c.execute('SELECT id,name,token_enc,base_url,model,created_at,owner_key FROM ai_tokens WHERE owner_key=? OR owner_key IS NULL ORDER BY id', (owner_key,))
    else:
        c.execute('SELECT id,name,token_enc,base_url,model,created_at,owner_key FROM ai_tokens ORDER BY id')
    rows = c.fetchall()
    conn.close()
    result = []
    for r in rows:
        result.append({
            'id': r[0], 'name': r[1],
            'token_masked': mask_token(decrypt(r[2])),
            'base_url': r[3], 'model': r[4], 'created_at': r[5],
            'owner_key': r[6]
        })
    return result


def get_ai_token_raw(token_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT token_enc,base_url,model FROM ai_tokens WHERE id=?', (token_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return decrypt(row[0]), row[1], row[2]
    return None, None, None


def get_first_ai_token_id(owner_key=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if owner_key:
        c.execute('SELECT id FROM ai_tokens WHERE owner_key=? LIMIT 1', (owner_key,))
        row = c.fetchone()
        if row:
            conn.close()
            return row[0]
    c.execute('SELECT id FROM ai_tokens LIMIT 1')
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


def delete_ai_token(token_id, owner_key=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if owner_key:
        c.execute('DELETE FROM ai_tokens WHERE id=? AND owner_key=?', (token_id, owner_key))
    else:
        c.execute('DELETE FROM ai_tokens WHERE id=?', (token_id,))
    conn.commit()
    conn.close()
    save_backup_file()


# ──────────────────────────────────────────────
# Kick Accounts (Multi-Tenant with Key-Scope)
# ──────────────────────────────────────────────

def add_kick_account(username, token, owner_key=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO kick_accounts (username,token_enc,owner_key) VALUES (?,?,?)',
              (username, encrypt(token), owner_key))
    id_ = c.lastrowid
    conn.commit()
    conn.close()
    save_backup_file()
    return id_


def get_kick_accounts(owner_key=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if owner_key:
        c.execute('SELECT id,username,token_enc,is_active,created_at,owner_key FROM kick_accounts WHERE owner_key=? ORDER BY id', (owner_key,))
        rows = c.fetchall()
        # Eğer bu key'e özel hesap henüz eklenmemişse varsayılan admin havuzunu görebilsin/kullanabilsin
        if not rows:
            c.execute('SELECT id,username,token_enc,is_active,created_at,owner_key FROM kick_accounts WHERE owner_key IS NULL ORDER BY id')
            rows = c.fetchall()
    else:
        c.execute('SELECT id,username,token_enc,is_active,created_at,owner_key FROM kick_accounts ORDER BY id')
        rows = c.fetchall()
    conn.close()
    return [{
        'id': r[0], 'username': r[1],
        'token_masked': mask_token(decrypt(r[2])),
        'is_active': bool(r[3]), 'created_at': r[4],
        'owner_key': r[5]
    } for r in rows]


def get_kick_token_raw(account_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT token_enc FROM kick_accounts WHERE id=?', (account_id,))
    row = c.fetchone()
    conn.close()
    return decrypt(row[0]) if row else None


def delete_kick_account(account_id, owner_key=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if owner_key:
        c.execute('DELETE FROM kick_accounts WHERE id=? AND owner_key=?', (account_id, owner_key))
    else:
        c.execute('DELETE FROM kick_accounts WHERE id=?', (account_id,))
    conn.commit()
    conn.close()
    save_backup_file()


# ──────────────────────────────────────────────
# Bots (Multi-Tenant with Key-Scope)
# ──────────────────────────────────────────────

def add_bot(data, owner_key=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''INSERT INTO bots
        (name,personality,style,interests,enabled,response_chance,
         min_delay,max_delay,daily_limit,ai_token_id,kick_account_id,system_prompt,owner_key)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (data.get('name', ''), data.get('personality', ''), data.get('style', ''),
         data.get('interests', ''), int(data.get('enabled', 1)),
         float(data.get('response_chance', 0.35)),
         int(data.get('min_delay', 8)), int(data.get('max_delay', 45)),
         int(data.get('daily_limit', 50)),
         data.get('ai_token_id'), data.get('kick_account_id'),
         data.get('system_prompt', ''),
         owner_key or data.get('owner_key')))
    id_ = c.lastrowid
    conn.commit()
    conn.close()
    save_backup_file()
    return id_


def get_bots(owner_key=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if owner_key:
        c.execute('SELECT * FROM bots WHERE owner_key=? ORDER BY id', (owner_key,))
        rows = c.fetchall()
        if not rows:
            c.execute('SELECT * FROM bots WHERE owner_key IS NULL ORDER BY id')
            rows = c.fetchall()
    else:
        c.execute('SELECT * FROM bots ORDER BY id')
        rows = c.fetchall()
    conn.close()
    cols = ['id', 'name', 'personality', 'style', 'interests', 'enabled',
            'response_chance', 'min_delay', 'max_delay', 'daily_limit',
            'ai_token_id', 'kick_account_id', 'system_prompt', 'created_at', 'owner_key']
    return [dict(zip(cols, r)) for r in rows]


def update_bot(bot_id, data, owner_key=None):
    allowed = ['name', 'personality', 'style', 'interests', 'enabled', 'response_chance',
               'min_delay', 'max_delay', 'daily_limit', 'ai_token_id', 'kick_account_id', 'system_prompt']
    fields = [f for f in allowed if f in data]
    if not fields:
        return
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    set_clause = ', '.join(f'{f}=?' for f in fields)
    values = [data[f] for f in fields]
    if owner_key:
        values += [bot_id, owner_key]
        c.execute(f'UPDATE bots SET {set_clause} WHERE id=? AND (owner_key=? OR owner_key IS NULL)', values)
    else:
        values += [bot_id]
        c.execute(f'UPDATE bots SET {set_clause} WHERE id=?', values)
    conn.commit()
    conn.close()
    save_backup_file()


def delete_bot(bot_id, owner_key=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if owner_key:
        c.execute('DELETE FROM bots WHERE id=? AND owner_key=?', (bot_id, owner_key))
    else:
        c.execute('DELETE FROM bots WHERE id=?', (bot_id,))
    conn.commit()
    conn.close()
    save_backup_file()


def insert_default_bots():
    if get_bots():
        return
    defaults = [
        {
            'name': 'MertBot', 'personality': 'Samimi kafa dengi izleyici',
            'style': 'Noktalamasız, çok kısa samimi küçükyazı, sokak ağzı',
            'interests': 'Oyun, yayın, muhabbet',
            'response_chance': 0.40, 'min_delay': 6, 'max_delay': 40, 'daily_limit': 60,
        },
        {
            'name': 'EceBot', 'personality': 'Makara komik chatci',
            'style': 'Noktalamasız kısa samimi chat dili',
            'interests': 'Müzik, sohbet',
            'response_chance': 0.35, 'min_delay': 8, 'max_delay': 50, 'daily_limit': 50,
        },
        {
            'name': 'TrolBot', 'personality': 'Muzip şakacı chatci',
            'style': 'Kısa noktalamasız makara',
            'interests': 'Makara, geyik',
            'response_chance': 0.25, 'min_delay': 15, 'max_delay': 90, 'daily_limit': 30,
        },
    ]
    for d in defaults:
        add_bot(d)


# ──────────────────────────────────────────────
# Message Logs (Multi-Tenant with Key-Scope)
# ──────────────────────────────────────────────

def log_message(msg_type, username, content, bot_name=None,
                analysis=None, status=None, error_msg=None, owner_key=None):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''INSERT INTO message_logs
            (msg_type,username,content,bot_name,analysis,status,error_msg,owner_key)
            VALUES (?,?,?,?,?,?,?,?)''',
            (msg_type, username, content[:500] if content else '',
             bot_name, analysis, status, error_msg, owner_key))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f'log_message error: {e}')


def get_message_logs(limit=200, owner_key=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if owner_key:
        c.execute('SELECT * FROM message_logs WHERE owner_key=? OR owner_key IS NULL ORDER BY id DESC LIMIT ?', (owner_key, limit))
    else:
        c.execute('SELECT * FROM message_logs ORDER BY id DESC LIMIT ?', (limit,))
    rows = c.fetchall()
    conn.close()
    cols = ['id', 'msg_type', 'username', 'content', 'bot_name',
            'analysis', 'status', 'error_msg', 'owner_key', 'timestamp']
    return list(reversed([dict(zip(cols, r)) for r in rows]))


# ──────────────────────────────────────────────
# Persistent Storage & Auto-Backup
# ──────────────────────────────────────────────

def export_all_data() -> dict:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. AI Tokens
    c.execute('SELECT id, name, token_enc, base_url, model, created_at FROM ai_tokens')
    ai_tokens = []
    for r in c.fetchall():
        raw_tok = decrypt(r[2])
        if raw_tok:
            ai_tokens.append({
                'name': r[1],
                'token': raw_tok,
                'base_url': r[3],
                'model': r[4]
            })
            
    # 2. Kick Accounts
    c.execute('SELECT id, username, token_enc, is_active, created_at FROM kick_accounts')
    kick_accounts = []
    for r in c.fetchall():
        raw_tok = decrypt(r[2])
        if raw_tok:
            kick_accounts.append({
                'username': r[1],
                'token': raw_tok,
                'is_active': r[3]
            })
            
    # 3. Bots
    c.execute('''SELECT id, name, personality, style, interests, enabled, response_chance,
                        min_delay, max_delay, daily_limit, ai_token_id, kick_account_id, system_prompt
                 FROM bots''')
    bots = []
    for r in c.fetchall():
        bots.append({
            'name': r[1], 'personality': r[2], 'style': r[3], 'interests': r[4],
            'enabled': r[5], 'response_chance': r[6], 'min_delay': r[7], 'max_delay': r[8],
            'daily_limit': r[9], 'ai_token_id': r[10], 'kick_account_id': r[11],
            'system_prompt': r[12]
        })
        
    # 4. Settings
    c.execute('SELECT key, value FROM settings')
    settings = {r[0]: r[1] for r in c.fetchall()}

    # 5. License Keys
    c.execute('SELECT id, key_code, duration_hours, created_at, activated_at, expires_at, bound_ip, bound_hwid, is_active, created_by FROM license_keys')
    license_keys = []
    for r in c.fetchall():
        license_keys.append({
            'key_code': r[1],
            'duration_hours': r[2],
            'created_at': r[3],
            'activated_at': r[4],
            'expires_at': r[5],
            'bound_ip': r[6],
            'bound_hwid': r[7],
            'is_active': r[8],
            'created_by': r[9]
        })
    
    conn.close()
    return {
        'ai_tokens': ai_tokens,
        'kick_accounts': kick_accounts,
        'bots': bots,
        'settings': settings,
        'license_keys': license_keys
    }


def save_backup_file():
    try:
        data = export_all_data()
        with open(BACKUP_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f'save_backup_file error: {e}')


def restore_all_data(data: dict) -> bool:
    if not isinstance(data, dict):
        return False
        
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. AI Tokens restore
    for t in data.get('ai_tokens', []):
        name = t.get('name')
        token = t.get('token')
        base_url = t.get('base_url', 'https://api.openai.com/v1')
        model = t.get('model', 'gpt-4o-mini')
        if name and token:
            c.execute('SELECT id FROM ai_tokens WHERE name=?', (name,))
            if not c.fetchone():
                c.execute('INSERT INTO ai_tokens (name,token_enc,base_url,model) VALUES (?,?,?,?)',
                          (name, encrypt(token), base_url, model))
                          
    # 2. Kick Accounts restore
    for a in data.get('kick_accounts', []):
        username = a.get('username')
        token = a.get('token')
        is_active = a.get('is_active', 1)
        if username and token:
            c.execute('SELECT id FROM kick_accounts WHERE username=?', (username,))
            if not c.fetchone():
                c.execute('INSERT INTO kick_accounts (username,token_enc,is_active) VALUES (?,?,?)',
                          (username, encrypt(token), is_active))
                          
    # 3. Bots restore
    for b in data.get('bots', []):
        name = b.get('name')
        if name:
            c.execute('SELECT id FROM bots WHERE name=?', (name,))
            if not c.fetchone():
                c.execute('''INSERT INTO bots
                    (name,personality,style,interests,enabled,response_chance,
                     min_delay,max_delay,daily_limit,ai_token_id,kick_account_id,system_prompt)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (name, b.get('personality',''), b.get('style',''), b.get('interests',''),
                     b.get('enabled', 1), b.get('response_chance', 0.35),
                     b.get('min_delay', 8), b.get('max_delay', 45),
                     b.get('daily_limit', 50), b.get('ai_token_id'),
                     b.get('kick_account_id'), b.get('system_prompt','')))
                     
    # 4. Settings restore
    for k, v in data.get('settings', {}).items():
        c.execute('INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)', (k, v))

    # 5. License Keys restore
    for lk in data.get('license_keys', []):
        code = lk.get('key_code')
        dur = lk.get('duration_hours', 24)
        active = lk.get('is_active', 1)
        creator = lk.get('created_by', 'system')
        created_at = lk.get('created_at')
        activated_at = lk.get('activated_at')
        expires_at = lk.get('expires_at')
        bound_ip = lk.get('bound_ip')
        bound_hwid = lk.get('bound_hwid')
        if code:
            c.execute('SELECT id FROM license_keys WHERE UPPER(TRIM(key_code))=UPPER(?)', (code,))
            existing = c.fetchone()
            if not existing:
                c.execute('''INSERT INTO license_keys (key_code, duration_hours, created_at, activated_at, expires_at, bound_ip, bound_hwid, is_active, created_by)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                          (code, dur, created_at, activated_at, expires_at, bound_ip, bound_hwid, active, creator))
            else:
                c.execute('''UPDATE license_keys SET duration_hours=?, activated_at=?, expires_at=?, bound_ip=?, bound_hwid=?, is_active=?, created_by=?
                             WHERE UPPER(TRIM(key_code))=UPPER(?)''',
                          (dur, activated_at, expires_at, bound_ip, bound_hwid, active, creator, code))
        
    conn.commit()
    conn.close()
    
    save_backup_file()
    return True


# ──────────────────────────────────────────────
# Kick Emotes Management
# ──────────────────────────────────────────────

DEFAULT_KICK_EMOTES = [
    "[emote:1579033:emojiAstonished]",
    "[emote:1579028:emojiLaughing]",
    "[emote:1579030:emojiFire]",
    "[emote:1579029:emojiCool]",
    "[emote:1579031:emojiHeart]",
    "[emote:1730774:emojiGamer]",
    "[emote:1730775:emojiGlass]",
    "[emote:1730776:emojiGoofy]",
    "[emote:1730782:emojiGramps]",
    "[emote:1579046:emojiGrimacing]",
    "[emote:1730785:emojiGrin]",
    "[emote:1730786:emojiGrumpy]",
    "[emote:1730787:emojiHappy]",
    "[emote:1730792:emojiLoading]",
    "[emote:1579050:emojiLaughing]",
    "[emote:1730791:emojiLady]",
    "[emote:1730790:emojiKiss]",
    "[emote:1730789:emojiKing]",
    "[emote:4200908:emojiHydrate]",
    "[emote:1730788:emojiHmm]",
    "[emote:1579047:emojiHeartEyes]",
    "[emote:1730794:emojiLol]",
    "[emote:1730796:emojiMan]",
    "[emote:1730798:emojiNo]",
    "[emote:1579051:emojiMoneyEyes]",
    "[emote:1730799:emojiOof]",
    "[emote:1730800:emojiOooh]",
    "[emote:1730802:emojiOuch]",
    "[emote:1579052:emojiPleading]",
    "[emote:1730830:emojiStare]",
    "[emote:1730829:emojiSorry]",
    "[emote:1579057:emojiSmiling]",
    "[emote:1579055:emojiSmerking]",
    "[emote:1730827:emojiSmart]",
    "[emote:1730825:emojiSleep]",
    "[emote:1730807:emojiShocked]",
    "[emote:1730803:emojiRich]",
    "[emote:1579058:emojiStarEyes]",
    "[emote:1730839:emojiYuh]",
    "[emote:1730840:emojiYum]",
    "[emote:1579059:emojiSwearing]",
    "[emote:1579061:emojiUnamused]",
    "[emote:1579062:emojiVomiting]",
    "[emote:1730831:emojiWink]",
    "[emote:1579038:emojiXEyes]",
    "[emote:1730834:emojiYay]",
    "[emote:1730835:emojiYes]",
    "[emote:3753119:asmonSmash]",
    "[emote:5380971:AURAPULSE]",
    "[emote:5756662:AYAYA]",
    "[emote:5882722:BANG]",
    "[emote:4147910:BBoomer]",
    "[emote:39251:beeBobble]",
    "[emote:37217:Bwop]",
    "[emote:5756614:CaptFail]",
    "[emote:39265:EDMusiC]",
    "[emote:3645850:EDDIE]",
    "[emote:4147914:duckPls]",
    "[emote:5756666:DonoWall]",
    "[emote:5756616:DanceDance]",
    "[emote:37218:Clap]",
    "[emote:4147900:catKISS]",
    "[emote:4148144:catblobDance]",
    "[emote:5756511:FLASHBANG]",
    "[emote:5756668:EZ]",
    "[emote:39402:Flowie]",
    "[emote:37243:gachiGASM]",
    "[emote:5756671:GIGACHAD]",
    "[emote:4055795:GnomeDisco]",
    "[emote:4148076:HaHaa]",
    "[emote:5273247:highCortisol]",
    "[emote:5756621:kkHuh]",
    "[emote:5756602:NugTime]",
    "[emote:5756504:NODDERS]",
    "[emote:5339426:kickDrops]",
    "[emote:5470844:kickclassic]",
    "[emote:5756628:MuteD]",
    "[emote:5273241:MOGGED]",
    "[emote:37226:KEKW]",
    "[emote:37225:KEKLEO]",
    "[emote:5756381:modCheck]",
    "[emote:4148128:mericCat]",
    "[emote:4147902:KEKBye]",
    "[emote:5452913:JudgeJackson]",
    "[emote:37227:LULW]",
    "[emote:5273243:lowCortisol]",
    "[emote:4148074:HYPERCLAP]",
    "[emote:4055796:ODAJAM]",
    "[emote:37230:POLICE]",
    "[emote:5755651:SIT]",
    "[emote:5756632:SUSSY]",
    "[emote:5756627:politeCat]",
    "[emote:37229:OOOO]",
    "[emote:5756623:OuttaPocket]",
    "[emote:4147888:ppJedi]",
    "[emote:37236:ThisIsFine]",
    "[emote:5756677:TriKool]",
    "[emote:37234:Prayge]",
    "[emote:4147892:PatrickBoo]",
    "[emote:37232:PeepoClap]",
    "[emote:5756644:ratJAM]",
    "[emote:3645849:TRUEING]",
    "[emote:4147884:vibePls]",
    "[emote:4148081:Sadge]",
    "[emote:37245:peepoDJ]",
    "[emote:5756675:peepoRiot]",
    "[emote:5756676:SenpaiWhoo]",
    "[emote:5756678:WeirdChamp]",
    "[emote:5756680:WeSmart]",
    "[emote:5380973:shoulderRoll]",
    "[emote:37233:PogU]"
]

def get_emotes() -> list[str]:
    raw = get_setting('kick_emotes')
    if raw:
        try:
            val = json.loads(raw)
            if isinstance(val, list) and val:
                return val
        except Exception:
            pass
    return list(DEFAULT_KICK_EMOTES)

def set_emotes(emotes_list: list[str]):
    set_setting('kick_emotes', json.dumps(emotes_list, ensure_ascii=False))

def add_emote(emote_str: str) -> list[str]:
    emote_str = emote_str.strip()
    if not emote_str:
        return get_emotes()
    emotes = get_emotes()
    if emote_str not in emotes:
        emotes.append(emote_str)
        set_emotes(emotes)
    return emotes

def delete_emote(emote_str: str) -> list[str]:
    emotes = get_emotes()
    if emote_str in emotes:
        emotes.remove(emote_str)
        set_emotes(emotes)
    return emotes


# ──────────────────────────────────────────────
# License Keys Management (1-IP Protected)
# ──────────────────────────────────────────────

import secrets
from datetime import datetime, timedelta

def create_license_key(duration_hours: int, created_by: str = 'discord') -> str:
    """Generate and store a new license key with given duration in hours."""
    key_code = f"TAXER-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}"
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''INSERT INTO license_keys (key_code, duration_hours, is_active, created_by)
                 VALUES (?, ?, 1, ?)''', (key_code, int(duration_hours), created_by))
    conn.commit()
    conn.close()
    save_backup_file()
    return key_code


def validate_license_key(key_code: str, client_ip: str, client_hwid: str = None) -> tuple[bool, str]:
    """
    Validates license key against expiration, IP binding, and optional HWID binding.
    Returns (is_valid: bool, reason_or_status: str).
    """
    key_code = key_code.strip()
    if not key_code:
        return False, 'Key boş olamaz'

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''SELECT id, key_code, duration_hours, created_at, activated_at, expires_at, bound_ip, bound_hwid, is_active
                 FROM license_keys WHERE UPPER(TRIM(key_code))=UPPER(?)''', (key_code,))
    row = c.fetchone()

    if not row:
        conn.close()
        return False, 'Geçersiz Lisans Anahtarı!'

    kid, real_key_code, duration_hours, _, activated_at, expires_at, bound_ip, bound_hwid, is_active = row

    if not is_active:
        conn.close()
        return False, 'Bu anahtar devre dışı bırakılmış!'

    now = datetime.utcnow()

    # First activation: Bind IP, HWID and calculate expiration
    if not activated_at:
        exp = now + timedelta(hours=duration_hours)
        now_str = now.strftime('%Y-%m-%d %H:%M:%S')
        exp_str = exp.strftime('%Y-%m-%d %H:%M:%S')
        c.execute('''UPDATE license_keys
                     SET activated_at=?, expires_at=?, bound_ip=?, bound_hwid=?
                     WHERE id=?''', (now_str, exp_str, client_ip, client_hwid or '', kid))
        conn.commit()
        conn.close()
        save_backup_file()
        return True, f'Key aktive edildi! Süre: {duration_hours} saat (Bitiş: {exp_str})'

    # Check IP Binding (Security Guard)
    def _norm_ip(ip):
        if not ip:
            return ''
        ip = str(ip).strip()
        if ip in ('127.0.0.1', '::1', 'localhost'):
            return '127.0.0.1'
        return ip

    if bound_ip and _norm_ip(bound_ip) != _norm_ip(client_ip):
        conn.close()
        return False, 'IP Uyuşmazlığı! Bu lisans anahtarı başka bir cihaza/ağa kilitlenmiş.'

    # Check HWID Binding if exists
    if bound_hwid and client_hwid and bound_hwid != client_hwid:
        conn.close()
        return False, 'Cihaz/Tarayıcı Uyuşmazlığı! Bu key farklı bir cihazda aktif.'

    # Check Expiration
    if expires_at:
        try:
            exp_dt = datetime.strptime(expires_at, '%Y-%m-%d %H:%M:%S')
            if now > exp_dt:
                c.execute('UPDATE license_keys SET is_active=0 WHERE id=?', (kid,))
                conn.commit()
                conn.close()
                return False, f'Lisans süreniz doldu! (Bitiş: {expires_at})'
        except Exception as e:
            logger.error(f'Date parse error: {e}')

    conn.close()
    return True, 'Lisans geçerli'


# ──────────────────────────────────────────────
# User Memory Store (Hatırlama ve Profilleme)
# ──────────────────────────────────────────────

def update_user_memory(username: str, topic: str = None, sentiment: str = None):
    if not username or username in ('system', 'unknown'):
        return
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    c.execute('''INSERT INTO user_memory (username, first_seen, last_seen, message_count, last_topic, sentiment)
                 VALUES (?, ?, ?, 1, ?, ?)
                 ON CONFLICT(username) DO UPDATE SET
                    last_seen=?,
                    message_count=message_count + 1,
                    last_topic=COALESCE(?, last_topic),
                    sentiment=COALESCE(?, sentiment)''',
              (username, now_str, now_str, topic or '', sentiment or 'neutral',
               now_str, topic, sentiment))
    conn.commit()
    conn.close()


def get_user_memory(username: str) -> dict | None:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT username, first_seen, last_seen, message_count, last_topic, sentiment FROM user_memory WHERE username=?', (username,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            'username': row[0], 'first_seen': row[1], 'last_seen': row[2],
            'message_count': row[3], 'last_topic': row[4], 'sentiment': row[5]
        }
    return None


def get_all_license_keys():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''SELECT id, key_code, duration_hours, created_at, activated_at, expires_at, bound_ip, is_active, created_by
                 FROM license_keys ORDER BY id DESC''')
    rows = c.fetchall()
    conn.close()
    cols = ['id', 'key_code', 'duration_hours', 'created_at', 'activated_at', 'expires_at', 'bound_ip', 'is_active', 'created_by']
    return [dict(zip(cols, r)) for r in rows]


def get_license_key_info(key_code: str):
    """Retrieve detailed expiration and status for a license key."""
    if not key_code:
        return None
    key_code = key_code.strip()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''SELECT id, key_code, duration_hours, created_at, activated_at, expires_at, bound_ip, is_active, created_by
                 FROM license_keys WHERE UPPER(TRIM(key_code))=UPPER(?)''', (key_code,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    cols = ['id', 'key_code', 'duration_hours', 'created_at', 'activated_at', 'expires_at', 'bound_ip', 'is_active', 'created_by']
    d = dict(zip(cols, row))
    
    # Calculate remaining time in seconds
    remaining_sec = 0
    if d.get('expires_at') and d.get('is_active'):
        try:
            exp_dt = datetime.strptime(d['expires_at'], '%Y-%m-%d %H:%M:%S')
            diff = (exp_dt - datetime.utcnow()).total_seconds()
            remaining_sec = max(0, int(diff))
        except Exception:
            pass
    elif not d.get('activated_at') and d.get('is_active'):
        remaining_sec = d.get('duration_hours', 24) * 3600
        
    d['remaining_seconds'] = remaining_sec
    return d


def delete_license_key(key_code: str) -> bool:
    """Delete a license key by key_code. Returns True if deleted, False if not found."""
    key_code = key_code.strip()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM license_keys WHERE UPPER(TRIM(key_code))=UPPER(?)', (key_code,))
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()
    if deleted:
        save_backup_file()
    return deleted


# ──────────────────────────────────────────────
# Banned Words Auto-Blacklist (Madde 26)
# ──────────────────────────────────────────────

def add_banned_word(word: str, reason: str = 'kick_automod'):
    word = word.strip().lower()
    if not word:
        return
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO banned_words (word, reason) VALUES (?, ?)', (word, reason))
    conn.commit()
    conn.close()


def get_banned_words() -> set[str]:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT word FROM banned_words')
    rows = c.fetchall()
    conn.close()
    return {r[0] for r in rows}


# ──────────────────────────────────────────────
# Proxy Health & Score Tracking (Madde 19 & 23)
# ──────────────────────────────────────────────

def record_proxy_result(proxy_str: str, success: bool, latency: float = 0.0):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    succ_inc = 1 if success else 0
    fail_inc = 0 if success else 1
    alive = 1 if (success or fail_inc < 3) else 0

    c.execute('''INSERT INTO proxy_stats (proxy, success_count, fail_count, latency_ms, last_tested, is_alive)
                 VALUES (?, ?, ?, ?, ?, ?)
                 ON CONFLICT(proxy) DO UPDATE SET
                    success_count = success_count + ?,
                    fail_count = fail_count + ?,
                    latency_ms = (latency_ms + ?) / 2.0,
                    last_tested = ?,
                    is_alive = ?''',
              (proxy_str, succ_inc, fail_inc, latency, now_str, alive,
               succ_inc, fail_inc, latency, now_str, alive))
    conn.commit()
    conn.close()


def get_proxy_stats():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT proxy, success_count, fail_count, latency_ms, last_tested, is_alive FROM proxy_stats ORDER BY success_count DESC')
    rows = c.fetchall()
    conn.close()
    cols = ['proxy', 'success_count', 'fail_count', 'latency_ms', 'last_tested', 'is_alive']
    return [dict(zip(cols, r)) for r in rows]




