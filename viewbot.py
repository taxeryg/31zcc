"""
Kick.com ViewBot - Proxy'siz sürüm
Flask app.py ile entegre çalışır
"""

import sys
import time
import random
import datetime
import threading
import asyncio
import websockets
import json
import os
from threading import Thread, Semaphore
from fake_useragent import UserAgent

try:
    import tls_client
    HAS_TLS_CLIENT = True
except ImportError:
    import requests
    HAS_TLS_CLIENT = False

CLIENT_TOKEN = "e1393935a959b4020a4491574f6490129f678acdaa92760471263db43487f823"

class ViewBot:
    def __init__(self, channel_name, viewer_count, log_callback=None):
        self.channel = self.clean_channel_name(channel_name)
        self.max_threads = int(viewer_count)
        self.log_callback = log_callback or (lambda msg: print(msg))
        
        # Stats
        self.channel_id = None
        self.stream_id = None
        self.connections = 0
        self.attempts = 0
        self.pings = 0
        self.heartbeats = 0
        self.viewers = 0
        self.last_check = 0
        
        # Control
        self.stop = False
        self.start_time = None
        self.threads = []
        self.thread_limit = None
        self.active = 0
        self.lock = threading.Lock()

    def clean_channel_name(self, name):
        """URL'den kanal adını temizle"""
        if "kick.com/" in name:
            parts = name.split("kick.com/")
            channel = parts[1].split("/")[0].split("?")[0]
            return channel.lower()
        return name.lower()

    def log(self, msg):
        """Log mesajı"""
        self.log_callback(msg)

    def get_channel_info(self):
        """Kanal ID ve Stream ID bilgilerini çek"""
        try:
            if HAS_TLS_CLIENT:
                s = tls_client.Session(client_identifier="chrome_120", random_tls_extension_order=True)
            else:
                s = requests.Session()
            
            s.headers.update({
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Referer': 'https://kick.com/',
                'Origin': 'https://kick.com',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-origin',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"',
            })
            
            # v2 API dene
            try:
                response = s.get(f'https://kick.com/api/v2/channels/{self.channel}')
                if response.status_code == 200:
                    data = response.json()
                    self.channel_id = data.get("id")
                    if 'livestream' in data and data['livestream']:
                        self.stream_id = data['livestream'].get('id')
                    if self.channel_id:
                        self.log(f"✅ Channel ID: {self.channel_id}")
                        if self.stream_id:
                            self.log(f"✅ Stream ID: {self.stream_id}")
                        return True
            except:
                pass
            
            # v1 API dene
            try:
                response = s.get(f'https://kick.com/api/v1/channels/{self.channel}')
                if response.status_code == 200:
                    data = response.json()
                    self.channel_id = data.get("id")
                    if 'livestream' in data and data['livestream']:
                        self.stream_id = data['livestream'].get('id')
                    if self.channel_id:
                        self.log(f"✅ Channel ID: {self.channel_id}")
                        if self.stream_id:
                            self.log(f"✅ Stream ID: {self.stream_id}")
                        return True
            except:
                pass
            
            self.log(f"❌ Kanal bilgisi alınamadı: {self.channel}")
            return False
        except Exception as e:
            self.log(f"❌ Hata: {e}")
            return False

    def get_token(self):
        """WebSocket token al"""
        try:
            if HAS_TLS_CLIENT:
                s = tls_client.Session(client_identifier="chrome_120", random_tls_extension_order=True)
            else:
                s = requests.Session()
            
            s.headers.update({
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Connection': 'keep-alive',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Upgrade-Insecure-Requests': '1',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"',
            })
            
            # Ana sayfaya git
            try:
                s.get("https://kick.com")
                s.headers["X-CLIENT-TOKEN"] = CLIENT_TOKEN
                response = s.get('https://websockets.kick.com/viewer/v1/token')
                if response.status_code == 200:
                    data = response.json()
                    token = data.get("data", {}).get("token")
                    if token:
                        return token
            except:
                pass
            
            # Alternatif endpoint'ler
            endpoints = [
                'https://websockets.kick.com/viewer/v1/token',
                'https://kick.com/api/websocket/token',
                'https://kick.com/api/v1/websocket/token'
            ]
            for endpoint in endpoints:
                try:
                    s.headers["X-CLIENT-TOKEN"] = CLIENT_TOKEN
                    response = s.get(endpoint)
                    if response.status_code == 200:
                        data = response.json()
                        token = data.get("data", {}).get("token") or data.get("token")
                        if token:
                            return token
                except:
                    continue
            return None
        except:
            return None

    def get_viewer_count(self):
        """Gerçek viewer sayısını çek"""
        if not self.stream_id:
            return 0
        
        try:
            if HAS_TLS_CLIENT:
                s = tls_client.Session(client_identifier="chrome_120", random_tls_extension_order=True)
            else:
                s = requests.Session()
            
            s.headers.update({
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.9',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            })
            
            url = f"https://kick.com/current-viewers?ids[]={self.stream_id}"
            response = s.get(url)
            
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    self.viewers = data[0].get('viewers', 0)
                    self.last_check = time.time()
                    return self.viewers
            return 0
        except:
            return 0

    async def websocket_handler(self, token):
        """WebSocket bağlantısı yönet"""
        connected = False
        
        try:
            url = f"wss://websockets.kick.com/viewer/v1/connect?token={token}"
            async with websockets.connect(url) as ws:
                with self.lock:
                    self.connections += 1
                connected = True
                
                # Handshake gönder
                handshake = {
                    "type": "channel_handshake",
                    "data": {"message": {"channelId": self.channel_id}}
                }
                await ws.send(json.dumps(handshake))
                with self.lock:
                    self.heartbeats += 1
                
                # Ping gönder (10 kez)
                ping_count = 0
                while not self.stop and ping_count < 10:
                    ping_count += 1
                    ping = {"type": "ping"}
                    await ws.send(json.dumps(ping))
                    with self.lock:
                        self.pings += 1
                    
                    sleep_time = 12 + random.randint(1, 5)
                    await asyncio.sleep(sleep_time)
        except:
            pass
        finally:
            if connected:
                with self.lock:
                    if self.connections > 0:
                        self.connections -= 1

    def send_connection(self):
        """Tek bir viewer bağlantısı gönder"""
        self.active += 1
        with self.lock:
            self.attempts += 1
        
        try:
            token = self.get_token()
            if not token:
                return
            
            if not self.channel_id:
                if not self.get_channel_info():
                    return
            
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.websocket_handler(token))
            except:
                pass
            finally:
                try:
                    loop.close()
                except:
                    pass
        except:
            pass
        finally:
            self.active -= 1
            self.thread_limit.release()

    def connect_worker(self):
        """Thread worker"""
        self.send_connection()

    def stats_monitor(self):
        """İstatistikleri göster"""
        while not self.stop:
            try:
                now = time.time()
                
                # Her 5 saniyede bir viewer sayısını güncelle
                if now - self.last_check >= 5:
                    self.get_viewer_count()
                
                with self.lock:
                    if self.start_time:
                        elapsed = datetime.datetime.now() - self.start_time
                        duration = f"{int(elapsed.total_seconds())}s"
                    else:
                        duration = "0s"
                    
                    msg = f"[ViewBot] Bağlantı: {self.connections} | Deneme: {self.attempts} | Ping: {self.pings} | Heartbeat: {self.heartbeats} | Süre: {duration}"
                    if self.stream_id:
                        msg += f" | Stream ID: {self.stream_id} | Viewer: {self.viewers}"
                    self.log(msg)
                
                time.sleep(5)
            except:
                time.sleep(5)

    def start(self):
        """ViewBot'u başlat"""
        self.log(f"🚀 ViewBot başlatılıyor: {self.channel} ({self.max_threads} viewer)")
        
        self.thread_limit = Semaphore(self.max_threads)
        self.start_time = datetime.datetime.now()
        
        # Kanal bilgilerini al
        if not self.get_channel_info():
            self.log("❌ Kanal bilgisi alınamadı, durduruluyor...")
            return False
        
        # Stats monitor başlat
        stats_thread = Thread(target=self.stats_monitor, daemon=True)
        stats_thread.start()
        
        # Viewer bağlantılarını başlat
        while not self.stop:
            for i in range(self.max_threads):
                if self.stop:
                    break
                if self.thread_limit.acquire(blocking=False):
                    t = Thread(target=self.connect_worker)
                    self.threads.append(t)
                    t.daemon = True
                    t.start()
                    time.sleep(0.35)
            
            if self.stop:
                for _ in range(self.max_threads):
                    try:
                        self.thread_limit.release()
                    except:
                        pass
                break
            
            # Bağlantılar bittikten sonra yeniden başlat
            time.sleep(10)
        
        self.log("🛑 ViewBot durduruldu")
        return True

    def stop_bot(self):
        """ViewBot'u durdur"""
        self.stop = True
        self.log("⏹️ ViewBot durduruluyor...")


# Standalone kullanım için
if __name__ == "__main__":
    try:
        os.system('cls' if os.name == 'nt' else 'clear')
        channel_input = input("Kanal adı veya URL: ").strip()
        if not channel_input:
            print("Kanal adı gerekli.")
            sys.exit(1)
        
        while True:
            try:
                thread_input = int(input("Viewer sayısı: ").strip())
                if thread_input > 0:
                    break
                else:
                    print("0'dan büyük olmalı")
            except ValueError:
                print("Geçerli bir sayı girin")
        
        bot = ViewBot(channel_input, thread_input)
        bot.start()
    except KeyboardInterrupt:
        print("\n🛑 Durduruluyor...")
        sys.exit(0)
