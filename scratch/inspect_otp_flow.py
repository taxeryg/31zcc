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
    print("Creating:", email, username, flush=True)
    driver.find_element(By.CSS_SELECTOR, 'input[name="email"]').send_keys(email)
    driver.find_element(By.CSS_SELECTOR, 'input[name="birthdate"]').send_keys("15051996")
    driver.find_element(By.CSS_SELECTOR, 'input[name="username"]').send_keys(username)
    p = driver.find_element(By.CSS_SELECTOR, 'input[name="password"]')
    p.send_keys(password)
    time.sleep(1)
    driver.execute_script("""
        let em = document.querySelector('input[name="email"]');
        let form = em.closest('form');
        let btn = form.querySelector('button[type="submit"]');
        btn.click();
    """)
    p.send_keys(Keys.RETURN)
    print("Form submitted, waiting for code...", flush=True)
    code = tf.poll_verification_code(timeout_secs=45)
    print("Code received:", code, flush=True)
    if code:
        time.sleep(2)
        inps = driver.find_elements(By.CSS_SELECTOR, 'input[inputmode="numeric"], input[autocomplete="one-time-code"], input[name*="code"]')
        print("Found code inputs count:", len(inps), flush=True)
        driver.save_screenshot("scratch/debug_before_otp.png")
        
        # Enter code
        driver.execute_script("""
            const code = arguments[0];
            let inps = document.querySelectorAll('input[inputmode="numeric"], input[autocomplete="one-time-code"], input[name*="code"]');
            if (inps.length === 6) {
                for (let i = 0; i < 6; i++) {
                    inps[i].focus();
                    inps[i].value = code[i];
                    inps[i].dispatchEvent(new Event('input', { bubbles: true }));
                    inps[i].dispatchEvent(new Event('change', { bubbles: true }));
                }
            } else if (inps.length === 1) {
                inps[0].focus();
                inps[0].value = code;
                inps[0].dispatchEvent(new Event('input', { bubbles: true }));
                inps[0].dispatchEvent(new Event('change', { bubbles: true }));
            }
        """, code)
        time.sleep(1)
        
        # Check buttons
        buttons = driver.execute_script("""
            return Array.from(document.querySelectorAll('button')).map(b => ({
                text: b.innerText.trim(),
                type: b.getAttribute('type'),
                disabled: b.disabled,
                classes: b.className
            }));
        """)
        print("Buttons on OTP page:", buttons, flush=True)
        
        # Click submit button
        clicked = driver.execute_script("""
            let inps = document.querySelectorAll('input[inputmode="numeric"], input[autocomplete="one-time-code"]');
            let container = inps.length > 0 ? (inps[0].closest('form') || inps[0].closest('[role="dialog"]') || inps[0].parentElement.parentElement) : document;
            let btn = container.querySelector('button[type="submit"]') || Array.from(container.querySelectorAll('button')).find(b => {
                let t = b.innerText.trim().toLowerCase();
                return t.includes('verify') || t.includes('onayla') || t.includes('continue') || t.includes('devam') || t.includes('accept');
            });
            if (btn) {
                btn.click();
                return btn.innerText.trim();
            }
            return null;
        """)
        print("Clicked button:", clicked, flush=True)
        
        # Wait 10 seconds and check logs
        for s in range(5):
            time.sleep(2)
            logs = driver.get_log("performance")
            for entry in logs:
                msg = entry.get("message", "")
                if "register" in msg or "verify" in msg or "token" in msg.lower() or "auth" in msg.lower():
                    if "Network.responseReceived" in msg:
                        print("INTERESTING RESPONSE:", msg[:300], flush=True)
                        
        driver.save_screenshot("scratch/debug_after_otp.png")
        print("Saved debug_after_otp.png", flush=True)
finally:
    driver.quit()
