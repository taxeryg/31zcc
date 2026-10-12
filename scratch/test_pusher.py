import websocket
import json
import time

clusters = ['us2', 'us1', 'us3', 'eu', 'ap1', 'ap2', 'ap3', 'sa1', 'mt1']
key = 'eb1d5f283081a78b932c'

for cluster in clusters:
    url = f'wss://ws-{cluster}.pusher.com/app/{key}?protocol=7&client=js&version=7.6.0&flash=false'
    print(f"Testing cluster: {cluster}")
    
    result = {'success': False, 'msg': ''}
    
    def on_message(ws, msg):
        print(f"  [{cluster}] MSG: {msg}")
        if 'connection_established' in msg:
            result['success'] = True
            ws.close()
        elif 'error' in msg:
            result['msg'] = msg
            ws.close()
            
    def on_error(ws, err):
        print(f"  [{cluster}] ERR: {err}")
        
    ws = websocket.WebSocketApp(url, on_message=on_message, on_error=on_error)
    ws.run_forever()
    if result['success']:
        print(f"*** FOUND WORKING CLUSTER: {cluster} ***")
        break
    else:
        print(f"  [{cluster}] Failed: {result['msg']}")
