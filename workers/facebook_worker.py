"""
workers/facebook_worker.py — Create a Facebook Page via Chrome CDP + Patchright

Flow:
  1. Connect to existing Chrome (running at localhost:9222 with STAGE FB account logged in)
  2. Navigate to facebook.com/pages/create
  3. Fill: page name + "Digital creator" category
  4. Submit → extract page ID
  5. Return FB page URL

Prerequisites (one-time manual setup):
  - Run: scripts/launch_chrome_debug.sh
  - Log into STAGE's Facebook account in that Chrome window
  - Keep Chrome running
"""

import random
import re
import time
import logging
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class FBPageResult:
    success:   bool
    page_id:   Optional[str] = None
    page_url:  Optional[str] = None
    page_name: Optional[str] = None
    error:     Optional[str] = None


# ── Selector waterfalls ───────────────────────────────────────────────────────

_NAME_SELECTORS = [
    'input[name="name"]',
    'input[placeholder="Page name"]',
    '[aria-label="Page name"]',
    '[aria-label="Name"]',
    'input[data-testid="page-creation-name-input"]',
    'form input[type="text"]:first-of-type',
]

_CATEGORY_SELECTORS = [
    'input[placeholder="Category"]',
    '[aria-label="Category"]',
    'input[name="category"]',
    '[aria-label*="category" i]',
    '[placeholder*="category" i]',
]

_OPTION_SELECTORS = [
    '[role="option"]:first-of-type',
    'ul[role="listbox"] li:first-child',
    'div[role="option"]:first-child',
    'li[role="option"]:first-child',
]

_CREATE_SELECTORS = [
    'div[aria-label="Create Page"]',
    'div[role="button"]:has-text("Create Page")',
    'button:has-text("Create Page")',
    'div[role="button"]:has-text("Create")',
    'button:has-text("Create")',
]

_BUSINESS_CHOOSER_SELECTORS = [
    'div[role="button"]:has-text("Business or brand")',
    'button:has-text("Business or brand")',
    '[aria-label*="Business or brand"]',
]


# ── Human behaviour helpers ───────────────────────────────────────────────────

def _delay(min_s: float = 0.8, max_s: float = 2.5):
    time.sleep(random.uniform(min_s, max_s))

def _human_type(page, selector: str, text: str, delay_range=(100, 280)):
    """Type text with per-character random delay (ms) to simulate human typing."""
    el = page.locator(selector).first
    el.click()
    _delay(0.3, 0.7)
    for char in text:
        page.keyboard.type(char, delay=random.randint(*delay_range))

def _human_scroll(page, pixels: Optional[int] = None):
    """Scroll a small random amount (simulate human reading)."""
    px = pixels or random.randint(60, 220)
    page.mouse.wheel(0, px)
    _delay(0.3, 0.8)

def _find_and_click(page, selectors: list[str], timeout: int = 5000) -> bool:
    """Try selectors in order, click the first one that exists. Return success."""
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=timeout):
                # Simulate mouse move toward element before clicking
                box = loc.bounding_box()
                if box:
                    tx = box["x"] + box["width"] / 2 + random.uniform(-4, 4)
                    ty = box["y"] + box["height"] / 2 + random.uniform(-3, 3)
                    page.mouse.move(tx, ty, steps=random.randint(5, 12))
                    _delay(0.1, 0.3)
                loc.click()
                return True
        except Exception:
            continue
    return False

def _find_selector(page, selectors: list[str], timeout: int = 5000) -> Optional[str]:
    """Return the first selector that matches a visible element."""
    for sel in selectors:
        try:
            if page.locator(sel).first.is_visible(timeout=timeout):
                return sel
        except Exception:
            continue
    return None


# ── Page ID extraction ────────────────────────────────────────────────────────

def _extract_page_id(url: str, content: str) -> Optional[str]:
    """Extract FB page numeric ID from URL or page source."""
    # Pattern 1: ?id=123456789
    m = re.search(r"[?&]id=(\d{10,})", url)
    if m:
        return m.group(1)

    # Pattern 2: /pages/slug/123456789/
    m = re.search(r"/pages/[^/]+/(\d{10,})", url)
    if m:
        return m.group(1)

    # Pattern 3: profile.php?id=
    m = re.search(r"profile\.php\?id=(\d{10,})", url)
    if m:
        return m.group(1)

    # Pattern 4: scan page source for page ID
    m = re.search(r'"page_id":"?(\d{10,})"?', content)
    if m:
        return m.group(1)

    return None


# ── Main worker ───────────────────────────────────────────────────────────────

