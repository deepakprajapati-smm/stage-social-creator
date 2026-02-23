"""
FastAPI Webhook Server
======================
CMS "Create Social Profiles" button → POST /webhook/create-profiles
Returns FB Page URL, YT Channel URL, IG Profile URL back to CMS
"""
from __future__ import annotations
import asyncio, hashlib, hmac, json, os, sys
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import WEBHOOK_SECRET, CMS_CALLBACK_URL
from db.models import init_db, get_session, TitleProfile
from workers.facebook_worker import create_fb_page

app = FastAPI(title="STAGE Social Creator API")

# Init DB on startup
@app.on_event("startup")
async def startup():
    init_db()
    print("[API] Database initialized ✓")


def verify_signature(body: bytes, signature: str) -> bool:
    """HMAC-SHA256 signature verification"""
    if not WEBHOOK_SECRET:
        return True  # Skip verification if not configured
    expected = hmac.new(
        WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


async def _create_profiles_task(title_id: str, title_name: str, title_type: str):
    """Background task: create all social profiles for a title"""
    results = {"title_id": title_id, "title_name": title_name}

    # ── Facebook Page ────────────────────────────────────────────────────────
    try:
        fb_result = await create_fb_page(title_name, title_id)
        results["facebook"] = {
            "status": "created",
            "page_id": fb_result.get("page_id"),
            "page_url": fb_result.get("page_url"),
        }
        print(f"[API] FB Page created: {fb_result.get('page_url')}")
    except Exception as e:
        results["facebook"] = {"status": "failed", "error": str(e)}
        print(f"[API] FB Page failed: {e}")

    # ── YouTube Channel — Phase 3 ────────────────────────────────────────────
    results["youtube"] = {"status": "pending", "note": "Phase 3"}

    # ── Instagram — Phase 2 ─────────────────────────────────────────────────
    results["instagram"] = {"status": "pending", "note": "Phase 2"}

    # ── Callback to CMS ─────────────────────────────────────────────────────
    if CMS_CALLBACK_URL:
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                await client.post(CMS_CALLBACK_URL, json=results, timeout=10)
            print(f"[API] CMS callback sent ✓")
        except Exception as e:
            print(f"[API] CMS callback failed: {e}")

    return results


@app.post("/webhook/create-profiles")
async def create_profiles(request: Request, background_tasks: BackgroundTasks):
    """
    CMS calls this when 'Create Social Profiles' button is clicked.
    
    Expected payload:
    {
        "title_id": "cms_123",
        "title_name": "Paani Wali Bahu",
        "title_type": "series"   // movie/series/microdrama
    }
    """
    body = await request.body()

    # Verify signature
    sig = request.headers.get("X-Hub-Signature-256", "")
    if sig and not verify_signature(body, sig):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = json.loads(body)
    title_id = payload.get("title_id")
    title_name = payload.get("title_name")
    title_type = payload.get("title_type", "content")

    if not title_id or not title_name:
        raise HTTPException(status_code=400, detail="title_id and title_name required")

    # Check idempotency — don't create twice for same title
    session = get_session()
    existing = session.query(TitleProfile).filter_by(title_id=title_id).first()
    session.close()

    if existing and existing.fb_page_id:
        return JSONResponse({
            "status": "already_exists",
            "title_id": title_id,
            "fb_page_url": existing.fb_page_url,
        })

    # Run creation in background — return immediately to CMS
    background_tasks.add_task(
        _create_profiles_task, title_id, title_name, title_type
    )

    return JSONResponse({
        "status": "creating",
        "title_id": title_id,
        "message": "Social profiles creation started. CMS will be notified when done.",
    })


@app.get("/status/{title_id}")
async def get_status(title_id: str):
    """Check creation status for a title"""
    session = get_session()
    try:
        profile = session.query(TitleProfile).filter_by(title_id=title_id).first()
        if not profile:
            raise HTTPException(status_code=404, detail="Title not found")
        return {
            "title_id": title_id,
            "title_name": profile.title_name,
            "status": profile.status,
            "fb_page_url": profile.fb_page_url,
            "yt_channel_url": profile.yt_channel_url,
            "ig_username": profile.ig_username,
        }
    finally:
        session.close()


@app.get("/health")
async def health():
    return {"status": "ok"}
