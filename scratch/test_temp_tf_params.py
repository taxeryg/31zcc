import requests

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Referer": "https://temp.tf/"
})

print("Testing temp.tf account generation with different params:")
for p in ["gmail", "outlook", "hotmail"]:
    r = s.get("https://temp.tf/api/account", params={"providers": p, "dot": "0", "plus": "0"})
    print(f"Provider {p}: status={r.status_code}, json={r.json()}")
