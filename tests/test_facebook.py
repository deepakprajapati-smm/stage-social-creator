"""
Facebook End-to-End Tests — Murat (TEA)
Tests run against REAL Chrome CDP — no mocks
"""
from __future__ import annotations
import asyncio, json, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

TEST_TITLE = "STAGE TEST DELETE 001"
TEST_TITLE_ID = "test_fb_001"


async def test_1_cookies_exist():
    """Test: fb_cookies.json exists and has c_user cookie"""
    print("\n[TEST 1] Checking FB cookies file...")
    from config.settings import FB_COOKIES_FILE

    assert os.path.exists(FB_COOKIES_FILE), (
        f"FAIL: {FB_COOKIES_FILE} not found.\n"
        "Run: python setup/get_fb_cookies.py"
    )
    with open(FB_COOKIES_FILE) as f:
        cookies = json.load(f)

    c_user = next((c for c in cookies if c["name"] == "c_user"), None)
    assert c_user, "FAIL: c_user cookie not found — FB not logged in"
    print(f"  ✅ Cookies valid. FB User ID: {c_user['value']}")


async def test_2_chrome_cdp_reachable():
    """Test: Chrome is running and CDP is reachable"""
    print("\n[TEST 2] Checking Chrome CDP...")
    import aiohttp
    async with aiohttp.ClientSession() as s:
        try:
            async with s.get("http://localhost:9222/json/version", timeout=aiohttp.ClientTimeout(total=5)) as r:
                data = await r.json()
                print(f"  ✅ Chrome CDP reachable. Browser: {data.get('Browser', 'unknown')}")
        except Exception as e:
            raise AssertionError(
                f"FAIL: Chrome CDP not reachable.\n"
                f"Run: bash scripts/launch_chrome.sh\n"
                f"Error: {e}"
            )


async def test_3_create_fb_page():
    """Test: Create a real Facebook test page"""
    print(f"\n[TEST 3] Creating FB test page: '{TEST_TITLE}'...")
    from workers.facebook_worker import create_fb_page

    result = await create_fb_page(TEST_TITLE, TEST_TITLE_ID)

    assert result.get("page_url"), f"FAIL: No page_url in result: {result}"
    assert "facebook.com" in result.get("page_url", ""), f"FAIL: Invalid page URL: {result}"

    print(f"  ✅ Page created!")
    print(f"     URL: {result['page_url']}")
    print(f"     ID:  {result.get('page_id', 'N/A')}")
    print(f"     Token: {'✓' if result.get('page_token') else 'Not fetched (META_SYSTEM_USER_TOKEN not set)'}")
    return result


async def test_4_db_record_saved():
    """Test: DB has record of created page"""
    print(f"\n[TEST 4] Verifying DB record...")
    from db.models import get_session, TitleProfile

    session = get_session()
    try:
        profile = session.query(TitleProfile).filter_by(title_id=TEST_TITLE_ID).first()
        assert profile, f"FAIL: No DB record for title_id={TEST_TITLE_ID}"
        assert profile.fb_page_url, "FAIL: fb_page_url not saved in DB"
        print(f"  ✅ DB record saved. Status: {profile.status}")
    finally:
        session.close()


async def run_all_tests():
    print("=" * 60)
    print("  STAGE Social Creator — Facebook Tests")
    print("=" * 60)

    tests = [
        test_1_cookies_exist,
        test_2_chrome_cdp_reachable,
        test_3_create_fb_page,
        test_4_db_record_saved,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            await test()
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {e}")
            failed += 1
        except Exception as e:
            print(f"  ❌ Unexpected error: {e}")
            failed += 1

    print(f"\n{'='*60}")
    print(f"  Results: {passed} passed, {failed} failed")
    print(f"{'='*60}\n")
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
