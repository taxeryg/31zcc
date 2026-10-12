import time
import undetected_chromedriver as uc

opts = uc.ChromeOptions()
opts.add_argument('--headless=new')
driver = uc.Chrome(options=opts, use_subprocess=True)
try:
    driver.get('https://kick.com')
    time.sleep(5)
    
    # Click Sign up
    driver.execute_script("""
        for (let b of document.querySelectorAll('button')) {
            if (b.innerText.trim().toLowerCase() === 'sign up') {
                b.click();
                break;
            }
        }
    """)
    time.sleep(3)
    
    # Inspect modal buttons
    btns = driver.execute_script("""
        let res = [];
        let modal = document.querySelector('div[role="dialog"]');
        if (!modal) return ['no modal'];
        let elements = modal.querySelectorAll('button, [role="button"], input[type="submit"]');
        for (let el of elements) {
            res.push({
                tag: el.tagName,
                type: el.getAttribute('type'),
                text: el.innerText.trim(),
                className: el.className,
                ariaLabel: el.getAttribute('aria-label')
            });
        }
        return res;
    """)
    print("Modal elements:", btns)
finally:
    driver.quit()
