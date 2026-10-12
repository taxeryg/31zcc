import requests, time

# Check bots and tokens
bots = requests.get('http://127.0.0.1:5000/api/bots').json()
for b in bots:
    kick_acc = b.get('kick_account_id')
    ai_tok = b.get('ai_token_id')
    print(f"Bot: {b['name']} | enabled={b['enabled']} | kick_account={kick_acc} | ai_token={ai_tok}")

tokens = requests.get('http://127.0.0.1:5000/api/tokens').json()
print("AI Tokens:", tokens)

kick_accounts = requests.get('http://127.0.0.1:5000/api/kick-accounts').json()
print("Kick Accounts:", kick_accounts)
