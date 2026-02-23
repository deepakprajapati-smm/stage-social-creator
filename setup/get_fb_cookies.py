"""
One-Time Facebook Cookie Extractor
===================================
Kya karta hai:
  - Chrome ko debug mode mein launch karta hai
  - User FB worker account mein ek baar login karta hai
  - Cookies automatically extract ho ke fb_cookies.json mein save ho jaati hain
  - Agal se sirf inject karni hain — login kabhi nahi karna padega

Run: python setup/get_fb_cookies.py
"""
from __future__ import annotations
import asyncio, json, os, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import CHROME_PROFILE_DIR, FB_COOKIES_FILE, CHROME_DEBUG_PORT


CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome",
    "chromium",
]


def find_chrome() -> str:
    for path in CHROME_PATHS:
        if os.path.exists(path):
            return path
    raise FileNotFoundError("Chrome not found. Install Google Chrome.")


def launch_chrome_debug() -> subprocess.Popen:
    chrome = find_chrome()
    profile_dir = CHROME_PROFILE_DIR
    os.makedirs(profile_dir, exist_ok=True)

    cmd = [
        chrome,
        f"--remote-debugging-port={CHROME_DEBUG_PORT}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "https://www.facebook.com",
    ]
    print(f"[SETUP] Launching Chrome with CDP on port {CHROME_DEBUG_PORT}...")
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(4)
    print("[SETUP] Chrome launched ✓")
    return proc


async def extract_and_save_cookies():
    from patchright.async_api import async_playwright

    print("\n" + "="*60)
    print("  STAGE FB Cookie Extractor")
    print("="*60)
    print("\nChrome window khulega. Facebook worker account mein LOGIN karo.")
    print("Login complete hone ke baad Enter dabao.\n")

    proc = launch_chrome_debug()
    input(">>> Facebook mein login karo, phir Enter dabao: ")

    print("\n[SETUP] Connecting to Chrome CDP...")
    p = await async_playwright().start()
    browser = await p.chromium.connect_over_cdp(f"http://localhost:{CHROME_DEBUG_PORT}")
    context = browser.contexts[0]

    # Get all Facebook cookies
    all_cookies = await context.cookies(["https://www.facebook.com", "https://facebook.com"])

    if not any(c["name"] == "c_user" for c in all_cookies):
        print("\n❌ Facebook login cookies nahi mili. Pehle FB mein login karo.")
        return False

    # Save cookies
    os.makedirs(os.path.dirname(FB_COOKIES_FILE) or ".", exist_ok=True)
    with open(FB_COOKIES_FILE, "w") as f:
        json.dump(all_cookies, f, indent=2)

    user_cookie = next(c for c in all_cookies if c["name"] == "c_user")
    print(f"\n✅ Cookies saved to: {FB_COOKIES_FILE}")
    print(f"   FB User ID: {user_cookie['value']}")
    print(f"   Total cookies: {len(all_cookies)}")
    print("\nAb se kabhi login nahi karna padega. Chrome band kar sakte ho.\n")

    return True


if __name__ == "__main__":
    success = asyncio.run(extract_and_save_cookies())
    sys.exit(0 if success else 1)
