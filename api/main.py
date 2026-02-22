"""
api/main.py — FastAPI service for STAGE social profile creation

Endpoints:
  POST /create-profiles    — Create FB Page + YT Channel + IG Account for a title
  GET  /status/{job_id}    — Check status of a creation job
  GET  /jobs               — List all jobs

Run: uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

Later: CRM will call POST /create-profiles when "Create Social Profiles" is clicked.
"""

import logging
import asyncio
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

log = logging.getLogger(__name__)

app = FastAPI(
    title="STAGE Social Creator",
    description="Auto-create FB Page + YT Channel + IG Account for any title",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Thread pool for blocking workers (Playwright, Appium are sync)
_executor = ThreadPoolExecutor(max_workers=4)


# ── Request / Response models ─────────────────────────────────────────────────

class CreateProfilesRequest(BaseModel):
    title:      str                    # "Banswara Ki Kahani" or "बांसवाड़ा की कहानी"
    language:   Optional[str] = None   # "vagdi", "hadoti", "hindi", "english" (optional hint)
    crm_id:     Optional[str] = None   # CRM record ID to callback with results
    callback_url: Optional[str] = None # URL to POST results when complete

class CreateProfilesResponse(BaseModel):
    job_id:    int
    status:    str
    handles:   dict
    message:   str

class StatusResponse(BaseModel):
    job_id:    int
    title:     str
    status:    str
    facebook:  dict
    youtube:   dict
    instagram: dict


# ── Background job runner ─────────────────────────────────────────────────────

def _run_creation_job(job_id: int, title: str, handles, callback_url: Optional[str]):
    """
    Run the full profile creation pipeline in background thread.
    FB + YT run in parallel. IG runs after.
    """
    from db.database import DB
    from workers.facebook_worker  import create_facebook_page
    from workers.youtube_worker   import create_youtube_channel
    from workers.instagram_worker import create_instagram_account
    from config.settings import CHROME_CDP_URL, FB_CATEGORY

    db = DB()
    db.set_status(job_id, "in_progress")

    fb_result = None
    yt_result = None

    # ── FB + YT in parallel threads ───────────────────────────────────────
    def run_fb():
        nonlocal fb_result
        log.info(f"[job {job_id}] Starting FB page creation: {handles.fb_page_name}")
        result = create_facebook_page(
            page_name    = handles.fb_page_name,
            category     = FB_CATEGORY,
            cdp_url      = CHROME_CDP_URL,
            screenshot_dir = f"/tmp/stage_job_{job_id}",
        )
        fb_result = result
        if result.success:
            db.update_fb(job_id, result.page_id or "", result.page_url or "", result.page_name or "")
        else:
            db.fail_fb(job_id, result.error or "Unknown error")

    def run_yt():
        nonlocal yt_result
        log.info(f"[job {job_id}] Starting YT channel creation: {handles.yt_channel_name}")
        result = create_youtube_channel(
            channel_name   = handles.yt_channel_name,
            cdp_url        = CHROME_CDP_URL,
            screenshot_dir = f"/tmp/stage_job_{job_id}",
        )
        yt_result = result
        if result.success:
            db.update_yt(job_id, result.channel_id or "", result.channel_url or "",
                         result.channel_name or "", result.handle)
        else:
            db.fail_yt(job_id, result.error or "Unknown error")

    import threading
    import os
    os.makedirs(f"/tmp/stage_job_{job_id}", exist_ok=True)

    fb_thread = threading.Thread(target=run_fb, name=f"fb-{job_id}")
    yt_thread = threading.Thread(target=run_yt, name=f"yt-{job_id}")

    fb_thread.start()
    yt_thread.start()
    fb_thread.join()
    yt_thread.join()

    # ── IG (sequential, needs GeeLark + OTP) ──────────────────────────────
    log.info(f"[job {job_id}] Starting IG account creation: @{handles.ig_handle}")
    ig_result = create_instagram_account(ig_handle=handles.ig_handle)
    if ig_result.success:
        db.update_ig_created(
            job_id,
            ig_result.ig_username or handles.ig_handle,
            ig_result.ig_password or "",
            ig_result.phone_used  or "",
            ig_result.device_id   or "",
            ig_result.warmup_status,
        )
    else:
        db.fail_ig(job_id, ig_result.error or "Unknown error")

    # ── Mark overall job status ────────────────────────────────────────────
    job = db.get_job(job_id)
    all_done   = all(job[k] == "done"    for k in ("fb_status", "yt_status"))
    any_failed = any(job[k] == "failed"  for k in ("fb_status", "yt_status", "ig_status"))

    if all_done and ig_result.success:
        db.mark_complete(job_id)
        log.info(f"[job {job_id}] All platforms created successfully")
    elif any_failed:
        db.mark_failed(job_id)
        log.warning(f"[job {job_id}] Some platforms failed")
    else:
        db.set_status(job_id, "partial")

    # ── Callback to CRM if URL provided ───────────────────────────────────
    if callback_url:
        try:
            import requests
            payload = db.summary(job_id)
            requests.post(callback_url, json=payload, timeout=10)
            log.info(f"[job {job_id}] Callback sent to {callback_url}")
        except Exception as e:
            log.warning(f"[job {job_id}] Callback failed: {e}")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/create-profiles", response_model=CreateProfilesResponse)
async def create_profiles(req: CreateProfilesRequest, background_tasks: BackgroundTasks):
    """
    Start creating social profiles for a title.

    Returns immediately with job_id.
    Check progress at GET /status/{job_id}
    """
    from workers.naming_engine import generate_handles
    from db.database import DB
    from config.settings import BRAND_PREFIX

    # Generate handles
    handles = generate_handles(req.title, brand_prefix=BRAND_PREFIX)

    # Create DB job
    db    = DB()
    job_id = db.create_job(req.title, handles)

    # Start background job
    background_tasks.add_task(
        _run_creation_job,
        job_id=job_id,
        title=req.title,
        handles=handles,
        callback_url=req.callback_url,
    )

    log.info(f"Created job {job_id} for title: {req.title}")

    return CreateProfilesResponse(
        job_id  = job_id,
        status  = "pending",
        handles = handles.as_dict(),
        message = f"Profile creation started. Check /status/{job_id} for progress.",
    )


@app.get("/status/{job_id}", response_model=StatusResponse)
async def get_status(job_id: int):
    """Get the current status of a profile creation job."""
    from db.database import DB

    db  = DB()
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    summary = db.summary(job_id)
    return StatusResponse(**summary)


@app.get("/jobs")
async def list_jobs(status: Optional[str] = None):
    """List all jobs, optionally filtered by status."""
    from db.database import DB
    db   = DB()
    jobs = db.list_jobs(status=status)
    return {"jobs": [db.summary(j["id"]) for j in jobs], "total": len(jobs)}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "stage-social-creator"}


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
