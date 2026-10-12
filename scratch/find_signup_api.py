from curl_cffi import requests
import re

s = requests.Session(impersonate='chrome120')
r = s.get('https://kick.com')

js_files = re.findall(r'src="([^"]+\.js)"', r.text)
print(f"Found {len(js_files)} JS files on kick.com")

for js in js_files:
    url = js if js.startswith('http') else ('https://kick.com' + js)
    try:
        resp = s.get(url, timeout=10)
        if 'send-verification-code' in resp.text:
            print("FOUND in:", url)
            idx = resp.text.find('send-verification-code')
            print("SNIPPET:", resp.text[max(0, idx-300):idx+400])
            break
    except Exception as e:
        pass
