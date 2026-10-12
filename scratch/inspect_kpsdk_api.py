import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import undetected_chromedriver as uc

opts = uc.ChromeOptions()
opts.add_argument("--window-size=1920,1080")
opts.add_argument("--headless=new")
driver = uc.Chrome(options=opts, use_subprocess=True)

try:
    driver.get("https://kick.com")
    time.sleep(6)
    
    kpsdk_info = driver.execute_script("""
        if (!window.KPSDK) return "No KPSDK";
        let keys = Object.keys(window.KPSDK);
        let protoKeys = Object.getOwnPropertyNames(Object.getPrototypeOf(window.KPSDK) || {});
        let vals = {};
        for (let k of keys) {
            try {
                vals[k] = typeof window.KPSDK[k] === 'function' ? 'function' : window.KPSDK[k];
            } catch(e) {
                vals[k] = 'err';
            }
        }
        return {
            keys: keys,
            protoKeys: protoKeys,
            vals: vals
        };
    """)
    print("KPSDK details:", json.dumps(kpsdk_info, indent=2))
finally:
    driver.quit()
