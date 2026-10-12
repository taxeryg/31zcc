import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By

opts = uc.ChromeOptions()
opts.add_argument("--window-size=1920,1080")
opts.add_argument("--headless=new")
driver = uc.Chrome(options=opts, use_subprocess=True)

try:
    print("Navigating to https://kick.com...", flush=True)
    driver.get("https://kick.com")
    time.sleep(5)
    print("Current URL:", driver.current_url, flush=True)
    print("Page Title:", driver.title, flush=True)
    
    # Check buttons
    btns = driver.execute_script("""
        return Array.from(document.querySelectorAll('button, a')).map(el => ({
            tag: el.tagName,
            text: el.innerText.trim(),
            href: el.getAttribute('href') || '',
            testid: el.getAttribute('data-testid') || '',
            aria: el.getAttribute('aria-label') || ''
        })).filter(x => x.text || x.testid || x.aria);
    """)
    print(f"Found {len(btns)} buttons/links. Sample:")
    for b in btns[:30]:
        print("  ", b)
        
    driver.save_screenshot("scratch/kick_home.png")
    
    # Now try clicking Sign up if found
    for b in driver.find_elements(By.TAG_NAME, "button"):
        t = b.text.strip().lower()
        if "sign up" in t or "kaydol" in t or "kayıt" in t:
            print("Found signup button via text:", b.text)
            driver.execute_script("arguments[0].click();", b)
            break
            
    time.sleep(3)
    driver.save_screenshot("scratch/kick_after_signup_click.png")
    
    inputs = driver.execute_script("""
        return Array.from(document.querySelectorAll('input')).map(i => ({
            name: i.name,
            type: i.type,
            placeholder: i.placeholder,
            id: i.id
        }));
    """)
    print("Inputs on page after click:", inputs)
finally:
    driver.quit()
