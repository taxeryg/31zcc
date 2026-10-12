import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import undetected_chromedriver as uc

opts = uc.ChromeOptions()
opts.add_argument("--window-size=1920,1080")
opts.add_argument("--headless=new")
driver = uc.Chrome(options=opts, use_subprocess=True)

try:
    driver.get("https://kick.com")
    time.sleep(5)
    
    # Check isReady
    ready = driver.execute_script("""
        if (window.KPSDK && window.KPSDK.isReady) {
            try {
                let res = window.KPSDK.isReady();
                return {
                    type: typeof res,
                    isPromise: res instanceof Promise,
                    val: String(res)
                };
            } catch(e) {
                return { err: e.message };
            }
        }
        return 'no_kpsdk';
    """)
    print("KPSDK isReady result:", ready)
finally:
    driver.quit()
