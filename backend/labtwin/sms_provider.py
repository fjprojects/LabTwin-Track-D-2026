"""Small, bounded Twilio Verify adapter; no SDK/dependency changes or SMS fallback."""
import base64
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from django.conf import settings
from django.views.decorators.debug import sensitive_variables


class SMSUnavailable(Exception):
    """Safe category only: never propagate provider bodies, numbers or secrets."""


def sid_valid(value, prefix):
    return isinstance(value, str) and bool(re.fullmatch(prefix + r"[0-9a-fA-F]{32}", value))


def credentials():
    key = getattr(settings, "TWILIO_API_KEY_SID", "")
    secret = getattr(settings, "TWILIO_API_KEY_SECRET", "")
    if key or secret:
        return (key, secret) if sid_valid(key, "SK") and len(secret) >= 16 else ("", "")
    return getattr(settings, "TWILIO_ACCOUNT_SID", ""), getattr(settings, "TWILIO_AUTH_TOKEN", "")


def ready():
    username, secret = credentials()
    return bool(getattr(settings, "LABTWIN_PASSWORD_RESET_SMS_ENABLED", False)
                and sid_valid(getattr(settings, "TWILIO_ACCOUNT_SID", ""), "AC")
                and sid_valid(getattr(settings, "TWILIO_VERIFY_SERVICE_SID", ""), "VA")
                and username and len(secret) >= 16)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward Basic credentials to a redirected host.


@sensitive_variables()
def post(endpoint, fields):
    if not ready():
        raise SMSUnavailable("not_configured")
    username, secret = credentials()
    authorization = base64.b64encode(f"{username}:{secret}".encode()).decode()
    service = settings.TWILIO_VERIFY_SERVICE_SID
    request = Request(f"https://verify.twilio.com/v2/Services/{service}/{endpoint}",
                      data=urlencode(fields).encode(), method="POST",
                      headers={"Authorization": f"Basic {authorization}",
                               "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
    try:
        # No automatic send retries: a timeout may have already delivered a
        # chargeable SMS. Application/provider rate limits bound manual retries.
        with build_opener(NoRedirect()).open(request, timeout=10) as response:
            raw = response.read(65537)
            if len(raw) > 65536:
                raise SMSUnavailable("invalid_response")
            result = json.loads(raw)
    except HTTPError as error:
        if endpoint == "VerificationCheck" and error.code in (400, 404):
            return None  # Invalid/expired/exhausted proofs have the same result.
        raise SMSUnavailable("provider_rejected") from None
    except (URLError, TimeoutError, OSError, ValueError, UnicodeError):
        raise SMSUnavailable("provider_unavailable") from None
    if not isinstance(result, dict):
        raise SMSUnavailable("invalid_response")
    return result


def matches(result, number, verification_sid=None):
    return bool(result and sid_valid(result.get("sid"), "VE")
                and (verification_sid is None or result["sid"] == verification_sid)
                and result.get("account_sid") == settings.TWILIO_ACCOUNT_SID
                and result.get("service_sid") == settings.TWILIO_VERIFY_SERVICE_SID
                and result.get("to") == number and result.get("channel") == "sms")


def send(number):
    result = post("Verifications", {"To": number, "Channel": "sms"})
    if not matches(result, number) or result.get("status") != "pending":
        raise SMSUnavailable("invalid_response")
    return result["sid"]


def approved(number, verification_sid, code):
    if not sid_valid(verification_sid, "VE"):
        return False
    result = post("VerificationCheck", {"VerificationSid": verification_sid, "Code": code})
    return bool(matches(result, number, verification_sid) and result.get("status") == "approved"
                and result.get("valid") is True)
