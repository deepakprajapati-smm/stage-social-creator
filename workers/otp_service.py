"""
workers/otp_service.py — Virtual phone number OTP for Instagram account creation

Supports:
  - SMS-Man.com  (primary, sms-activate.io replacement, 500+ platforms)
  - 5sim.net     (bulk/cheap, excellent API, public stats page)

Note: sms-activate.io shut down December 29, 2025.

Usage:
    from workers.otp_service import get_instagram_otp
    result = get_instagram_otp()   # uses config.OTP_SERVICE setting
"""

import time
import logging
import requests
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class OTPResult:
    success:    bool
    phone:      Optional[str] = None
    otp:        Optional[str] = None
    request_id: Optional[str] = None
    service:    Optional[str] = None
    error:      Optional[str] = None


# ── SMS-Man.com ───────────────────────────────────────────────────────────────

class SMSManClient:
    """
    SMS-Man.com client for Instagram OTP.
    Docs: https://api.sms-man.com/control
    Get API key: sms-man.com → Profile → API
    """
    BASE = "https://api.sms-man.com/control"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._instagram_app_id: Optional[int] = None

    def _get(self, action: str, **params) -> dict:
        r = requests.get(
            f"{self.BASE}/{action}",
            params={"token": self.api_key, **params},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict) and "error_code" in data:
            raise RuntimeError(f"SMS-Man error: {data.get('error_msg', data)}")
        return data

    def _get_instagram_app_id(self) -> int:
        if self._instagram_app_id:
            return self._instagram_app_id
        apps = self._get("applications")
        for app in apps:
            if "instagram" in app.get("name", "").lower():
                self._instagram_app_id = int(app["id"])
                return self._instagram_app_id
        raise RuntimeError("Instagram not found in SMS-Man application list")

    def get_number(self, country_id: int = 14) -> tuple[str, str]:
        """
        Request a number for Instagram OTP.
        Returns: (request_id, phone_number)
        country_id: 14=India, 7=Russia, 62=Indonesia, 1=USA
        """
        app_id = self._get_instagram_app_id()
        data   = self._get("get-number", country_id=country_id, application_id=app_id)
        return str(data["request_id"]), str(data["number"])

    def wait_for_otp(
        self,
        request_id: str,
        poll_interval: int = 10,
        max_wait:      int = 300,
    ) -> Optional[str]:
        """Poll for OTP code. Returns code or None on timeout."""
        attempts = max_wait // poll_interval
        for _ in range(attempts):
            time.sleep(poll_interval)
            try:
                data = self._get("get-sms", request_id=request_id)
                code = data.get("sms_code")
                if code:
                    log.info(f"SMS-Man OTP received: {code}")
                    return str(code)
                err = data.get("error_code", "")
                if err not in ("wait_sms", ""):
                    log.warning(f"SMS-Man unexpected status: {data}")
                    return None
            except Exception as e:
                log.warning(f"SMS-Man poll error: {e}")
        return None

    def cancel(self, request_id: str):
        try:
            self._get("set-status", request_id=request_id, status="reject")
        except Exception:
            pass

    def confirm(self, request_id: str):
        try:
            self._get("set-status", request_id=request_id, status="success")
        except Exception:
            pass


# ── 5sim.net ──────────────────────────────────────────────────────────────────

