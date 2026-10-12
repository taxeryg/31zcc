import sys
import os
import time
import json
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

import kick_account_creator as kac
import kick_client as kc
import storage

TARGET_COUNT = 1
MAX_ATTEMPTS = 3
CHANNEL_NAME = "sozcutv"
RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "batch_results.json")

# 1. Fetch channel info
chatroom_id, slug = kc.get_channel_info(CHANNEL_NAME)
logger.info(f"Hedef Kanal: {CHANNEL_NAME} -> chatroom_id={chatroom_id}")

if not chatroom_id:
    logger.error("Hedef kanalın chatroom ID bilgisi alınamadı!")
    sys.exit(1)

created_accounts = []
failed_count = 0
attempt = 0

print(f"=== BATCH HESAP OLUŞTURMA & SOZCUTV 'SA' TESTİ BAŞLIYOR (Hedef: {TARGET_COUNT}) ===", flush=True)

while len(created_accounts) < TARGET_COUNT and attempt < MAX_ATTEMPTS:
    attempt += 1
    current_idx = len(created_accounts) + 1
    prov = "temptf"
    print(f"\n=======================================================", flush=True)
    print(f"--- [Hedef {current_idx}/{TARGET_COUNT} | Deneme {attempt}/{MAX_ATTEMPTS}] Kayıt Başlatılıyor (Mail: {prov}) ---", flush=True)
    print(f"=======================================================", flush=True)
    
    session = kac.KickAccountCreatorSession()
    try:
        res = session.start_creation_async(use_temp_mail=True, headless=True, mail_provider=prov)
        print(f"Async başlangıç: {res}", flush=True)
        
        if session._thread:
            session._thread.join(timeout=150)
            
        if session.status == "success" and session.bearer_token:
            username = session.current_username
            token = session.bearer_token
            email = session.current_email
            print(f"[BAŞARILI] Hesap Açıldı: {username} | Email: {email}", flush=True)
            print(f"[TOKEN] {token[:20]}...{token[-10:]}", flush=True)
            
            # Veritabanında var mı kontrol et, yoksa ekle
            existing = [acc for acc in storage.get_kick_accounts() if acc.get('username') == username]
            if not existing:
                storage.add_kick_account(username, token)
                print(f"[DB] {username} veritabanına eklendi.", flush=True)
            
            # Test: sozcutv kanalına "sa" mesajı gönder
            print(f"[TEST] {CHANNEL_NAME} (chatroom_id={chatroom_id}) kanalına 'sa' atılıyor...", flush=True)
            time.sleep(2)
            msg_ok, msg_resp = kc.send_kick_message(chatroom_id, "sa", token)
            print(f"[MESAJ SONUCU] Gönderildi: {msg_ok} | Yanıt: {str(msg_resp)[:150]}", flush=True)
            
            acc_entry = {
                "index": current_idx,
                "username": username,
                "email": email,
                "token": token,
                "msg_sent": msg_ok,
                "msg_resp": str(msg_resp)[:200],
                "time": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            created_accounts.append(acc_entry)
            
            with open(RESULTS_FILE, "w", encoding="utf-8") as f:
                json.dump(created_accounts, f, ensure_ascii=False, indent=2)
                
            print(f"--> Toplam Başarılı: {len(created_accounts)} / {TARGET_COUNT}", flush=True)
        else:
            print(f"[BAŞARISIZ] Durum: {session.status}", flush=True)
            failed_count += 1
    except Exception as e:
        print(f"[HATA] Döngü hatası: {e}", flush=True)
        failed_count += 1
    finally:
        session.stop()
        
    time.sleep(3)

print("\n================ BATCH TOPLU SONUÇ RAPORU ================", flush=True)
print(f"Toplam Deneme: {attempt}")
print(f"Başarıyla Açılan ve Sisteme Eklenen: {len(created_accounts)}")
print(f"Başarısız: {failed_count}")
for idx, acc in enumerate(created_accounts, 1):
    print(f"{idx}. {acc['username']} | Email: {acc['email']} | Sa Sonucu: {acc['msg_sent']} | Yanıt: {acc['msg_resp']}")
print("==========================================================", flush=True)
