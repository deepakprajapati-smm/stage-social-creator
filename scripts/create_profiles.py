#!/usr/bin/env python3
"""
scripts/create_profiles.py — CLI to create social profiles for a title

Usage:
    python scripts/create_profiles.py "Banswara Ki Kahani"
    python scripts/create_profiles.py "बांसवाड़ा की कहानी"
    python scripts/create_profiles.py "Kota" --only fb yt
    python scripts/create_profiles.py "Banswara" --dry-run
"""

import argparse
import json
import logging
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Create FB Page + YT Channel + IG Account for a title"
    )
    parser.add_argument("title", help='Title e.g. "Banswara Ki Kahani" or "बांसवाड़ा"')
    parser.add_argument(
        "--only",
        nargs="+",
        choices=["fb", "yt", "ig", "naming"],
        default=["fb", "yt", "ig"],
        help="Which platforms to create (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only generate handles, do not create anything",
    )
    parser.add_argument(
        "--cdp-url",
        default="http://localhost:9222",
        help="Chrome CDP URL (default: http://localhost:9222)",
    )
    args = parser.parse_args()

    # ── Step 1: Generate handles ─────────────────────────────────────────────
    from workers.naming_engine import generate_handles
    from config.settings import BRAND_PREFIX

    log.info(f"Generating handles for: {args.title}")
    handles = generate_handles(args.title, brand_prefix=BRAND_PREFIX)

    print("\n" + "─" * 55)
    print("HANDLES GENERATED")
    print("─" * 55)
    print(json.dumps(handles.as_dict(), ensure_ascii=False, indent=2))

    if args.dry_run or "naming" in args.only:
        print("\n[dry-run] Stopping here — no accounts created.")
        return

    # ── Step 2: Create DB job ────────────────────────────────────────────────
    from db.database import DB
    db     = DB()
    job_id = db.create_job(args.title, handles)
    log.info(f"Job created: {job_id}")

    results = {}

    # ── Step 3: Create FB page ───────────────────────────────────────────────
    if "fb" in args.only:
        print("\n" + "─" * 55)
        print("CREATING FACEBOOK PAGE")
        print("─" * 55)
        from workers.facebook_worker import create_facebook_page
        from config.settings import FB_CATEGORY

        fb = create_facebook_page(
            page_name     = handles.fb_page_name,
            category      = FB_CATEGORY,
            cdp_url       = args.cdp_url,
            screenshot_dir= f"/tmp/stage_job_{job_id}",
        )
        os.makedirs(f"/tmp/stage_job_{job_id}", exist_ok=True)
        results["facebook"] = fb

        if fb.success:
            db.update_fb(job_id, fb.page_id or "", fb.page_url or "", fb.page_name or "")
            print(f"  ✓ FB Page created: {fb.page_url}")
        else:
            db.fail_fb(job_id, fb.error or "Unknown")
            print(f"  ✗ FB Page FAILED: {fb.error}")

    # ── Step 4: Create YT channel ────────────────────────────────────────────
    if "yt" in args.only:
        print("\n" + "─" * 55)
        print("CREATING YOUTUBE CHANNEL")
        print("─" * 55)
        from workers.youtube_worker import create_youtube_channel

        yt = create_youtube_channel(
            channel_name  = handles.yt_channel_name,
            cdp_url       = args.cdp_url,
            screenshot_dir= f"/tmp/stage_job_{job_id}",
        )
        results["youtube"] = yt

        if yt.success:
            db.update_yt(job_id, yt.channel_id or "", yt.channel_url or "",
                         yt.channel_name or "", yt.handle)
            print(f"  ✓ YT Channel created: {yt.channel_url}")
            if yt.handle:
                print(f"    Handle: {yt.handle}")
        else:
            db.fail_yt(job_id, yt.error or "Unknown")
            print(f"  ✗ YT Channel FAILED: {yt.error}")

    # ── Step 5: Create IG account ────────────────────────────────────────────
    if "ig" in args.only:
        print("\n" + "─" * 55)
        print("CREATING INSTAGRAM ACCOUNT")
        print("─" * 55)
        from workers.instagram_worker import create_instagram_account

        ig = create_instagram_account(ig_handle=handles.ig_handle)
        results["instagram"] = ig

        if ig.success:
            db.update_ig_created(
                job_id,
                ig.ig_username or handles.ig_handle,
                ig.ig_password or "",
                ig.phone_used  or "",
                ig.device_id   or "",
                ig.warmup_status,
            )
            print(f"  ✓ IG Account created: {ig.ig_handle}")
            print(f"    Warmup: {ig.warmup_status} (30 days via GeeLark)")
        else:
            db.fail_ig(job_id, ig.error or "Unknown")
            print(f"  ✗ IG Account FAILED: {ig.error}")

    # ── Step 6: Summary ──────────────────────────────────────────────────────
    print("\n" + "─" * 55)
    print("FINAL STATUS")
    print("─" * 55)
    summary = db.summary(job_id)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nJob ID: {job_id} — check anytime with:")
    print(f"  python scripts/create_profiles.py --status {job_id}")


if __name__ == "__main__":
    main()
