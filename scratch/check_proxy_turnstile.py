import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kick_account_creator import LocalAuthProxyBridge
from DrissionPage import ChromiumPage, ChromiumOptions
import time, requests, json

bridge = LocalAuthProxyBridge('45.38.107.97', 6014, 'gpbzberw', 'ripdlkneqpn0')
local_px = bridge.start()

co = ChromiumOptions()
co.headless(True)
co.set_browser_path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
co.set_proxy(f'http://{local_px}')

page = ChromiumPage(co)
try:
    page.get('https://kick.com')
    time.sleep(4)

    page.run_js("""
        let btn = document.getElementById('onetrust-accept-btn-handler');
        if (btn) btn.click();
        let ot = document.getElementById('onetrust-consent-sdk');
        if (ot) ot.remove();
    """)
    time.sleep(1)

    btn = page.ele('text:Kaydol') or page.ele('@data-testid=sign-up')
    btn.click(by_js=True)
    time.sleep(2)

    page.ele('@name=email').input('testcheck9918@gmail.com')
    page.run_js("""
        const el = document.querySelector('input[name="birthdate"]');
        const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        nativeSetter.call(el, '2000-01-01');
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        el.dispatchEvent(new Event('blur', { bubbles: true }));
    """)
    page.ele('@name=username').input('usr_test7781')
    page.ele('@name=password').input('Pass991!@#')
    time.sleep(1)

    sub = page.ele('@data-testid=sign-up-submit')
    sub.click(by_js=True)
    time.sleep(5)

    diag = page.run_js("""
        let d = document.querySelector('[role="dialog"]');
        return d ? d.innerText : 'NO DIALOG';
    """)
    print('Dialog on proxy 45.38.107.97:\n', diag)

    iframes = [f.attrs.get('src', '') for f in page.eles('tag:iframe')]
    print('Iframes:', [f for f in iframes if 'cloud' in f or 'turnstile' in f])

finally:
    page.quit()
    bridge.stop()
