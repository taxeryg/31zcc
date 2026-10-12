import sys
import os
import time
import json
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

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
    except:
        pass
    time.sleep(1)
    
    driver.execute_script("document.querySelector('button[data-testid=\"sign-up\"]').click();")
    time.sleep(3)
    
    # Fill inputs
    driver.find_element(By.CSS_SELECTOR, 'input[name="email"]').send_keys("denemehesap9981@gmail.com")
    bday = driver.find_element(By.CSS_SELECTOR, 'input[name="birthdate"]')
    bday.send_keys("12121995")
    driver.find_element(By.CSS_SELECTOR, 'input[name="username"]').send_keys("deneme_hesap_9981")
    p = driver.find_element(By.CSS_SELECTOR, 'input[name="password"]')
    p.send_keys("Sifre123456!*")
    time.sleep(1)
    
    # Clear performance logs
    driver.get_log("performance")
    
    # Press ENTER on password field
    print("Sending RETURN on password field...", flush=True)
    p.send_keys(Keys.RETURN)
    time.sleep(3)
    
    # Check if network request happened
    logs = driver.get_log("performance")
    api_calls = []
    for l in logs:
        m = l.get("message", "")
        if "Network.requestWillBeSent" in m and "kick.com" in m:
            api_calls.append(m)
            
    print(f"Captured {len(api_calls)} kick network requests after pressing Enter.", flush=True)
    for c in api_calls[:10]:
        try:
            parsed = json.loads(c)
            req = parsed.get("message", {}).get("params", {}).get("request", {})
            print("REQ URL:", req.get("url"), "METHOD:", req.get("method"), flush=True)
        except:
            pass

    # Check console errors
    console_logs = driver.execute_script("return window.performance.getEntriesByType('resource').map(r => r.name);")
    print("Resource entries with kick:", [r for r in console_logs if "api" in r or "register" in r or "auth" in r], flush=True)

finally:
    driver.quit()
