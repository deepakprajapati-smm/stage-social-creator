from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

CHROME_DEBUG_PORT = int(os.getenv("CHROME_DEBUG_PORT", "9222"))
CHROME_PROFILE_DIR = os.getenv("CHROME_PROFILE_DIR", str(Path.home() / ".chrome-stage-debug"))
CDP_URL = f"http://localhost:{CHROME_DEBUG_PORT}"

FB_COOKIES_FILE = os.getenv("FB_COOKIES_FILE", str(CONFIG_DIR / "fb_cookies.json"))
META_APP_ID = os.getenv("META_APP_ID", "")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")
META_SYSTEM_USER_TOKEN = os.getenv("META_SYSTEM_USER_TOKEN", "")
META_BUSINESS_ID = os.getenv("META_BUSINESS_ID", "")

PROXY_SERVER = os.getenv("PROXY_SERVER", "")
PROXY_USERNAME = os.getenv("PROXY_USERNAME", "")
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD", "")

DB_PATH = os.getenv("DB_PATH", str(DATA_DIR / "stage_social.db"))
DB_URL = f"sqlite:///{DB_PATH}"

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8000"))
CMS_CALLBACK_URL = os.getenv("CMS_CALLBACK_URL", "")
