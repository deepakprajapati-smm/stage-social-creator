"""
Facebook Worker Account — One-Time Setup
=========================================
Kya karta hai:
  FB_WORKER_EMAIL + FB_WORKER_PASSWORD (.env se) → programmatically login
  → Session cookies config/fb_cookies.json mein save
  → Aage kabhi login nahi karna

Agar CAPTCHA/checkpoint aaye:
  → Browser window visible rahega → solve karo → script continue
  → Ye sirf pehli baar hoga

Run: python setup/setup_fb_worker.py
"""
from __future__ import annotations
import asyncio, json, os, sys
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

FB_EMAIL    = os.getenv("FB_WORKER_EMAIL", "")
FB_PASSWORD = os.getenv("FB_WORKER_PASSWORD", "")
COOKIES_OUT = Path(__file__).parent.parent / "config" / "fb_cookies.json"


async def setup_fb_worker():
    if not FB_EMAIL or not FB_PASSWORD:
        print("❌ .env mein FB_WORKER_EMAIL aur FB_WORKER_PASSWORD daalo")
        sys.exit(1)

    from camoufox.async_api import AsyncCamoufox

    print(f"[SETUP] Camoufox (Firefox) launch ho raha hai...")
    print(f"[SETUP] Account: {FB_EMAIL}")

    async with AsyncCamoufox(headless=False, geoip=True) as browser:
        page = await browser.new_page()

        # ── FB login page ────────────────────────────────────────────────────
        await page.goto("https://www.facebook.com", wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)

        # Already logged in? (profile se purana session)
        if "login" not in page.url and "accounts" not in page.url:
            cookies = await page.context.cookies()
            fb_cookies = [c for c in cookies if "facebook.com" in c.get("domain", "")]
            if any(c["name"] == "c_user" for c in fb_cookies):
                _save_cookies(fb_cookies)
                print("✅ Already logged in — cookies saved!")
                return

        # ── Fill login form ──────────────────────────────────────────────────
        print("[SETUP] Filling login form...")

        # Email field — multiple selector fallbacks
        for sel in ['#email', 'input[name="email"]', 'input[type="email"]']:
            try:
                await page.wait_for_selector(sel, timeout=5000)
                await page.fill(sel, FB_EMAIL)
                break
            except:
                continue

        await asyncio.sleep(0.8)

        # Password field
        for sel in ['#pass', 'input[name="pass"]', 'input[type="password"]']:
            try:
                await page.fill(sel, FB_PASSWORD)
                break
            except:
                continue

        await asyncio.sleep(1.2)

        # Submit
        for sel in ['button[name="login"]', 'input[value="Log In"]', '[data-testid="royal_login_button"]', 'button[type="submit"]']:
            try:
                await page.click(sel, timeout=3000)
                break
            except:
                continue

        print("[SETUP] Login submit kiya — wait kar raha hoon...")

        # ── Wait for successful login OR checkpoint ──────────────────────────
        await asyncio.sleep(5)

        for _ in range(24):  # Max 2 minutes wait
            url = page.url
            if "checkpoint" in url:
                print(f"\n⚠️  Checkpoint detected: {url}")
                print("Browser window mein checkpoint handle karo...")
                print("Handle karne ke baad yahan Enter dabao.")
                await asyncio.get_event_loop().run_in_executor(None, input, ">>> Enter dabao: ")
            elif "login" not in url and "accounts" not in url:
                break  # Logged in
            await asyncio.sleep(5)

        # ── Verify + save cookies ────────────────────────────────────────────
        cookies = await page.context.cookies()
        fb_cookies = [c for c in cookies if "facebook.com" in c.get("domain", "")]
        c_user = next((c for c in fb_cookies if c["name"] == "c_user"), None)

        if not c_user:
            print(f"\n❌ Login nahi hua. Current URL: {page.url}")
            print("Email/password check karo ya manually browser mein login karo.")
            sys.exit(1)

        _save_cookies(fb_cookies)
        print(f"\n✅ Login successful!")
        print(f"   FB User ID: {c_user['value']}")
        print(f"   Cookies saved: {COOKIES_OUT}")
        print(f"   Ab kabhi login nahi karna padega.\n")


def _save_cookies(cookies: list):
    COOKIES_OUT.parent.mkdir(exist_ok=True)
    with open(COOKIES_OUT, "w") as f:
        json.dump(cookies, f, indent=2)


if __name__ == "__main__":
    asyncio.run(setup_fb_worker())
