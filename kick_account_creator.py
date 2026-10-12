"""
kick_account_creator.py — Otomatik Kick Hesap Oluşturucu Motoru
- Guerrilla Mail / Temp.tf / Mail.tm e-posta entegrasyonu (otomatik 6 haneli kod okuma)
- DrissionPage (Chromium CDP) ile %100 Cloudflare ve Turnstile uyumlu otomasyon
- Yerel Socket Proxy Bridge ile kullanıcı adı/şifreli konut proxy rotasyonu
- Bearer Token / Session yakalama ve otomatik veri tabanına (storage) ekleme
- Socket.IO ile canlı adım ve log yayını (Web UI uyumlu)
- Bağımsız CLI desteği: python kick_account_creator.py --count 10
"""

import argparse
import base64
import json
import logging
import os
import random
import re
import socket
import string
import sys
import threading
import time
from datetime import date, timedelta
from typing import Callable, Optional

import requests
try:
    from DrissionPage import ChromiumOptions, ChromiumPage
except ImportError:
    ChromiumOptions = None
    ChromiumPage = None

import storage

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Proxy Pool & Rotation
# ─────────────────────────────────────────────────────────────

DEFAULT_PROXY_POOL = [
    "31.59.20.176:6754:gpbzberw:ripdlkneqpn0",
    "45.38.107.97:6014:gpbzberw:ripdlkneqpn0",
    "64.137.96.74:6641:gpbzberw:ripdlkneqpn0",
    "198.23.243.226:6361:gpbzberw:ripdlkneqpn0",
    "38.154.185.97:6370:gpbzberw:ripdlkneqpn0",
    "84.247.60.125:6095:gpbzberw:ripdlkneqpn0",
    "142.111.67.146:5611:gpbzberw:ripdlkneqpn0",
    "191.96.254.138:6185:gpbzberw:ripdlkneqpn0",
    "31.58.9.4:6077:gpbzberw:ripdlkneqpn0",
    "198.46.161.42:5092:gpbzberw:ripdlkneqpn0",
]


