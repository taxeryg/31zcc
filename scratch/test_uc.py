import sys
import os
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import undetected_chromedriver as uc
    print("Testing uc.Chrome()...")
    options = uc.ChromeOptions()
    options.add_argument("--headless=new")
    driver = uc.Chrome(options=options, use_subprocess=True)
    print("Chrome launched successfully!")
    driver.get("https://kick.com")
    print("Title:", driver.title)
    driver.quit()
except BaseException as e:
    print("Caught exception:")
    traceback.print_exc()
