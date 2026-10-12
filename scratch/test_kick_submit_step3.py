from DrissionPage import ChromiumPage, ChromiumOptions
import time, json, requests, re, sys

def log(msg):
    print(msg, flush=True)

log('=== TESTING SIGNUP SUBMIT WITH CLEAN MODAL V3 ===')

# 1. Fresh email from temp.tf
mail_resp = requests.get('https://temp.tf/api/account', params={'providers': 'outlook,hotmail,gmail', 'dot': '1', 'plus': '0'}, timeout=10)
email = mail_resp.json().get('email')
log(f'Email from temp.tf: {email}')

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

    log(f'Filling fields: {email}, {uname}')
    page.ele('@name=email').input(email)
    page.run_js("""
        const el = document.querySelector('input[name="birthdate"]');
        el.value = '1999-08-20';
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
    """)
    page.ele('@name=username').input(uname)
    page.ele('@name=password').input(pwd)
    time.sleep(1)

    sub_btn = page.ele('@data-testid=sign-up-submit')
    log(f'Clicking sign-up-submit: {sub_btn.text if sub_btn else "None"}')
    sub_btn.click(by_js=True)
    time.sleep(5)

    # Check dialog text now
    res_dialog = page.run_js("""
        const d = document.querySelector('[role="dialog"]');
        if (!d) return { hasDialog: false };
        return {
            text: d.innerText,
            inputs: Array.from(d.querySelectorAll('input')).map(i => ({
                name: i.name,
                placeholder: i.placeholder,
                inputmode: i.getAttribute('inputmode'),
                value: i.value,
                type: i.type
            })),
            iframes: Array.from(document.querySelectorAll('iframe')).map(f => f.src)
        };
    """)
    log('Dialog after submit:\n' + json.dumps(res_dialog, indent=2))

    # Check temp.tf for mail
    log('Polling temp.tf for Kick verification email (45s)...')
    for attempt in range(15):
        time.sleep(3)
        check_r = requests.post('https://temp.tf/api/check', json={'email': email, 'wait': False}, timeout=10)
        items = check_r.json().get('data', [])
        for item in items:
            subj = item.get('subject', '')
            sender = item.get('from', '')
            log(f'Attempt {attempt+1}: message from {sender} - "{subj}"')
            if any(k in f'{subj} {sender}'.lower() for k in ['kick', 'verify', 'kod', 'onay']):
                log('SUCCESS! KICK EMAIL RECEIVED!')
                body = item.get('body') or item.get('text') or ''
                codes = re.findall(r'\\b\\d{6}\\b', f'{subj} {body}')
                log(f'Verification code: {codes}')
                break
        else:
            continue
        break

finally:
    page.quit()
    log('Done!')
