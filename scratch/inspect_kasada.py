import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import undetected_chromedriver as uc

opts = uc.ChromeOptions()
opts.add_argument("--window-size=1920,1080")
opts.add_argument("--headless=new")
opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})
driver = uc.Chrome(options=opts, use_subprocess=True)

try:
    driver.get("https://kick.com")
    time.sleep(8)
    
    kasada_state = driver.execute_script("""
        let scripts = Array.from(document.querySelectorAll('script')).map(s => s.src).filter(s => s.includes('149e9513') || s.includes('p.js') || s.includes('kpsdk'));
        let cookies = document.cookie;
        let windowKeys = Object.keys(window).filter(k => k.toLowerCase().includes('kpsdk') || k.toLowerCase().includes('kasada'));
        return {
            scripts: scripts,
            cookies: cookies,
            windowKeys: windowKeys
        };
    """)
    print("Kasada state on home page:", json.dumps(kasada_state, indent=2))
    
    # Now open Sign Up modal
    driver.execute_script("""
        for (let b of document.querySelectorAll('button')) {
            if (b.innerText.trim().toLowerCase() === 'sign up') {
                b.click();
                break;
            }
        }
    """)
    time.sleep(6)
    
    kasada_modal_state = driver.execute_script("""
        let scripts = Array.from(document.querySelectorAll('script')).map(s => s.src).filter(s => s.includes('149e9513') || s.includes('p.js') || s.includes('kpsdk'));
        let cookies = document.cookie;
        let windowKeys = Object.keys(window).filter(k => k.toLowerCase().includes('kpsdk') || k.toLowerCase().includes('kasada'));
        return {
            scripts: scripts,
            cookies: cookies,
            windowKeys: windowKeys
        };
    """)
    print("Kasada state after modal open:", json.dumps(kasada_modal_state, indent=2))
    
    # Check all cookies
    cd = driver.get_cookies()
    print("All driver cookies:")
    for c in cd:
        print(f"  {c['name']} = {c['value'][:40]}... (domain={c.get('domain')})")
        
finally:
    driver.quit()
