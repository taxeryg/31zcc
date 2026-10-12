import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import kick_account_creator as kac

opts = uc.ChromeOptions()
opts.add_argument("--window-size=1920,1080")
opts.add_argument("--headless=new")
opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})
driver = uc.Chrome(options=opts, use_subprocess=True)

try:
    driver.get("https://kick.com")
    time.sleep(5)
    try:
        driver.find_element(By.ID, "onetrust-accept-btn-handler").click()
    except Exception:
        pass
    time.sleep(1)
    
    driver.execute_script("""
        for (let b of document.querySelectorAll('button')) {
            if (b.innerText.trim().toLowerCase() === 'sign up') {
                b.click();
                break;
            }
        }
    """)
    time.sleep(3)
    
    tf = kac.TempTfMailClient()
    mb = tf.create_mailbox()
    email = mb["email"]
    username = kac.generate_username()
    password = kac.generate_password()
    print("Creating account:", username, "|", email, flush=True)
    
    driver.find_element(By.CSS_SELECTOR, 'input[name="email"]').send_keys(email)
    driver.find_element(By.CSS_SELECTOR, 'input[name="birthdate"]').send_keys("15051996")
    driver.find_element(By.CSS_SELECTOR, 'input[name="username"]').send_keys(username)
    p = driver.find_element(By.CSS_SELECTOR, 'input[name="password"]')
    p.send_keys(password)
    time.sleep(1)
    
    driver.execute_script("""
        let em = document.querySelector('input[name="email"]');
        let container = em.closest('form') || em.closest('[class*="modal"]') || em.parentElement.parentElement.parentElement.parentElement;
        let btn = container.querySelector('button[type="submit"]');
        if (btn) btn.click();
    """)
    p.send_keys(Keys.RETURN)
    print("Form submitted, waiting for OTP...", flush=True)
    
    code = tf.poll_verification_code(timeout_secs=60)
    print("Code received:", code, flush=True)
    
    if code:
        time.sleep(2)
        driver.get_log("performance") # clear before OTP submit
        
        inps = driver.find_elements(By.CSS_SELECTOR, 'input[inputmode="numeric"], input[autocomplete="one-time-code"]')
        if len(inps) == 6:
            for i in range(6):
                inps[i].click()
                inps[i].send_keys(code[i])
                time.sleep(0.08)
        elif len(inps) == 1:
            inps[0].send_keys(code)
            
        time.sleep(1)
        driver.execute_script("""
            let inps = document.querySelectorAll('input[inputmode="numeric"], input[autocomplete="one-time-code"]');
            let container = inps.length > 0 ? (inps[0].closest('form') || inps[0].closest('[role="dialog"]') || inps[0].parentElement.parentElement) : document;
            let btn = container.querySelector('button[type="submit"]') || Array.from(container.querySelectorAll('button')).find(b => {
                let t = b.innerText.trim().toLowerCase();
                return t.includes('verify') || t.includes('onayla') || t.includes('continue');
            });
            if (btn) btn.click();
        """)
        
        print("OTP submitted, inspecting network responses for 10 seconds...", flush=True)
        for s in range(5):
            time.sleep(2)
            logs = driver.get_log("performance")
            for entry in logs:
                m = entry.get("message", "")
                if "Network.responseReceived" in m:
                    try:
                        obj = json.loads(m)
                        params = obj["message"]["params"]
                        url = params["response"]["url"]
                        req_id = params["requestId"]
                        status = params["response"]["status"]
                        if any(kw in url for kw in ["verify", "signup", "login", "user", "token", "identity"]):
                            print(f"RESPONSE [{status}] {url} (req_id={req_id})", flush=True)
                            try:
                                body = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": req_id})
                                print(f"BODY [{url}]: {body['body'][:300]}", flush=True)
                            except Exception as e_cdp:
                                print(f"CDP error for {url}: {e_cdp}", flush=True)
                    except Exception:
                        pass
finally:
    driver.quit()
