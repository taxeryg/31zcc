import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import undetected_chromedriver as uc
import kick_account_creator as kac

ip, port, user, pwd = kac.PROXY_POOL[0].split(":")
ext_path = kac.create_proxy_auth_extension(ip, port, user, pwd)

opts = uc.ChromeOptions()
opts.add_argument("--headless=new")
opts.add_extension(ext_path)

driver = uc.Chrome(options=opts, use_subprocess=True)
try:
    driver.get("https://httpbin.org/ip")
    time.sleep(3)
    print("PAGE SOURCE:", driver.page_source)
finally:
    driver.quit()
    if os.path.exists(ext_path):
        os.remove(ext_path)
