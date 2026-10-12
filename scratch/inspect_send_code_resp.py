import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
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
    
    # Click Sign Up
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
    print(f"Testing signup with: {email} | {username}", flush=True)
    
    em_el = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="email"]')))
    em_el.send_keys(email)
    
    driver.find_element(By.CSS_SELECTOR, 'input[name="birthdate"]').send_keys("15051996")
    driver.find_element(By.CSS_SELECTOR, 'input[name="username"]').send_keys(username)
    p = driver.find_element(By.CSS_SELECTOR, 'input[name="password"]')
    p.send_keys(password)
    time.sleep(1)
    
    # Clear performance log
    driver.get_log("performance")
    
    # Click Submit
    driver.execute_script("""
        let em = document.querySelector('input[name="email"]');
        let form = em.closest('form');
        let btn = form.querySelector('button[type="submit"]');
        if (btn) btn.click();
    """)
    p.send_keys(Keys.RETURN)
    print("Form submitted. Waiting for response...", flush=True)
    
    time.sleep(6)
    
    # Check on-screen errors
    screen_info = driver.execute_script("""
        let alerts = Array.from(document.querySelectorAll('[role="alert"], [class*="error"], span.text-danger, p.text-danger, [data-testid*="error"]')).map(e => e.innerText.trim()).filter(Boolean);
        let inputs = Array.from(document.querySelectorAll('input')).map(i => ({name: i.name, type: i.type, val: i.value}));
        let modalHeading = document.querySelector('h1, h2, h3, [role="dialog"]') ? (document.querySelector('h1, h2, h3, [role="dialog"]').innerText.trim()) : '';
        return {
            alerts: alerts,
            modalHeading: modalHeading,
            inputs: inputs
        };
    """)
    print("Screen info:", screen_info, flush=True)
    
    # Inspect performance logs for send-verification-code response
    logs = driver.get_log("performance")
    req_ids = []
    for entry in logs:
        m = entry.get("message", "")
        if "send-verification-code" in m:
            print("LOG EVENT:", m[:350], flush=True)
            if "Network.responseReceived" in m:
                try:
                    obj = json.loads(m)
                    req_id = obj["message"]["params"]["requestId"]
                    status = obj["message"]["params"]["response"]["status"]
                    print(f"send-verification-code STATUS: {status}, req_id: {req_id}", flush=True)
                    try:
                        body = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": req_id})
                        print("RESPONSE BODY:", body, flush=True)
                    except Exception as e_cdp:
                        print("CDP getResponseBody error:", e_cdp, flush=True)
                except Exception as e_p:
                    print("Parse error:", e_p, flush=True)
                    
finally:
    driver.quit()
