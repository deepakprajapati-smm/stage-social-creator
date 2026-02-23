"""
workers/youtube_worker.py — Create a YouTube Brand Account channel via Chrome CDP + Patchright

Flow:
  1. Connect to existing Chrome (running at localhost:9222 with STAGE Google account)
  2. Navigate to youtube.com/create_channel
  3. Select "Use a custom name" (Brand Account)
  4. Enter channel name + set handle
  5. Submit → extract channel ID
  6. Return YT channel URL

Prerequisites (one-time manual setup):
  - Run: scripts/launch_chrome_debug.sh
  - Log into STAGE's Google account in that Chrome window
  - Keep Chrome running

Note: YT channel handle (@handle) is auto-assigned from channel name.
      Can be changed manually after creation in YouTube Studio.

Rate limit: Wait 10+ minutes between creating multiple channels.
"""

import random
import re
import time
import logging
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class YTChannelResult:
    success:      bool
    channel_id:   Optional[str] = None
    channel_url:  Optional[str] = None
    channel_name: Optional[str] = None
    handle:       Optional[str] = None
    error:        Optional[str] = None


# ── Selector waterfalls ───────────────────────────────────────────────────────
# YouTube uses Polymer/custom elements — selectors pierce Shadow DOM via patchright

_CUSTOM_NAME_SELECTORS = [
    'paper-button:has-text("Use a custom name")',
    'button:has-text("Use a custom name")',
    'yt-button-renderer:has-text("Use a custom name")',
    '[aria-label*="custom name"]',
    'tp-yt-paper-button:has-text("Use a custom name")',
]

_CHANNEL_NAME_SELECTORS = [
    '#channel-name input',
    'tp-yt-paper-input input',
    'input[id*="channel-name"]',
    'input[placeholder*="channel" i]',
    'input[aria-label*="Channel name" i]',
    'input[aria-label*="channel name" i]',
    'ytd-channel-name input',
    'input[type="text"]',
]

_TOS_CHECKBOX_SELECTORS = [
    'input[type="checkbox"]',
    'tp-yt-paper-checkbox',
    '[aria-label*="terms" i]',
]

_SUBMIT_SELECTORS = [
    'button:has-text("Create channel")',
    'paper-button:has-text("Create channel")',
    'tp-yt-paper-button:has-text("Done")',
    'paper-button:has-text("Done")',
    'button:has-text("Done")',
    'yt-button-renderer:has-text("Done")',
    '[aria-label="Done"]',
    '[aria-label="Create channel"]',
]


# ── Human behaviour helpers ───────────────────────────────────────────────────

def _delay(min_s: float = 0.8, max_s: float = 2.5):
    time.sleep(random.uniform(min_s, max_s))

def _human_type(page, selector: str, text: str, delay_range=(80, 220)):
    el = page.locator(selector).first
    el.click()
    _delay(0.3, 0.6)
    for char in text:
        page.keyboard.type(char, delay=random.randint(*delay_range))

def _human_scroll(page, pixels: Optional[int] = None):
    px = pixels or random.randint(50, 180)
    page.mouse.wheel(0, px)
    _delay(0.2, 0.6)

def _find_and_click(page, selectors: list[str], timeout: int = 5000) -> bool:
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=timeout):
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
    for sel in selectors:
        try:
            if page.locator(sel).first.is_visible(timeout=timeout):
                return sel
        except Exception:
            continue
    return None


# ── Channel ID extraction ─────────────────────────────────────────────────────

def _extract_channel_id(url: str, content: str) -> Optional[str]:
    """Extract YouTube channel ID (UCxxxxxxxx) from URL or page source."""
    # Pattern 1: /channel/UCxxxxxxxx in URL
    m = re.search(r"/channel/(UC[a-zA-Z0-9_-]{22})", url)
    if m:
        return m.group(1)

    # Pattern 2: YouTube Studio URL
    m = re.search(r"studio\.youtube\.com/channel/(UC[a-zA-Z0-9_-]{22})", url)
    if m:
        return m.group(1)

    # Pattern 3: Scan page source
    m = re.search(r'"channelId":\s*"(UC[a-zA-Z0-9_-]{22})"', content)
    if m:
        return m.group(1)

    m = re.search(r'"externalId":\s*"(UC[a-zA-Z0-9_-]{22})"', content)
    if m:
        return m.group(1)

    return None

