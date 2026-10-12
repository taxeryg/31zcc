import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import time
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import kick_account_creator as kac

print("Testing non-headless genuine Chrome window (Bypassing Kasada CDP hooks)...", flush=True)

opts = uc.ChromeOptions()
opts.add_argument("--window-size=1280,800")
# NO headless, NO loggingPrefs (CDP flag trigger)
driver = uc.Chrome(options=opts, use_subprocess=True)

try:
    print("1. Opening kick.com...", flush=True)
    driver.get("https://kick.com")
    time.sleep(5)
    
    # Accept cookies
    for b in driver.find_elements(By.TAG_NAME, "button"):
        if "accept" in b.text.lower():
            b.click()
            break
    time.sleep(2)
    
    # Click Sign Up
    for b in driver.find_elements(By.TAG_NAME, "button"):
        if b.text.strip().lower() in ["sign up", "kaydol"]:
            b.click()
            break
    time.sleep(3)
    
    # Create temp mail
    tf = kac.TempTfMailClient()
    mb = tf.create_mailbox()
    email = mb["email"]
    username = kac.generate_username()
    password = kac.generate_password()
    print(f"Data: {email} | {username} | {password}", flush=True)
    
    em_el = WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="email"]')))
    em_el.send_keys(email)
    time.sleep(0.5)
    
    bday_el = driver.find_element(By.CSS_SELECTOR, 'input[name="birthdate"]')
    bday_el.send_keys("15051996")
    time.sleep(0.5)
    
    u_el = driver.find_element(By.CSS_SELECTOR, 'input[name="username"]')
    u_el.send_keys(username)
    time.sleep(0.5)
    
    p_el = driver.find_element(By.CSS_SELECTOR, 'input[name="password"]')
    p_el.send_keys(password)
    time.sleep(1)
    
    # Submit
    print("Submitting form in visible window...", flush=True)
    driver.execute_script("""
        let em = document.querySelector('input[name="email"]');
        let form = em.closest('form');
        let btn = form.querySelector('button[type="submit"]');
        if (btn) btn.click();
    """)
    p_el.send_keys(Keys.RETURN)
    
    # Wait and check if OTP code appears on screen or errors
    for i in range(15):
        time.sleep(2)
        otp_len = driver.execute_script("return document.querySelectorAll('input[inputmode=\"numeric\"]').length;")
        errs = driver.execute_script("return Array.from(document.querySelectorAll('form [class*=\"error\"], [role=\"alert\"]')).map(e => e.innerText.trim()).filter(Boolean);")
        print(f"[{i*2}s] OTP inputs: {otp_len} | Visible errors: {errs}", flush=True)
        if otp_len > 0:
            print("OTP SCREEN REACHED! Checking mailbox...", flush=True)
            code = tf.poll_verification_code(timeout_secs=45)
            print("MAILBOX CODE:", code, flush=True)
            break

finally:
    time.sleep(5)
    driver.quit()
    print("Test finished.", flush=True)