def create_facebook_page(
    page_name:    str,
    category:     str = "Digital creator",
    cdp_url:      str = "http://localhost:9222",
    screenshot_dir: Optional[str] = None,
) -> FBPageResult:
    """
    Create a Facebook Page using an existing Chrome session via CDP.

    Args:
        page_name:  Full page name, e.g. "STAGE Banswara Ki Kahani"
        category:   FB category search string (default: "Digital creator")
        cdp_url:    Chrome DevTools Protocol URL (default: localhost:9222)
        screenshot_dir: If set, saves a screenshot on completion/failure

    Returns:
        FBPageResult with success, page_id, page_url, error
    """
    try:
        from patchright.sync_api import sync_playwright
        log.info("Using patchright (stealth mode)")
    except ImportError:
        from playwright.sync_api import sync_playwright
        log.warning("patchright not installed — falling back to playwright (less stealthy)")

    with sync_playwright() as p:
        log.info(f"Connecting to Chrome at {cdp_url}")
        browser = p.chromium.connect_over_cdp(cdp_url)
        context = browser.contexts[0]
        page    = context.new_page()

        # Stealth: mask webdriver flag
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )

        try:
            # ── Step 1: Verify FB session ──────────────────────────────────
            log.info("Navigating to facebook.com to verify session...")
            page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30000)
            _delay(2.0, 4.0)  # "reading" delay

            if "login" in page.url.lower():
                return FBPageResult(success=False, error="Facebook session expired — re-login in Chrome debug window")

            # ── Step 2: Navigate to page creation ─────────────────────────
            log.info("Navigating to pages/create...")
            page.goto("https://www.facebook.com/pages/create", wait_until="domcontentloaded", timeout=30000)
            _delay(3.0, 6.0)  # longer delay — simulate reading the form

            # ── Step 3: Handle Business/Creator chooser (if shown) ─────────
            chooser = _find_selector(page, _BUSINESS_CHOOSER_SELECTORS, timeout=3000)
            if chooser:
                log.info("Business/Creator chooser visible — clicking 'Business or brand'")
                _find_and_click(page, _BUSINESS_CHOOSER_SELECTORS)
                _delay(0.8, 1.5)

            # ── Step 4: Fill page name ─────────────────────────────────────
            log.info(f"Filling page name: {page_name}")
            name_sel = _find_selector(page, _NAME_SELECTORS, timeout=8000)
            if not name_sel:
                return FBPageResult(success=False, error="Could not find page name input — FB UI may have changed")

            _human_scroll(page)
            _human_type(page, name_sel, page_name)
            _delay(0.5, 1.0)

            # ── Step 5: Fill category ──────────────────────────────────────
            log.info(f"Filling category: {category}")
            cat_sel = _find_selector(page, _CATEGORY_SELECTORS, timeout=8000)
            if not cat_sel:
                log.warning("Category field not found — trying to submit without it")
            else:
                _human_type(page, cat_sel, category, delay_range=(150, 310))
                _delay(1.5, 2.5)  # wait for autocomplete dropdown

                # Click first option in dropdown
                if not _find_and_click(page, _OPTION_SELECTORS, timeout=4000):
                    log.warning("Category dropdown option not clicked — proceeding anyway")
                _delay(0.5, 1.0)

            # ── Step 6: Scroll + pause before submitting ───────────────────
            _human_scroll(page, random.randint(80, 200))
            _delay(1.0, 2.5)  # "reviewing" pause

            # ── Step 7: Click Create Page ──────────────────────────────────
            log.info("Clicking Create Page...")
            if not _find_and_click(page, _CREATE_SELECTORS, timeout=8000):
                if screenshot_dir:
                    page.screenshot(path=f"{screenshot_dir}/fb_create_fail.png")
                return FBPageResult(success=False, error="Create Page button not found or not clickable")

            # ── Step 8: Wait for redirect ──────────────────────────────────
            log.info("Waiting for redirect after page creation...")
            for _ in range(30):
                _delay(1.0, 1.0)
                current_url = page.url
                if "pages/create" not in current_url and "facebook.com" in current_url:
                    break
            else:
                return FBPageResult(success=False, error="Timed out waiting for redirect after Create Page click")

            _delay(2.0, 4.0)
            current_url = page.url

            # ── Step 9: Check for checkpoint ──────────────────────────────
            if "checkpoint" in current_url or "checkpoint" in page.content().lower():
                if screenshot_dir:
                    page.screenshot(path=f"{screenshot_dir}/fb_checkpoint.png")
                return FBPageResult(
                    success=False,
                    error="Facebook checkpoint triggered — human intervention required in Chrome debug window"
                )

            # ── Step 10: Extract page ID ───────────────────────────────────
            page_id = _extract_page_id(current_url, page.content())
            page_url = current_url if page_id else None

            if page_id:
                log.info(f"FB Page created: ID={page_id}, URL={page_url}")
            else:
                log.warning(f"Page created but ID not extracted from URL: {current_url}")
                page_url = current_url

            if screenshot_dir:
                page.screenshot(path=f"{screenshot_dir}/fb_page_created.png")

            return FBPageResult(
                success  = True,
                page_id  = page_id,
                page_url = page_url,
                page_name= page_name,
            )

        except Exception as e:
            log.error(f"FB page creation error: {e}")
            if screenshot_dir:
                try:
                    page.screenshot(path=f"{screenshot_dir}/fb_error.png")
                except Exception:
                    pass
            return FBPageResult(success=False, error=str(e))

        finally:
            page.close()


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    name = sys.argv[1] if len(sys.argv) > 1 else "STAGE Test Page"
    print(f"\nCreating FB page: '{name}'")
    result = create_facebook_page(page_name=name, screenshot_dir="/tmp")
    print(f"\nResult: {result}")
