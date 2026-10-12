"""
kick_creator.py — Automated Kick.com Account Generator
Uses DrissionPage (headless Chromium) to bypass Cloudflare & Kasada,
mail.tm for instant verification codes, and Kick's official web API
to register accounts and retrieve 1-year Bearer tokens.

NO SMS/phone verification required!
NO 2captcha required!
"""
import asyncio
import json
import logging
import os
import random
import re
import shutil
import string
import tempfile
import time
import urllib.parse
from typing import Optional, Callable, Awaitable

from DrissionPage import ChromiumPage, ChromiumOptions

from mailtm import create_mailTm_account, MailTmAccount

logger = logging.getLogger("KickCreator")


def _make_proxy_extension(proxy_url: str) -> Optional[str]:
    """
    Creates a temporary unpacked Chrome extension that handles proxy authentication.
    DrissionPage's set_proxy() does NOT support user:pass auth, so we use an extension instead.
    
    proxy_url formats supported:
      - "host:port:user:pass"
      - "http://user:pass@host:port"
    
    Returns: path to extension dir (caller must shutil.rmtree it) or None on failure.
    """
    try:
        if proxy_url.startswith("http://") or proxy_url.startswith("https://"):
            p = urllib.parse.urlparse(proxy_url)
            host = p.hostname or ""
            port = p.port or 80
            user = urllib.parse.unquote(p.username or "")
            password = urllib.parse.unquote(p.password or "")
        else:
            parts = proxy_url.split(":")
            if len(parts) < 4:
                return None
            host, port, user, password = parts[0], int(parts[1]), parts[2], parts[3]

        # Escape for JS strings
        def _js_esc(s: str) -> str:
            return s.replace("\\", "\\\\").replace('"', '\\"').replace("'", "\\'")

        host_e = _js_esc(str(host))
        user_e = _js_esc(str(user))
        pass_e = _js_esc(str(password))

        manifest = json.dumps({
            "version": "1.0.0",
            "manifest_version": 2,
            "name": "Proxy Auth",
            "permissions": [
                "proxy", "tabs", "unlimitedStorage", "storage",
                "<all_urls>", "webRequest", "webRequestBlocking"
            ],
            "background": {"scripts": ["bg.js"]},
            "minimum_chrome_version": "22.0.0"
        })

        bg_js = (
            f'var config = {{'
            f'  mode: "fixed_servers",'
            f'  rules: {{'
            f'    singleProxy: {{ scheme: "http", host: "{host_e}", port: {int(port)} }},'
            f'    bypassList: ["localhost", "127.0.0.1"]'
            f'  }}'
            f'}};\n'
            f'chrome.proxy.settings.set({{value: config, scope: "regular"}}, function() {{}});\n'
            f'chrome.webRequest.onAuthRequired.addListener(\n'
            f'  function() {{ return {{ authCredentials: {{ username: "{user_e}", password: "{pass_e}" }} }}; }},\n'
            f'  {{ urls: ["<all_urls>"] }},\n'
            f'  ["blocking"]\n'
            f');\n'
        )

        ext_dir = tempfile.mkdtemp(prefix="kc_proxy_ext_")
        with open(os.path.join(ext_dir, "manifest.json"), "w", encoding="utf-8") as f:
            f.write(manifest)
        with open(os.path.join(ext_dir, "bg.js"), "w", encoding="utf-8") as f:
            f.write(bg_js)

        logger.debug(f"[ProxyExt] Created extension at {ext_dir} for {host}:{port}")
        return ext_dir

    except Exception as e:
        logger.warning(f"[ProxyExt] Failed to create proxy extension: {e}")
        return None


def _rand_username(n: int = 8) -> str:
    prefix = random.choice(["kc", "live", "pro", "xd", "fast", "cool", "top"])
    return prefix + "".join(random.choices(string.ascii_lowercase + string.digits, k=n))

def _rand_password(n: int = 12) -> str:
    return "P@ss" + "".join(random.choices(string.ascii_letters + string.digits, k=n)) + "!"

def _rand_birthdate() -> str:
    year = random.randint(1990, 2004)
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    return f"{year}-{month:02d}-{day:02d}"


class CreationResult:
    def __init__(self):
        self.success: bool = False
        self.username: str = ""
        self.email: str = ""
        self.password: str = ""
        self.token: str = ""
        self.error: str = ""

    def __repr__(self):
        return f"<CreationResult success={self.success} username={self.username} token={self.token[:15]}... error={self.error}>"


