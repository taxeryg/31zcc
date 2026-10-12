import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
import kick_account_creator as kac

logging.basicConfig(level=logging.INFO)

print("--- Testing Username & Pass Generators ---")
username = kac.generate_username()
password = kac.generate_password()
birthdate = kac.generate_birthdate()
print(f"Generated: User={username}, Pass={password}, Bday={birthdate}")

print("\n--- Testing TempTfMailClient ---")
try:
    tf = kac.TempTfMailClient()
    mb = tf.create_mailbox()
    print("TempTf Mail:", mb)
except Exception as e:
    print("TempTf Error:", e)

print("\n--- Testing GuerrillaMailClient ---")
try:
    gm = kac.GuerrillaMailClient()
    mb = gm.create_mailbox()
    print("Guerrilla Mail:", mb)
except Exception as e:
    print("Guerrilla Error:", e)

print("\n--- Testing MailTmClient ---")
try:
    mt = kac.MailTmClient()
    mb = mt.create_mailbox()
    print("MailTm Mail:", mb)
except Exception as e:
    print("MailTm Error:", e)
