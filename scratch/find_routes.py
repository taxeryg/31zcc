from curl_cffi import requests
import re

s = requests.Session(impersonate='chrome120')
resp = s.get('https://assets.kick.com/main/_next/static/chunks/1fkb1dhb3mn7w.js')

for m in re.finditer(r'path:"([^"]+)"', resp.text):
    print("ROUTE:", m.group(1))
