from DrissionPage import ChromiumPage, ChromiumOptions
import time, json, requests, re

def log(msg):
    print(msg, flush=True)

log('=== TESTING KICK REGISTRATION WITH GUERRILLA MAIL ===')

# 1. Get Guerrilla email
g_resp = requests.get('https://api.guerrillamail.com/ajax.php?f=get_email_address', timeout=10)
g_data = g_resp.json()
sid_token = g_data.get('sid_token')
email = g_data.get('email_addr')
log(f'Guerrilla email: {email} (sid={sid_token}, len={len(email)})')

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
    time.sleep(5)

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

    # Poll Guerrilla Mail for Kick verification email
    log('Polling Guerrilla Mail for Kick verification email (60s)...')
    for attempt in range(15):
        time.sleep(4)
        check_r = requests.get(f'https://api.guerrillamail.com/ajax.php?f=check_email&seq=0&sid_token={sid_token}', timeout=10)
        mail_list = check_r.json().get('list', [])
        for mail in mail_list:
            subj = mail.get('mail_subject', '')
            sender = mail.get('mail_from', '')
            log(f'Attempt {attempt+1}: message from {sender} - "{subj}"')
            if any(k in f'{subj} {sender}'.lower() for k in ['kick', 'kod', 'onay', 'verify', 'account']):
                log('KICK VERIFICATION EMAIL RECEIVED IN GUERRILLA!')
                mail_id = mail.get('mail_id')
                f_resp = requests.get(f'https://api.guerrillamail.com/ajax.php?f=fetch_email&email_id={mail_id}&sid_token={sid_token}', timeout=10)
                body = f_resp.json().get('mail_body', '')
                codes = re.findall(r'\\b\\d{6}\\b', f'{subj} {body}')
                log(f'Verification codes found: {codes}')
                break
        else:
            continue
        break

finally:
    page.quit()
    log('Done!')
