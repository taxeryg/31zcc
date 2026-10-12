from DrissionPage import ChromiumPage, ChromiumOptions
import time, requests, re, json

print('=== TESTING REAL SIGN UP SUBMIT ===')

# 1. Fetch fresh email from temp.tf
print('Getting email from temp.tf...')
mail_resp = requests.get('https://temp.tf/api/account', params={'providers': 'outlook,hotmail,gmail', 'dot': '1', 'plus': '0'}, timeout=10)
mail_data = mail_resp.json()
email = mail_data.get('email')
print('Got email:', email)

co = ChromiumOptions()
co.headless(True)
co.set_browser_path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
page = ChromiumPage(co)

try:
    print('Opening kick.com...')
    page.get('https://kick.com')
    time.sleep(3)

    # Accept cookies
    accept_btn = page.ele('#onetrust-accept-btn-handler') or page.ele('text:Tümünü Kabul Et')
    if accept_btn:
        accept_btn.click(by_js=True)
        time.sleep(1)

    # Click Kaydol (Sign up)
    btn = page.ele('text:Kaydol') or page.ele('@data-testid=sign-up')
    if btn:
        btn.click(by_js=True)
        time.sleep(2)

    uname = 'nex_' + str(int(time.time()))[-6:]
    pwd = 'TestPassword99!@'
    print(f'Filling: email={email}, user={uname}, bday=2000-06-15')

    email_inp = page.ele('@name=email')
    bday_inp = page.ele('@name=birthdate')
    user_inp = page.ele('@name=username')
    pass_inp = page.ele('@name=password')

    email_inp.input(email)
    page.run_js("""
        arguments[0].value = '2000-06-15';
        arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
        arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
    """, bday_inp)
    user_inp.input(uname)
    pass_inp.input(pwd)
    time.sleep(1)

    # Locate the submit button with data-testid="sign-up-submit"
    sub = page.ele('@data-testid=sign-up-submit') or page.ele('css:button[data-testid="sign-up-submit"]')
    print('Submit button:', sub.text if sub else 'NOT FOUND')

    if sub:
        print('CLICKING SUBMIT BUTTON...')
        sub.click(by_js=True)
        time.sleep(4)

    # Check state after submit
    print('Page URL after submit:', page.url)

    # Look for errors or dialog content
    dialog_info = page.run_js("""
        const dialog = document.querySelector('[role="dialog"]') || document.querySelector('.fixed');
        if (!dialog) return { hasDialog: false };
        const text = dialog.innerText;
        const inputs = Array.from(dialog.querySelectorAll('input')).map(i => ({
            name: i.name,
            placeholder: i.placeholder,
            inputmode: i.getAttribute('inputmode'),
            type: i.type
        }));
        const buttons = Array.from(dialog.querySelectorAll('button')).map(b => b.innerText.trim());
        const iframes = Array.from(dialog.querySelectorAll('iframe')).map(f => f.src);
        return { text, inputs, buttons, iframes };
    """)
    print('Dialog info after submit:', json.dumps(dialog_info, indent=2))

    # Check if Turnstile or Cloudflare appeared anywhere
    cf_frames = [f.attrs.get('src', '') for f in page.eles('tag:iframe') if 'cloudflare' in f.attrs.get('src', '') or 'turnstile' in f.attrs.get('src', '')]
    print('Cloudflare/Turnstile iframes:', cf_frames)

    # Poll temp.tf for Kick verification email
    print('Polling temp.tf for Kick verification email (60 seconds)...')
    for attempt in range(20):
        time.sleep(3)
        check_r = requests.post('https://temp.tf/api/check', json={'email': email, 'wait': False}, timeout=10)
        items = check_r.json().get('data', [])
        for item in items:
            subj = item.get('subject', '')
            sender = item.get('from', '')
            print(f'Attempt {attempt+1}: found message from {sender} - "{subj}"')
            if 'kick' in subj.lower() or 'kick' in sender.lower() or 'verify' in subj.lower() or 'onay' in subj.lower():
                print('KICK EMAIL DETECTED! Content:')
                body = item.get('body') or item.get('text') or ''
                code_matches = re.findall(r'\\b\\d{6}\\b', f'{subj} {body}')
                print('Found codes:', code_matches)
                break
        else:
            continue
        break

finally:
    page.quit()
    print('Finished script!')
