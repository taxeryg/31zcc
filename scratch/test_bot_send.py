import requests, time, storage, kick_client

# Simulate an incoming message directly through the pipeline
# to test if the bot responds correctly

# Get the chatroom_id from settings
chatroom_id = storage.get_setting('chatroom_id')
print(f'Chatroom ID: {chatroom_id}')

# Test the bot sending a manual message
r = requests.post('http://127.0.0.1:5000/api/bots/1/send', json={
    'content': 'Merhaba! Ben AI botum, test ediyorum.',
    'chatroom_id': chatroom_id
})
print('Bot send response:', r.status_code, r.text)
