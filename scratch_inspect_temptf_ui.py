import undetected_chromedriver as uc
import time
import json

options = uc.ChromeOptions()
options.add_argument("--headless=new")
options.add_argument("--window-size=1280,850")
driver = uc.Chrome(options=options, use_subprocess=True)

try:
    print("Navigating to temp.tf...")
    driver.get("https://temp.tf")
    time.sleep(4)
    print("Title:", driver.title)

    # Inspect checkboxes, buttons, and email display
    res = driver.execute_script("""
        const checkboxes = Array.from(document.querySelectorAll('input[type="checkbox"]')).map(c => ({
            id: c.id,
            checked: c.checked,
            label: (c.closest('label') || c.parentElement || {}).innerText || ''
        }));
        const buttons = Array.from(document.querySelectorAll('button')).map(b => b.innerText);
        const inputs = Array.from(document.querySelectorAll('input')).map(i => ({
            type: i.type,
            value: i.value,
            placeholder: i.placeholder,
            readOnly: i.readOnly
        }));
        return {
            checkboxes,
            buttons,
            inputs
        };
    """)
    print("UI Elements:")
    print(json.dumps(res, indent=2))

finally:
    driver.quit()
