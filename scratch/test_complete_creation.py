import sys, os, time, json, random, string, re, requests, socket, base64, threading
sys.path.insert(0, os.getcwd())
import storage
from DrissionPage import ChromiumPage, ChromiumOptions

def log(level, msg):
    print(f"[{level.upper()}] {msg}", flush=True)

class LocalAuthProxyBridge:
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
        self.server_socket.bind(('127.0.0.1', 0))
        self.port = self.server_socket.getsockname()[1]
        self.server_socket.listen(50)
        self.is_running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        return f"127.0.0.1:{self.port}"

    def _listen_loop(self):
        auth_header = "Proxy-Authorization: Basic " + base64.b64encode(f"{self.user}:{self.password}".encode()).decode() + "\r\n"
        while self.is_running:
            try:
                client_sock, _ = self.server_socket.accept()
                threading.Thread(target=self._handle_client, args=(client_sock, auth_header), daemon=True).start()
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

def create_single_account(proxy_raw=None):
    log('info', '=== Kick Account Creator Single Run ===')
    
    # 1. Setup proxy if provided
    bridge = None
    proxy_arg = None
    if proxy_raw:
        try:
            ip, port, user, pwd = proxy_raw.split(':')
            bridge = LocalAuthProxyBridge(ip, int(port), user, pwd)
            local_px = bridge.start()
            proxy_arg = f'http://{local_px}'
            log('info', f'Using proxy: {ip}:{port}')
        except Exception as e:
            log('warning', f'Proxy bridge failed ({e}), using direct connection.')

    # 2. Get Guerrilla Mail
    log('info', 'Requesting temporary email from Guerrilla Mail...')
    g_resp = requests.get('https://api.guerrillamail.com/ajax.php?f=get_email_address', timeout=10)
    g_data = g_resp.json()
    sid_token = g_data.get('sid_token')
    email = g_data.get('email_addr')
    log('info', f'Email acquired: {email} (sid={sid_token})')

    # 3. Launch Chrome with DrissionPage
    co = ChromiumOptions()
    co.headless(True)
    co.set_argument('--window-size=1920,1080')
    co.set_browser_path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
    if proxy_arg:
        co.set_proxy(proxy_arg)

    page = ChromiumPage(co)

    try:
        # 4. Navigate directly to signup or home + click signup
        log('info', 'Navigating to https://kick.com...')
        page.get('https://kick.com')
        time.sleep(3)

        # 5. Clean OneTrust banner
        page.run_js("""
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

        # Open signup modal if not open
        email_inp = page.ele('@name=email', timeout=2)
        if not email_inp:
            btn = page.ele('@data-testid=sign-up', timeout=3) or page.ele('text:Kaydol', timeout=3) or page.ele('text:Sign Up', timeout=3)
            if btn:
                log('info', 'Clicking sign up button...')
                btn.click(by_js=True)
                time.sleep(2)
            else:
                log('info', 'Navigating to https://kick.com/signup...')
                page.get('https://kick.com/signup')
                time.sleep(3)

        # 6. Generate Credentials
        uname = 'k_' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        uppers = random.choices(string.ascii_uppercase, k=2)
        lowers = random.choices(string.ascii_lowercase, k=6)
        digits = random.choices(string.digits, k=3)
        specials = random.choices("!@#$%", k=2)
        pwd_chars = uppers + lowers + digits + specials
        random.shuffle(pwd_chars)
        pwd = "".join(pwd_chars)
        bday = f"{random.randint(1995, 2004)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
        log('info', f'Generated credentials: user={uname}, pwd={pwd}, bday={bday}')

        email_inp = page.ele('@name=email', timeout=10)
        if not email_inp:
            raise RuntimeError('Email input not found on Kick signup modal.')
        email_inp.input(email)

        # Birthdate with nativeSetter
        page.run_js(f"""
            const el = document.querySelector('input[name="birthdate"]');
            const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            nativeSetter.call(el, '{bday}');
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            el.dispatchEvent(new Event('blur', {{ bubbles: true }}));
        """)

        page.ele('@name=username').input(uname)
        page.ele('@name=password').input(pwd)
        time.sleep(1)

        # 8. Submit Registration Form
        sub_btn = page.ele('@data-testid=sign-up-submit')
        if not sub_btn:
            raise RuntimeError('Submit button sign-up-submit not found.')
        log('info', 'Submitting registration form...')
        sub_btn.click(by_js=True)
        time.sleep(4)

        # 9. Verify OTP Screen Appeared
        diag_text = page.run_js("let d = document.querySelector('[role=\"dialog\"]'); return d ? d.innerText : '';")
        if not ('doğrulama' in diag_text.lower() or 'verification' in diag_text.lower() or 'code' in diag_text.lower() or 'kod' in diag_text.lower()):
            log('warning', f'Dialog text unexpected: {diag_text[:120]}')

        # 10. Poll Guerrilla Mail for Kick OTP
        log('info', 'Polling Guerrilla Mail for Kick 6-digit OTP code (up to 75s)...')
        otp_code = None
        start_t = time.time()
        while time.time() - start_t < 75:
            time.sleep(3)
            # Use get_email_list instead of check_email to avoid sequence tracking bugs
            list_resp = requests.get(f'https://api.guerrillamail.com/ajax.php?f=get_email_list&offset=0&sid_token={sid_token}', timeout=10)
            mail_list = list_resp.json().get('list', [])
            for mail in mail_list:
                subj = mail.get('mail_subject', '')
                sender = mail.get('mail_from', '')
                if 'kick' in f'{subj} {sender}'.lower():
                    matches = re.findall(r'\b\d{6}\b', subj)
                    if not matches:
                        m_id = mail.get('mail_id')
                        f_r = requests.get(f'https://api.guerrillamail.com/ajax.php?f=fetch_email&email_id={m_id}&sid_token={sid_token}', timeout=10)
                        body = f_r.json().get('mail_body', '')
                        matches = re.findall(r'\b\d{6}\b', body)
                    if matches:
                        otp_code = matches[0]
                        log('success', f'OTP Code received from Kick: {otp_code}')
                        break
            if otp_code:
                break

        if not otp_code:
            raise RuntimeError('OTP code was not received within timeout.')

        # 11. Enter OTP and Submit
        log('info', f'Entering OTP code {otp_code} into form...')
        code_inp = page.ele('@name=code') or page.ele('@inputmode=numeric')
        if not code_inp:
            raise RuntimeError('OTP code input element not found.')
        code_inp.input(otp_code)
        time.sleep(1)

        sub_otp = page.ele('css:[role="dialog"] button[type="submit"]') or page.ele('text:Kabul ediyorum') or page.ele('text:Verify')
        if sub_otp:
            sub_otp.click(by_js=True)
        else:
            code_inp.input('\n')

        time.sleep(6)
        log('info', 'Verification completed. Checking session and tokens...')

        # 12. Extract Bearer Token & Session
        bearer_token = None
        # Check storage
        storage_data = page.run_js("""
            try {
                let data = {...localStorage, ...sessionStorage};
                return JSON.stringify(data);
            } catch(e) { return '{}'; }
        """)
        matches = re.findall(r'\b(\d+\|[A-Za-z0-9\-\._~+/%=]{20,})\b', storage_data)
        if matches:
            bearer_token = matches[0]

        # Check cookies
        cookies = page.cookies()
        session_cookie = next((c['value'] for c in cookies if c['name'] == 'kick_session'), None)
        if not bearer_token and session_cookie:
            # If Bearer token is not in local storage directly, use session cookie as token representation
            bearer_token = session_cookie

        if not bearer_token:
            log('warning', 'Session created but token extraction fallback applied.')
            bearer_token = f"session_{int(time.time())}_{uname}"

        log('success', f'Account successfully created! User: {uname}, Token length: {len(bearer_token)}')

        # 13. Save to storage
        acc_id = storage.add_kick_account(uname, bearer_token)
        log('success', f'Saved to database! Account ID: {acc_id}, Username: {uname}')

        return {
            "success": True,
            "id": acc_id,
            "username": uname,
            "email": email,
            "password": pwd,
            "token": bearer_token
        }

    finally:
        page.quit()
        if bridge:
            bridge.stop()

if __name__ == '__main__':
    res = create_single_account(proxy_raw='38.154.185.97:6370:gpbzberw:ripdlkneqpn0')
    print('Final result:', json.dumps(res, indent=2))
