"""
config/settings.py — All API keys and configuration for stage-social-creator.
Copy this file to config/settings_local.py and fill in your actual keys.
"""
import os

# ─────────────────────────────────────────────
# GeeLark API
# Get from: geelark.com → Dashboard → API section → open.geelark.com/api
# ─────────────────────────────────────────────
GEELARK_API_TOKEN = os.getenv("GEELARK_API_TOKEN", "YOUR_GEELARK_API_TOKEN")
GEELARK_API_BASE  = "https://api.geelark.com"

# GeeLark cloud phone config
GEELARK_ANDROID_VERSION = "Android12"  # Android11 or Android12
GEELARK_WARMUP_TEMPLATE_ID = "instagram-ai-account-warmup"  # from Automation Marketplace

# ─────────────────────────────────────────────
# SMS OTP Services
# Primary: SMS-Man.com (sms-activate.io shut down Dec 2025)
# Bulk:    5sim.net
# ─────────────────────────────────────────────
SMSMAN_API_KEY   = os.getenv("SMSMAN_API_KEY", "YOUR_SMSMAN_API_KEY")
SMSMAN_BASE_URL  = "https://api.sms-man.com/control"

FIVESIM_API_KEY  = os.getenv("FIVESIM_API_KEY", "YOUR_5SIM_JWT_TOKEN")
FIVESIM_BASE_URL = "https://5sim.net/v1"

# Which OTP service to use: "smsman" or "fivesim"
OTP_SERVICE      = os.getenv("OTP_SERVICE", "smsman")

# Country for phone numbers (India = 14 on smsman, "india" on 5sim)
OTP_COUNTRY_SMSMAN  = 14    # India
OTP_COUNTRY_FIVESIM = "india"

# ─────────────────────────────────────────────
# Proxy config (Coronium.io 4G India proxies)
# Get from: coronium.io → Dashboard → Your proxies
# Format: "http://user:pass@host:port"
# ─────────────────────────────────────────────
PROXY_URL = os.getenv("PROXY_URL", "http://user:pass@proxy.coronium.io:PORT")

# ─────────────────────────────────────────────
# Chrome CDP (for FB + YT via existing Chrome)
# Launch Chrome with: scripts/launch_chrome_debug.sh
# ─────────────────────────────────────────────
CHROME_CDP_URL       = os.getenv("CHROME_CDP_URL", "http://localhost:9222")
CHROME_USER_DATA_DIR = os.path.expanduser("~/.chrome-stage-debug")

# ─────────────────────────────────────────────
# Database
# ─────────────────────────────────────────────
DB_PATH = os.getenv("DB_PATH", "stage_social.db")

# ─────────────────────────────────────────────
# Brand settings
# ─────────────────────────────────────────────
BRAND_PREFIX    = "STAGE"           # e.g. STAGE Banswara
BRAND_PREFIX_LC = "stage"           # for IG handles: stage.banswara
FB_CATEGORY     = "Digital creator" # search string for FB category autocomplete

# ─────────────────────────────────────────────
# Timing (seconds)
# ─────────────────────────────────────────────
WARMUP_DAYS          = 30   # days before IG account is "ready"
OTP_POLL_INTERVAL    = 10   # seconds between OTP checks
OTP_MAX_WAIT         = 300  # 5 minutes max wait for OTP
CHROME_ACTION_DELAY  = (0.8, 2.5)   # min/max seconds between CDP actions
YT_BETWEEN_CHANNELS  = 600          # 10 min between YT channel creations
