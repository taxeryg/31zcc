from DrissionPage import ChromiumPage, ChromiumOptions
import time, json

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
    """)

    # Click Kaydol
    btn = page.ele('text:Kaydol') or page.ele('@data-testid=sign-up')
    btn.click(by_js=True)
    time.sleep(2)

    bday = page.ele('@name=birthdate')
    print('Initial bday value:', bday.attrs.get('value'))

    # Method 1: native setter + React tracker bypass
    res = page.run_js("""
        const el = document.querySelector('input[name="birthdate"]');
        if (!el) return { error: 'no el' };

        const prototype = Object.getPrototypeOf(el);
        const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        
        nativeSetter.call(el, '1999-05-15');
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        el.dispatchEvent(new Event('blur', { bubbles: true }));

        return {
            val: el.value,
            attrVal: el.getAttribute('value'),
            invalid: el.getAttribute('aria-invalid')
        };
    """)
    print('After nativeSetter JS:', res)

    # Check if age error is gone
    errors = page.run_js("""
        return Array.from(document.querySelectorAll('[role="dialog"] [class*="error"], [role="dialog"] p')).map(p => p.innerText);
    """)
    print('Dialog texts:', [t for t in errors if '13' in t or 'yaş' in t])

finally:
    page.quit()
