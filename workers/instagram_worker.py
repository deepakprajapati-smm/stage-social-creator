"""
workers/instagram_worker.py — Create a fresh Instagram account via GeeLark cloud phone

Flow:
  1. Create GeeLark cloud phone instance (ARM, unique fingerprint)
  2. Assign Coronium.io 4G India proxy to instance
  3. Install Instagram APK on cloud phone
  4. Connect Appium via ADB to cloud phone
  5. Automate Instagram signup with OTP from SMS-Man
  6. Save credentials
  7. Trigger 30-day AI warmup via GeeLark automation template
  8. Return IG account handle + warmup status

Prerequisites:
  - GeeLark account (Pro plan) — geelark.com
  - API token from open.geelark.com/api
  - Coronium.io proxy subscription — coronium.io
  - SMS-Man.com API key — sms-man.com
  - Appium server running locally: appium --port 4723
  - adb installed: brew install android-platform-tools
"""

import time
import random
import logging
import requests
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class IGAccountResult:
    success:      bool
    ig_handle:    Optional[str] = None
    ig_username:  Optional[str] = None
    ig_password:  Optional[str] = None
    phone_used:   Optional[str] = None
    device_id:    Optional[str] = None   # GeeLark device ID
    warmup_status: str          = "not_started"
    error:        Optional[str] = None


# ── GeeLark API client ────────────────────────────────────────────────────────

class GeeLarkClient:
    """
    GeeLark REST API client.
    Full API docs: open.geelark.com/api (requires GeeLark account login)
    Base URL: https://api.geelark.com
    """

    def __init__(self, api_token: str, base_url: str = "https://api.geelark.com"):
        self.base_url = base_url
        self.headers  = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type":  "application/json",
        }

    def _post(self, path: str, payload: dict) -> dict:
        r = requests.post(f"{self.base_url}{path}", headers=self.headers, json=payload, timeout=30)
        r.raise_for_status()
        return r.json()

    def _get(self, path: str) -> dict:
        r = requests.get(f"{self.base_url}{path}", headers=self.headers, timeout=30)
        r.raise_for_status()
        return r.json()

    def create_device(self, name: str, proxy_url: str, android_version: str = "Android12") -> dict:
        """
        Create and launch a new cloud phone instance.
        Returns device info including device_id.
        NOTE: Exact payload field names must be verified from open.geelark.com/api
        """
        payload = {
            "name":    name,
            "os":      android_version,
            "proxy":   proxy_url,
        }
        return self._post("/devices/launch", payload)

    def get_device(self, device_id: str) -> dict:
        """Get device info including ADB connection IP/port/auth."""
        return self._get(f"/devices/{device_id}")

    def start_device(self, device_id: str) -> dict:
        return self._post(f"/devices/{device_id}/start", {})

    def stop_device(self, device_id: str) -> dict:
        return self._post(f"/devices/{device_id}/stop", {})

    def install_app(self, device_id: str, package_name: str) -> dict:
        """Install an app by package name (e.g. com.instagram.android)."""
        return self._post(f"/devices/{device_id}/install", {"package": package_name})

    def trigger_warmup(self, device_id: str, template_id: str) -> dict:
        """Trigger a GeeLark Automation Marketplace template (e.g. Instagram AI warmup)."""
        return self._post("/tasks", {
            "device_id":   device_id,
            "template_id": template_id,
        })

    def wait_for_device_ready(self, device_id: str, max_wait: int = 120) -> bool:
        """Poll until device status is 'running'."""
        for _ in range(max_wait // 5):
            time.sleep(5)
            try:
                info   = self.get_device(device_id)
                status = info.get("status", "")
                log.info(f"GeeLark device {device_id} status: {status}")
                if status in ("running", "online", "active"):
                    return True
            except Exception as e:
                log.warning(f"GeeLark poll error: {e}")
        return False


# ── ADB + Appium connection ───────────────────────────────────────────────────

def _adb_connect(ip: str, port: int, auth_code: str) -> bool:
    """Connect ADB to a GeeLark cloud phone."""
    import subprocess
    try:
        subprocess.run(["adb", "connect", f"{ip}:{port}"], check=True, capture_output=True)
        subprocess.run(["adb", "-s", f"{ip}:{port}", "shell", "glogin", auth_code],
                       check=True, capture_output=True)
        time.sleep(3)
        return True
    except subprocess.CalledProcessError as e:
        log.error(f"ADB connect failed: {e}")
        return False

def _get_appium_driver(ip: str, port: int):
    """Connect Appium to a GeeLark cloud phone running Instagram."""
    from appium import webdriver

    caps = {
        "platformName":      "Android",
        "deviceName":        "GeeLark",
        "deviceId":          f"{ip}:{port}",
        "automationName":    "UiAutomator2",
        "appPackage":        "com.instagram.android",
        "appActivity":       ".activity.MainTabActivity",
        "noReset":           True,
        "newCommandTimeout": 300,
    }
    return webdriver.Remote("http://localhost:4723/wd/hub", caps)


# ── Instagram signup automation ───────────────────────────────────────────────

def _generate_password() -> str:
    """Generate a strong random password."""
    import string
    chars = string.ascii_letters + string.digits + "!@#$%"
    return "".join(random.choices(chars, k=16))

def _delay(min_s: float, max_s: float):
    time.sleep(random.uniform(min_s, max_s))

def _signup_instagram(driver, ig_handle: str, phone: str, otp_getter) -> dict:
    """
    Automate Instagram signup via Appium on the GeeLark cloud phone.

    Args:
        driver:     Appium WebDriver connected to GeeLark phone
        ig_handle:  Desired Instagram username
        phone:      Phone number for OTP verification
        otp_getter: Callable() → str that returns OTP code

    Returns:
        dict with username, password, success
    """
    from appium.webdriver.common.appiumby import AppiumBy

    password = _generate_password()

    def find(by, value, timeout=10):
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        return WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, value))
        )

    def tap_text(text: str, timeout: int = 10):
        el = find(AppiumBy.ANDROID_UIAUTOMATOR,
                  f'new UiSelector().textContains("{text}")', timeout)
        el.click()
        _delay(0.5, 1.2)

    def type_field(resource_id_fragment: str, text: str):
        el = find(AppiumBy.ANDROID_UIAUTOMATOR,
                  f'new UiSelector().resourceIdMatches(".*{resource_id_fragment}.*")')
        el.clear()
        for char in text:
            el.send_keys(char)
            time.sleep(random.uniform(0.05, 0.15))
        _delay(0.3, 0.8)

    try:
        # Launch Instagram
        driver.activate_app("com.instagram.android")
        _delay(2.0, 4.0)

        # Tap "Create new account"
        tap_text("Create new account")
        tap_text("Sign up with phone")

        # Enter phone number
        type_field("phone_number", phone)
        tap_text("Next")
        _delay(3.0, 6.0)  # wait for OTP SMS

        # Get OTP
        otp = otp_getter()
        if not otp:
            return {"success": False, "error": "OTP not received"}

        # Enter OTP
        type_field("confirmation_code", otp)
        tap_text("Next")
        _delay(1.0, 2.0)

        # Enter name (use handle as display name)
        display_name = ig_handle.replace(".", " ").replace("_", " ").title()
        type_field("full_name", display_name)
        tap_text("Next")
        _delay(0.5, 1.0)

        # Enter password
        type_field("password", password)
        tap_text("Next")
        _delay(1.0, 2.0)

        # Birthday (skip/next)
        try:
            tap_text("Next")
        except Exception:
            pass
        _delay(0.5, 1.0)

        # Username — clear default and set our handle
        try:
            username_field = find(AppiumBy.ANDROID_UIAUTOMATOR,
                                  'new UiSelector().resourceIdMatches(".*username.*")')
            username_field.clear()
            for char in ig_handle:
                username_field.send_keys(char)
                time.sleep(random.uniform(0.05, 0.12))
            _delay(1.0, 2.0)
            tap_text("Next")
        except Exception as e:
            log.warning(f"Could not set custom username: {e}")

        _delay(2.0, 4.0)

        # Skip optional steps (contacts, notifications, etc.)
        for skip_text in ["Not Now", "Skip", "Later", "Allow"]:
            try:
                tap_text(skip_text)
                _delay(0.5, 1.0)
            except Exception:
                pass

        return {
            "success":  True,
            "username": ig_handle,
            "password": password,
        }

    except Exception as e:
        log.error(f"Instagram signup automation error: {e}")
        return {"success": False, "error": str(e)}


