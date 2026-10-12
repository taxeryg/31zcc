import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests
import kick_account_creator as kac

working = []
print("Testing proxies in pool...")
for raw in kac.PROXY_POOL:
    try:
        ip, port, user, pwd = raw.split(":")
        px = f"http://{user}:{pwd}@{ip}:{port}"
        r = requests.get("https://httpbin.org/ip", proxies={"http": px, "https": px}, timeout=5)
        if r.status_code == 200:
            print(f"[OK] {raw[:25]}... -> {r.json()}")
            working.append(raw)
        else:
            print(f"[FAIL {r.status_code}] {raw}")
    except Exception as e:
        print(f"[FAIL] {raw[:25]}... -> {e}")

print("\nWORKING PROXIES:")
print(working)
