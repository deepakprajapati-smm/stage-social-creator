"""
Facebook Page Creation Worker — Camoufox (Firefox stealth)
===========================================================
Chrome CDP se koi lena dena nahi. Zero tab-closing issues.

Flow per title:
  1. fb_cookies.json load karo → Camoufox context mein inject
  2. facebook.com/pages/create navigate karo (already logged in)
  3. page.route() → GraphQL intercept → category_ids inject (field_exception fix)
  4. Page name + category fill → submit
  5. Page URL extract → Graph API se token → DB mein save → return

Requirements:
  - config/fb_cookies.json (run setup/setup_fb_worker.py once)
  - .env mein META_SYSTEM_USER_TOKEN (optional, for token fetch)
"""
from __future__ import annotations

import asyncio, json, os, re, sys, urllib.parse, requests
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import FB_COOKIES_FILE, META_SYSTEM_USER_TOKEN
from db.models import get_session, TitleProfile, TokenVault, EventLog

FB_CATEGORY_ENTERTAINMENT = 2200  # Valid FB category ID


def _load_cookies() -> list[dict]:
    if not Path(FB_COOKIES_FILE).exists():
        raise FileNotFoundError(
            f"Cookies nahi mili: {FB_COOKIES_FILE}\n"
            "Run: python setup/setup_fb_worker.py"
        )
    return json.loads(Path(FB_COOKIES_FILE).read_text())


async def create_fb_page(title_name: str, title_id: str) -> dict:
    """
    FB Page banao STAGE title ke liye.
    Returns: {"page_id": ..., "page_url": ..., "page_token": ...}
    """
    from camoufox.async_api import AsyncCamoufox

    cookies = _load_cookies()
    print(f"\n[FB] '{title_name}' ke liye page bana raha hoon...")

    async with AsyncCamoufox(headless=True, geoip=True) as browser:
        context = browser
        page = await context.new_page()

        # ── 1. Cookies inject karo → login bypass ───────────────────────────
        await context.add_cookies(cookies)
        print("[FB] Cookies injected ✓")

        # ── 2. facebook.com/pages/create pe navigate karo ───────────────────
        await page.goto(
            "https://www.facebook.com/pages/create",
            wait_until="networkidle",
            timeout=30000,
        )
        await asyncio.sleep(2)

        # Session valid hai? (login page pe redirect nahi hua)
        if "login" in page.url or "accounts/login" in page.url:
            raise RuntimeError(
                "FB session expire ho gayi.\n"
                "Run: python setup/setup_fb_worker.py"
            )
        print(f"[FB] pages/create pe hoon ✓  (URL: {page.url})")

        # ── 3. GraphQL interceptor — category_ids inject karo ───────────────
        async def inject_category(route):
            req = route.request
            if req.method == "POST" and "graphql" in req.url:
                body = req.post_data or ""
                if "additional_profile_plus_create" in body or \
                   "create_page" in body.lower() or \
                   "PageCreationMutation" in body:
                    try:
                        parsed = urllib.parse.parse_qs(body)
                        vars_raw = parsed.get("variables", ['{}'])[0]
                        variables = json.loads(vars_raw)

                        # category_ids inject — har jagah try karo
                        if "input" in variables:
                            variables["input"]["category_ids"] = [FB_CATEGORY_ENTERTAINMENT]
                        else:
                            variables["category_ids"] = [FB_CATEGORY_ENTERTAINMENT]

                        parsed["variables"] = [json.dumps(variables)]
                        new_body = urllib.parse.urlencode({k: v[0] for k, v in parsed.items()})
                        print("[FB] GraphQL intercept → category_ids injected ✓")
                        await route.continue_(post_data=new_body)
                        return
                    except Exception as ex:
                        print(f"[FB] Interceptor skip (non-fatal): {ex}")
            await route.continue_()

        await page.route("**/*graphql*", inject_category)

        # ── 4. Page name type karo ───────────────────────────────────────────
        print(f"[FB] Page name type kar raha hoon: {title_name}")
        name_selectors = [
            'input[name="name"]',
            'input[placeholder*="name" i]',
            'input[aria-label*="Page name" i]',
            'input[aria-label*="name" i]',
        ]
        name_input = None
        for sel in name_selectors:
            try:
                name_input = await page.wait_for_selector(sel, timeout=6000)
                break
            except:
                continue

        if not name_input:
            raise RuntimeError("Page name input field nahi mila. FB ka UI change ho gaya hoga.")

        await name_input.click()
        await asyncio.sleep(0.5)
        await name_input.fill(title_name)
        await asyncio.sleep(1.5)

        # ── 5. Category select karo ──────────────────────────────────────────
        print("[FB] Category select kar raha hoon...")
        cat_selectors = [
            'input[placeholder*="categor" i]',
            'input[aria-label*="categor" i]',
        ]
        for sel in cat_selectors:
            try:
                cat = await page.wait_for_selector(sel, timeout=5000)
                await cat.click()
                await asyncio.sleep(0.4)
                await cat.type("Entertainment", delay=70)
                await asyncio.sleep(1.5)
                # First dropdown option click karo
                opt = await page.wait_for_selector(
                    '[role="option"]:first-child, [role="listbox"] li:first-child',
                    timeout=4000
                )
                await opt.click()
                await asyncio.sleep(1)
                print("[FB] Category selected ✓")
                break
            except:
                continue

        # ── 6. Create Page button click karo ────────────────────────────────
        print("[FB] Create Page click kar raha hoon...")
        btn_selectors = [
            'button[type="submit"]',
            'div[role="button"]:has-text("Create Page")',
            'div[aria-label*="Create Page" i]',
            'button:has-text("Create Page")',
        ]
        btn = None
        for sel in btn_selectors:
            try:
                btn = await page.wait_for_selector(sel, timeout=5000)
                break
            except:
                continue

        if not btn:
            raise RuntimeError("Create Page button nahi mila.")

        await asyncio.sleep(0.5)
        await btn.click()

        # ── 7. Naye page ka URL wait karo ────────────────────────────────────
        print("[FB] Page creation ka wait kar raha hoon...")
        await page.wait_for_url(
            lambda u: (
                re.search(r"facebook\.com/.+/(about|settings|dashboard|posts|manage)", u) or
                (re.search(r"facebook\.com/\d{5,}", u) and "create" not in u)
            ) is not None,
            timeout=30000,
        )
        page_url = page.url
        print(f"[FB] Page ban gaya! URL: {page_url}")

        # ── 8. Page ID extract karo ──────────────────────────────────────────
        page_id = _extract_page_id(page_url)

        # ── 9. Page Access Token fetch karo ─────────────────────────────────
        page_token = _fetch_page_token(page_id, title_name) if META_SYSTEM_USER_TOKEN else None

        result = {
            "page_id": page_id,
            "page_url": page_url,
            "page_token": page_token,
        }

    # ── 10. DB mein save karo (browser band hone ke baad) ───────────────────
    _save_to_db(title_id, title_name, result)

    print(f"[FB] ✅ Done — {title_name}: {page_url}")
    return result


