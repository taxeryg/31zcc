from DrissionPage import ChromiumPage, ChromiumOptions
import time, json

co = ChromiumOptions()
co.headless(True)
co.set_browser_path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
page = ChromiumPage(co)

try:
    page.get('https://kick.com')
    time.sleep(3)
    accept_btn = page.ele('#onetrust-accept-btn-handler') or page.ele('text:Tümünü Kabul Et')
    if accept_btn:
        accept_btn.click(by_js=True)
        time.sleep(1)

    btn = page.ele('text:Kaydol') or page.ele('@data-testid=sign-up')
    if btn:
        btn.click(by_js=True)
        time.sleep(2)

    res_init = page.run_js("""
        const form = document.querySelector('form');
        if (!form) return { hasForm: false };
        const inputs = Array.from(form.querySelectorAll('input')).map(i => ({
            name: i.name,
            type: i.type,
            required: i.required,
            value: i.value,
            invalid: i.getAttribute('aria-invalid'),
            disabled: i.disabled
        }));
        const buttons = Array.from(form.querySelectorAll('button')).map(b => ({
            type: b.type,
            text: b.innerText,
            disabled: b.disabled,
            class: b.className
        }));
        return { hasForm: true, inputs, buttons };
    """)
    print('Initial form:', json.dumps(res_init, indent=2))

    page.ele('@name=email').input('testguy99124@gmail.com')
    bday = page.ele('@name=birthdate')
    page.run_js("""
        arguments[0].value = '1998-04-12';
        arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
        arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
    """, bday)
    page.ele('@name=username').input('kshadow99281')
    page.ele('@name=password').input('UltraPass99!@')
    time.sleep(1)

    res_filled = page.run_js("""
        const form = document.querySelector('form');
        const inputs = Array.from(form.querySelectorAll('input')).map(i => ({
            name: i.name,
            value: i.value,
            invalid: i.getAttribute('aria-invalid')
        }));
        const buttons = Array.from(form.querySelectorAll('button')).map(b => ({
            type: b.type,
            text: b.innerText,
            disabled: b.disabled
        }));
        return { inputs, buttons };
    """)
    print('Filled form:', json.dumps(res_filled, indent=2))

    # Click submit
    sub_btn = page.ele('css:form button[type="submit"]')
    if sub_btn:
        print('Clicking submit button by JS...')
        sub_btn.click(by_js=True)
        time.sleep(5)

    res_after = page.run_js("""
        const form = document.querySelector('form');
        const errors = Array.from(document.querySelectorAll('[class*="error"], [class*="invalid"], [aria-invalid="true"], [role="alert"]')).map(e => ({
            tag: e.tagName,
            text: e.innerText,
            class: e.className
        }));
        const allText = document.body.innerText;
        return { errors, hasForm: !!form };
    """)
    print('After submit:', json.dumps(res_after, indent=2))

    # Let's see what network requests happened if possible or iframes
    iframes = page.eles('tag:iframe')
    print('Iframes:', len(iframes))
    for ifr in iframes:
        print('Iframe:', ifr.attrs.get('src', ''))

finally:
    page.quit()