def _extract_handle(url: str, content: str) -> Optional[str]:
    """Extract @handle from URL or page source after channel creation."""
    m = re.search(r"youtube\.com/@([a-zA-Z0-9_.\-]+)", url)
    if m:
        return f"@{m.group(1)}"
    m = re.search(r'"vanityUrls":\["@([a-zA-Z0-9_.\-]+)"\]', content)
    if m:
        return f"@{m.group(1)}"
    return None


# ── Get channel ID from Studio ────────────────────────────────────────────────

def _get_id_from_studio(page) -> Optional[str]:
    """Navigate to YouTube Studio to extract channel ID from URL."""
    try:
        page.goto("https://studio.youtube.com/", wait_until="domcontentloaded", timeout=30000)
        _delay(2.0, 3.0)
        channel_id = _extract_channel_id(page.url, page.content())
        if not channel_id:
            # Try: studio.youtube.com/channel/UCxxx
            m = re.search(r"studio\.youtube\.com/channel/(UC[a-zA-Z0-9_-]{22})", page.url)
            if m:
                channel_id = m.group(1)
        return channel_id
    except Exception as e:
        log.warning(f"Could not get channel ID from Studio: {e}")
        return None


# ── Main worker ───────────────────────────────────────────────────────────────

def create_youtube_channel(
    channel_name: str,
    cdp_url:      str = "http://localhost:9222",
    screenshot_dir: Optional[str] = None,
) -> YTChannelResult:
    """
    Create a YouTube Brand Account channel using an existing Chrome session.

    Args:
        channel_name:   Display name, e.g. "STAGE Banswara Ki Kahani"
        cdp_url:        Chrome DevTools Protocol URL
        screenshot_dir: If set, saves screenshots on completion/failure

    Returns:
        YTChannelResult with success, channel_id, channel_url, handle, error
    """
    try:
        from patchright.sync_api import sync_playwright
        log.info("Using patchright (Shadow DOM + stealth support)")
    except ImportError:
        from playwright.sync_api import sync_playwright
        log.warning("patchright not installed — Shadow DOM selectors may fail")

    with sync_playwright() as p:
        log.info(f"Connecting to Chrome at {cdp_url}")
        browser = p.chromium.connect_over_cdp(cdp_url)
        context = browser.contexts[0]
        # Reuse existing page (avoids ERR_NAME_NOT_RESOLVED on new pages in debug Chrome)
        if len(context.pages) > 1:
            page = context.pages[1]  # Use Google tab
        elif context.pages:
            page = context.pages[0]
        else:
            page = context.new_page()

        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )

        try:
            # ── Step 1: Verify Google/YT session ──────────────────────────
            log.info("Navigating to youtube.com to verify session...")
            page.goto("https://www.youtube.com/", wait_until="domcontentloaded", timeout=30000)
            _delay(2.0, 4.0)

            if "accounts.google.com" in page.url or "signin" in page.url.lower():
                return YTChannelResult(success=False, error="Google session expired — run: python scripts/login_helper.py")

            # Check for sign-in button (logged out state)
            signin_visible = page.locator('a[href*="accounts.google.com/ServiceLogin"], ytd-button-renderer:has-text("Sign in")').count() > 0
            if signin_visible:
                if screenshot_dir:
                    page.screenshot(path=f"{screenshot_dir}/yt_not_logged_in.png")
                return YTChannelResult(success=False, error="YouTube not logged in (Sign in button visible) — run: python scripts/login_helper.py")

            # ── Step 2: Navigate to channel creation ───────────────────────
            log.info("Navigating to create_channel...")
            page.goto("https://www.youtube.com/create_channel", wait_until="domcontentloaded", timeout=30000)
            _delay(2.5, 5.0)

            # Fallback: channel_switcher if create_channel redirects away
            if "create_channel" not in page.url and "youtube.com" in page.url:
                log.info("Trying channel_switcher fallback...")
                page.goto("https://www.youtube.com/channel_switcher", wait_until="domcontentloaded", timeout=30000)
                _delay(2.0, 3.5)
                _find_and_click(page, [
                    'a:has-text("Create a new channel")',
                    'button:has-text("Create a new channel")',
                    '[href*="create_channel"]',
                ], timeout=5000)
                _delay(2.0, 3.0)

            # ── Step 3: Click "Use a custom name" (Brand Account) ──────────
            log.info("Selecting 'Use a custom name' (Brand Account)...")
            if not _find_and_click(page, _CUSTOM_NAME_SELECTORS, timeout=8000):
                # Some accounts skip straight to the name input — check
                name_sel = _find_selector(page, _CHANNEL_NAME_SELECTORS, timeout=3000)
                if not name_sel:
                    if screenshot_dir:
                        page.screenshot(path=f"{screenshot_dir}/yt_no_dialog.png")
                    return YTChannelResult(success=False, error="Could not find 'Use a custom name' button or name input")
                log.info("Name input found directly (no chooser shown)")
            else:
                _delay(1.0, 2.0)

            # ── Step 4: Fill channel name ──────────────────────────────────
            log.info(f"Filling channel name: {channel_name}")
            name_sel = _find_selector(page, _CHANNEL_NAME_SELECTORS, timeout=8000)
            if not name_sel:
                return YTChannelResult(success=False, error="Channel name input not found — YT UI may have changed")

            _human_scroll(page)
            _human_type(page, name_sel, channel_name)
            _delay(0.8, 1.5)

            # ── Step 5: Accept TOS checkbox (if shown) ─────────────────────
            tos_sel = _find_selector(page, _TOS_CHECKBOX_SELECTORS, timeout=3000)
            if tos_sel:
                log.info("TOS checkbox found — clicking...")
                _find_and_click(page, _TOS_CHECKBOX_SELECTORS)
                _delay(0.5, 1.0)

            # ── Step 6: Scroll + review pause ─────────────────────────────
            _human_scroll(page, random.randint(60, 150))
            _delay(1.0, 2.0)

            # ── Step 7: Click Create channel / Done ────────────────────────
            log.info("Clicking Create channel...")
            if not _find_and_click(page, _SUBMIT_SELECTORS, timeout=8000):
                if screenshot_dir:
                    page.screenshot(path=f"{screenshot_dir}/yt_submit_fail.png")
                return YTChannelResult(success=False, error="Create channel / Done button not found")

            # ── Step 8: Wait for redirect ──────────────────────────────────
            log.info("Waiting for channel creation redirect...")
            for _ in range(30):
                _delay(1.0, 1.0)
                current_url = page.url
                if "create_channel" not in current_url and "channel_switcher" not in current_url:
                    if "youtube.com" in current_url or "studio.youtube.com" in current_url:
                        break
            else:
                return YTChannelResult(success=False, error="Timed out waiting for redirect after channel creation")

            _delay(2.0, 4.0)
            current_url = page.url
            content     = page.content()

            # ── Step 9: Extract channel ID ─────────────────────────────────
            channel_id = _extract_channel_id(current_url, content)
            handle     = _extract_handle(current_url, content)

            if not channel_id:
                log.info("Channel ID not in URL — checking YouTube Studio...")
                channel_id = _get_id_from_studio(page)

            if channel_id:
                channel_url = f"https://www.youtube.com/channel/{channel_id}"
                log.info(f"YT Channel created: ID={channel_id}, handle={handle}")
            else:
                channel_url = current_url
                log.warning(f"Channel created but ID not extracted. URL: {current_url}")

            if screenshot_dir:
                page.screenshot(path=f"{screenshot_dir}/yt_channel_created.png")

            return YTChannelResult(
                success      = True,
                channel_id   = channel_id,
                channel_url  = channel_url,
                channel_name = channel_name,
                handle       = handle,
            )

        except Exception as e:
            log.error(f"YT channel creation error: {e}")
            if screenshot_dir:
                try:
                    page.screenshot(path=f"{screenshot_dir}/yt_error.png")
                except Exception:
                    pass
            return YTChannelResult(success=False, error=str(e))

        finally:
            # Navigate back to YouTube homepage to keep the tab alive for next run
            try:
                page.evaluate("() => { window.location.href = 'https://www.youtube.com/'; }")
            except Exception:
                pass


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    name = sys.argv[1] if len(sys.argv) > 1 else "STAGE Test Channel"
    print(f"\nCreating YT channel: '{name}'")
    result = create_youtube_channel(channel_name=name, screenshot_dir="/tmp")
    print(f"\nResult: {result}")
