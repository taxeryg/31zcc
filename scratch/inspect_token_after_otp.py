import sys, os, time, json, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import kick_account_creator as kac

raw = random.choice(kac.PROXY_POOL)
ip, port, user, pwd = raw.split(":")
print(f"Using proxy: {ip}:{port}", flush=True)

bridge = kac.LocalAuthProxyBridge(ip, int(port), user, pwd)
bridge_url = bridge.start()

opts = uc.ChromeOptions()
opts.add_argument("--window-size=1920,1080")
opts.add_argument("--headless=new")
opts.add_argument(f"--proxy-server={bridge_url}")
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
    
    tf = kac.TempTfMailClient(proxy_dict={"http": f"http://{user}:{pwd}@{ip}:{port}", "https": f"http://{user}:{pwd}@{ip}:{port}"})
    mb = tf.create_mailbox()
    email = mb["email"]
    username = kac.generate_username()
    password = kac.generate_password()
    bday = kac.generate_birthdate()
    print(f"Creating account: {username} | {email}", flush=True)
    
    driver.find_element(By.CSS_SELECTOR, 'input[name="email"]').send_keys(email)
    driver.find_element(By.CSS_SELECTOR, 'input[name="birthdate"]').send_keys("15051996")
    driver.find_element(By.CSS_SELECTOR, 'input[name="username"]').send_keys(username)
    p_el = driver.find_element(By.CSS_SELECTOR, 'input[name="password"]')
    p_el.send_keys(password)
    time.sleep(1)
    
    driver.execute_script("""
        let em = document.querySelector('input[name="email"]');
        let form = em.closest('form');
        let btn = form.querySelector('button[type="submit"]');
        if (btn) btn.click();
    """)
    p_el.send_keys(Keys.RETURN)
    print("Form submitted, waiting for OTP...", flush=True)
    
    code = tf.poll_verification_code(timeout_secs=60)
    print(f"OTP Code received: {code}", flush=True)
    
    if code:
        time.sleep(2)
        driver.get_log("performance") # clear performance logs before OTP submit
        
        inps = driver.find_elements(By.CSS_SELECTOR, 'input[inputmode="numeric"], input[autocomplete="one-time-code"], input[name*="code"], input[data-testid*="code"]')
        print(f"Found {len(inps)} OTP inputs", flush=True)
        if len(inps) == 6:
            for idx, ch in enumerate(code[:6]):
                inps[idx].click()
                inps[idx].clear()
                inps[idx].send_keys(ch)
                time.sleep(0.08)
        elif len(inps) == 1:
            inps[0].click()
            inps[0].clear()
            inps[0].send_keys(code)
            
        time.sleep(1)
        driver.execute_script("""
            let inps = document.querySelectorAll('input[inputmode="numeric"], input[autocomplete="one-time-code"]');
            let container = inps.length > 0 ? (inps[0].closest('form') || inps[0].closest('[role="dialog"]') || inps[0].parentElement.parentElement) : document;
            let btn = container.querySelector('button[type="submit"]') || Array.from(container.querySelectorAll('button')).find(b => {
                let t = b.innerText.trim().toLowerCase();
                return t.includes('verify') || t.includes('onayla') || t.includes('continue') || t.includes('devam') || t.includes('accept');
            });
            if (btn) btn.click();
        """)
        if inps:
            inps[-1].send_keys(Keys.RETURN)
            
        print("OTP submitted! Monitoring responses for 10 seconds...", flush=True)
        for i in range(5):
            time.sleep(2)
            ls = driver.execute_script("return JSON.stringify({...window.localStorage, ...window.sessionStorage});")
            ck = driver.get_cookies()
            print(f"[{i*2}s] LocalStorage keys: {list(json.loads(ls).keys()) if ls else []}", flush=True)
            print(f"[{i*2}s] Cookies count: {len(ck)}", flush=True)
            for c in ck:
                print(f"Cookie: {c['name']} = {c['value'][:30]}...", flush=True)
                
            logs = driver.get_log("performance")
            for entry in logs:
                m = entry.get("message", "")
                if "verify" in m or "login" in m or "token" in m or "user" in m or "auth" in m:
                    if "Network.responseReceived" in m:
                        print("PERF RESPONSE:", m[:300], flush=True)
                        try:
                            obj = json.loads(m)
                            req_id = obj["message"]["params"]["requestId"]
                            url = obj["message"]["params"]["response"]["url"]
                            status = obj["message"]["params"]["response"]["status"]
                            print(f"URL: {url} | STATUS: {status} | REQ_ID: {req_id}", flush=True)
                            try:
                                body = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": req_id})
                                print(f"BODY for {url}: {body}", flush=True)
                            except Exception as e_cdp:
                                print("CDP error:", e_cdp, flush=True)
                        except Exception:
                            pass
finally:
    driver.quit()
    bridge.stop()
