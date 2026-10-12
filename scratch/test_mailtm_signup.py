import sys, os, time, json, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import kick_account_creator as kac

# 1. Test MailTm
print("Getting Mail.tm email...", flush=True)
mt = kac.MailTmClient()
mb = mt.create_mailbox()
email = mb["email"]
username = kac.generate_username()
password = kac.generate_password()
print(f"Generated email from Mail.tm: {email}", flush=True)

# Pick proxy
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
    driver.get("https://kick.com")
    time.sleep(6)
    
    driver.execute_script("""
        for (let b of document.querySelectorAll('button')) {
            let t = b.innerText.trim().toLowerCase();
            if (t.includes('accept') || t.includes('kabul') || b.id === 'onetrust-accept-btn-handler') {
                b.click();
            }
        }
    """)
    time.sleep(1)
    
    driver.execute_script("""
        for (let b of document.querySelectorAll('button, a')) {
            let t = b.innerText.trim().toLowerCase();
            let testid = b.getAttribute('data-testid') || '';
            if (testid === 'sign-up' || t === 'sign up' || t === 'kaydol') {
                b.click();
                break;
            }
        }
    """)
    time.sleep(3)
    
    em_input = driver.find_element(By.CSS_SELECTOR, 'input[name="email"]')
    em_input.send_keys(email)
    driver.find_element(By.CSS_SELECTOR, 'input[name="birthdate"]').send_keys("15051996")
    driver.find_element(By.CSS_SELECTOR, 'input[name="username"]').send_keys(username)
    p = driver.find_element(By.CSS_SELECTOR, 'input[name="password"]')
    p.send_keys(password)
    time.sleep(1)
    
    # Check if there is an instant validation error on email field!
    instant_error = driver.execute_script("""
        let em = document.querySelector('input[name="email"]');
        let form = em.closest('form');
        let errs = Array.from(form.querySelectorAll('[role="alert"], [class*="error"], span.text-danger, p.text-danger')).map(e => e.innerText.trim()).filter(Boolean);
        return {
            valid: em.checkValidity(),
            validationMessage: em.validationMessage,
            errors: errs
        };
    """)
    print("Email field validation before submit:", instant_error, flush=True)
    
    driver.get_log("performance")
    
    # Submit
    driver.execute_script("""
        let em = document.querySelector('input[name="email"]');
        let form = em.closest('form');
        let btn = form.querySelector('button[type="submit"]');
        if (btn) btn.click();
    """)
    p.send_keys(Keys.RETURN)
    print("Form submitted. Checking response for Mail.tm...", flush=True)
    
    time.sleep(5)
    
    logs = driver.get_log("performance")
    for entry in logs:
        m = entry.get("message", "")
        if "send-verification-code" in m and "Network.responseReceived" in m:
            obj = json.loads(m)
            status = obj["message"]["params"]["response"]["status"]
            req_id = obj["message"]["params"]["requestId"]
            print(f"--> send-verification-code STATUS for {email}: {status}, req_id: {req_id}", flush=True)
            try:
                body = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": req_id})
                print("--> RESPONSE BODY:", body, flush=True)
            except Exception as e:
                print("CDP err:", e)
                
    post_error = driver.execute_script("""
        let alerts = Array.from(document.querySelectorAll('[role="alert"], [class*="error"], span.text-danger, p.text-danger')).map(e => e.innerText.trim()).filter(Boolean);
        return alerts;
    """)
    print("On-screen alerts post-submit:", post_error, flush=True)
    
finally:
    driver.quit()
    if os.path.exists(ext_path):
        os.remove(ext_path)
