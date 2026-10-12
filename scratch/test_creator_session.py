import sys
import os
import logging
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO)

import kick_account_creator as kac

def log_cb(evt, data):
    print(f"[EMIT {evt}] {data}")

ac = kac.KickAccountCreatorSession(emit_fn=log_cb)

print("Starting creation test...")
res = ac.start_creation_async(use_temp_mail=True, headless=True)
print("Start result:", res)

# Wait for process
if ac._thread:
    ac._thread.join(timeout=120)

print("Final status:", ac.status)
print("Current username:", ac.current_username)
print("Current email:", ac.current_email)
print("Bearer token:", ac.bearer_token)
