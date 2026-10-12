import sys, os, time, json, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import kick_account_creator as kac

# Pick a fresh working proxy
raw = random.choice(kac.PROXY_POOL)
ip, port, user, pwd = raw.split(":")
print(f"Testing with proxy: {ip}:{port}", flush=True)

ext_path = kac.create_proxy_auth_extension(ip, port, user, pwd)

opts = uc.ChromeOptions()
opts.add_argument("--window-size=1920,1080")
opts.add_argument("--headless=new")
opts.add_extension(ext_path)
opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})
driver = uc.Chrome(options=opts, use_subprocess=True)

try:
    print("Navigating to https://kick.com via proxy...", flush=True)
    driver.get("https://kick.com")
    time.sleep(6)
    
    # Close cookies directly via JS
    driver.execute_script("""
        for (let b of document.querySelectorAll('button')) {
            let t = b.innerText.trim().toLowerCase();
            if (t.includes('accept') || t.includes('kabul') || b.id === 'onetrust-accept-btn-handler') {
                b.click();
            }
        }
    """)
    time.sleep(1)
    
    # Find and click Sign up directly via JS
    clicked_signup = driver.execute_script("""
        for (let b of document.querySelectorAll('button, a')) {
            let t = b.innerText.trim().toLowerCase();
            let testid = b.getAttribute('data-testid') || '';
            if (testid === 'sign-up' || t === 'sign up' || t === 'kaydol') {
                b.click();
                return 'clicked: ' + (testid || t);
            }
        }
        return 'not_found';
    """)
    print("Sign up button click result:", clicked_signup, flush=True)
    time.sleep(3)
    
    # Check if email input appeared
    inps = driver.find_elements(By.CSS_SELECTOR, 'input[name="email"]')
    print(f"Found {len(inps)} email inputs", flush=True)
    if not inps:
        driver.save_screenshot("scratch/proxy_no_modal.png")
        print("Modal did not open! Exiting.", flush=True)
        sys.exit(1)
        
    tf = kac.TempTfMailClient(proxy_dict={"http": f"http://{user}:{pwd}@{ip}:{port}", "https": f"http://{user}:{pwd}@{ip}:{port}"})
    mb = tf.create_mailbox()
    email = mb["email"]
    username = kac.generate_username()
    password = kac.generate_password()
    print(f"Testing signup: {email} | {username}", flush=True)
    
    inps[0].send_keys(email)
    driver.find_element(By.CSS_SELECTOR, 'input[name="birthdate"]').send_keys("15051996")
    driver.find_element(By.CSS_SELECTOR, 'input[name="username"]').send_keys(username)
    p = driver.find_element(By.CSS_SELECTOR, 'input[name="password"]')
    p.send_keys(password)
    time.sleep(1)
    
    # Clear performance log
    driver.get_log("performance")
    
    # Submit
    driver.execute_script("""
        let em = document.querySelector('input[name="email"]');
        let form = em.closest('form');
        let btn = form.querySelector('button[type="submit"]');
        if (btn) btn.click();
    """)
    p.send_keys(Keys.RETURN)
    print("Submitted form. Checking response...", flush=True)
    
    time.sleep(5)
    
    logs = driver.get_log("performance")
    found_status = None
    for entry in logs:
        m = entry.get("message", "")
        if "send-verification-code" in m and "Network.responseReceived" in m:
            obj = json.loads(m)
            status = obj["message"]["params"]["response"]["status"]
            req_id = obj["message"]["params"]["requestId"]
            found_status = status
            print(f"--> send-verification-code HTTP STATUS: {status}, req_id: {req_id}", flush=True)
            try:
                body = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": req_id})
                print("--> RESPONSE BODY:", body, flush=True)
            except Exception as e:
                print("CDP err:", e)
                
    if found_status == 200 or found_status == 204:
        print("SUCCESS! Verification code requested successfully. Polling for code...", flush=True)
        code = tf.poll_verification_code(timeout_secs=60)
        print("POLL RESULT CODE:", code, flush=True)
    else:
        print(f"Response status was {found_status}, not 200/204.", flush=True)
        
finally:
    driver.quit()
    if os.path.exists(ext_path):
        os.remove(ext_path)
