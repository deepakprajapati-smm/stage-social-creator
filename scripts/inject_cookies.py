"""
scripts/inject_cookies.py — Inject FB + Google cookies from regular Chrome into debug Chrome

Run this whenever sessions expire in the debug Chrome window.
Automatically extracts cookies from your regular Chrome (no manual login needed).

Usage:
    python scripts/inject_cookies.py
"""

import sys, time
from typing import Optional

CDP_URL = "http://localhost:9222"

try:
    import browser_cookie3
except ImportError:
    print("Installing browser-cookie3...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "browser-cookie3"], check=True)
    import browser_cookie3

try:
    from patchright.sync_api import sync_playwright
except ImportError:
    from playwright.sync_api import sync_playwright

import requests


def open_cdp_tab(cdp_url: str, target_url: str) -> Optional[str]:
    try:
        resp = requests.put(f"{cdp_url}/json/new?{target_url}", timeout=10)
        return resp.json().get("id")
    except Exception as e:
        print(f"  Warning: could not open tab: {e}")
        return None


def cookie_to_pw(c):
    domain = c.domain or ""
    if domain and not domain.startswith("."):
        domain = "." + domain
    name  = str(c.name  or "")
    value = str(c.value or "")
    if not name:
        return None
    d = {"name": name, "value": value, "domain": domain, "path": c.path or "/"}
    if c.expires and c.expires > 0:
        d["expires"] = float(c.expires)
    if c.secure:
        d["secure"] = True
    return d


def main():
    print("=" * 55)
    print("  STAGE Cookie Injector")
    print("=" * 55)

    # Check Chrome is running
    try:
        r = requests.get(f"{CDP_URL}/json/version", timeout=3)
        print(f"\n✅ Chrome found: {r.json().get('Browser','?')}")
    except Exception:
        print(f"\n❌ Chrome not running at {CDP_URL}")
        print("   Run: bash scripts/launch_chrome_debug.sh")
        sys.exit(1)

    # ── Step 1: Open FB + YT tabs BEFORE starting Patchright session ──────────
    # CRITICAL: Tabs opened via CDP HTTP API are only visible in context.pages
    # if they were opened BEFORE the Patchright session connects.
    print("\nOpening FB + YT tabs (before Patchright session)...")
    open_cdp_tab(CDP_URL, "https://www.facebook.com/")
    open_cdp_tab(CDP_URL, "https://www.youtube.com/")
    print("   Waiting for pages to initialize (8s)...")
    time.sleep(8)

    # Verify tabs appeared in CDP
    try:
        targets = requests.get(f"{CDP_URL}/json", timeout=5).json()
        page_urls = [t.get("url","") for t in targets if t.get("type") == "page"]
        print(f"   Chrome page tabs: {len(page_urls)}")
        for u in page_urls:
            print(f"     {u[:70]}")
    except Exception:
        pass

    # ── Step 2: Extract cookies from regular Chrome ────────────────────────────
    print("\nExtracting cookies from your regular Chrome...")
    try:
        fb_raw = list(browser_cookie3.chrome(domain_name=".facebook.com"))
        g_raw  = list(browser_cookie3.chrome(domain_name=".google.com"))
        yt_raw = list(browser_cookie3.chrome(domain_name=".youtube.com"))
    except Exception as e:
        print(f"❌ Cookie extraction failed: {e}")
        print("   Make sure regular Chrome is open with FB + Google logged in")
        sys.exit(1)

    all_raw = fb_raw + g_raw + yt_raw
    all_pw  = [c for c in (cookie_to_pw(r) for r in all_raw) if c is not None]
    print(f"   Found {len(all_pw)} cookies (FB:{len(fb_raw)} G:{len(g_raw)} YT:{len(yt_raw)})")

    # ── Step 3: Connect Patchright and inject cookies ──────────────────────────
    # IMPORTANT: Use manual start/stop (not "with" context manager) so Playwright
    # does NOT call browser.close() on exit — that would close all Chrome tabs!
    print("\nInjecting cookies into debug Chrome...")
    p = sync_playwright().start()
    try:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        ctx = browser.contexts[0]

        print(f"   Patchright sees {len(ctx.pages)} pages")
        for pg in ctx.pages:
            print(f"     {pg.url[:70]}")

        ok = fail = 0
        for cookie in all_pw:
            try:
                ctx.add_cookies([cookie])
                ok += 1
            except Exception:
                fail += 1
        print(f"   Injected: {ok} ✅  |  Skipped: {fail}")

        # ── Step 4: Reload FB + YT to apply cookies ────────────────────────────
        print("\nReloading pages with new cookies...")
        fb_page = yt_page = None
        for pg in ctx.pages:
            if "facebook.com" in pg.url:
                fb_page = pg
            elif "youtube.com" in pg.url:
                yt_page = pg

        if fb_page:
            try:
                fb_page.reload(wait_until="domcontentloaded", timeout=20000)
                time.sleep(2)
                print(f"   FB reloaded: {fb_page.url[:70]}")
            except Exception as e:
                print(f"   FB reload error: {e}")

        if yt_page:
            try:
                yt_page.reload(wait_until="domcontentloaded", timeout=20000)
                time.sleep(2)
                print(f"   YT reloaded: {yt_page.url[:70]}")
            except Exception as e:
                print(f"   YT reload error: {e}")

        time.sleep(3)

        # ── Step 5: Verify sessions ────────────────────────────────────────────
        print("\nVerifying sessions...")
        fb_ok = yt_ok = False

        if fb_page:
            try:
                login_visible = fb_page.locator('input[name="email"]').count() > 0
                fb_ok = not login_visible
                print(f"   FB ({fb_page.url[:50]}): login_form={login_visible} → {'✅' if fb_ok else '❌'}")
            except Exception as e:
                print(f"   FB verify error: {e}")

        if yt_page:
            try:
                signin = yt_page.locator('ytd-button-renderer:has-text("Sign in")').count()
                yt_ok = (signin == 0)
                print(f"   YT ({yt_page.url[:50]}): signin_btn={signin} → {'✅' if yt_ok else '❌'}")
            except Exception as e:
                print(f"   YT verify error: {e}")

        print(f"\n  Facebook:  {'✅ Logged in' if fb_ok else '❌ Check manually'}")
        print(f"  YouTube:   {'✅ Logged in' if yt_ok else '❌ Check manually'}")

        if fb_ok and yt_ok:
            print("\n🎉 Sessions ready! Run: python scripts/test_create.py")
        else:
            print("\n⚠️  Sessions unverified — may still work.")
            print("   Check the debug Chrome window to confirm login state.")

    finally:
        # IMPORTANT: Do NOT call browser.close() or p.stop() here!
        # Those send a CDP close command that kills the Chrome tabs.
        # Just let the Python process exit naturally — Chrome stays alive.
        pass

    print("=" * 55)


if __name__ == "__main__":
    main()
