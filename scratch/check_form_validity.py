import time, undetected_chromedriver as uc
from selenium.webdriver.common.by import By

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
    except Exception:
        pass
    time.sleep(1)
    
    driver.execute_script("""
        for (let b of document.querySelectorAll('button')) {
            if (b.innerText.trim().toLowerCase() === 'sign up') { b.click(); break; }
        }
    """)
    time.sleep(3)
    
    driver.find_element(By.CSS_SELECTOR, 'input[name="email"]').send_keys("testuser9921@gmail.com")
    driver.find_element(By.CSS_SELECTOR, 'input[name="birthdate"]').send_keys("15051996")
    driver.find_element(By.CSS_SELECTOR, 'input[name="username"]').send_keys("testuser9921")
    p = driver.find_element(By.CSS_SELECTOR, 'input[name="password"]')
    p.send_keys("Password12345!*")
    time.sleep(1)
    
    res = driver.execute_script("""
        let em = document.querySelector('input[name="email"]');
        let form = em.closest('form');
        let btn = form.querySelector('button[type="submit"]');
        
        let inputs = Array.from(form.querySelectorAll('input')).map(i => ({
            name: i.name,
            value: i.value,
            valid: i.checkValidity(),
            validationMessage: i.validationMessage
        }));
        
        let btnDisabled = btn ? btn.disabled : 'no_btn';
        let turnstile = document.querySelectorAll('iframe[src*="cloudflare"], iframe[src*="turnstile"], div[class*="turnstile"], div[id*="turnstile"]');
        let turnstileDetails = Array.from(turnstile).map(t => t.outerHTML.slice(0, 100));
        
        return {
            inputs: inputs,
            btnDisabled: btnDisabled,
            turnstileCount: turnstile.length,
            turnstileDetails: turnstileDetails
        };
    """)
    print("Form validity:", res)
    
    # Now click the button with ActionChains or real click
    btn = driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]')
    print("Clicking submit button via driver click...", flush=True)
    btn.click()
    
    time.sleep(3)
    after_click = driver.execute_script("""
        let errs = Array.from(document.querySelectorAll('[role="alert"], [class*="error"], span.text-danger, p.text-danger')).map(e => e.innerText.trim()).filter(Boolean);
        let iframes = Array.from(document.querySelectorAll('iframe')).map(f => f.src);
        let codeInputs = document.querySelectorAll('input[inputmode="numeric"], input[autocomplete="one-time-code"]');
        return {
            errors: errs,
            codeInputs: codeInputs.length,
            iframes: iframes
        };
    """)
    print("After click:", after_click)
finally:
    driver.quit()
