import sys
import os
import time
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

opts = uc.ChromeOptions()
opts.add_argument("--window-size=1920,1080")
opts.add_argument("--headless=new")
driver = uc.Chrome(options=opts, use_subprocess=True)

try:
    driver.get("https://kick.com")
    time.sleep(5)
    
    # Cookie accept
    try:
        driver.find_element(By.ID, "onetrust-accept-btn-handler").click()
    except:
        pass
    time.sleep(1)
    
    # Open sign up
    driver.execute_script("document.querySelector('button[data-testid=\"sign-up\"]').click();")
    time.sleep(3)
    
    # Let's inspect React props on the form or inputs
    print("Inspecting React props...", flush=True)
    res = driver.execute_script("""
        let em = document.querySelector('input[name="email"]');
        let form = em.closest('form');
        let btn = form.querySelector('button[type="submit"]');
        return {
            formAction: form.action,
            btnDisabled: btn.disabled,
            btnClass: btn.className,
            btnText: btn.innerText
        };
    """)
    print("Pre-fill info:", res, flush=True)
    
    # Let's type using send_keys
    em = driver.find_element(By.CSS_SELECTOR, 'input[name="email"]')
    em.click()
    em.send_keys("testuser99281@gmail.com")
    time.sleep(0.5)
    
    bday = driver.find_element(By.CSS_SELECTOR, 'input[name="birthdate"], input[type="date"]')
    bday.click()
    bday.send_keys("12121998")
    time.sleep(0.5)
    
    u = driver.find_element(By.CSS_SELECTOR, 'input[name="username"]')
    u.click()
    u.send_keys("neon_rider_9921")
    time.sleep(0.5)
    
    p = driver.find_element(By.CSS_SELECTOR, 'input[name="password"]')
    p.click()
    p.send_keys("Aa123456789!#%")
    time.sleep(1)
    
    # Check what React thinks now
    check = driver.execute_script("""
        let em = document.querySelector('input[name="email"]');
        let form = em.closest('form');
        let btn = form.querySelector('button[type="submit"]');
        return {
            emVal: em.value,
            bdayVal: document.querySelector('input[name="birthdate"]').value,
            uVal: document.querySelector('input[name="username"]').value,
            pVal: document.querySelector('input[name="password"]').value,
            btnDisabled: btn.disabled,
            btnAriaDisabled: btn.getAttribute('aria-disabled')
        };
    """)
    print("Post-fill check:", check, flush=True)
    
    # Now click submit button using ActionChains (physical click simulation)
    btn_el = driver.find_element(By.CSS_SELECTOR, 'form button[type="submit"]')
    print("Performing ActionChains click on submit button...", flush=True)
    ActionChains(driver).move_to_element(btn_el).click().perform()
    
    for i in range(5):
        time.sleep(2)
        r = driver.execute_script("""
            let cf = document.querySelectorAll('iframe[src*="cloudflare"], iframe[src*="turnstile"], div.cf-turnstile');
            let errs = Array.from(document.querySelectorAll('form p, form span, [role="alert"]')).map(e => e.innerText).filter(t => t.length > 0 && t.length < 100);
            return {
                cfCount: cf.length,
                errs: errs,
                url: window.location.href
            };
        """)
        print(f"[{i*2}s state]:", r, flush=True)
        
    driver.save_screenshot("scratch/test_actionchains.png")
    print("Saved scratch/test_actionchains.png", flush=True)
finally:
    driver.quit()
