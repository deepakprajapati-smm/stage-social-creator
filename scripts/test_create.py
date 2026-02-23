"""
scripts/test_create.py — Quick test: create one FB Page + one YT Channel

Usage:
    python scripts/test_create.py
    python scripts/test_create.py "STAGE Banswara"
"""

import sys
import logging
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)

sys.path.insert(0, ".")

from workers.facebook_worker import create_facebook_page
from workers.youtube_worker import create_youtube_channel

TITLE = sys.argv[1] if len(sys.argv) > 1 else "STAGE Test Banswara"

print("\n" + "=" * 55)
print(f"  Creating social profiles for: '{TITLE}'")
print("=" * 55)

# ── Facebook ─────────────────────────────────────────────────
print("\n[1/2] Creating Facebook Page...")
fb = create_facebook_page(
    page_name=TITLE,
    category="Digital creator",
    screenshot_dir="/tmp",
)
print(f"\nFacebook result:")
print(f"  success  : {fb.success}")
print(f"  page_id  : {fb.page_id}")
print(f"  page_url : {fb.page_url}")
if fb.error:
    print(f"  error    : {fb.error}")

if not fb.success:
    print("\n⚠️  FB failed. Check /tmp/fb_*.png for screenshots.")
    print("   Fix login first: python scripts/login_helper.py")
    sys.exit(1)

# ── Rate limit pause ─────────────────────────────────────────
print("\n⏳ Waiting 12 seconds between creations...")
time.sleep(12)

# ── YouTube ──────────────────────────────────────────────────
print("\n[2/2] Creating YouTube Channel...")
yt = create_youtube_channel(
    channel_name=TITLE,
    screenshot_dir="/tmp",
)
print(f"\nYouTube result:")
print(f"  success      : {yt.success}")
print(f"  channel_id   : {yt.channel_id}")
print(f"  channel_url  : {yt.channel_url}")
print(f"  handle       : {yt.handle}")
if yt.error:
    print(f"  error        : {yt.error}")

# ── Summary ──────────────────────────────────────────────────
print("\n" + "=" * 55)
print("  SUMMARY")
print("=" * 55)
print(f"  Facebook : {'✅ ' + (fb.page_url or '') if fb.success else '❌ ' + (fb.error or 'failed')}")
print(f"  YouTube  : {'✅ ' + (yt.channel_url or '') if yt.success else '❌ ' + (yt.error or 'failed')}")
print("=" * 55)
