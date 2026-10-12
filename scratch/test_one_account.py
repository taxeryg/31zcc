import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

import kick_account_creator as kac
import kick_client as kc

print("--- Testing single account creation ---", flush=True)
session = kac.KickAccountCreatorSession()
try:
    res = session.start_creation_async(use_temp_mail=True, headless=False, mail_provider="temptf")
    print(f"Async response: {res}", flush=True)
    if session._thread:
        session._thread.join(timeout=180)
        
    print(f"Final session status: {session.status}", flush=True)
    print(f"Current username: {session.current_username}", flush=True)
    print(f"Bearer token: {session.bearer_token}", flush=True)
    
    if session.bearer_token:
        # Test sending sa to sozcutv
        ok, resp = kc.send_kick_message(71783953, "sa", session.bearer_token)
        print(f"Send 'sa' test: ok={ok}, resp={resp}", flush=True)
finally:
    session.stop()
