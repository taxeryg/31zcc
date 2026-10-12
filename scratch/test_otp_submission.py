import sys, os, time, json, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import kick_account_creator as kac

print("--- Testing OTP submission with proxy ---", flush=True)
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
    driver.get("https://kick.com")
    time.sleep(5)
    
    # Cookie accept
    try:
        cb = driver.find_element(By.ID, "onetrust-accept-btn-handler")
        cb.click()
    except Exception:
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
    
    tf = kac.TempTfMailClient(proxy_dict={"http": f"http://{user}:{pwd}@{ip}:{port}", "https": f"http://{user}:{pwd}@{ip}:{port}"})
    mb = tf.create_mailbox()
    email = mb["email"]
    username = kac.generate_username()
    password = kac.generate_password()
    bday = kac.generate_birthdate()
    print(f"Account data: {username} | {email} | {bday} | {password}", flush=True)
    
    # Fill fields
    em_el = WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="email"]')))
    em_el.clear()
    em_el.send_keys(email)
    time.sleep(0.3)
    
    bday_el = driver.find_element(By.CSS_SELECTOR, 'input[name="birthdate"]')
    bday_el.send_keys("15051996")
    time.sleep(0.3)
    
    u_el = driver.find_element(By.CSS_SELECTOR, 'input[name="username"]')
    u_el.send_keys(username)
    time.sleep(0.3)
    
    p_el = driver.find_element(By.CSS_SELECTOR, 'input[name="password"]')
    p_el.send_keys(password)
    time.sleep(1)
    
    # Submit form
    print("Submitting signup form...", flush=True)
    driver.execute_script("""
        let em = document.querySelector('input[name="email"]');
        let form = em.closest('form');
        let btn = form.querySelector('button[type="submit"]');
        if (btn) btn.click();
    """)
    p_el.send_keys(Keys.RETURN)
    
    # Wait for OTP code
    print("Waiting for verification code...", flush=True)
    code = tf.poll_verification_code(timeout_secs=60)
    print(f"Code received: {code}", flush=True)
    
    if not code:
        print("Code not received!", flush=True)
        driver.save_screenshot("scratch/test_no_code.png")
    else:
        time.sleep(2)
        driver.save_screenshot("scratch/test_otp_screen_before.png")
        
        # Check inputs
        inps = driver.find_elements(By.CSS_SELECTOR, 'input[inputmode="numeric"], input[autocomplete="one-time-code"], input[name*="code"], input[data-testid*="code"]')
        print(f"Found {len(inps)} OTP inputs", flush=True)
        
        # Test inputting code character by character using send_keys ONLY
        if len(inps) == 6:
            for idx, ch in enumerate(code[:6]):
                inps[idx].click()
                inps[idx].clear()
                inps[idx].send_keys(ch)
                time.sleep(0.1)
        elif len(inps) == 1:
            inps[0].click()
            inps[0].clear()
            inps[0].send_keys(code)
            
        time.sleep(2)
        driver.save_screenshot("scratch/test_otp_screen_after_fill.png")
        
        # Check input values
        values = [inp.get_attribute("value") for inp in inps]
        print(f"OTP input values: {values}", flush=True)
        
        # Find submit button on OTP modal
        btn_info = driver.execute_script("""
            let inps = document.querySelectorAll('input[inputmode="numeric"], input[autocomplete="one-time-code"]');
            let container = inps.length > 0 ? (inps[0].closest('form') || inps[0].closest('[role="dialog"]') || inps[0].parentElement.parentElement) : document;
            let btns = Array.from(container.querySelectorAll('button')).map(b => ({
                text: b.innerText.trim(),
                type: b.getAttribute('type'),
                disabled: b.disabled,
                classes: b.className
            }));
            return btns;
        """)
        print(f"Buttons on OTP modal: {btn_info}", flush=True)
        
        # Click submit button or press Enter
        submitted = driver.execute_script("""
            let inps = document.querySelectorAll('input[inputmode="numeric"], input[autocomplete="one-time-code"]');
            let container = inps.length > 0 ? (inps[0].closest('form') || inps[0].closest('[role="dialog"]') || inps[0].parentElement.parentElement) : document;
            let btn = container.querySelector('button[type="submit"]') || Array.from(container.querySelectorAll('button')).find(b => {
                let t = b.innerText.trim().toLowerCase();
                return t.includes('verify') || t.includes('onayla') || t.includes('continue') || t.includes('devam') || t.includes('accept');
            });
            if (btn) {
                btn.click();
                return 'button_clicked: ' + btn.innerText.trim();
            }
            return 'no_button';
        """)
        print(f"Submit attempt result: {submitted}", flush=True)
        if inps:
            inps[-1].send_keys(Keys.RETURN)
            
        # Monitor for 15 seconds: inspect localStorage, performance logs, URL
        for sec in range(8):
            time.sleep(2)
            ls_data = driver.execute_script("return JSON.stringify({...window.localStorage, ...window.sessionStorage});")
            cookies = driver.get_cookies()
            logs = driver.get_log("performance")
            
            bearer_found = []
            for entry in logs:
                m = entry.get("message", "")
                if "Bearer" in m or "Authorization" in m:
                    bearer_found.append(m[:250])
                    
            print(f"[{sec*2}s] URL: {driver.current_url} | Bearer hits: {len(bearer_found)} | Cookies: {len(cookies)}", flush=True)
            if bearer_found:
                print("BEARER SAMPLES:", bearer_found[:2], flush=True)
            if "token" in ls_data.lower() or "auth" in ls_data.lower():
                print("LS sample:", ls_data[:300], flush=True)
                
        driver.save_screenshot("scratch/test_otp_final.png")
        print("Final screenshot saved.", flush=True)

finally:
    driver.quit()
    if os.path.exists(ext_path):
        os.remove(ext_path)
