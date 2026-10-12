from DrissionPage import ChromiumPage, ChromiumOptions
import time, json, requests, re

def log(msg):
    print(msg, flush=True)

log('=== INSPECTING OTP VERIFICATION NETWORK RESPONSE ===')

# Get Guerrilla email
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

    uname = 'usr_' + str(int(time.time()))[-7:]
    pwd = 'SecurePassword99!@'

    page.ele('@name=email').input(email)
    page.run_js("""
        const el = document.querySelector('input[name="birthdate"]');
        const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        nativeSetter.call(el, '2000-01-01');
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

    # Poll Guerrilla Mail for OTP
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
        log('OTP timeout')
        exit(1)

    # Start listening to all network traffic
    page.listen.start()

    code_inp = page.ele('@name=code') or page.ele('@inputmode=numeric')
    code_inp.input(otp_code)
    time.sleep(1)

    # Click verify/submit
    sub_otp = page.ele('css:[role="dialog"] button[type="submit"]') or page.ele('text:Kabul ediyorum') or page.ele('text:Verify')
    if sub_otp:
        sub_otp.click(by_js=True)
    else:
        code_inp.input('\n')

    time.sleep(6)

    # Look through captured packets
    log('Analyzing captured packets after OTP submit...')
    found_tokens = []
    for i in range(30):
        packet = page.listen.wait(timeout=0.5)
        if not packet:
            continue
        url = packet.url
        # Check request headers
        req_auth = (packet.request.headers or {}).get('Authorization') or (packet.request.headers or {}).get('authorization')
        if req_auth:
            log(f'REQ AUTH in {url}: {req_auth}')
            found_tokens.append(req_auth)
        # Check response body
        try:
            body = packet.response.body
            if body and isinstance(body, str) and any(k in body.lower() for k in ['token', 'bearer', '|']):
                log(f'RESP BODY in {url}:\n{body[:400]}')
                # Find pipes
                pipes = re.findall(r'\b\d+\|[A-Za-z0-9\-\._~+/%=]{20,}\b', body)
                if pipes:
                    log(f'FOUND SANCTUM TOKEN: {pipes}')
                    found_tokens.extend(pipes)
        except Exception:
            pass

    log(f'Total tokens captured: {found_tokens}')

finally:
    page.quit()
    log('Done!')
