import requests
import websocket
import json, time

channels = ['ataberkgaming', 'mertcan', 'poyraz', 'azizgaming', 'kafadengi', 'atatv']
live_ch = None

for ch in channels:
    try:
        r = requests.get(f'https://kick.com/api/v2/channels/{ch}', headers={'User-Agent': 'Mozilla/5.0'}, timeout=4)
        if r.status_code == 200:
            data = r.json()
            if data.get('livestream'):
                viewers = data['livestream'].get('viewer_count', 0)
                chatroom_id = data.get('chatroom', {}).get('id')
                print(f'LIVE: {ch} viewers={viewers} chatroom_id={chatroom_id}')
                live_ch = (ch, chatroom_id)
    except Exception as e:
        print(f'Error {ch}: {e}')

print('Done searching. Live:', live_ch)

# If a live channel found, listen to it for 15 seconds
if live_ch:
    ch_name, chatroom_id = live_ch
    url = 'wss://ws-us2.pusher.com/app/32cbd69e4b950bf97679?protocol=7&client=js&version=7.6.0&flash=false'
    msgs = []
    
    def on_message(ws, msg):
        data = json.loads(msg)
        if data.get('event') == 'pusher:connection_established':
            ws.send(json.dumps({'event': 'pusher:subscribe', 'data': {'channel': f'chatrooms.{chatroom_id}.v2'}}))
        elif data.get('event') == 'pusher_internal:subscription_succeeded':
            print(f'Subscribed to {ch_name}! Waiting for messages...')
        elif 'ChatMessage' in data.get('event', ''):
            msg_data = json.loads(data.get('data', '{}'))
            sender = msg_data.get('sender', {}).get('username', '?')
            content = msg_data.get('content', '')
            print(f'MSG: [{sender}]: {content}')
            msgs.append(msg_data)
            if len(msgs) >= 3:
                ws.close()
    
    ws = websocket.WebSocketApp(url, on_message=on_message)
    import ssl
    ws.run_forever(sslopt={'cert_reqs': ssl.CERT_NONE})
    print(f'Total messages received: {len(msgs)}')
