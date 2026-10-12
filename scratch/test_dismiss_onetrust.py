from DrissionPage import ChromiumPage, ChromiumOptions
import time, json

co = ChromiumOptions()
co.headless(True)
co.set_browser_path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
page = ChromiumPage(co)

try:
    page.get('https://kick.com')
    time.sleep(3)

    # Cleanly remove OneTrust banner and backdrop
    page.run_js("""
        let btn = document.getElementById('onetrust-accept-btn-handler');
        if (btn) btn.click();
        let ot = document.getElementById('onetrust-consent-sdk');
        if (ot) ot.remove();
        let banner = document.querySelector('.onetrust-pc-dark');
        if (banner) banner.remove();
        let overlay = document.querySelector('.onetrust-pc-dark-overlay');
        if (overlay) overlay.remove();
    """)
    time.sleep(1)

    # Click Sign Up (Kaydol)
    btn = page.ele('text:Kaydol') or page.ele('@data-testid=sign-up')
    print('Kaydol button found:', btn.text if btn else 'No')
    if btn:
        btn.click(by_js=True)
        time.sleep(2)

    # Check dialogs
    res = page.run_js("""
        const dialogs = Array.from(document.querySelectorAll('[role="dialog"]')).map(d => ({
            id: d.id,
            textSnippet: d.innerText.slice(0, 100),
            inputs: Array.from(d.querySelectorAll('input')).map(i => i.name),
            buttons: Array.from(d.querySelectorAll('button')).map(b => ({
                text: b.innerText.trim(),
                testId: b.getAttribute('data-testid')
            }))
        }));
        return dialogs;
    """)
    print('Dialogs after clicking Kaydol:', json.dumps(res, indent=2))

finally:
    page.quit()
