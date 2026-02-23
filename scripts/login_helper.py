"""
scripts/login_helper.py — One-time login helper for Chrome debug session

Navigates Chrome to FB + Google login pages.
You just type credentials in the Chrome window.
Script auto-detects when login completes, then saves session.

Usage:
    python scripts/login_helper.py
"""

import time
import sys

CDP_URL = "http://localhost:9222"

try:
    from patchright.sync_api import sync_playwright
except ImportError:
    from playwright.sync_api import sync_playwright


def check_fb_logged_in(page) -> bool:
    try:
        # Logged in = no login form visible
        login_form = page.locator('input[name="email"], input[data-testid="royal_email"]').count()
        return login_form == 0
    except Exception:
        return False


def check_google_logged_in(page) -> bool:
    try:
        url = page.url
        if "accounts.google.com" in url and "signin" in url:
            return False
        # Check for user avatar on YT
        signin_btn = page.locator('a[href*="accounts.google.com/ServiceLogin"]').count()
        return signin_btn == 0
    except Exception:
        return False


def wait_for_login(page, platform: str, check_fn, timeout_sec=300) -> bool:
    print(f"\n⏳ Waiting for {platform} login (you have {timeout_sec//60} minutes)...")
    print(f"   👉 Type your credentials in the Chrome window now")
    start = time.time()
    dots = 0
    while time.time() - start < timeout_sec:
        try:
            page.reload(wait_until="domcontentloaded", timeout=15000)
            time.sleep(2)
            if check_fn(page):
                print(f"\n✅ {platform} login detected!")
                return True
        except Exception:
            pass
        dots += 1
        print("." * (dots % 4 + 1), end="\r", flush=True)
        time.sleep(3)
    print(f"\n❌ Timeout waiting for {platform} login")
    return False


def main():
    print("=" * 55)
    print("  STAGE Social Creator — One-Time Login Setup")
    print("=" * 55)
    print(f"\nConnecting to Chrome at {CDP_URL}...")

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            print(f"\n❌ Cannot connect to Chrome: {e}")
            print("\nFix: Run this first:")
            print("  bash scripts/launch_chrome_debug.sh")
            sys.exit(1)

        ctx = browser.contexts[0]

        # ── FACEBOOK LOGIN ────────────────────────────────────────
        print("\n[1/2] FACEBOOK LOGIN")
        print("-" * 40)

        # Use first page or create one
        if ctx.pages:
            fb_page = ctx.pages[0]
        else:
            fb_page = ctx.new_page()

        fb_page.goto("https://www.facebook.com/login", wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        if check_fb_logged_in(fb_page):
            print("✅ Facebook already logged in!")
            fb_ok = True
        else:
            print("   Facebook login page is open in Chrome.")
            print("   Enter your STAGE Facebook credentials there.")
            fb_ok = wait_for_login(fb_page, "Facebook", check_fb_logged_in)

        # ── GOOGLE / YOUTUBE LOGIN ────────────────────────────────
        print("\n[2/2] GOOGLE (YouTube) LOGIN")
        print("-" * 40)

        # Use second page or create one
        if len(ctx.pages) > 1:
            yt_page = ctx.pages[1]
        else:
            yt_page = ctx.new_page()

        yt_page.goto("https://accounts.google.com/ServiceLogin", wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        # Check via YouTube (more reliable indicator)
        yt_page.goto("https://www.youtube.com/", wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        if check_google_logged_in(yt_page):
            print("✅ Google/YouTube already logged in!")
            yt_ok = True
        else:
            yt_page.goto("https://accounts.google.com/ServiceLogin", wait_until="domcontentloaded", timeout=30000)
            print("   Google login page is open in Chrome.")
            print("   Enter your STAGE Google credentials there.")
            yt_ok = wait_for_login(yt_page, "Google", check_google_logged_in)

        # ── SUMMARY ───────────────────────────────────────────────
        print("\n" + "=" * 55)
        print("  Login Summary")
        print("=" * 55)
        print(f"  Facebook:  {'✅ Logged in' if fb_ok else '❌ Failed'}")
        print(f"  Google/YT: {'✅ Logged in' if yt_ok else '❌ Failed'}")

        if fb_ok and yt_ok:
            print("\n🎉 Both sessions active! Sessions saved permanently.")
            print("   Chrome profile: ~/.chrome-stage-debug")
            print("   You won't need to login again (unless Chrome profile is deleted).")
            print("\n   Next step: python scripts/test_create.py")
        else:
            print("\n⚠️  Some logins failed. Re-run this script and try again.")

        print("=" * 55)


if __name__ == "__main__":
    main()
