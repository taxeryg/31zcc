import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import time
import json
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

opts = uc.ChromeOptions()
opts.add_argument("--window-size=1920,1080")
opts.add_argument("--headless=new")
opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})
driver = uc.Chrome(options=opts, use_subprocess=True)

try:
    print("Navigating to kick.com...", flush=True)
    driver.get("https://kick.com")
    time.sleep(5)
    
    try:
        driver.find_element(By.ID, "onetrust-accept-btn-handler").click()
    except:
        pass
    time.sleep(1)
    
    signup_btn = None
    try:
        signup_btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-testid="sign-up"]'))
        )
    except:
        pass
    if not signup_btn:
        for b in driver.find_elements(By.TAG_NAME, "button"):
            if b.text.strip().lower() in ["sign up", "kayıt ol", "kaydol"]:
                signup_btn = b
                break
    driver.execute_script("arguments[0].click();", signup_btn)
    time.sleep(3)
    
    import kick_account_creator as kac
    tf = kac.TempTfMailClient()
    mb = tf.create_mailbox()
    email = mb["email"]
    username = kac.generate_username()
    password = kac.generate_password()
    print(f"Data: {email} | {username} | {password}", flush=True)
    
    em_el = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="email"]')))
    em_el.send_keys(email)
    
    bday = driver.find_element(By.CSS_SELECTOR, 'input[name="birthdate"]')
    bday.send_keys("15051996")
    
    u_el = driver.find_element(By.CSS_SELECTOR, 'input[name="username"]')
    u_el.send_keys(username)
    
    p = driver.find_element(By.CSS_SELECTOR, 'input[name="password"]')
    p.send_keys(password)
    time.sleep(1)
    
    # Form submission: find button inside the same form as email
    submitted = driver.execute_script("""
        let em = document.querySelector('input[name="email"]');
        let form = em.closest('form');
        let btn = form.querySelector('button[type="submit"]');
        if (btn) {
            btn.click();
            return 'button_clicked';
        }
        form.requestSubmit();
        return 'form_submitted';
    """)
    print("Submit JS executed:", submitted, flush=True)
    p.send_keys(Keys.RETURN)
    print("Sent RETURN on password.", flush=True)
    
    time.sleep(5)
    
    # Check if network request happened
    logs = driver.get_log("performance")
    for l in logs:
        m = l.get("message", "")
        if "send-verification-code" in m:
            print("FOUND LOG:", m[:200], flush=True)
            
    print("Polling temp.tf for 45s...", flush=True)
    code = tf.poll_verification_code(timeout_secs=45)
    print("RECEIVED VERIFICATION CODE:", code, flush=True)
    
    driver.save_screenshot("scratch/test_code_arrival.png")

finally:
    driver.quit()
