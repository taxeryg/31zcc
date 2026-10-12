from DrissionPage import ChromiumPage, ChromiumOptions
import time

co = ChromiumOptions()
co.headless(True)
co.set_browser_path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
page = ChromiumPage(co)
try:
    page.get('https://kick.com/signup')
    time.sleep(3)
    p_inp = page.ele('@name=password')
    p_inp.input('Abc123!@#')
    time.sleep(1)
    errs = page.run_js("let d = document.querySelector('[role=\"dialog\"]'); return d ? d.innerText : '';")
    print('Dialog after typing password:\n', errs)
finally:
    page.quit()
