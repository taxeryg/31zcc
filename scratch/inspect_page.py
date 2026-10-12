import sys
import os
import time
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kick_account_creator as kac

print("Starting debug run to inspect page and turnstile...")
session = kac.KickAccountCreatorSession()
session.start_creation_async(use_temp_mail=True, headless=True)

# Monitor driver while running
time.sleep(15)
for step in range(30):
    time.sleep(3)
    if session.driver:
        try:
            current_url = session.driver.current_url
            title = session.driver.title
            print(f"[{step}] URL: {current_url} | Title: {title} | Status: {session.status}")
            
            # Check for turnstile iframes
            iframes = session.driver.find_elements("css selector", "iframe")
            for idx, ifr in enumerate(iframes):
                src = ifr.get_attribute("src") or ""
                if "cloudflare" in src or "turnstile" in src or "challenge" in src:
                    print(f"-> FOUND CLOUDFLARE IFRAME: {src[:80]}")
            
            # Check for error messages or disabled submit buttons
            errs = session.driver.find_elements("css selector", "div[class*='error'], p[class*='error'], span[class*='error']")
            for err in errs:
                if err.is_displayed() and err.text:
                    print(f"-> VISIBLE ERROR: {err.text}")
                    
            if session.status in ["success", "waiting_code", "error"]:
                # take screenshot
                shot_path = os.path.join(os.path.dirname(__file__), "debug_screenshot.png")
                session.driver.save_screenshot(shot_path)
                print(f"Saved screenshot to {shot_path}")
                break
        except Exception as e:
            print(f"Inspect error: {e}")
    if not session.is_running:
        break

if session._thread:
    session._thread.join(timeout=30)
session.stop()
print("Debug run finished.")
