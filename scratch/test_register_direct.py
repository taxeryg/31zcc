import sys
import os
import time
import json
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kick_account_creator as kac

print("1. Generating test data...", flush=True)
username = kac.generate_username()
password = kac.generate_password()
birthdate = kac.generate_birthdate()

mail_client = kac.TempTfMailClient()
mb = mail_client.create_mailbox()
email = mb["email"]
print(f"Data: user={username}, email={email}, bday={birthdate}", flush=True)

opts = uc.ChromeOptions()
opts.add_argument("--window-size=1920,1080")
opts.add_argument("--no-first-run")
opts.add_argument("--disable-blink-features=AutomationControlled")
# Try non-headless or headless
opts.add_argument("--headless=new")

print("2. Starting Chrome...", flush=True)
driver = uc.Chrome(options=opts, use_subprocess=True)

try:
    print("3. Navigating to kick.com...", flush=True)
    driver.get("https://kick.com")
    time.sleep(5)
    
    # Cookie accept
    try:
        cb = driver.find_element(By.ID, "onetrust-accept-btn-handler")
        cb.click()
        print("Accepted cookies.", flush=True)
    except:
        pass
        
    # Click Sign up
    print("4. Clicking sign up...", flush=True)
    signup = None
    try:
        signup = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-testid="sign-up"]')))
    except:
        pass
    if not signup:
        for b in driver.find_elements(By.TAG_NAME, "button"):
            if b.text.strip().lower() in ["sign up", "kaydol", "kayıt ol"]:
                signup = b
                break
    if signup:
        driver.execute_script("arguments[0].click();", signup)
    else:
        driver.get("https://kick.com/register")
    time.sleep(4)
    
    # Fill email
    print("5. Filling form...", flush=True)
    em_el = driver.find_element(By.CSS_SELECTOR, 'input[name="email"]')
    em_el.send_keys(email)
    time.sleep(0.5)
    
    # Fill birthdate
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
    """, bday_el, birthdate)
    time.sleep(0.5)
    
    # Fill username
    u_el = driver.find_element(By.CSS_SELECTOR, 'input[name="username"]')
    u_el.send_keys(username)
    time.sleep(0.5)
    
    # Fill password
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
    """, p_el, password)
    time.sleep(1)
    
    # Check what buttons are in the modal / form
    print("6. Locating submit button inside dialog...", flush=True)
    modal = driver.find_elements(By.CSS_SELECTOR, 'div[role="dialog"]')
    search_root = modal[0] if modal else driver
    
    sub_btns = search_root.find_elements(By.CSS_SELECTOR, 'button[type="submit"]')
    print(f"Found {len(sub_btns)} submit buttons in dialog.", flush=True)
    for idx, sb in enumerate(sub_btns):
        print(f"Btn {idx}: text='{sb.text}', enabled={sb.is_enabled()}, displayed={sb.is_displayed()}", flush=True)
        
    if sub_btns:
        btn = sub_btns[0]
        print(f"Clicking submit button: text='{btn.text}', disabled={btn.get_attribute('disabled')}", flush=True)
        driver.execute_script("arguments[0].click();", btn)
    else:
        print("No submit button found!", flush=True)
        
    # Wait and inspect page state
    print("7. Inspecting post-submit state for 15 seconds...", flush=True)
    for s in range(8):
        time.sleep(2)
        # Check iframes
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for ifr in iframes:
            src = ifr.get_attribute("src") or ""
            title = ifr.get_attribute("title") or ""
            if any(k in src.lower() or k in title.lower() for k in ["turnstile", "cloudflare", "challenge", "recaptcha"]):
                print(f"[{s*2}s] Captcha iframe found! src={src[:70]}, displayed={ifr.is_displayed()}", flush=True)
                
        # Check inputs on page (are we on OTP step?)
        code_inps = driver.find_elements(By.CSS_SELECTOR, 'input[inputmode="numeric"], input[autocomplete="one-time-code"]')
        if code_inps:
            print(f"[{s*2}s] SUCCESS: OTP INPUTS DETECTED! Count={len(code_inps)}", flush=True)
            break
            
        # Check errors
        err_els = search_root.find_elements(By.CSS_SELECTOR, '[class*="error"], [role="alert"]')
        for err in err_els:
            if err.is_displayed() and err.text.strip():
                print(f"[{s*2}s] Form Error: {err.text.strip()}", flush=True)

    driver.save_screenshot("scratch/test_step_result.png")
    print("Saved screenshot to scratch/test_step_result.png", flush=True)

finally:
    driver.quit()
    print("Driver closed.", flush=True)
