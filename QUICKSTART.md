# STAGE Social Creator — Quickstart

Auto-create Facebook Page + YouTube Channel + Instagram Account for any movie/series title.

---

## One-Time Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
patchright install chrome
```

### 2. Fill in API keys
Edit `config/settings.py` and add:
- `GEELARK_API_TOKEN` — from [open.geelark.com/api](https://open.geelark.com/api)
- `SMSMAN_API_KEY` — from [sms-man.com](https://sms-man.com) → Profile → API
- `PROXY_URL` — from [coronium.io](https://coronium.io) → 4G India proxy
- `FIVESIM_API_KEY` — from [5sim.net](https://5sim.net) → Profile (optional bulk)

### 3. Launch Chrome debug window (for FB + YT)
```bash
bash scripts/launch_chrome_debug.sh
```
After Chrome opens:
- Log into **STAGE's Facebook account**
- Log into **STAGE's Google/YouTube account**
- **Leave Chrome open** — do not close

### 4. Start Appium server (for Instagram)
```bash
appium --port 4723
```

---

## Usage

### CLI (simplest)
```bash
# English title
python scripts/create_profiles.py "Banswara Ki Kahani"

# Hindi title
python scripts/create_profiles.py "बांसवाड़ा की कहानी"

# Only FB + YT (skip Instagram)
python scripts/create_profiles.py "Kota" --only fb yt

# Just preview handles (no account creation)
python scripts/create_profiles.py "Udaipur" --dry-run
```

### API (for CRM integration later)
```bash
# Start the API server
uvicorn api.main:app --host 0.0.0.0 --port 8000

# Create profiles
curl -X POST http://localhost:8000/create-profiles \
  -H "Content-Type: application/json" \
  -d '{"title": "Banswara Ki Kahani"}'

# Check status
curl http://localhost:8000/status/1

# List all jobs
curl http://localhost:8000/jobs
```

---

## What Gets Created

For title **"Banswara Ki Kahani"**:

| Platform | What | Handle/URL |
|---|---|---|
| Facebook | Page | `facebook.com/StageBanswadaKiKahani` |
| YouTube | Brand Channel | `@StageBanswadaKiKahani` |
| Instagram | Fresh Account | `@stage.banswadakikahani` |

Instagram account goes through **30-day AI warmup** via GeeLark before it's "ready" for posting.

---

## Folder Structure

```
stage-social-creator/
├── api/
│   └── main.py              # FastAPI — POST /create-profiles
├── workers/
│   ├── naming_engine.py     # Hindi title → social handles
│   ├── facebook_worker.py   # FB Page via Patchright + Chrome CDP
│   ├── youtube_worker.py    # YT Channel via Patchright + Chrome CDP
│   ├── instagram_worker.py  # IG Account via GeeLark + Appium
│   └── otp_service.py       # SMS-Man / 5sim OTP
├── db/
│   └── database.py          # SQLite status tracker
├── scripts/
│   ├── create_profiles.py   # CLI entry point
│   └── launch_chrome_debug.sh
├── config/
│   └── settings.py          # API keys + config
├── requirements.txt
└── QUICKSTART.md
```

---

## OTP Services (sms-activate.io is dead since Dec 2025)

| Service | Use | Price |
|---|---|---|
| **SMS-Man.com** | Primary (recommended) | ~$0.05/number |
| **5sim.net** | Bulk/cheap | ~$0.01/number |
| TextVerified.com | High-value accounts (US numbers) | $0.25/number |

---

## Instagram Warmup Timeline

After account creation, GeeLark AI warmup runs automatically:

| Days | Status |
|---|---|
| Day 0 | Account created, warmup starts |
| Day 1-3 | Browse only (no actions) |
| Day 4-7 | Light likes + follows |
| Day 8-14 | Moderate engagement + first post |
| Day 15-30 | Full engagement ramp-up |
| Day 30+ | **READY** — add to posting tool |

---

## CRM Integration (Later)

When ready to connect to STAGE's CRM:

1. Deploy this API on a server
2. Add "Create Social Profiles" button in CRM that calls:
   ```
   POST https://your-server/create-profiles
   {"title": "Movie Name", "crm_id": "123", "callback_url": "https://crm/update"}
   ```
3. CRM gets callback when all profiles are created with URLs

---

## Costs (~12 districts)

| Service | Monthly |
|---|---|
| GeeLark Pro (20 profiles) | $19 |
| GeeLark cloud phone usage | ~$14 |
| Coronium.io 4G India proxy | ~$20 |
| SMS-Man OTP (12 accounts) | ~$1 |
| **Total** | **~$54/month** |
