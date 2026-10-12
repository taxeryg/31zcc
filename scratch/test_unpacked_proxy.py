import sys, os, time, tempfile, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import undetected_chromedriver as uc
import kick_account_creator as kac

def create_unpacked_proxy_ext(ip: str, port: str, user: str, pwd: str) -> str:
    ext_dir = tempfile.mkdtemp(prefix="proxy_ext_")
    manifest_json = {
        "version": "1.0.0",
        "manifest_version": 2,
        "name": "Chrome Proxy Auth",
        "permissions": [
            "proxy",
            "tabs",
            "unlimitedStorage",
            "storage",
            "<all_urls>",
            "webRequest",
            "webRequestBlocking"
        ],
        "background": {
            "scripts": ["background.js"]
        },
        "minimum_chrome_version": "22.0.0"
    }

    background_js = f"""
    var config = {{
        mode: "fixed_servers",
        rules: {{
          singleProxy: {{
            scheme: "http",
            host: "{ip}",
            port: parseInt({port})
          }},
          bypassList: ["localhost"]
        }}
      }};
    chrome.proxy.settings.set({{value: config, scope: "regular"}}, function() {{}});
    function callbackFn(details) {{
        return {{
            authCredentials: {{
                username: "{user}",
                password: "{pwd}"
            }}
        }};
    }}
    chrome.webRequest.onAuthRequired.addListener(
        callbackFn,
        {{urls: ["<all_urls>"]}},
        ['blocking']
    );
    """

    with open(os.path.join(ext_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest_json, f, indent=2)

    with open(os.path.join(ext_dir, "background.js"), "w", encoding="utf-8") as f:
        f.write(background_js)

    return ext_dir

ip, port, user, pwd = kac.PROXY_POOL[0].split(":")
ext_dir = create_unpacked_proxy_ext(ip, port, user, pwd)

opts = uc.ChromeOptions()
opts.add_argument("--headless=new")
opts.add_argument(f"--load-extension={ext_dir}")

driver = uc.Chrome(options=opts, use_subprocess=True)
try:
    driver.get("https://httpbin.org/ip")
    time.sleep(3)
    print("PAGE SOURCE WITH UNPACKED PROXY:", driver.page_source)
finally:
    driver.quit()