class FiveSimClient:
    """
    5sim.net client for Instagram OTP.
    Docs: https://5sim.net/docs
    Get JWT token: 5sim.net → Profile → Developer
    """
    BASE = "https://5sim.net/v1"

    def __init__(self, api_key: str):
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept":        "application/json",
        }

    def _get(self, path: str) -> dict:
        r = requests.get(f"{self.BASE}{path}", headers=self.headers, timeout=15)
        r.raise_for_status()
        return r.json()

    def get_number(self, country: str = "india") -> tuple[str, str]:
        """
        Buy a number for Instagram OTP.
        Returns: (order_id, phone_number)
        """
        data = self._get(f"/user/buy/activation/{country}/any/instagram")
        return str(data["id"]), str(data["phone"])

    def wait_for_otp(
        self,
        order_id:      str,
        poll_interval: int = 10,
        max_wait:      int = 300,
    ) -> Optional[str]:
        """Poll for OTP. Returns code or None."""
        attempts = max_wait // poll_interval
        for _ in range(attempts):
            time.sleep(poll_interval)
            try:
                data   = self._get(f"/user/check/{order_id}")
                status = data.get("status", "")
                if status == "RECEIVED":
                    sms_list = data.get("sms", [])
                    if sms_list:
                        code = sms_list[0].get("code")
                        log.info(f"5sim OTP received: {code}")
                        return str(code)
                elif status in ("CANCELED", "TIMEOUT", "BANNED"):
                    log.warning(f"5sim order {order_id} ended with status: {status}")
                    return None
            except Exception as e:
                log.warning(f"5sim poll error: {e}")
        return None

    def cancel(self, order_id: str):
        try:
            requests.get(f"{self.BASE}/user/cancel/{order_id}", headers=self.headers, timeout=10)
        except Exception:
            pass

    def confirm(self, order_id: str):
        try:
            requests.get(f"{self.BASE}/user/finish/{order_id}", headers=self.headers, timeout=10)
        except Exception:
            pass


# ── Unified interface ─────────────────────────────────────────────────────────

def get_instagram_otp(
    service:       str = "smsman",
    api_key:       str = "",
    country:             = None,
    poll_interval: int = 10,
    max_wait:      int = 300,
) -> OTPResult:
    """
    Get a virtual phone number and wait for Instagram OTP.

    Args:
        service:  "smsman" (default) or "fivesim"
        api_key:  API key for the chosen service
        country:  Country for number (smsman: int 14=India; fivesim: str "india")
        poll_interval: Seconds between OTP polls
        max_wait: Max seconds to wait for OTP

    Returns:
        OTPResult with success, phone, otp, request_id
    """
    if not api_key:
        from config.settings import SMSMAN_API_KEY, FIVESIM_API_KEY, OTP_SERVICE
        service = service or OTP_SERVICE
        api_key = SMSMAN_API_KEY if service == "smsman" else FIVESIM_API_KEY

    request_id = None

    try:
        if service == "smsman":
            client     = SMSManClient(api_key)
            country_id = country if country is not None else 14  # India
            log.info(f"SMS-Man: requesting India number for Instagram...")
            request_id, phone = client.get_number(country_id=country_id)
            log.info(f"SMS-Man: got number {phone} (request_id={request_id})")

            otp = client.wait_for_otp(request_id, poll_interval, max_wait)
            if otp:
                client.confirm(request_id)
                return OTPResult(success=True, phone=phone, otp=otp, request_id=request_id, service="smsman")
            else:
                client.cancel(request_id)
                return OTPResult(success=False, phone=phone, error="OTP not received within timeout", service="smsman")

        elif service == "fivesim":
            client      = FiveSimClient(api_key)
            country_str = country if country is not None else "india"
            log.info(f"5sim: requesting {country_str} number for Instagram...")
            request_id, phone = client.get_number(country=country_str)
            log.info(f"5sim: got number {phone} (order_id={request_id})")

            otp = client.wait_for_otp(request_id, poll_interval, max_wait)
            if otp:
                client.confirm(request_id)
                return OTPResult(success=True, phone=phone, otp=otp, request_id=request_id, service="fivesim")
            else:
                client.cancel(request_id)
                return OTPResult(success=False, phone=phone, error="OTP not received within timeout", service="fivesim")

        else:
            return OTPResult(success=False, error=f"Unknown OTP service: {service}")

    except Exception as e:
        log.error(f"OTP service error: {e}")
        # Attempt to cancel if we got a request_id
        if request_id and service == "smsman":
            try:
                SMSManClient(api_key).cancel(request_id)
            except Exception:
                pass
        elif request_id and service == "fivesim":
            try:
                FiveSimClient(api_key).cancel(request_id)
            except Exception:
                pass
        return OTPResult(success=False, error=str(e))