def _create_one_account_sync(
    proxy_url: Optional[str] = None,
    progress_fn: Optional[Callable[[str], None]] = None,
) -> CreationResult:
    """Synchronous worker that runs DrissionPage headless browser."""
    res = CreationResult()

    def _log(msg: str):
        logger.info(f"[Creator] {msg}")
        if progress_fn:
            try:
                progress_fn(msg)
            except Exception:
                pass

    # 1. Generate temp mail
    _log("📧 Creating temporary email address...")
    mail = asyncio.run(create_mailTm_account())
    if not mail:
        res.error = "Failed to create email (mail.tm service unavailable)"
        return res

    email = mail.address
    username = _rand_username(7)
    password = _rand_password(10)
    birthdate = _rand_birthdate()

    res.email = email
    res.username = username
    res.password = password
    _log(f"📧 Email: `{email}` | Username: `{username}`")

    # 2. Setup headless Chromium options
    co = ChromiumOptions()
    co.set_browser_path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
    co.headless(True)
    co.set_argument('--no-first-run')
    co.set_argument('--disable-blink-features=AutomationControlled')
    if proxy_url:
        co.set_proxy(proxy_url)

    page = None
    try:
        _log("🌐 Initializing browser session & warming up security checks...")
        page = ChromiumPage(co)
        page.get('https://kick.com', retry=2, timeout=20)
        time.sleep(2.5)

        # 3. Request verification code via Kick API
        _log("📨 Sending email verification code via Kick API...")
        send_res = page.run_js(f"""
            return fetch('https://web.kick.com/api/v1/user/identity/send-verification-code', {{
                method: 'POST',
                headers: {{
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                    'x-app-platform': 'web'
                }},
                body: JSON.stringify({{
                    email: '{email}'
                }})
            }}).then(async r => ({{ status: r.status, text: await r.text() }}))
               .catch(e => ({{ error: e.toString() }}));
        """)

        status = send_res.get('status') if isinstance(send_res, dict) else None
        if status not in (200, 201, 204):
            err_text = str(send_res.get('text', ''))[:100] if isinstance(send_res, dict) else str(send_res)
            res.error = f"Failed to send verification code ({status}): {err_text}"
            return res

        # 4. Wait for code from mail.tm
        _log("⏳ Waiting for 6-digit verification code from email...")
        msg = asyncio.run(mail.wait_for_mail(timeout=45))
        if not msg:
            res.error = "Verification email did not arrive in 45s"
            return res

        subject = str(msg.get('subject', ''))
        code_match = re.search(r'\b(\d{6})\b', subject)
        if not code_match:
            body = str(msg.get('text', '')) or str(msg.get('html', ''))
            code_match = re.search(r'\b(\d{6})\b', body)

        if not code_match:
            res.error = "Could not extract 6-digit code from email"
            return res

        code = code_match.group(1)
        _log(f"🎯 Extracted verification code: `{code}`")

        # 5. Register account via Kick API
        _log("🚀 Registering account and generating Bearer token...")
        reg_payload = {
            'email': email,
            'username': username,
            'password': password,
            'date_of_birth': birthdate,
            'terms_of_service_consent': True,
            'marketing_emails_consent': False,
            'verification_code': code,
        }

        reg_res = page.run_js(f"""
            return fetch('https://web.kick.com/api/v1/user/identity/register', {{
                method: 'POST',
                headers: {{
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                    'x-app-platform': 'web'
                }},
                body: JSON.stringify({json.dumps(reg_payload)})
            }}).then(async r => ({{ status: r.status, text: await r.text() }}))
               .catch(e => ({{ error: e.toString() }}));
        """)

        reg_status = reg_res.get('status') if isinstance(reg_res, dict) else None
        reg_text = reg_res.get('text', '') if isinstance(reg_res, dict) else ''

        if reg_status not in (200, 201):
            res.error = f"Registration API rejected ({reg_status}): {reg_text[:120]}"
            return res

        token = None
        try:
            data = json.loads(reg_text)
            token = (
                data.get('data', {}).get('access_token')
                or data.get('access_token')
                or data.get('token')
            )
        except Exception:
            pass

        if not token:
            res.error = f"No access token found in response: {reg_text[:100]}"
            return res

        res.token = token
        res.success = True
        _log(f"🎉 Account created! Token: `{token[:22]}...`")

    except Exception as e:
        res.error = f"Automation error: {str(e)}"
    finally:
        if page:
            try:
                page.quit()
            except Exception:
                pass

    return res


async def create_one_account(
    proxy_url: Optional[str] = None,
    progress_cb: Optional[Callable[[str], Awaitable[None]]] = None,
) -> CreationResult:
    """
    Async interface to create a single Kick account.
    Runs headless Chromium worker in a background thread to avoid blocking asyncio event loop.
    """
    loop = asyncio.get_running_loop()

    def sync_progress(msg: str):
        if progress_cb:
            asyncio.run_coroutine_threadsafe(progress_cb(msg), loop)

    return await asyncio.to_thread(_create_one_account_sync, proxy_url, sync_progress)
