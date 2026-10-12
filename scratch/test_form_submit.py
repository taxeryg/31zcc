import sys
import os
import time
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kick_account_creator as kac

print("Testing exact submit button inside email form...", flush=True)

opts = uc.ChromeOptions()
opts.add_argument("--window-size=1920,1080")
opts.add_argument("--headless=new")
driver = uc.Chrome(options=opts, use_subprocess=True)

try:
    driver.get("https://kick.com")
    time.sleep(5)
    
    # Cookie accept
    try:
        cb = driver.find_element(By.ID, "onetrust-accept-btn-handler")
        cb.click()
    except:
        pass
    time.sleep(1)
    
    # Click Sign up
    driver.execute_script("""
        for (let b of document.querySelectorAll('button')) {
            if (b.innerText.trim().toLowerCase() === 'sign up') {
                b.click();
                break;
            }
        }
    """)
    time.sleep(3)
    
    # Generate data
    u = kac.generate_username()
    p = kac.generate_password()
    bday = kac.generate_birthdate()
    
    tf = kac.TempTfMailClient()
    mb = tf.create_mailbox()
    em = mb["email"]
    print(f"Form data: {u} | {em} | {bday} | {p}", flush=True)
    
    # Fill inputs
    driver.find_element(By.CSS_SELECTOR, 'input[name="email"]').send_keys(em)
    
    bday_el = driver.find_element(By.CSS_SELECTOR, 'input[name="birthdate"], input[type="date"]')
    driver.execute_script("""
        const el = arguments[0];
        el.focus();
        if (el._valueTracker) { el._valueTracker.setValue(''); }
        const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        nativeSetter.call(el, arguments[1]);
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        el.blur();
    """, bday_el, bday)
    
    driver.find_element(By.CSS_SELECTOR, 'input[name="username"]').send_keys(u)
    
    p_el = driver.find_element(By.CSS_SELECTOR, 'input[name="password"]')
    driver.execute_script("""
        const el = arguments[0];
        el.focus();
        if (el._valueTracker) { el._valueTracker.setValue(''); }
        const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        nativeSetter.call(el, arguments[1]);
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        el.blur();
    """, p_el, p)
    
    time.sleep(1)
    
    # Find all buttons near email input
    info = driver.execute_script("""
        let em = document.querySelector('input[name="email"]');
        let container = em.closest('form') || em.closest('[class*="modal"]') || em.parentElement.parentElement.parentElement.parentElement;
        let btns = [];
        for (let b of container.querySelectorAll('button')) {
            btns.push({
                text: b.innerText.trim(),
                className: b.className,
                type: b.getAttribute('type'),
                disabled: b.disabled
            });
        }
        return {containerTag: container.tagName, buttons: btns};
    """)
    print("Container & Buttons info:", info, flush=True)
    
    # Click the green Sign Up button inside the container
    clicked = driver.execute_script("""
        let em = document.querySelector('input[name="email"]');
        let container = em.closest('form') || em.closest('[class*="modal"]') || em.parentElement.parentElement.parentElement.parentElement;
        for (let b of container.querySelectorAll('button')) {
            let t = b.innerText.trim().toLowerCase();
            if (t === 'sign up' || t === 'kayıt ol' || b.getAttribute('type') === 'submit') {
                b.click();
                return {clicked: true, text: b.innerText.trim()};
            }
        }
        return {clicked: false};
    """)
    print("Clicked result:", clicked, flush=True)
    
    # Wait 10 seconds and check page state
    for i in range(5):
        time.sleep(2)
        state = driver.execute_script("""
            let codeInps = document.querySelectorAll('input[inputmode="numeric"], input[autocomplete="one-time-code"]');
            let iframes = document.querySelectorAll('iframe');
            let ifrSrcs = Array.from(iframes).map(f => f.src);
            let alerts = Array.from(document.querySelectorAll('[role="alert"], [class*="error"]')).map(a => a.innerText.trim()).filter(Boolean);
            return {
                codeInputsCount: codeInps.length,
                iframes: ifrSrcs,
                alerts: alerts,
                url: window.location.href
            };
        """)
        print(f"[{i*2}s post-click state]:", state, flush=True)
        if state["codeInputsCount"] > 0:
            print("OTP INPUTS FOUND!", flush=True)
            break
            
    driver.save_screenshot("scratch/test_after_click.png")
    print("Saved scratch/test_after_click.png", flush=True)

finally:
    driver.quit()
