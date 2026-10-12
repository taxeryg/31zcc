import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
import time
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
    
    # Accept cookies
    for b in driver.find_elements(By.TAG_NAME, "button"):
        if "accept" in b.text.lower():
            driver.execute_script("arguments[0].click();", b)
            break
    time.sleep(1)
    
    for b in driver.find_elements(By.TAG_NAME, "button"):
        if b.text.strip().lower() in ["sign up", "kaydol"]:
            driver.execute_script("arguments[0].click();", b)
            break
    time.sleep(3)
    
    tf = kac.TempTfMailClient()
    mb = tf.create_mailbox()
    email = mb["email"]
    username = kac.generate_username()
    password = kac.generate_password()
    print(f"Submitting: {email} / {username}", flush=True)
    
    driver.find_element(By.CSS_SELECTOR, 'input[name="email"]').send_keys(email)
    driver.find_element(By.CSS_SELECTOR, 'input[name="birthdate"]').send_keys("15051996")
    driver.find_element(By.CSS_SELECTOR, 'input[name="username"]').send_keys(username)
    p = driver.find_element(By.CSS_SELECTOR, 'input[name="password"]')
    p.send_keys(password)
    time.sleep(1)
    
    driver.get_log("performance")
    
    # Click button in form
    driver.execute_script("""
        let em = document.querySelector('input[name="email"]');
        let form = em.closest('form');
        let btn = form.querySelector('button[type="submit"]');
        btn.click();
    """)
    p.send_keys(Keys.RETURN)
    
    # Listen to responses for 10 seconds
    for _ in range(5):
        time.sleep(2)
        logs = driver.get_log("performance")
        for entry in logs:
            msg = entry.get("message", "")
            if "responseReceived" in msg and "send-verification-code" in msg:
                print("RAW RESPONSE EVENT:", msg[:400], flush=True)
            if "Network.requestWillBeSent" in msg and "send-verification-code" in msg:
                print("RAW REQUEST EVENT:", msg[:400], flush=True)

finally:
    driver.quit()
