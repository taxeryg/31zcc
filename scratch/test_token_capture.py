from DrissionPage import ChromiumPage, ChromiumOptions
import time, json, requests, re

def log(msg):
    print(msg, flush=True)

# Test token extraction from an active session
# Let's run a test where after submitting OTP, we listen to network requests while visiting a channel
log('=== TESTING BEARER TOKEN EXTRACTION ===')

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

    uname = 'nex_' + str(int(time.time()))[-6:]
    pwd = 'SecurePassword99!@'

    page.ele('@name=email').input(email)
    page.run_js("""
        const el = document.querySelector('input[name="birthdate"]');
        const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        nativeSetter.call(el, '1999-05-15');
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

    # Poll Guerrilla Mail
    otp_code = None
    for attempt in range(15):
        time.sleep(3)
        check_r = requests.get(f'https://api.guerrillamail.com/ajax.php?f=check_email&seq=0&sid_token={sid_token}', timeout=10)
        mail_list = check_r.json().get('list', [])
        for mail in mail_list:
            subj = mail.get('mail_subject', '')
            if 'kick' in subj.lower():
                matches = re.findall(r'\b\d{6}\b', subj)
                if matches:
                    otp_code = matches[0]
                    log(f'OTP Code: {otp_code}')
                    break
        if otp_code:
            break

    if not otp_code:
        log('Failed to get OTP')
        exit(1)

    # Enter OTP
    code_inp = page.ele('@name=code') or page.ele('@inputmode=numeric')
    code_inp.clear()
    code_inp.input(otp_code)
    time.sleep(1)

    # Start listening to network requests right before completing registration
    page.listen.start('kick.com/api')

    sub_otp = page.ele('css:[role="dialog"] button[type="submit"]') or page.ele('text:Kabul ediyorum') or page.ele('text:Verify')
    if sub_otp:
        sub_otp.click(by_js=True)
    else:
        code_inp.input('\n')

    time.sleep(5)

    # Visit a channel or profile to trigger API calls
    log('Navigating to a channel to trigger API calls...')
    page.get('https://kick.com/sozcutv')
    time.sleep(5)

    # Check packets
    captured_token = None
    for i in range(25):
        packet = page.listen.wait(timeout=1)
        if not packet:
            continue
        req_headers = packet.request.headers or {}
        auth = req_headers.get('Authorization') or req_headers.get('authorization')
        if auth and 'Bearer ' in auth:
            captured_token = auth.split('Bearer ')[1].strip()
            log(f'FOUND BEARER TOKEN IN API REQUEST: {captured_token}')
            break
        # Also check response body for token
        try:
            body = packet.response.body
            if body and isinstance(body, str):
                m = re.findall(r'(\d+\|[A-Za-z0-9\-\._~+/%=]{20,})', body)
                if m:
                    captured_token = m[0]
                    log(f'FOUND TOKEN IN RESPONSE BODY: {captured_token}')
                    break
        except Exception:
            pass

    log(f'RESULT: username={uname}, email={email}, token={captured_token}')

finally:
    page.quit()
    log('Done!')
