import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import storage
import kick_client as kc
import traceback

try:
    conn = sqlite3.connect(storage.DB_FILE)
    c = conn.cursor()
    c.execute('SELECT username, token_enc FROM kick_accounts')
    rows = c.fetchall()
    conn.close()
    for u, enc in rows:
        tok = storage.decrypt(enc)
        print(f"Testing user: {u}, token len={len(tok)}")
        ok, resp = kc.send_kick_message(71783953, "sa", tok)
        print(f"User {u}: ok={ok}, resp={resp}")
except Exception as e:
    traceback.print_exc()
