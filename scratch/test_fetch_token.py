import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import socket, base64, threading

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

from DrissionPage import ChromiumPage, ChromiumOptions
import time, requests, re, json, random, string

def log(msg):
    print(msg, flush=True)

# 1. Guerrilla Mail
g_resp = requests.get('https://api.guerrillamail.com/ajax.php?f=get_email_address', timeout=10)
g_data = g_resp.json()
sid_token = g_data.get('sid_token')
email = g_data.get('email_addr')
log(f'Email: {email}')

# Use proxy #2: 45.38.107.97:6014:gpbzberw:ripdlkneqpn0
bridge = LocalAuthProxyBridge('45.38.107.97', 6014, 'gpbzberw', 'ripdlkneqpn0')
local_px = bridge.start()
log(f'Proxy bridge on {local_px}')

co = ChromiumOptions()
co.headless(True)
co.set_browser_path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
co.set_proxy(f'http://{local_px}')

page = ChromiumPage(co)

try:
    page.get('https://kick.com')
    time.sleep(3)

    # Clean OneTrust
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

    btn = page.ele('text:Kaydol') or page.ele('text:Sign Up') or page.ele('@data-testid=sign-up')
    btn.click(by_js=True)
    time.sleep(2)

    uname = 'k_' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=7))
    pwd = 'TestPassword99!@#'

    log(f'Filling registration: user={uname}, email={email}')
    page.ele('@name=email').input(email)
    page.run_js("""
        const el = document.querySelector('input[name="birthdate"]');
        const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        nativeSetter.call(el, '1998-09-12');
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        el.dispatchEvent(new Event('blur', { bubbles: true }));
    """)
    page.ele('@name=username').input(uname)
    page.ele('@name=password').input(pwd)
    time.sleep(1)

    sub_btn = page.ele('@data-testid=sign-up-submit')
    sub_btn.click(by_js=True)
    log('Submitted registration form, waiting for OTP...')

    # Poll Guerrilla Mail
    otp_code = None
    for attempt in range(18):
        time.sleep(3)
        check_r = requests.get(f'https://api.guerrillamail.com/ajax.php?f=check_email&seq=0&sid_token={sid_token}', timeout=10)
        mail_list = check_r.json().get('list', [])
        for mail in mail_list:
            subj = mail.get('mail_subject', '')
            if 'kick' in subj.lower():
                matches = re.findall(r'\b\d{6}\b', subj)
                if not matches:
                    mail_id = mail.get('mail_id')
                    f_resp = requests.get(f'https://api.guerrillamail.com/ajax.php?f=fetch_email&email_id={mail_id}&sid_token={sid_token}', timeout=10)
                    body = f_resp.json().get('mail_body', '')
                    matches = re.findall(r'\b\d{6}\b', body)
                if matches:
                    otp_code = matches[0]
                    log(f'SUCCESS: OTP Code received: {otp_code}')
                    break
        if otp_code:
            break

    if not otp_code:
        log('OTP timeout')
        exit(1)

    # Enter OTP
    code_inp = page.ele('@name=code') or page.ele('@inputmode=numeric')
    code_inp.input(otp_code)
    time.sleep(1)

    sub_otp = page.ele('css:[role="dialog"] button[type="submit"]') or page.ele('text:Kabul ediyorum') or page.ele('text:Verify')
    if sub_otp:
        sub_otp.click(by_js=True)
    else:
        code_inp.input('\n')

    time.sleep(6)
    log('Registration verified! Testing internal API fetch from browser context...')

    # Run browser JS fetch to inspect auth state / user token
    api_test = page.run_js("""
        async function checkAuth() {
            let userResp = await fetch('/api/v1/user').then(r => r.json()).catch(e => ({ error: e.toString() }));
            let tokenResp = await fetch('/api/internal/auth/token').then(r => r.json()).catch(e => ({ error: e.toString() }));
            return { userResp, tokenResp };
        }
        return checkAuth();
    """)
    log('API responses:\n' + json.dumps(api_test, indent=2))

    # Also let's inspect window object for any Kick auth tokens
    win_auth = page.run_js("""
        let found = {};
        for (let k in window) {
            if (typeof window[k] === 'string' && (window[k].includes('|') || window[k].includes('Bearer'))) {
                found[k] = window[k];
            }
        }
        // Check Next.js / React query state
        if (window.__NEXT_DATA__) {
            found['next_data'] = JSON.stringify(window.__NEXT_DATA__).slice(0, 500);
        }
        return found;
    """)
    log('Window auth:\n' + json.dumps(win_auth, indent=2))

    # Check cookies
    cookies = page.cookies()
    log('Cookies:\n' + json.dumps(cookies, indent=2))

finally:
    page.quit()
    bridge.stop()
    log('Done!')
