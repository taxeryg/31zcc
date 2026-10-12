with open(r'C:\Users\mama1\.gemini\antigravity-ide\brain\9bfa61bb-95bb-4333-b946-91b05f48c097\.system_generated\tasks\task-316.log', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

import re, json
for m in re.finditer(r'RAW REQUEST EVENT: ({.*?})\n', text):
    try:
        d = json.loads(m.group(1))
        req = d.get('message', {}).get('params', {}).get('request', {})
        if 'send-verification-code' in req.get('url', ''):
            print("METHOD:", req.get('method'))
            print("HEADERS:", req.get('headers'))
            print("POSTDATA:", req.get('postData'))
    except Exception as e:
        print("Err:", e)
