import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import kick_account_creator as kac

print("Testing Proxy Pool...")
for raw in kac.PROXY_POOL:
    try:
        ip, port, user, pwd = raw.split(":")
        px = f"http://{user}:{pwd}@{ip}:{port}"
        r = requests.get("https://httpbin.org/ip", proxies={"http": px, "https": px}, timeout=5)
        print(f"Proxy {ip}:{port} SUCCESS -> {r.json()}")
    except Exception as e:
        print(f"Proxy {raw[:20]}... FAILED -> {e}")
