"""
db/database.py — SQLite status tracker for social profile creation jobs

Schema:
  profiles table — one row per title, tracks FB/YT/IG creation status

Usage:
    from db.database import DB
    db = DB()
    db.create_job("Banswara Ki Kahani", handles)
    db.update_fb(job_id, fb_url)
    db.update_ig_warmup_day(job_id, 5)
    db.get_job(job_id)
"""

import sqlite3
import json
import time
import logging
from dataclasses import dataclass, asdict
from typing import Optional
from contextlib import contextmanager

log = logging.getLogger(__name__)

DEFAULT_DB_PATH = "stage_social.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    slug            TEXT NOT NULL,

    -- Naming engine output (JSON)
    handles_json    TEXT,

    -- Status: pending | in_progress | done | failed
    status          TEXT DEFAULT 'pending',

    -- Facebook
    fb_status       TEXT DEFAULT 'pending',
    fb_page_name    TEXT,
    fb_page_id      TEXT,
    fb_url          TEXT,
    fb_error        TEXT,

    -- YouTube
    yt_status       TEXT DEFAULT 'pending',
    yt_channel_name TEXT,
    yt_channel_id   TEXT,
    yt_url          TEXT,
    yt_handle       TEXT,
    yt_error        TEXT,

    -- Instagram
    ig_status       TEXT DEFAULT 'pending',
    ig_handle       TEXT,
    ig_username     TEXT,
    ig_password     TEXT,   -- stored (consider encrypting in production)
    ig_phone        TEXT,
    ig_device_id    TEXT,   -- GeeLark device ID
    ig_warmup_day   INTEGER DEFAULT 0,
    ig_warmup_status TEXT DEFAULT 'not_started',
    ig_url          TEXT,
    ig_error        TEXT,

    -- Timestamps
    created_at      INTEGER,
    updated_at      INTEGER,
    completed_at    INTEGER
);