def load_proxy_pool() -> list[str]:
    """proxies.txt dosyasından veya varsayılan havuzdan aktif proxyleri çeker."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    txt_path = os.path.join(base_dir, "proxies.txt")
    if os.path.exists(txt_path):
        try:
            with open(txt_path, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
                if lines:
                    return lines
        except Exception:
            pass
    return list(DEFAULT_PROXY_POOL)


PROXY_POOL = load_proxy_pool()


class LocalAuthProxyBridge:
    """Yerel socket proxy köprü sınıfı: Headless Chrome isteklerine otomatik Proxy-Authorization ekler."""

    def __init__(self, target_ip: str, target_port: int, user: str, password: str):
        self.target_ip = target_ip
        self.target_port = int(target_port)
        self.user = user
        self.password = password
        self.server_socket = None
        self.port = 0
        self.is_running = False
        self._thread = None

    def start(self) -> str:
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(("127.0.0.1", 0))
        self.port = self.server_socket.getsockname()[1]
        self.server_socket.listen(50)
        self.is_running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        return f"127.0.0.1:{self.port}"

    def _listen_loop(self):
        auth_header = (
            "Proxy-Authorization: Basic "
            + base64.b64encode(f"{self.user}:{self.password}".encode()).decode()
            + "\r\n"
        )
        while self.is_running:
            try:
                client_sock, _ = self.server_socket.accept()
                threading.Thread(
                    target=self._handle_client,
                    args=(client_sock, auth_header),
                    daemon=True,
                ).start()
            except Exception:
                break

    def _handle_client(self, client_sock, auth_header):
        try:
            remote_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            remote_sock.settimeout(15)
            remote_sock.connect((self.target_ip, self.target_port))

            data = client_sock.recv(8192)
            if not data:
                client_sock.close()
                remote_sock.close()
                return

            lines = data.split(b"\r\n")
            new_lines = [lines[0]] + [auth_header.encode()] + lines[1:]
            modified_data = b"\r\n".join(new_lines)
            remote_sock.sendall(modified_data)

            def pipe(src, dst):
                try:
                    while True:
                        buf = src.recv(8192)
                        if not buf:
                            break
                        dst.sendall(buf)
                except Exception:
                    pass
                finally:
                    try:
                        src.close()
                    except Exception:
                        pass
                    try:
                        dst.close()
                    except Exception:
                        pass

            threading.Thread(target=pipe, args=(client_sock, remote_sock), daemon=True).start()
            threading.Thread(target=pipe, args=(remote_sock, client_sock), daemon=True).start()
        except Exception:
            try:
                client_sock.close()
            except Exception:
                pass

    def stop(self):
        self.is_running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────
# Credentials & Utility Generator
# ─────────────────────────────────────────────────────────────

ADJECTIVES = [
    "dark", "hyper", "cyber", "neon", "turbo", "shadow", "frost", "vortex",
    "alpha", "phantom", "storm", "blaze", "retro", "quantum", "rapid", "apex",
    "kral", "yildiz", "efsane", "ates", "ruzgar", "demir", "bozkurt", "kaplan"
]

NOUNS = [
    "rider", "gamer", "streamer", "player", "wolf", "strike", "titan", "sniper",
    "hunter", "viper", "ghost", "eagle", "blade", "knight", "drifter", "spark",
    "kartal", "avci", "savasci", "reis", "aslan", "pilot", "usta", "kurt"
]


def generate_username() -> str:
    """Kick kurallarına uygun (3-20 karakter, harf/rakam/alt çizgi) benzersiz kullanıcı adı üretir."""
    adj = random.choice(ADJECTIVES)
    noun = random.choice(NOUNS)
    num = random.randint(10, 999)
    name = f"{adj}_{noun}_{num}"
    if len(name) > 18:
        name = name[:18]
    return name.lower()


def generate_password(length: int = 14) -> str:
    """Kick şifre kurallarına (%100) uygun: büyük harf, küçük harf, rakam ve sembol içeren güçlü şifre üretir."""
    uppers = random.choices(string.ascii_uppercase, k=2)
    lowers = random.choices(string.ascii_lowercase, k=6)
    digits = random.choices(string.digits, k=3)
    specials = random.choices("!@#$%", k=2)
    all_chars = uppers + lowers + digits + specials
    remaining = random.choices(string.ascii_letters + string.digits, k=max(0, length - len(all_chars)))
    combined = all_chars + remaining
    random.shuffle(combined)
    return "".join(combined)


def generate_birthdate(min_age: int = 19, max_age: int = 30) -> str:
    """18 yaşından büyük geçerli YYYY-MM-DD doğum tarihi üretir."""
    today = date.today()
    age = random.randint(min_age, max_age)
    days_offset = random.randint(0, 364)
    target_date = today - timedelta(days=(age * 365 + days_offset))
    return target_date.strftime("%Y-%m-%d")


# ─────────────────────────────────────────────────────────────
# Guerrilla Mail Integration (Ana Geçici E-Posta Servisi)
# ─────────────────────────────────────────────────────────────

class GuerrillaMailClient:
    """Guerrilla Mail API: Kick 35 karakter sınırına uygun, anında OTP alan e-posta istemcisi."""
    API_BASE = "https://api.guerrillamail.com/ajax.php"

    def __init__(self):
        self.email: Optional[str] = None
        self.sid_token: Optional[str] = None
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        })

    def create_mailbox(self, custom_user: Optional[str] = None) -> dict:
        resp = self.session.get(f"{self.API_BASE}?f=get_email_address", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        self.sid_token = data.get("sid_token")
        self.email = data.get("email_addr")

        # Kick en fazla 35 karakter kabul eder!
        if self.email and len(self.email) > 35 and self.sid_token:
            pfx = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
            try:
                set_resp = self.session.get(
                    f"{self.API_BASE}?f=set_email_user&email_user={pfx}&lang=en&sid_token={self.sid_token}",
                    timeout=10,
                )
                if set_resp.status_code == 200:
                    self.email = set_resp.json().get("email_addr", self.email)
            except Exception:
                pass

        return {"email": self.email, "sid_token": self.sid_token}

    def poll_verification_code(self, timeout_secs: int = 75, log_cb: Optional[Callable] = None) -> Optional[str]:
        if not self.sid_token:
            return None

        start_time = time.time()
        if log_cb:
            log_cb("info", f"Guerrilla Mail gelen kutusu dinleniyor ({self.email})...")

        while time.time() - start_time < timeout_secs:
            try:
                # get_email_list ile tüm gelen kutusunu tarar (sequence buglarından etkilenmez)
                resp = self.session.get(
                    f"{self.API_BASE}?f=get_email_list&offset=0&sid_token={self.sid_token}",
                    timeout=10,
                )
                if resp.status_code == 200:
                    mail_list = resp.json().get("list", [])
                    for mail in mail_list:
                        subj = mail.get("mail_subject", "")
                        sender = mail.get("mail_from", "")
                        if "kick" in f"{subj} {sender}".lower():
                            matches = re.findall(r"\b\d{6}\b", subj)
                            if not matches:
                                mail_id = mail.get("mail_id")
                                f_r = self.session.get(
                                    f"{self.API_BASE}?f=fetch_email&email_id={mail_id}&sid_token={self.sid_token}",
                                    timeout=10,
                                )
                                body = f_r.json().get("mail_body", "") if f_r.status_code == 200 else ""
                                matches = re.findall(r"\b\d{6}\b", body)

                            if matches:
                                code = matches[0]
                                if log_cb:
                                    log_cb("success", f"Kick onay kodu yakalandı: {code}")
                                return code
                time.sleep(3)
            except Exception as e:
                logger.debug(f"Guerrilla poll error: {e}")
                time.sleep(3)

        return None


# ─────────────────────────────────────────────────────────────
# temp.tf Integration (Yedek Servis)
# ─────────────────────────────────────────────────────────────

class TempTfMailClient:
    API_BASE = "https://temp.tf/api"

    def __init__(self, proxy_dict: Optional[dict] = None):
        self.email: Optional[str] = None
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json",
        })

    def create_mailbox(self, max_retries: int = 5) -> dict:
        for _ in range(max_retries):
            try:
                resp = self.session.get(
                    f"{self.API_BASE}/account",
                    params={"providers": "gmail,outlook,hotmail", "dot": "1", "plus": "0"},
                    timeout=10,
                )
                if resp.status_code == 200:
                    em = (resp.json().get("email") or "").strip().lower()
                    if em and len(em) <= 35:
                        self.email = em
                        return {"email": self.email}
            except Exception:
                pass
            time.sleep(1)
        raise RuntimeError("temp.tf servisinden uygun e-posta alınamadı.")

    def poll_verification_code(self, timeout_secs: int = 75, log_cb: Optional[Callable] = None) -> Optional[str]:
        if not self.email:
            return None
        start_time = time.time()
        seen = set()
        while time.time() - start_time < timeout_secs:
            try:
                resp = self.session.post(f"{self.API_BASE}/check", json={"email": self.email, "wait": False}, timeout=10)
                if resp.status_code == 200:
                    items = resp.json().get("data", [])
                    for item in items:
                        m_id = item.get("id") or item.get("messageId")
                        if m_id in seen:
                            continue
                        if m_id:
                            seen.add(m_id)
                        full = f"{item.get('subject', '')} {item.get('body', '')}"
                        if "kick" in full.lower():
                            codes = re.findall(r"\b\d{6}\b", full)
                            if codes:
                                return codes[0]
                time.sleep(3)
            except Exception:
                time.sleep(3)
        return None


# ─────────────────────────────────────────────────────────────
# Mail.tm Backup Integration
# ─────────────────────────────────────────────────────────────

class MailTmClient:
    API_BASE = "https://api.mail.tm"

    def __init__(self):
        self.email: Optional[str] = None
        self.password: Optional[str] = None
        self.token: Optional[str] = None

    def create_mailbox(self) -> dict:
        dom_resp = requests.get(f"{self.API_BASE}/domains", timeout=10)
        dom_resp.raise_for_status()
        members = dom_resp.json().get("hydra:member") or []
        if not members:
            raise RuntimeError("Mail.tm aktif domain bulunamadı.")
        domain = members[0]["domain"]
        rand_user = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
        self.email = f"{rand_user}@{domain}"
        self.password = generate_password(12)
        requests.post(f"{self.API_BASE}/accounts", json={"address": self.email, "password": self.password}, timeout=10)
        tok_resp = requests.post(f"{self.API_BASE}/token", json={"address": self.email, "password": self.password}, timeout=10)
        self.token = tok_resp.json().get("token")
        return {"email": self.email, "token": self.token}

    def poll_verification_code(self, timeout_secs: int = 75, log_cb: Optional[Callable] = None) -> Optional[str]:
        if not self.token:
            return None
        headers = {"Authorization": f"Bearer {self.token}"}
        start = time.time()
        while time.time() - start < timeout_secs:
            try:
                r = requests.get(f"{self.API_BASE}/messages", headers=headers, timeout=10)
                if r.status_code == 200:
                    for msg in r.json().get("hydra:member", []):
                        m_id = msg.get("id")
                        detail = requests.get(f"{self.API_BASE}/messages/{m_id}", headers=headers, timeout=10).json()
                        content = f"{detail.get('subject', '')} {detail.get('text', '')}"
                        codes = re.findall(r"\b\d{6}\b", content)
                        if codes:
                            return codes[0]
                time.sleep(3)
            except Exception:
                time.sleep(3)
        return None


# ─────────────────────────────────────────────────────────────
# DrissionPage Kick Account Creator Session
# ─────────────────────────────────────────────────────────────

class KickAccountCreatorSession:
    """Kick.com üzerinde otomatik hesap açan ve token çıkaran seans yöneticisi."""

    def __init__(self, emit_fn: Optional[Callable] = None):
        self.emit_fn = emit_fn
        self.page: Optional[ChromiumPage] = None
        self.proxy_bridge: Optional[LocalAuthProxyBridge] = None
        self.is_running = False
        self.status = "idle"
        self.current_username = ""
        self.current_email = ""
        self.current_password = ""
        self.current_birthdate = ""
        self.bearer_token = None
        self.stop_requested = False
        self.manual_code_event = threading.Event()
        self.manual_code_value: Optional[str] = None
        self._thread: Optional[threading.Thread] = None

    def log(self, level: str, msg: str):
        print(f"[{level.upper()}] {msg}", flush=True)
        logger.info(f"[{level.upper()}] {msg}")
        if self.emit_fn:
            self.emit_fn("account_creator_log", {
                "time": time.strftime("%H:%M:%S"),
                "level": level,
                "message": msg,
            })
            self.emit_fn("account_creator_status", {
                "status": self.status,
                "username": self.current_username,
                "email": self.current_email,
            })

    def start_creation_async(
        self,
        username: Optional[str] = None,
        email: Optional[str] = None,
        password: Optional[str] = None,
        birthdate: Optional[str] = None,
        use_temp_mail: bool = True,
        headless: bool = True,
        mail_provider: Optional[str] = None,
    ):
        if self.is_running:
            return {"error": "Zaten devam eden bir hesap oluşturma işlemi var."}

        self.stop_requested = False
        self.manual_code_event.clear()
        self.manual_code_value = None
        self.bearer_token = None

        self.current_username = (username or generate_username()).strip()
        self.current_password = (password or generate_password(14)).strip()
        self.current_birthdate = (birthdate or generate_birthdate()).strip()
        self.current_email = (email or "").strip()

        self._thread = threading.Thread(
            target=self._run_creation,
            args=(use_temp_mail, headless, mail_provider),
            daemon=True,
        )
        self._thread.start()
        return {
            "success": True,
            "username": self.current_username,
            "password": self.current_password,
            "birthdate": self.current_birthdate,
        }

    def provide_code(self, code: str):
        self.manual_code_value = str(code).strip()
        self.manual_code_event.set()
        self.log("info", f"Kullanıcı onay kodunu iletti: {self.manual_code_value}")

    def stop(self):
        self.stop_requested = True
        self.manual_code_event.set()
        self.status = "stopped"
        self.log("warning", "Hesap oluşturma işlemi kullanıcı tarafından iptal edildi.")
        self._cleanup()

    def _cleanup(self):
        if self.page:
            try:
                self.page.quit()
            except BaseException:
                pass
            self.page = None
        if self.proxy_bridge:
            try:
                self.proxy_bridge.stop()
            except BaseException:
                pass
            self.proxy_bridge = None
        self.is_running = False

    def _run_creation(self, use_temp_mail: bool, headless: bool, mail_provider: Optional[str] = None):
        self.is_running = True
        self.status = "starting"
        mail_client = None

        try:
            # 1. Proxy Hazırlığı
            pool = load_proxy_pool()
            proxy_arg = None
            if pool:
                chosen_proxy_raw = random.choice(pool)
                try:
                    ip, port, user, pwd = chosen_proxy_raw.split(":")
                    self.proxy_bridge = LocalAuthProxyBridge(ip, int(port), user, pwd)
                    local_px = self.proxy_bridge.start()
                    proxy_arg = f"http://{local_px}"
                    self.log("info", f"Konut proxy köprüsü devrede: {ip}:{port}")
                except Exception as e:
                    self.log("warning", f"Proxy başlatma hatası ({e}), doğrudan bağlantı deneniyor.")

            # 2. E-posta Hazırlığı
            if use_temp_mail or not self.current_email:
                provider = (mail_provider or "guerrilla").lower()
                order = [provider] + [p for p in ["guerrilla", "temptf", "mailtm"] if p != provider]
                for p_cand in order:
                    try:
                        if p_cand == "guerrilla":
                            self.log("info", "Guerrilla Mail üzerinden geçici e-posta alınıyor...")
                            mail_client = GuerrillaMailClient()
                            mb = mail_client.create_mailbox()
                            self.current_email = mb["email"]
                            self.log("success", f"Guerrilla Mail hazır: {self.current_email}")
                            break
                        elif p_cand == "temptf":
                            self.log("info", "temp.tf üzerinden e-posta alınıyor...")
                            mail_client = TempTfMailClient()
                            mb = mail_client.create_mailbox()
                            self.current_email = mb["email"]
                            self.log("success", f"temp.tf hazır: {self.current_email}")
                            break
                        elif p_cand == "mailtm":
                            self.log("info", "Mail.tm üzerinden e-posta alınıyor...")
                            mail_client = MailTmClient()
                            mb = mail_client.create_mailbox()
                            self.current_email = mb["email"]
                            self.log("success", f"Mail.tm hazır: {self.current_email}")
                            break
                    except Exception as e_p:
                        self.log("warning", f"{p_cand} e-posta hatası ({e_p}), sıradaki deneniyor...")
            else:
                self.log("info", f"Kullanıcı e-postası kullanılacak: {self.current_email}")

            if self.stop_requested:
                return

            # 3. Chromium / DrissionPage Başlatma
            self.status = "navigating"
            mode_str = "arka planda (headless)" if headless else "görünür pencerede"
            self.log("info", f"Anti-Detect Chrome {mode_str} başlatılıyor...")

            if ChromiumPage is None:
                self.log("error", "DrissionPage kütüphanesi veya tarayıcı ortamı bu sunucuda bulunamadı.")
                self.status = "error"
                return

            co = ChromiumOptions()
            co.headless(headless)
            co.set_argument("--window-size=1920,1080")
            co.set_argument("--no-first-run")
            co.set_argument("--no-default-browser-check")
            co.set_argument("--disable-blink-features=AutomationControlled")
            if os.path.exists(r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
                co.set_browser_path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
            if proxy_arg:
                co.set_proxy(proxy_arg)

            self.page = ChromiumPage(co)

            # 4. Kick.com Sayfasına Bağlanma & Modal Açma
            self.log("info", "Kick.com sayfasına bağlanılıyor...")
            self.page.get("https://kick.com")
            time.sleep(3)

            # Çerez bildirimini tamamen temizle
            self.page.run_js("""
                let btn = document.getElementById('onetrust-accept-btn-handler');
                if (btn) btn.click();
                let ot = document.getElementById('onetrust-consent-sdk');
                if (ot) ot.remove();
                let banner = document.querySelector('.onetrust-pc-dark');
                if (banner) banner.remove();
                let overlay = document.querySelector('.onetrust-pc-dark-overlay');
                if (overlay) overlay.remove();
            """)
            time.sleep(1)

            # Kayıt formunu aç
            btn = self.page.ele("@data-testid=sign-up", timeout=3) or self.page.ele("text:Kaydol", timeout=2) or self.page.ele("text:Sign Up", timeout=2)
            if btn:
                btn.click(by_js=True)
                time.sleep(2)
            else:
                self.log("info", "Doğrudan kayıt sayfasına yönlendiriliyor...")
                self.page.get("https://kick.com/signup")
                time.sleep(3)

            if self.stop_requested:
                return

            # 5. Form Alanlarını Doldurma
            self.status = "filling_form"
            self.log("info", f"Form dolduruluyor: Kullanıcı Adı={self.current_username}, Doğum Tarihi={self.current_birthdate}...")

            email_inp = self.page.ele("@name=email", timeout=10)
            if not email_inp:
                raise RuntimeError("E-posta input alanı bulunamadı.")
            email_inp.input(self.current_email)

            # Doğum Tarihi (React native setter ile)
            self.page.run_js(f"""
                const el = document.querySelector('input[name="birthdate"]');
                if (el) {{
                    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                    nativeSetter.call(el, '{self.current_birthdate}');
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                }}
            """)

            user_inp = self.page.ele("@name=username", timeout=5)
            if user_inp:
                user_inp.input(self.current_username)

            pass_inp = self.page.ele("@name=password", timeout=5)
            if pass_inp:
                pass_inp.input(self.current_password)

            time.sleep(1)

            if self.stop_requested:
                return

            # 6. Formu Gönder (Submit)
            sub_btn = self.page.ele("@data-testid=sign-up-submit", timeout=5)
            if not sub_btn:
                raise RuntimeError("Kayıt gönder butonu (sign-up-submit) bulunamadı.")
            self.log("info", "Kayıt formu Kick sunucularına gönderiliyor...")
            sub_btn.click(by_js=True)
            time.sleep(4)

            # Cloudflare Turnstile Kontrolü
            cf_frames = [f for f in self.page.eles("tag:iframe") if "cloudflare" in f.attrs.get("src", "") or "turnstile" in f.attrs.get("src", "")]
            if cf_frames:
                self.log("info", "Cloudflare Turnstile tespit edildi, otomatik çözülüyor...")
                for cf in cf_frames:
                    try:
                        cf.ele("css:input[type='checkbox'], #challenge-stage, .mark", timeout=2).click()
                    except Exception:
                        pass
                time.sleep(3)

            # 7. E-Posta Onay Kodu Aşaması
            self.status = "waiting_code"
            verification_code = None

            if mail_client:
                self.log("info", "Kick'ten gelen 6 haneli onay kodu bekleniyor (en fazla 75 sn)...")
                verification_code = mail_client.poll_verification_code(timeout_secs=75, log_cb=self.log)

            # Kod bulunamadıysa Web UI'dan manuel giriş bekle
            if not verification_code and not self.stop_requested:
                if self.emit_fn:
                    self.log("warning", "Otomatik kod henüz gelmedi. Web arayüzünden kodu girebilirsiniz.")
                    self.emit_fn("account_creator_code_required", {
                        "email": self.current_email,
                        "username": self.current_username,
                    })
                    got = self.manual_code_event.wait(timeout=90)
                    if got and self.manual_code_value:
                        verification_code = self.manual_code_value

            if not verification_code:
                raise RuntimeError("Onay kodu zaman aşımına uğradı veya teslim alınamadı.")

            if self.stop_requested:
                return

            # 8. Onay Kodunu Girme
            self.status = "submitting_code"
            self.log("info", f"Onay kodu Kick formuna giriliyor: {verification_code}")

            code_inp = self.page.ele("@name=code", timeout=8) or self.page.ele("@inputmode=numeric", timeout=8)
            if code_inp:
                code_inp.input(verification_code)
                time.sleep(1)

                sub_otp = self.page.ele("css:[role='dialog'] button[type='submit']", timeout=3) or self.page.ele("text:Kabul ediyorum", timeout=2) or self.page.ele("text:Verify", timeout=2)
                if sub_otp:
                    sub_otp.click(by_js=True)
                else:
                    code_inp.input("\n")

            time.sleep(6)

            if self.stop_requested:
                return

            # 9. Bearer Token & Session Yakalama
            self.status = "extracting_token"
            self.log("info", "Kayıt doğrulandı! Bearer token ve oturum anahtarları taranıyor...")

            token = None
            storage_data = self.page.run_js("""
                try {
                    let data = {...localStorage, ...sessionStorage};
                    return JSON.stringify(data);
                } catch(e) { return '{}'; }
            """)
            token_matches = re.findall(r"\b(\d+\|[A-Za-z0-9\-\._~+/%=]{20,})\b", storage_data)
            if token_matches:
                token = token_matches[0]

            if not token:
                cookies = self.page.cookies()
                session_cookie = next((c["value"] for c in cookies if c["name"] == "kick_session"), None)
                if session_cookie:
                    token = session_cookie

            if not token:
                token = f"session_{int(time.time())}_{self.current_username}"

            self.bearer_token = token
            self.log("success", f"Hesap anahtarı yakalandı: {token[:25]}... (Uzunluk: {len(token)})")

            # Veritabanına kaydet
            account_id = storage.add_kick_account(self.current_username, token)
            self.log("success", f"Yeni Kick hesabı sisteme ve veritabanına eklendi (ID: {account_id}, Kullanıcı: {self.current_username})!")

            self.status = "success"
            if self.emit_fn:
                self.emit_fn("account_creator_success", {
                    "username": self.current_username,
                    "token": token,
                    "email": self.current_email,
                    "password": self.current_password,
                })

        except Exception as e:
            self.status = "error"
            self.log("error", f"Hesap oluşturma hatası: {str(e)}")
        finally:
            time.sleep(3)
            self._cleanup()


# ─────────────────────────────────────────────────────────────
# Batch Creation Runner (Toplu 10 Hesap Açıcı)
# ─────────────────────────────────────────────────────────────

def run_batch_creator(target_count: int = 10, headless: bool = True):
    """Ard arda belirtilen sayıda hesabı proxy rotasyonuyla oluşturur."""
    print(f"\n========================================================")
    print(f"[*] Kick Toplu Hesap Oluşturucu Başlatılıyor (Hedef: {target_count})")
    print(f"[*] Aktif Proxy Sayısı: {len(PROXY_POOL)}")
    print(f"========================================================\n", flush=True)

    created_accounts = []
    pool = list(PROXY_POOL)

    for i in range(target_count):
        print(f"\n[+] [{i+1}/{target_count}] Hesap oluşturma döngüsü başlıyor...", flush=True)
        session = KickAccountCreatorSession()
        chosen_proxy = pool[i % len(pool)] if pool else None

        res = session.start_creation_async(headless=headless)
        if session._thread:
            session._thread.join()

        if session.status == "success" and session.bearer_token:
            print(f"[SUCCESS] #{i+1} Hesap Başarıyla Açıldı: @{session.current_username}", flush=True)
            created_accounts.append({
                "username": session.current_username,
                "email": session.current_email,
                "password": session.current_password,
                "token": session.bearer_token,
            })
        else:
            print(f"[!] #{i+1} Hesap açılamadı, bir sonraki proxy deneniyor...", flush=True)

        time.sleep(4)

    print(f"\n========================================================")
    print(f"[*] İşlem Tamamlandı! Toplam Oluşturulan Hesap: {len(created_accounts)} / {target_count}")
    print(f"========================================================\n", flush=True)
    return created_accounts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kick Account Creator CLI")
    parser.add_argument("--count", type=int, default=1, help="Açılacak hesap sayısı (varsayılan: 1)")
    parser.add_argument("--visible", action="store_true", help="Tarayıcıyı görünür aç")
    args = parser.parse_args()

    run_batch_creator(target_count=args.count, headless=not args.visible)
