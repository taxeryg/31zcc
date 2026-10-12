from DrissionPage import ChromiumPage, ChromiumOptions
import time, json, requests, re

def log(msg):
    print(msg, flush=True)

log('=== TESTING KICK REGISTRATION WITH HOTMAIL+ ADDRESS ===')

# Get hotmail from temp.tf
r = requests.get('https://temp.tf/api/account', params={'providers': 'hotmail', 'dot': '0', 'plus': '1'}, timeout=10)
email = r.json().get('email')
log(f'Email from temp.tf: {email} (len={len(email)})')

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
    email_inp = page.ele('@name=email')
    email_inp.input(email)
    
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

    # Check if email input has any validation error
    val_check = page.run_js("""
        const em = document.querySelector('input[name="email"]');
        return {
            val: em.value,
            maxlength: em.maxLength,
            invalid: em.getAttribute('aria-invalid')
        };
    """)
    log(f'Email field validation: {val_check}')

    sub_btn = page.ele('@data-testid=sign-up-submit')
    log('Clicking sign-up-submit...')
    sub_btn.click(by_js=True)
    time.sleep(6)

    # Check dialog state
    res_dialog = page.run_js("""
        const d = document.querySelector('[role="dialog"]');
        if (!d) return { hasDialog: false };
        return {
            text: d.innerText,
            inputs: Array.from(d.querySelectorAll('input')).map(i => ({
                name: i.name,
                value: i.value,
                invalid: i.getAttribute('aria-invalid')
            }))
        };
    """)
    log('Dialog after submit:\n' + json.dumps(res_dialog, indent=2))

    # Poll temp.tf for Kick verification email
    log('Polling temp.tf for Kick verification email (60s)...')
    for attempt in range(20):
        time.sleep(3)
        check_r = requests.post('https://temp.tf/api/check', json={'email': email, 'wait': False}, timeout=10)
        items = check_r.json().get('data', [])
        for item in items:
            subj = item.get('subject', '')
            sender = item.get('from', '')
            log(f'Attempt {attempt+1}: message from {sender} - "{subj}"')
            if any(k in f'{subj} {sender}'.lower() for k in ['kick', 'kod', 'onay', 'verify', 'account']):
                log('KICK VERIFICATION EMAIL RECEIVED!')
                body = item.get('body') or item.get('text') or ''
                codes = re.findall(r'\\b\\d{6}\\b', f'{subj} {body}')
                log(f'Verification codes found: {codes}')
                break
        else:
            continue
        break

finally:
    page.quit()
    log('Done!')
