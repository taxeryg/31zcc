import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import time
import json
import random
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import kick_account_creator as kac

print("Testing full flow WITH PROXY from pool...", flush=True)

# 1. Pick a proxy
raw = random.choice(kac.PROXY_POOL)
ip, port, user, pwd = raw.split(":")
print(f"Using proxy: {ip}:{port}", flush=True)
ext_path = kac.create_proxy_auth_extension(ip, port, user, pwd)

opts = uc.ChromeOptions()
opts.add_argument("--window-size=1920,1080")
opts.add_argument("--headless=new")
opts.add_extension(ext_path)
opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})
driver = uc.Chrome(options=opts, use_subprocess=True)

try:
    print("1. Loading kick.com...", flush=True)
    driver.get("https://kick.com")
    time.sleep(6)
    
    # 2. Click Kick's custom Accept All Cookies banner
    print("2. Accepting cookies...", flush=True)
    accepted = driver.execute_script("""
        let clicked = false;
        for (let b of document.querySelectorAll('button')) {
            let t = b.innerText.trim().toLowerCase();
            if (t.includes('accept all cookies') || t.includes('tümünü kabul et') || b.id === 'onetrust-accept-btn-handler') {
                b.click();
                clicked = true;
                break;
            }
        }
        return clicked;
    """)
    print("Cookie accept result:", accepted, flush=True)
    time.sleep(2)
    
    # 3. Click Sign up
    print("3. Clicking Sign up...", flush=True)
    driver.execute_script("""
        for (let b of document.querySelectorAll('button')) {
            if (b.innerText.trim().toLowerCase() === 'sign up' || b.getAttribute('data-testid') === 'sign-up') {
                b.click();
                break;
            }
        }
    """)
    time.sleep(3)
    
    # 4. Prepare data
    tf = kac.TempTfMailClient(proxy_dict={"http": f"http://{user}:{pwd}@{ip}:{port}", "https": f"http://{user}:{pwd}@{ip}:{port}"})
    mb = tf.create_mailbox()
    email = mb["email"]
    username = kac.generate_username()
    password = kac.generate_password()
    print(f"Data: {email} | {username} | {password}", flush=True)
    
    # 5. Fill fields
    em_el = WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="email"]')))
    em_el.clear()
    em_el.send_keys(email)
    time.sleep(0.3)
    
    bday_el = driver.find_element(By.CSS_SELECTOR, 'input[name="birthdate"]')
    bday_el.send_keys("18041997")
    time.sleep(0.3)
    
    u_el = driver.find_element(By.CSS_SELECTOR, 'input[name="username"]')
    u_el.send_keys(username)
    time.sleep(0.3)
    
    p_el = driver.find_element(By.CSS_SELECTOR, 'input[name="password"]')
    p_el.send_keys(password)
    time.sleep(1)
    
    # Clear performance logs
    driver.get_log("performance")
    
    # 6. Submit via form button
    print("6. Submitting form...", flush=True)
    submit_res = driver.execute_script("""
        let em = document.querySelector('input[name="email"]');
        if (!em) return 'no_email_input';
        let form = em.closest('form');
        if (!form) return 'no_form';
        let btn = form.querySelector('button[type="submit"]');
        if (btn) {
            btn.click();
            return 'button_clicked';
        }
        form.requestSubmit();
        return 'form_submitted';
    """)
    print("Submit result:", submit_res, flush=True)
    p_el.send_keys(Keys.RETURN)
    
    # 7. Monitor for 20 seconds
    for sec in range(10):
        time.sleep(2)
        logs = driver.get_log("performance")
        for entry in logs:
            msg = entry.get("message", "")
            if "responseReceived" in msg and "send-verification-code" in msg:
                try:
                    d = json.loads(msg)
                    resp = d["message"]["params"]["response"]
                    print(f"[{sec*2}s] VERIFICATION CODE API RESPONSE:", resp.get("status"), resp.get("statusText"), flush=True)
                except Exception as ex:
                    print("Parse error:", ex)
                    
        otp_count = driver.execute_script("""
            return document.querySelectorAll('input[inputmode="numeric"], input[autocomplete="one-time-code"]').length;
        """)
        if otp_count > 0:
            print(f"[{sec*2}s] SUCCESS! OTP input fields appeared: count={otp_count}", flush=True)
            break
            
        errs = driver.execute_script("""
            return Array.from(document.querySelectorAll('form [class*=\"error\"], [role=\"alert\"]')).map(e => e.innerText.trim()).filter(Boolean);
        """)
        if errs:
            print(f"[{sec*2}s] Visible errors:", errs, flush=True)

    driver.save_screenshot("scratch/test_proxy_flow.png")
    print("Saved scratch/test_proxy_flow.png", flush=True)

finally:
    driver.quit()
    if os.path.exists(ext_path):
        os.remove(ext_path)
    print("Done.", flush=True)
