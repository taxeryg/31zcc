"""
storage.py — SQLite + Fernet şifreli token yönetimi
"""
import sqlite3
import os
import logging
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

DB_FILE = os.environ.get('DB_FILE', 'botdash.db')
_KEY_FILE = '.secret_key'


def _get_or_create_fernet():
    env_key = os.environ.get('FERNET_KEY')
    if env_key:
        return Fernet(env_key.encode() if isinstance(env_key, str) else env_key)
    if os.path.exists(_KEY_FILE):
        with open(_KEY_FILE, 'rb') as f:
            key = f.read().strip()
    else:
        key = Fernet.generate_key()
        with open(_KEY_FILE, 'wb') as f:
            f.write(key)
    return Fernet(key)


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

    c.execute('''CREATE TABLE IF NOT EXISTS ai_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        token_enc TEXT NOT NULL,
        base_url TEXT DEFAULT 'https://api.openai.com/v1',
        model TEXT DEFAULT 'gpt-4o-mini',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS kick_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        token_enc TEXT NOT NULL,
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
        timestamp TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    conn.commit()
    conn.close()


# ──────────────────────────────────────────────
# Settings
# ──────────────────────────────────────────────

def get_setting(key, default=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT value FROM settings WHERE key=?', (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default


def set_setting(key, value):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)', (key, value))
    conn.commit()
    conn.close()


# ──────────────────────────────────────────────
# AI Tokens
# ──────────────────────────────────────────────

def add_ai_token(name, token, base_url, model):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO ai_tokens (name,token_enc,base_url,model) VALUES (?,?,?,?)',
              (name, encrypt(token), base_url, model))
    id_ = c.lastrowid
    conn.commit()
    conn.close()
    return id_


def get_ai_tokens():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id,name,token_enc,base_url,model,created_at FROM ai_tokens ORDER BY id')
    rows = c.fetchall()
    conn.close()
    result = []
    for r in rows:
        result.append({
            'id': r[0], 'name': r[1],
            'token_masked': mask_token(decrypt(r[2])),
            'base_url': r[3], 'model': r[4], 'created_at': r[5]
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


def get_first_ai_token_id():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id FROM ai_tokens LIMIT 1')
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


def delete_ai_token(token_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM ai_tokens WHERE id=?', (token_id,))
    conn.commit()
    conn.close()


# ──────────────────────────────────────────────
# Kick Accounts
# ──────────────────────────────────────────────

def add_kick_account(username, token):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO kick_accounts (username,token_enc) VALUES (?,?)',
              (username, encrypt(token)))
    id_ = c.lastrowid
    conn.commit()
    conn.close()
    return id_


def get_kick_accounts():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id,username,token_enc,is_active,created_at FROM kick_accounts ORDER BY id')
    rows = c.fetchall()
    conn.close()
    return [{
        'id': r[0], 'username': r[1],
        'token_masked': mask_token(decrypt(r[2])),
        'is_active': bool(r[3]), 'created_at': r[4]
    } for r in rows]


def get_kick_token_raw(account_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT token_enc FROM kick_accounts WHERE id=?', (account_id,))
    row = c.fetchone()
    conn.close()
    return decrypt(row[0]) if row else None


def delete_kick_account(account_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM kick_accounts WHERE id=?', (account_id,))
    conn.commit()
    conn.close()


# ──────────────────────────────────────────────
# Bots
# ──────────────────────────────────────────────

def add_bot(data):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''INSERT INTO bots
        (name,personality,style,interests,enabled,response_chance,
         min_delay,max_delay,daily_limit,ai_token_id,kick_account_id,system_prompt)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
        (data.get('name', ''), data.get('personality', ''), data.get('style', ''),
         data.get('interests', ''), int(data.get('enabled', 1)),
         float(data.get('response_chance', 0.35)),
         int(data.get('min_delay', 8)), int(data.get('max_delay', 45)),
         int(data.get('daily_limit', 50)),
         data.get('ai_token_id'), data.get('kick_account_id'),
         data.get('system_prompt', '')))
    id_ = c.lastrowid
    conn.commit()
    conn.close()
    return id_


def get_bots():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT * FROM bots ORDER BY id')
    rows = c.fetchall()
    conn.close()
    cols = ['id', 'name', 'personality', 'style', 'interests', 'enabled',
            'response_chance', 'min_delay', 'max_delay', 'daily_limit',
            'ai_token_id', 'kick_account_id', 'system_prompt', 'created_at']
    return [dict(zip(cols, r)) for r in rows]


def update_bot(bot_id, data):
    allowed = ['name', 'personality', 'style', 'interests', 'enabled', 'response_chance',
               'min_delay', 'max_delay', 'daily_limit', 'ai_token_id', 'kick_account_id', 'system_prompt']
    fields = [f for f in allowed if f in data]
    if not fields:
        return
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    set_clause = ', '.join(f'{f}=?' for f in fields)
    values = [data[f] for f in fields] + [bot_id]
    c.execute(f'UPDATE bots SET {set_clause} WHERE id=?', values)
    conn.commit()
    conn.close()


def delete_bot(bot_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM bots WHERE id=?', (bot_id,))
    conn.commit()
    conn.close()


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
# Message Logs
# ──────────────────────────────────────────────

def log_message(msg_type, username, content, bot_name=None,
                analysis=None, status=None, error_msg=None):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''INSERT INTO message_logs
            (msg_type,username,content,bot_name,analysis,status,error_msg)
            VALUES (?,?,?,?,?,?,?)''',
            (msg_type, username, content[:500] if content else '',
             bot_name, analysis, status, error_msg))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f'log_message error: {e}')


def get_message_logs(limit=200):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT * FROM message_logs ORDER BY id DESC LIMIT ?', (limit,))
    rows = c.fetchall()
    conn.close()
    cols = ['id', 'msg_type', 'username', 'content', 'bot_name',
            'analysis', 'status', 'error_msg', 'timestamp']
    return list(reversed([dict(zip(cols, r)) for r in rows]))
