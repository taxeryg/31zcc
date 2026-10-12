import os
import sys
import json
import requests
import concurrent.futures

RAW_FILE = os.path.join(os.path.dirname(__file__), "raw_tokens.txt")
DISCORD_TOKENS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "discordbot", "tokens.json")

HEADERS_BASE = {
    'Accept': 'application/json',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Content-Type': 'application/json',
    'Referer': 'https://kick.com/',
    'Origin': 'https://kick.com',
}

def check_token(tok):
    clean_tok = tok.strip()
    if not clean_tok:
        return None, False, None, "empty"
    
    headers = {**HEADERS_BASE, 'Authorization': f'Bearer {clean_tok}'}
    try:
        r = requests.get('https://kick.com/api/v1/user', headers=headers, timeout=8)
        if r.status_code == 200:
            data = r.json()
            username = data.get('username', 'unknown')
            user_id = data.get('id', 'unknown')
            return clean_tok, True, {"username": username, "id": user_id}, "200 OK"
        else:
            return clean_tok, False, None, f"HTTP {r.status_code}"
    except Exception as e:
        return clean_tok, False, None, f"Err: {str(e)[:40]}"

def main():
    print("=== KICK TOKENLERI TEST EDILIYOR ===", flush=True)
    
    with open(RAW_FILE, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
        
    unique_tokens = list(dict.fromkeys(lines))
    print(f"Toplam Gelen Token: {len(lines)} (Benzersiz: {len(unique_tokens)})", flush=True)
    
    valid_tokens = []
    invalid_tokens = []
    
    # 15 concurrent threads
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        future_to_tok = {executor.submit(check_token, t): t for t in unique_tokens}
        for future in concurrent.futures.as_completed(future_to_tok):
            tok, ok, info, status_msg = future.result()
            if ok:
                valid_tokens.append((tok, info))
                print(f"[+] ÇALIŞIYOR: {tok[:15]}... -> @{info['username']} (ID: {info['id']})", flush=True)
            else:
                invalid_tokens.append((tok, status_msg))
                print(f"[-] PATLAK: {tok[:15]}... -> {status_msg}", flush=True)
                
    print("\n================ ÖZET TEST SONUCU ================", flush=True)
    print(f"Toplam Test Edilen: {len(unique_tokens)}")
    print(f"Aktif / Çalışan Token: {len(valid_tokens)}")
    print(f"Geçersiz / Patlak Token: {len(invalid_tokens)}")
    
    # Load existing tokens from discordbot/tokens.json
    existing = []
    if os.path.exists(DISCORD_TOKENS_FILE):
        try:
            with open(DISCORD_TOKENS_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception as e:
            print(f"Mevcut tokens.json okunamadı: {e}", flush=True)
            existing = []
            
    existing_set = set(existing)
    new_added = 0
    for tok, info in valid_tokens:
        if tok not in existing_set:
            existing.append(tok)
            existing_set.add(tok)
            new_added += 1
            
    with open(DISCORD_TOKENS_FILE, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)
        
    print(f"\n[DISCORD BOT] {DISCORD_TOKENS_FILE} dosyasına kaydedildi!")
    print(f"Yeni Eklenen Token Sayısı: {new_added}")
    print(f"discordbot/tokens.json Toplam Token: {len(existing)}")

if __name__ == '__main__':
    main()
