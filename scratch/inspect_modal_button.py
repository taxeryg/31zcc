from DrissionPage import ChromiumPage, ChromiumOptions
import time, json

co = ChromiumOptions()
co.headless(True)
co.set_browser_path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
page = ChromiumPage(co)

try:
    page.get('https://kick.com')
    time.sleep(3)
    accept_btn = page.ele('#onetrust-accept-btn-handler') or page.ele('text:Tümünü Kabul Et')
    if accept_btn:
        accept_btn.click(by_js=True)
        time.sleep(1)

    btn = page.ele('text:Kaydol') or page.ele('@data-testid=sign-up')
    if btn:
        btn.click(by_js=True)
        time.sleep(2)

    # Let's inspect the email element's parent hierarchy and buttons near it
    res = page.run_js("""
        let em = document.querySelector('input[name="email"]');
        if (!em) return { error: "no email input" };

        let dialog = em.closest('[role="dialog"]') || em.closest('[data-dialog]') || em.closest('.fixed');
        let buttons = Array.from((dialog || document).querySelectorAll('button')).map(b => ({
            text: b.innerText.trim(),
            type: b.getAttribute('type'),
            testId: b.getAttribute('data-testid'),
            classes: b.className
        }));

        return {
            dialogTag: dialog ? dialog.tagName : null,
            dialogClass: dialog ? dialog.className : null,
            buttons: buttons
        };
    """)
    print('Modal and buttons:', json.dumps(res, indent=2))

finally:
    page.quit()
