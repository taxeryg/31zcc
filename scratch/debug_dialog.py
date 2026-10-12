from DrissionPage import ChromiumPage, ChromiumOptions
import time, json, requests, re, random, string

def log(msg):
    print(msg, flush=True)

g_resp = requests.get('https://api.guerrillamail.com/ajax.php?f=get_email_address', timeout=10)
g_data = g_resp.json()
sid_token = g_data.get('sid_token')
email = g_data.get('email_addr')
log(f'Email: {email}')

co = ChromiumOptions()
co.headless(True)
co.set_browser_path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
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

    btn = page.ele('text:Kaydol') or page.ele('@data-testid=sign-up')
    btn.click(by_js=True)
    time.sleep(2)

    # Unique random username
    uname = 'usr_' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    pwd = 'StrongPass99!@#'

    log(f'Filling: email={email}, user={uname}')
    page.ele('@name=email').input(email)
    page.run_js("""
        const el = document.querySelector('input[name="birthdate"]');
        const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        nativeSetter.call(el, '2000-03-14');
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        el.dispatchEvent(new Event('blur', { bubbles: true }));
    """)
    page.ele('@name=username').input(uname)
    page.ele('@name=password').input(pwd)
    time.sleep(1)

    sub_btn = page.ele('@data-testid=sign-up-submit')
    sub_btn.click(by_js=True)
    time.sleep(4)

    # Check dialog content
    diag = page.run_js("""
        const d = document.querySelector('[role="dialog"]');
        return d ? d.innerText : 'NO DIALOG';
    """)
    log('Dialog after submit:\n' + diag)

    # Check for Cloudflare Turnstile iframes
    cf = [f.attrs.get('src', '') for f in page.eles('tag:iframe') if 'cloudflare' in f.attrs.get('src', '') or 'turnstile' in f.attrs.get('src', '') or 'challenges' in f.attrs.get('src', '')]
    log(f'Turnstile iframes: {cf}')

finally:
    page.quit()
