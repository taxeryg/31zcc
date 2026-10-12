from DrissionPage import ChromiumPage, ChromiumOptions
import time, json, requests, re

def log(msg):
    print(msg, flush=True)

log('=== FULL KICK REGISTRATION + OTP + TOKEN EXTRACTION TEST ===')

# 1. Guerrilla Mail
g_resp = requests.get('https://api.guerrillamail.com/ajax.php?f=get_email_address', timeout=10)
g_data = g_resp.json()
sid_token = g_data.get('sid_token')
email = g_data.get('email_addr')
log(f'Guerrilla email: {email} (sid={sid_token})')

co = ChromiumOptions()
co.headless(True)
co.set_browser_path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
page = ChromiumPage(co)

try:
    log('Opening kick.com...')
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

    # Click Kaydol
    btn = page.ele('text:Kaydol') or page.ele('@data-testid=sign-up')
    btn.click(by_js=True)
    time.sleep(2)

    uname = 'nex_' + str(int(time.time()))[-6:]
    pwd = 'SecurePassword99!@'

    log(f'Filling fields: {email}, user={uname}')
    page.ele('@name=email').input(email)
    
    # Fill birthdate with nativeSetter
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
    log('Clicking sign-up-submit...')
    sub_btn.click(by_js=True)
    time.sleep(4)

    # Poll Guerrilla Mail for Kick verification code
    log('Polling Guerrilla Mail for Kick OTP code...')
    otp_code = None
    for attempt in range(15):
        time.sleep(3)
        check_r = requests.get(f'https://api.guerrillamail.com/ajax.php?f=check_email&seq=0&sid_token={sid_token}', timeout=10)
        mail_list = check_r.json().get('list', [])
        for mail in mail_list:
            subj = mail.get('mail_subject', '')
            sender = mail.get('mail_from', '')
            log(f'Attempt {attempt+1}: message from {sender} - "{subj}"')
            if 'kick' in f'{subj} {sender}'.lower():
                matches = re.findall(r'\b\d{6}\b', subj)
                if not matches:
                    mail_id = mail.get('mail_id')
                    f_resp = requests.get(f'https://api.guerrillamail.com/ajax.php?f=fetch_email&email_id={mail_id}&sid_token={sid_token}', timeout=10)
                    body = f_resp.json().get('mail_body', '')
                    matches = re.findall(r'\b\d{6}\b', body)
                if matches:
                    otp_code = matches[0]
                    log(f'FOUND KICK OTP CODE: {otp_code}')
                    break
        if otp_code:
            break

    if not otp_code:
        log('OTP code NOT received within timeout!')
    else:
        log(f'Entering OTP code into Kick form: {otp_code}')
        # Check code input in dialog
        code_inp = page.ele('@name=code') or page.ele('@inputmode=numeric')
        if code_inp:
            log('Found code input, typing OTP...')
            code_inp.clear()
            code_inp.input(otp_code)
            time.sleep(1)

            # Check if there is a verify / submit button or automatic submission
            sub_otp = page.ele('css:[role="dialog"] button[type="submit"]') or page.ele('text:Doğrula') or page.ele('text:Verify')
            if sub_otp:
                log(f'Clicking OTP submit button: {sub_otp.text}')
                sub_otp.click(by_js=True)
            else:
                log('No OTP button found, sending Enter key...')
                code_inp.input('\n')

            time.sleep(6)

            # Check page status after entering code
            log(f'Current URL: {page.url}')
            
            # Check local storage & cookies for Bearer token
            tokens = page.run_js("""
                let results = {};
                for (let k in localStorage) {
                    let v = localStorage.getItem(k);
                    if (v && (v.includes('|') || v.includes('Bearer') || k.includes('token') || k.includes('auth'))) {
                        results[k] = v;
                    }
                }
                for (let k in sessionStorage) {
                    let v = sessionStorage.getItem(k);
                    if (v && (v.includes('|') || v.includes('Bearer') || k.includes('token') || k.includes('auth'))) {
                        results['session_' + k] = v;
                    }
                }
                return results;
            """)
            log('Tokens found in storage:\n' + json.dumps(tokens, indent=2))

            cookies = page.cookies()
            kick_cookies = [c for c in cookies if 'kick' in c.get('name', '').lower() or 'token' in c.get('name', '').lower() or 'session' in c.get('name', '').lower()]
            log('Cookies found:\n' + json.dumps(kick_cookies, indent=2))

finally:
    page.quit()
    log('Done!')
