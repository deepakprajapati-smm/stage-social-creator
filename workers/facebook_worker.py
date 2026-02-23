"""
Facebook Page Creation Worker — Ghost + Kai
Chrome CDP + cookie injection. Zero manual steps.

Flow:
  1. Load fb_cookies.json → inject into Chrome via CDP (bypass login entirely)
  2. Navigate to facebook.com/pages/create
  3. page.route() intercepts GraphQL → injects category_ids (fixes field_exception bug)
  4. Fill form, submit → extract Page URL + ID
  5. Fetch Page token via Graph API
  6. Save to DB
"""
from __future__ import annotations

import json
import asyncio
import re
import sys
import os
import time
import requests
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config.settings import CDP_URL, FB_COOKIES_FILE, META_SYSTEM_USER_TOKEN
from db.models import get_session, TitleProfile, TokenVault, EventLog
from datetime import datetime, timezone

# Valid FB Entertainment category ID (injected into GraphQL to fix field_exception)
FB_CATEGORY_ENTERTAINMENT = 2200


def _load_cookies() -> list[dict]:
    if not os.path.exists(FB_COOKIES_FILE):
        raise FileNotFoundError(
            f"FB cookies not found: {FB_COOKIES_FILE}\n"
            "Run: python setup/get_fb_cookies.py"
        )
    with open(FB_COOKIES_FILE) as f:
        return json.load(f)


async def _open_fb_tab_via_cdp_http(port: int) -> None:
    """
    Opens facebook.com/pages/create via CDP HTTP API BEFORE Patchright starts.
    Critical: Patchright CDP only sees tabs opened before the session begins.
    """
    import aiohttp
    async with aiohttp.ClientSession() as s:
        async with s.put(
            f"http://localhost:{port}/json/new?https://www.facebook.com/pages/create"
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"CDP HTTP tab open failed: HTTP {resp.status}")
            print("[FB] Tab opened via CDP HTTP ✓")


async def create_fb_page(title_name: str, title_id: str) -> dict:
    """
    Create a Facebook Page for a STAGE title. Returns page_id, page_url, page_token.
    """
    from patchright.async_api import async_playwright

    print(f"\n[FB] Creating page for: {title_name}")
    cookies = _load_cookies()

    # ── 1. Open FB tab BEFORE Patchright (critical for CDP tab visibility) ──
    await _open_fb_tab_via_cdp_http(9222)
    await asyncio.sleep(6)  # Give tab time to load

    # ── 2. Connect to existing Chrome — NO context manager (keeps tabs alive) ──
    p = await async_playwright().start()
    browser = await p.chromium.connect_over_cdp(CDP_URL)
    context = browser.contexts[0]

    # Find the Facebook tab we just opened
    fb_tab = None
    for pg in context.pages:
        if "facebook.com" in pg.url:
            fb_tab = pg
            break

    if not fb_tab:
        fb_tab = await context.new_page()

    # ── 3. Inject cookies → logged in without any login flow ────────────────
    print("[FB] Injecting session cookies...")
    await context.add_cookies(cookies)
    await fb_tab.reload(wait_until="networkidle", timeout=30000)

    # Verify login — not redirected to login/checkpoint
    if "login" in fb_tab.url or "checkpoint" in fb_tab.url:
        raise RuntimeError(
            "Facebook session invalid.\n"
            "Cookies expired — run: python setup/get_fb_cookies.py"
        )
    print(f"[FB] Logged in ✓  (URL: {fb_tab.url})")

    # ── 4. Navigate to pages/create ─────────────────────────────────────────
    if "pages/create" not in fb_tab.url:
        await fb_tab.goto(
            "https://www.facebook.com/pages/create",
            wait_until="networkidle",
            timeout=30000
        )
    print("[FB] On pages/create ✓")

    # ── 5. Set up GraphQL interceptor — fixes field_exception (category_ids) ──
    async def inject_category_ids(route):
        req = route.request
        if req.method == "POST" and "graphql" in req.url:
            raw = req.post_data or ""
            if "additional_profile_plus_create" in raw or "create_page" in raw.lower():
                try:
                    parsed = urllib.parse.parse_qs(raw)
                    variables = json.loads(parsed.get("variables", ["{}"])[0])

                    # Inject category_ids wherever they should go
                    inp = variables.get("input", variables)
                    inp["category_ids"] = [FB_CATEGORY_ENTERTAINMENT]

                    if "input" in variables:
                        variables["input"] = inp
                    else:
                        variables = inp

                    parsed["variables"] = [json.dumps(variables)]
                    new_body = urllib.parse.urlencode({k: v[0] for k, v in parsed.items()})
                    print(f"[FB] GraphQL intercepted — category_ids injected ✓")
                    await route.continue_(post_data=new_body)
                    return
                except Exception as e:
                    print(f"[FB] Interceptor non-fatal error: {e}")
        await route.continue_()

    await fb_tab.route("**/*graphql*", inject_category_ids)

    # ── 6. Type page name ────────────────────────────────────────────────────
    print(f"[FB] Typing page name: {title_name}")
    name_sel = 'input[name="name"], input[placeholder*="name" i], input[aria-label*="name" i]'
    name_input = await fb_tab.wait_for_selector(name_sel, timeout=15000)
    await asyncio.sleep(0.8)
    await name_input.click()
    await name_input.fill("")  # Clear any existing value
    await name_input.type(title_name, delay=75)
    await asyncio.sleep(1.5)

    # ── 7. Select category ───────────────────────────────────────────────────
    print("[FB] Selecting category: Entertainment")
    cat_sel = 'input[placeholder*="categor" i], input[aria-label*="categor" i]'
    try:
        cat_input = await fb_tab.wait_for_selector(cat_sel, timeout=8000)
        await cat_input.click()
        await asyncio.sleep(0.5)
        await cat_input.type("Entertainment", delay=75)
        await asyncio.sleep(1.5)

        # Click the first matching option in dropdown
        option = await fb_tab.wait_for_selector(
            '[role="option"]:first-child, [role="listbox"] [role="option"]:first-child',
            timeout=6000
        )
        await option.click()
        await asyncio.sleep(1)
        print("[FB] Category selected ✓")
    except Exception as e:
        print(f"[FB] Category selection warning: {e} — continuing anyway")

    # ── 8. Click Create Page ─────────────────────────────────────────────────
    print("[FB] Clicking Create Page...")
    btn_sel = (
        'button[type="submit"], '
        'div[role="button"]:has-text("Create Page"), '
        'div[aria-label*="Create Page"]'
    )
    create_btn = await fb_tab.wait_for_selector(btn_sel, timeout=10000)
    await asyncio.sleep(0.5)
    await create_btn.click()

    # ── 9. Wait for redirect to new page URL ────────────────────────────────
    print("[FB] Waiting for page creation to complete...")
    await fb_tab.wait_for_url(
        lambda url: (
            re.search(r"facebook\.com/[^/]+/(about|settings|dashboard|posts)", url) is not None
            or re.search(r"facebook\.com/\d+", url) is not None
        ),
        timeout=30000
    )
    page_url = fb_tab.url
    print(f"[FB] Page created! URL: {page_url}")

    # ── 10. Extract Page ID ──────────────────────────────────────────────────
    page_id = _extract_page_id(page_url)

    # ── 11. Fetch Page Access Token via Graph API ────────────────────────────
    page_token = None
    if META_SYSTEM_USER_TOKEN:
        page_token = _fetch_page_token(page_id, title_name)

    result = {
        "page_id": page_id,
        "page_url": page_url,
        "page_token": page_token,
    }

    # ── 12. Save to DB ───────────────────────────────────────────────────────
    _save_to_db(title_id, title_name, result)

    # ── 13. Remove route interceptor (keep Chrome alive) ────────────────────
    await fb_tab.unroute("**/*graphql*")

    print(f"[FB] ✅ Done — {title_name}")
    return result