# ── Main worker ───────────────────────────────────────────────────────────────

def create_instagram_account(
    ig_handle:           str,
    geelark_api_token:   str = "",
    proxy_url:           str = "",
    otp_service:         str = "smsman",
    otp_api_key:         str = "",
    warmup_template_id:  str = "instagram-ai-account-warmup",
    android_version:     str = "Android12",
) -> IGAccountResult:
    """
    Create a fresh Instagram account on a GeeLark cloud phone.

    Args:
        ig_handle:          Desired Instagram username (e.g. "stage.banswara")
        geelark_api_token:  GeeLark API token from open.geelark.com/api
        proxy_url:          Coronium.io 4G India proxy "http://user:pass@host:port"
        otp_service:        "smsman" or "fivesim"
        otp_api_key:        API key for the OTP service
        warmup_template_id: GeeLark automation template ID for IG warmup
        android_version:    "Android11" or "Android12"

    Returns:
        IGAccountResult
    """
    # Load from config if not provided
    if not geelark_api_token or not proxy_url or not otp_api_key:
        from config.settings import (
            GEELARK_API_TOKEN, PROXY_URL,
            OTP_SERVICE, SMSMAN_API_KEY, FIVESIM_API_KEY,
            GEELARK_ANDROID_VERSION, GEELARK_WARMUP_TEMPLATE_ID,
        )
        geelark_api_token  = geelark_api_token  or GEELARK_API_TOKEN
        proxy_url          = proxy_url           or PROXY_URL
        otp_service        = otp_service         or OTP_SERVICE
        otp_api_key        = otp_api_key         or (SMSMAN_API_KEY if otp_service == "smsman" else FIVESIM_API_KEY)
        android_version    = android_version     or GEELARK_ANDROID_VERSION
        warmup_template_id = warmup_template_id  or GEELARK_WARMUP_TEMPLATE_ID

    geelark   = GeeLarkClient(geelark_api_token)
    device_id = None

    try:
        # ── Step 1: Create GeeLark cloud phone ────────────────────────────
        device_name = f"stage_{ig_handle}_{int(time.time())}"
        log.info(f"Creating GeeLark cloud phone: {device_name}")
        device_info = geelark.create_device(device_name, proxy_url, android_version)
        device_id   = device_info.get("device_id") or device_info.get("id")
        if not device_id:
            return IGAccountResult(success=False, error=f"GeeLark device creation failed: {device_info}")

        log.info(f"GeeLark device created: {device_id}")

        # ── Step 2: Wait for device to be running ─────────────────────────
        if not geelark.wait_for_device_ready(device_id):
            return IGAccountResult(success=False, device_id=device_id,
                                   error="GeeLark device did not become ready within 2 minutes")

        # ── Step 3: Install Instagram ──────────────────────────────────────
        log.info("Installing Instagram on cloud phone...")
        geelark.install_app(device_id, "com.instagram.android")
        time.sleep(15)  # wait for install

        # ── Step 4: Get ADB connection info ────────────────────────────────
        log.info("Getting ADB connection info...")
        info    = geelark.get_device(device_id)
        adb_ip   = info.get("adb_ip") or info.get("ip")
        adb_port = int(info.get("adb_port") or info.get("port", 5555))
        auth_code = info.get("auth_code") or info.get("adb_auth", "")

        if not adb_ip:
            return IGAccountResult(success=False, device_id=device_id,
                                   error="Could not get ADB connection info from GeeLark")

        # ── Step 5: Connect ADB ────────────────────────────────────────────
        log.info(f"Connecting ADB to {adb_ip}:{adb_port}")
        if not _adb_connect(adb_ip, adb_port, auth_code):
            return IGAccountResult(success=False, device_id=device_id,
                                   error="ADB connection failed")

        # ── Step 6: Get OTP number ─────────────────────────────────────────
        from workers.otp_service import get_instagram_otp
        log.info(f"Requesting OTP number from {otp_service}...")
        otp_result = get_instagram_otp(service=otp_service, api_key=otp_api_key)
        if not otp_result.success or not otp_result.phone:
            return IGAccountResult(success=False, device_id=device_id,
                                   error=f"OTP number acquisition failed: {otp_result.error}")

        phone = otp_result.phone
        log.info(f"Got phone number: {phone}")

        # ── Step 7: Connect Appium + automate signup ───────────────────────
        log.info("Connecting Appium...")
        driver = _get_appium_driver(adb_ip, adb_port)

        # OTP getter — OTP may already be in otp_result, or we need to wait
        if otp_result.otp:
            otp_code = otp_result.otp
            otp_getter = lambda: otp_code
        else:
            from workers.otp_service import SMSManClient, FiveSimClient
            if otp_service == "smsman":
                client = SMSManClient(otp_api_key)
                otp_getter = lambda: client.wait_for_otp(otp_result.request_id)
            else:
                client = FiveSimClient(otp_api_key)
                otp_getter = lambda: client.wait_for_otp(otp_result.request_id)

        log.info("Starting Instagram signup automation...")
        signup = _signup_instagram(driver, ig_handle, phone, otp_getter)
        driver.quit()

        if not signup.get("success"):
            return IGAccountResult(
                success=False,
                device_id=device_id,
                phone_used=phone,
                error=signup.get("error", "Signup automation failed"),
            )

        # ── Step 8: Trigger GeeLark AI warmup template ─────────────────────
        log.info(f"Triggering GeeLark AI warmup template: {warmup_template_id}")
        try:
            geelark.trigger_warmup(device_id, warmup_template_id)
            warmup_status = "warming_up"
            log.info("Warmup template triggered — will run for 30 days")
        except Exception as e:
            log.warning(f"Warmup trigger failed (non-fatal): {e}")
            warmup_status = "warmup_trigger_failed"

        return IGAccountResult(
            success       = True,
            ig_handle     = f"@{ig_handle}",
            ig_username   = ig_handle,
            ig_password   = signup["password"],
            phone_used    = phone,
            device_id     = device_id,
            warmup_status = warmup_status,
        )

    except Exception as e:
        log.error(f"Instagram account creation error: {e}")
        return IGAccountResult(
            success=False,
            device_id=device_id,
            error=str(e),
        )


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    handle = sys.argv[1] if len(sys.argv) > 1 else "stage.testaccount"
    print(f"\nCreating IG account: @{handle}")
    result = create_instagram_account(ig_handle=handle)
    print(f"\nResult: {result}")