def _extract_page_id(url: str) -> str | None:
    m = re.search(r"facebook\.com/(\d{8,})", url)
    return m.group(1) if m else None


def _fetch_page_token(page_id: str | None, page_name: str) -> str | None:
    try:
        r = requests.get(
            "https://graph.facebook.com/v19.0/me/accounts",
            params={
                "access_token": META_SYSTEM_USER_TOKEN,
                "fields": "id,name,access_token",
            },
            timeout=15,
        )
        r.raise_for_status()
        for page in r.json().get("data", []):
            if (page_id and page.get("id") == page_id) or \
               page.get("name", "").lower() == page_name.lower():
                return page.get("access_token")
    except Exception as e:
        print(f"[FB] Token fetch failed (non-fatal): {e}")
    return None


def _save_to_db(title_id: str, title_name: str, result: dict):
    session = get_session()
    try:
        p = session.query(TitleProfile).filter_by(title_id=title_id).first()
        if not p:
            p = TitleProfile(title_id=title_id, title_name=title_name, title_type="content")
            session.add(p)
        p.fb_page_id  = result.get("page_id")
        p.fb_page_url = result.get("page_url")
        p.status      = "fb_done"
        p.updated_at  = datetime.now(timezone.utc)

        if result.get("page_token"):
            session.add(TokenVault(
                title_id=title_id, platform="facebook",
                token_type="page_token", token_value=result["page_token"],
            ))
        session.add(EventLog(
            entity_type="title", entity_id=title_id,
            event_type="fb_page_created", event_data=json.dumps(result),
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
    print(f"\nResult: {json.dumps(result, indent=2)}")
