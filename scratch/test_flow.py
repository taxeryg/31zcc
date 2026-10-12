from DrissionPage import ChromiumPage, ChromiumOptions
import time, requests, re, os

# Ensure scratch directory
print('=== Kick Registration Step Test ===')

# 1. Get email from temp.tf
print('Requesting email from temp.tf...')
r = requests.get('https://temp.tf/api/account', params={'providers': 'outlook,hotmail,gmail', 'dot': '1', 'plus': '0'}, timeout=10)
email = r.json().get('email')
print('Got email:', email)

co = ChromiumOptions()
co.headless(True)
co.set_browser_path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
page = ChromiumPage(co)

try:
    print('Navigating to kick.com...')
    page.get('https://kick.com')
    time.sleep(4)

    # Accept cookies
    try:
        accept_btn = page.ele('#onetrust-accept-btn-handler') or page.ele('text:Tümünü Kabul Et') or page.ele('text:Allow All')
        if accept_btn:
            accept_btn.click(by_js=True)
            time.sleep(1)
            print('Accepted cookies')
    except Exception as e:
        print('Cookie banner error:', e)

    # Click Kaydol
    btn = page.ele('text:Kaydol') or page.ele('@data-testid=sign-up')
    if btn:
        btn.click(by_js=True)
        time.sleep(3)
        print('Clicked Kaydol')

    # Fill form
    email_inp = page.ele('@name=email')
    bday_inp = page.ele('@name=birthdate')
    user_inp = page.ele('@name=username')
    pass_inp = page.ele('@name=password')

    uname = 'nex_' + str(int(time.time()))[-6:]
    pwd = 'KickUser99!@#'

    print(f'Filling form: email={email}, user={uname}')
    if email_inp:
        email_inp.clear()
        email_inp.input(email)
    if bday_inp:
        page.run_js("""
            const el = arguments[0];
            el.value = '2001-05-15';
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        """, bday_inp)
    if user_inp:
        user_inp.clear()
        user_inp.input(uname)
    if pass_inp:
        pass_inp.clear()
        pass_inp.input(pwd)

    time.sleep(1)

    # Find submit button in the modal
    submit_btn = None
    for b in page.eles('tag:button'):
        if b.text and b.text.strip() == 'Kaydol':
            submit_btn = b
    if submit_btn:
        print('Clicking submit button...')
        submit_btn.click(by_js=True)
    else:
        print('Submit button not found!')

    time.sleep(5)

    print('URL after submit:', page.url)

    # Check if Turnstile iframe appeared
    iframes = page.eles('tag:iframe')
    for ifr in iframes:
        src = ifr.attrs.get('src', '')
        print('Iframe src:', src[:90])

    # Check for text messages / errors / headings
    all_p = page.eles('tag:p') + page.eles('tag:span') + page.eles('tag:div')
    for el in all_p:
        t = el.text
        if t and any(k in t.lower() for k in ['kod', 'code', 'doğrula', 'verify', 'error', 'hata', 'geçersiz', 'invalid', 'e-posta', 'turnstile', 'güvenlik', 'robot', 'gönderdik', 'sent']):
            if len(t) < 150:
                print('Alert text:', t)

    # Check temp.tf for incoming mail
    print('Checking temp.tf for OTP code for 30s...')
    for i in range(10):
        time.sleep(3)
        check_r = requests.post('https://temp.tf/api/check', json={'email': email, 'wait': False}, timeout=10)
        items = check_r.json().get('data', [])
        print(f'Attempt {i+1}: received {len(items)} items')
        if items:
            print('MAIL RECEIVED! Details:', items)
            break

finally:
    page.quit()
    print('Finished!')
