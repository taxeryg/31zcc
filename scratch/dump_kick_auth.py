import sys, os, time, json, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import kick_account_creator as kac

print("--- DIAGNOSTIC RUN: Catch Kick Auth payload ---", flush=True)

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
        driver.find_element(By.ID, "onetrust-accept-btn-handler").click()
    except Exception:
        pass
    time.sleep(1)
    
    driver.execute_script("""
        for (let b of document.querySelectorAll('button')) {
            if (b.innerText.trim().toLowerCase() === 'sign up') { b.click(); break; }
        }
    """)
    time.sleep(3)
    
    # Use temp.tf with proxy
    tf = kac.TempTfMailClient(proxy_dict={"http": f"http://{user}:{pwd}@{ip}:{port}", "https": f"http://{user}:{pwd}@{ip}:{port}"})
    mb = tf.create_mailbox()
    email = mb["email"]
    username = kac.generate_username()
    password = kac.generate_password()
    bday = kac.generate_birthdate()
    print(f"User: {username} | Email: {email}", flush=True)
    
    em_el = WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="email"]')))
    em_el.clear()
    em_el.send_keys(email)
    time.sleep(0.3)
    
    driver.find_element(By.CSS_SELECTOR, 'input[name="birthdate"]').send_keys("15051996")
    time.sleep(0.3)
    driver.find_element(By.CSS_SELECTOR, 'input[name="username"]').send_keys(username)
    time.sleep(0.3)
    p = driver.find_element(By.CSS_SELECTOR, 'input[name="password"]')
    p.send_keys(password)
    time.sleep(1)
    
    # Submit
    driver.execute_script("""
        let em = document.querySelector('input[name="email"]');
        let form = em.closest('form');
        let btn = form.querySelector('button[type="submit"]');
        if (btn) btn.click();
    """)
    p.send_keys(Keys.RETURN)
    print("Form submitted. Polling code...", flush=True)
    
    code = tf.poll_verification_code(timeout_secs=60)
    print(f"Code received: {code}", flush=True)
    
    if code:
        time.sleep(1)
        inps = driver.find_elements(By.CSS_SELECTOR, 'input[inputmode="numeric"], input[autocomplete="one-time-code"], input[name*="code"]')
        print(f"Found {len(inps)} code inputs", flush=True)
        if len(inps) == 6:
            for idx, ch in enumerate(code[:6]):
                inps[idx].click()
                inps[idx].clear()
                inps[idx].send_keys(ch)
                time.sleep(0.05)
        elif len(inps) == 1:
            inps[0].click()
            inps[0].clear()
            inps[0].send_keys(code)
            
        time.sleep(1)
        # Click submit on OTP modal
        driver.execute_script("""
            let inps = document.querySelectorAll('input[inputmode="numeric"], input[autocomplete="one-time-code"], input[name*="code"]');
            let container = inps.length > 0 ? (inps[0].closest('form') || inps[0].closest('[role="dialog"]') || inps[0].parentElement.parentElement) : document;
            for (let b of container.querySelectorAll('button')) {
                let t = b.innerText.trim().toLowerCase();
                if (t.includes('verify') || t.includes('onayla') || t.includes('continue') || t.includes('devam') || t.includes('accept') || t.includes('sign up') || t.includes('submit')) {
                    b.click();
                    break;
                }
            }
        """)
        if inps:
            inps[-1].send_keys(Keys.RETURN)
            
        print("Waiting 10 seconds post-OTP...", flush=True)
        time.sleep(10)
        
        # DUMP EVERYTHING
        cookies = driver.get_cookies()
        print(f"\n--- COOKIES ({len(cookies)}) ---")
        for c in cookies:
            print(f"  {c['name']} = {c['value'][:50]}... (domain={c.get('domain')})")
            
        ls = driver.execute_script("return JSON.stringify({...window.localStorage});")
        ss = driver.execute_script("return JSON.stringify({...window.sessionStorage});")
        print(f"\n--- LOCAL STORAGE ---\n{ls}")
        print(f"\n--- SESSION STORAGE ---\n{ss}")
        
        # Check logs
        perf = driver.get_log("performance")
        print(f"\n--- PERFORMANCE LOGS ({len(perf)} entries) ---")
        relevant = []
        for p_log in perf:
            m = p_log.get("message", "")
            if any(term in m for term in ["Bearer", "Authorization", "token", "signup", "verify", "mobile", "user"]):
                relevant.append(m)
        print(f"Found {len(relevant)} relevant network events:")
        for r_entry in relevant[:10]:
            print(" ", r_entry[:200])
            
        # Refresh and check if user profile is loaded
        driver.get("https://kick.com")
        time.sleep(5)
        logged_in_user = driver.execute_script("""
            let u = document.querySelector('[data-testid="user-avatar"], [class*="avatar"], button[aria-label*="profile"]');
            return u ? u.outerHTML.slice(0, 100) : 'no avatar found';
        """)
        print(f"Post-refresh avatar check: {logged_in_user}")
        driver.save_screenshot("scratch/dump_final.png")
finally:
    driver.quit()
    if os.path.exists(ext_path):
        os.remove(ext_path)
