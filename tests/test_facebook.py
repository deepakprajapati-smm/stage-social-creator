"""
Facebook Tests — Murat (TEA)
Real Camoufox tests — no mocks
"""
from __future__ import annotations
import asyncio, json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

TEST_NAME = "STAGE TEST DELETE"
TEST_ID   = "test_fb_001"


async def test_1_cookies_exist():
    print("\n[T1] Cookies check...")
    from config.settings import FB_COOKIES_FILE
    assert Path(FB_COOKIES_FILE).exists(), \
        f"FAIL: {FB_COOKIES_FILE} nahi mili\nRun: python setup/setup_fb_worker.py"
    cookies = json.loads(Path(FB_COOKIES_FILE).read_text())
    assert any(c["name"] == "c_user" for c in cookies), \
        "FAIL: c_user cookie nahi — session invalid"
    c_user = next(c for c in cookies if c["name"] == "c_user")
    print(f"  ✅ Cookies valid. FB User ID: {c_user['value']}")


async def test_2_camoufox_loads():
    print("\n[T2] Camoufox basic launch check...")
    from camoufox.async_api import AsyncCamoufox
    async with AsyncCamoufox(headless=True) as browser:
        page = await browser.new_page()
        await page.goto("https://example.com", timeout=15000)
        title = await page.title()
        assert "Example" in title, f"FAIL: Unexpected title: {title}"
    print(f"  ✅ Camoufox working. Page title: {title}")


async def test_3_fb_session_valid():
    print("\n[T3] FB session check...")
    from camoufox.async_api import AsyncCamoufox
    from config.settings import FB_COOKIES_FILE
    cookies = json.loads(Path(FB_COOKIES_FILE).read_text())

    async with AsyncCamoufox(headless=True, geoip=True) as browser:
        page = await browser.new_page()
        await browser.add_cookies(cookies)
        await page.goto("https://www.facebook.com", wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)

        assert "login" not in page.url, \
            f"FAIL: FB login page — session expired\nURL: {page.url}\nRun: python setup/setup_fb_worker.py"
        print(f"  ✅ FB session valid. URL: {page.url}")


async def test_4_create_fb_page():
    print(f"\n[T4] FB Page creation test: '{TEST_NAME}'...")
    from workers.facebook_worker import create_fb_page
    result = await create_fb_page(TEST_NAME, TEST_ID)

    assert result.get("page_url"), f"FAIL: page_url missing. Result: {result}"
    assert "facebook.com" in result["page_url"], f"FAIL: bad URL: {result['page_url']}"
    print(f"  ✅ Page created!")
    print(f"     URL:   {result['page_url']}")
    print(f"     ID:    {result.get('page_id', 'N/A')}")
    print(f"     Token: {'✓' if result.get('page_token') else 'N/A (META_SYSTEM_USER_TOKEN not set)'}")
    return result


async def test_5_db_record():
    print(f"\n[T5] DB record check...")
    from db.models import get_session, TitleProfile
    session = get_session()
    try:
        p = session.query(TitleProfile).filter_by(title_id=TEST_ID).first()
        assert p, f"FAIL: DB mein record nahi. title_id={TEST_ID}"
        assert p.fb_page_url, "FAIL: fb_page_url DB mein nahi"
        print(f"  ✅ DB record saved. Status: {p.status}, URL: {p.fb_page_url}")
    finally:
        session.close()


async def run_all():
    print("=" * 55)
    print("  STAGE Social Creator — Facebook Tests (Camoufox)")
    print("=" * 55)

    tests = [test_1_cookies_exist, test_2_camoufox_loads,
             test_3_fb_session_valid, test_4_create_fb_page, test_5_db_record]
    passed = failed = 0

    for t in tests:
        try:
            await t()
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {e}")
            failed += 1
        except Exception as e:
            print(f"  ❌ {type(e).__name__}: {e}")
            failed += 1

    print(f"\n{'='*55}")
    print(f"  {passed} passed  |  {failed} failed")
    print(f"{'='*55}\n")
    return failed == 0

if __name__ == "__main__":
    ok = asyncio.run(run_all())
    sys.exit(0 if ok else 1)