def _extract_page_id(url: str) -> str | None:
    # Numeric ID in URL
    m = re.search(r"facebook\.com/(\d{10,})", url)
    if m:
        return m.group(1)
    return None


def _fetch_page_token(page_id: str | None, page_name: str) -> str | None:
    """Get Page Access Token from /me/accounts"""
    if not META_SYSTEM_USER_TOKEN:
        return None
    try:
        resp = requests.get(
            "https://graph.facebook.com/v19.0/me/accounts",
            params={"access_token": META_SYSTEM_USER_TOKEN, "fields": "id,name,access_token"},
            timeout=15,
        )
        resp.raise_for_status()
        for page in resp.json().get("data", []):
            if (page_id and page.get("id") == page_id) or \
               page.get("name", "").lower() == page_name.lower():
                return page.get("access_token")
    except Exception as e:
        print(f"[FB] Token fetch failed: {e}")
    return None


def _save_to_db(title_id: str, title_name: str, result: dict):
    session = get_session()
    try:
        profile = session.query(TitleProfile).filter_by(title_id=title_id).first()
        if not profile:
            profile = TitleProfile(
                title_id=title_id, title_name=title_name, title_type="content"
            )
            session.add(profile)

        profile.fb_page_id = result.get("page_id")
        profile.fb_page_url = result.get("page_url")
        profile.status = "fb_done"
        profile.updated_at = datetime.now(timezone.utc)

        if result.get("page_token"):
            session.add(TokenVault(
                title_id=title_id,
                platform="facebook",
                token_type="page_token",
                token_value=result["page_token"],
                expires_at=None,
            ))

        session.add(EventLog(
            entity_type="title",
            entity_id=title_id,
            event_type="fb_page_created",
            event_data=json.dumps(result),
        ))
        session.commit()
        print("[DB] Saved ✓")
    except Exception as e:
        session.rollback()
        print(f"[DB] Save failed: {e}")
    finally:
        session.close()


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "STAGE Test Page"
    tid  = sys.argv[2] if len(sys.argv) > 2 else "test_001"
    result = asyncio.run(create_fb_page(name, tid))
    print(f"\n✅ Result:\n{json.dumps(result, indent=2)}")