CREATE INDEX IF NOT EXISTS idx_slug   ON profiles(slug);
CREATE INDEX IF NOT EXISTS idx_status ON profiles(status);
"""


@contextmanager
def _conn(db_path: str):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


class DB:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._init()

    def _init(self):
        with _conn(self.db_path) as con:
            con.executescript(SCHEMA)

    def _now(self) -> int:
        return int(time.time())

    # ── Create ────────────────────────────────────────────────────────────────

    def create_job(self, title: str, handles) -> int:
        """
        Create a new profile creation job.
        Returns the job ID.
        """
        from workers.naming_engine import SocialHandles
        handles_dict = handles.as_dict() if isinstance(handles, SocialHandles) else handles
        slug = handles_dict.get("slug", title.lower().replace(" ", "-"))
        now  = self._now()

        with _conn(self.db_path) as con:
            cur = con.execute(
                """
                INSERT INTO profiles
                  (title, slug, handles_json, status, created_at, updated_at)
                VALUES (?, ?, ?, 'pending', ?, ?)
                """,
                (title, slug, json.dumps(handles_dict, ensure_ascii=False), now, now),
            )
            return cur.lastrowid

    # ── Updates ───────────────────────────────────────────────────────────────

    def _update(self, job_id: int, **kwargs):
        kwargs["updated_at"] = self._now()
        cols  = ", ".join(f"{k} = ?" for k in kwargs)
        vals  = list(kwargs.values()) + [job_id]
        with _conn(self.db_path) as con:
            con.execute(f"UPDATE profiles SET {cols} WHERE id = ?", vals)

    def update_fb(self, job_id: int, page_id: str, page_url: str, page_name: str):
        self._update(job_id,
                     fb_status="done", fb_page_id=page_id,
                     fb_url=page_url, fb_page_name=page_name)
        log.info(f"[job {job_id}] FB done: {page_url}")

    def fail_fb(self, job_id: int, error: str):
        self._update(job_id, fb_status="failed", fb_error=error)

    def update_yt(self, job_id: int, channel_id: str, channel_url: str,
                  channel_name: str, handle: Optional[str]):
        self._update(job_id,
                     yt_status="done", yt_channel_id=channel_id,
                     yt_url=channel_url, yt_channel_name=channel_name,
                     yt_handle=handle)
        log.info(f"[job {job_id}] YT done: {channel_url}")

    def fail_yt(self, job_id: int, error: str):
        self._update(job_id, yt_status="failed", yt_error=error)

    def update_ig_created(self, job_id: int, ig_username: str, ig_password: str,
                          ig_phone: str, device_id: str, warmup_status: str):
        handle = f"@{ig_username}"
        ig_url = f"https://instagram.com/{ig_username}"
        self._update(job_id,
                     ig_status="warming_up",
                     ig_handle=handle,
                     ig_username=ig_username,
                     ig_password=ig_password,
                     ig_phone=ig_phone,
                     ig_device_id=device_id,
                     ig_warmup_status=warmup_status,
                     ig_url=ig_url)
        log.info(f"[job {job_id}] IG created: {handle}")

    def fail_ig(self, job_id: int, error: str):
        self._update(job_id, ig_status="failed", ig_error=error)

    def update_ig_warmup_day(self, job_id: int, day: int):
        self._update(job_id, ig_warmup_day=day)

    def mark_ig_ready(self, job_id: int):
        self._update(job_id, ig_status="ready", ig_warmup_status="complete")
        log.info(f"[job {job_id}] IG warmup complete — account ready")

    def mark_complete(self, job_id: int):
        now = self._now()
        self._update(job_id, status="done", completed_at=now)

    def mark_failed(self, job_id: int):
        self._update(job_id, status="failed")

    def set_status(self, job_id: int, status: str):
        self._update(job_id, status=status)

    # ── Reads ─────────────────────────────────────────────────────────────────

    def get_job(self, job_id: int) -> Optional[dict]:
        with _conn(self.db_path) as con:
            row = con.execute("SELECT * FROM profiles WHERE id = ?", (job_id,)).fetchone()
            return dict(row) if row else None

    def get_by_slug(self, slug: str) -> Optional[dict]:
        with _conn(self.db_path) as con:
            row = con.execute("SELECT * FROM profiles WHERE slug = ?", (slug,)).fetchone()
            return dict(row) if row else None

    def list_jobs(self, status: Optional[str] = None) -> list[dict]:
        with _conn(self.db_path) as con:
            if status:
                rows = con.execute("SELECT * FROM profiles WHERE status = ? ORDER BY id DESC", (status,)).fetchall()
            else:
                rows = con.execute("SELECT * FROM profiles ORDER BY id DESC").fetchall()
            return [dict(r) for r in rows]

    def summary(self, job_id: int) -> dict:
        """Return a clean summary dict suitable for API response."""
        job = self.get_job(job_id)
        if not job:
            return {}
        return {
            "job_id":  job_id,
            "title":   job["title"],
            "status":  job["status"],
            "facebook": {
                "status":   job["fb_status"],
                "page_name": job["fb_page_name"],
                "url":      job["fb_url"],
            },
            "youtube": {
                "status":       job["yt_status"],
                "channel_name": job["yt_channel_name"],
                "handle":       job["yt_handle"],
                "url":          job["yt_url"],
            },
            "instagram": {
                "status":        job["ig_status"],
                "handle":        job["ig_handle"],
                "warmup_day":    job["ig_warmup_day"],
                "warmup_status": job["ig_warmup_status"],
                "url":           job["ig_url"],
            },
        }


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json
    from workers.naming_engine import generate_handles

    db = DB("/tmp/test_stage.db")
    h  = generate_handles("Banswara Ki Kahani")
    jid = db.create_job("Banswara Ki Kahani", h)
    print(f"Created job: {jid}")

    db.update_fb(jid, "123456789", "https://facebook.com/StageBanswara", "STAGE Banswara")
    db.update_yt(jid, "UCtest123", "https://youtube.com/channel/UCtest123",
                 "STAGE Banswara Ki Kahani", "@StageBanswara")
    db.update_ig_created(jid, "stage.banswara", "Abcd1234!", "+91XXXXXXXXXX",
                         "geelark-device-001", "warming_up")

    print(json.dumps(db.summary(jid), indent=2, ensure_ascii=False))
