"""
storage.py — SQLite + Fernet şifreli token yönetimi
"""
import json
import sqlite3
import os
import logging
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

DB_FILE = os.environ.get('DB_FILE', 'botdash.db')
BACKUP_FILE = os.environ.get('BACKUP_FILE', 'persistent_storage.json')
_KEY_FILE = '.secret_key'

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
    save_backup_file()


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
    save_backup_file()
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
    save_backup_file()


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
    save_backup_file()
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
    save_backup_file()


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
    save_backup_file()
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
    save_backup_file()


def delete_bot(bot_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
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
    
    conn.close()
    return {
        'ai_tokens': ai_tokens,
        'kick_accounts': kick_accounts,
        'bots': bots,
        'settings': settings
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
