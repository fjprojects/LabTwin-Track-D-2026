"""Verified-phone binding and reset-only SMS proof for existing accounts."""
import json
import re
from datetime import timedelta
from uuid import UUID, uuid4

from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import RequestDataTooBig
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import F
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_http_methods

from . import password_reset as recovery, sms_provider
from .access import authenticate_request
from .models import Account, PhoneOTP, RecoveryPhone

TIMEOUT = 600
MAX_ATTEMPTS = 5
UNAVAILABLE = "Phone OTP is unavailable on this deployment. Please use email recovery or contact the administrator."
REQUEST_MESSAGE = "If an eligible account has verified that phone, an SMS code will be sent."
INVALID_CODE = "This code is invalid, expired or has reached its attempt limit. Please request a new code after ten minutes."


def number_value(value):
    if not isinstance(value, str):
        raise ValueError()
    number = value.strip()
    if not re.fullmatch(r"\+[1-9][0-9]{7,14}", number):
        raise ValueError()
    return number


def phone_snapshot(account):
    phone = RecoveryPhone.objects.filter(account=account).first()
    return [phone.number, str(phone.verified_at)] if phone else []


def state_digest(account):
    user = account.user
    state = [user.pk, user.password, user.email, str(user.last_login), phone_snapshot(account)]
    return salted_hmac("labtwin-phone-recovery-state", json.dumps(state), algorithm="sha256").hexdigest()


def request_allowed(request, number):
    # The same budget applies to existing and nonexistent numbers and both
    # purposes. Twilio reuses pending codes for ten minutes; local resends must
    # not reset the attempt budget or extend that validity window.
    return (recovery.rate_allowed("sms-request-ip", request.META.get("REMOTE_ADDR", ""), 10, 900)
            and recovery.rate_allowed("sms-request-phone", number, 1, TIMEOUT))


@sensitive_variables()
def send_code(values):
    purpose, number, identity, issued_at, account_id, expected_state = values
    if not sms_provider.ready() or issued_at + timedelta(seconds=TIMEOUT) <= timezone.now():
        return
    if purpose == "reset":
        phone = RecoveryPhone.objects.select_related("account__user").filter(number=number).first()
        account = phone.account if phone else None
    else:
        account = Account.objects.select_related("user").filter(pk=account_id).first()
    if not account or not account.user.is_active or not account.user.has_usable_password():
        return
    snapshot = state_digest(account)
    if purpose == "bind" and not constant_time_compare(expected_state, snapshot):
        return
    fields = {"number": number, "request_id": identity, "state_digest": snapshot,
              "verification_sid": "", "status": "queued", "issued_at": issued_at,
              "expires_at": issued_at + timedelta(seconds=TIMEOUT), "attempts": 0, "consumed_at": None}
    with transaction.atomic():
        _, created = PhoneOTP.objects.get_or_create(account=account, purpose=purpose, defaults=fields)
        if not created and not PhoneOTP.objects.filter(account=account, purpose=purpose, issued_at__lt=issued_at).update(**fields):
            return
    try:
        sid = sms_provider.send(number)
        PhoneOTP.objects.filter(request_id=identity, status="queued", expires_at__gt=timezone.now()).update(
            verification_sid=sid, status="pending")
    except sms_provider.SMSUnavailable as error:
        PhoneOTP.objects.filter(request_id=identity, status="queued").update(status="failed")
        recovery.logger.warning("Phone recovery delivery unavailable (%s).", type(error).__name__)


def start(request, purpose, number, account=None):
    if not sms_provider.ready():
        return recovery.reply({"error": UNAVAILABLE}, 503)
    if not request_allowed(request, number):
        return recovery.reply({"error": "Too many SMS requests. Wait ten minutes before requesting another code."}, 429)
    identity = uuid4()
    values = (purpose, number, identity, timezone.now(), account.pk if account else None,
              state_digest(account) if account else "")
    # Account lookup and SMS delivery are deferred for the public reset request,
    # so its response does not disclose registration or wait for a provider.
    if not recovery.schedule_delivery(send_code, values):
        return recovery.reply({"error": "Phone OTP delivery is temporarily busy. Please try again later."}, 503)
    return recovery.reply({"message": REQUEST_MESSAGE if purpose == "reset" else "An SMS verification code has been requested. Enter it to save your recovery phone.",
                           "request_id": str(identity), "expires_in": TIMEOUT})


@csrf_protect
@require_http_methods(["POST"])
def request_reset(request):
    try:
        number = number_value(recovery.payload(request).get("phone"))
        return start(request, "reset", number)
    except (ValueError, TypeError, UnicodeDecodeError, RequestDataTooBig):
        return recovery.reply({"error": "Enter a phone number with its country code, for example +919876543210."}, 400)


@sensitive_post_parameters("password")
@sensitive_variables()
@csrf_protect
@require_http_methods(["GET", "POST", "DELETE"])
def setup_phone(request):
    account = authenticate_request(request)
    if not account:
        return recovery.reply({"error": "Please sign in."}, 401)
    if request.method == "GET":
        phone = RecoveryPhone.objects.filter(account=account).first()
        return recovery.reply({"available": sms_provider.ready(), "verified": bool(phone),
                               "masked_phone": "••••" + phone.number[-4:] if phone else None})
    if not recovery.rate_allowed("phone-setup-account", str(account.pk), 10, 900):
        return recovery.reply({"error": "Too many recovery-phone attempts. Please try again later."}, 429)
    try:
        data = recovery.payload(request)
        password = data.get("password")
        if not isinstance(password, str) or len(password) > 1024 or not account.user.check_password(password):
            return recovery.reply({"error": "Enter your current account password."}, 400)
        if request.method == "DELETE":
            with transaction.atomic():
                owner = type(account.user).objects.select_for_update().get(pk=account.user_id)
                if not owner.check_password(password):
                    return recovery.reply({"error": "Enter your current account password."}, 400)
                RecoveryPhone.objects.filter(account=account).delete()
                PhoneOTP.objects.filter(account=account).update(consumed_at=timezone.now())
            return recovery.reply({"message": "Recovery phone removed. Email recovery and your account data are unchanged."})
        return start(request, "bind", number_value(data.get("phone")), account)
    except (ValueError, TypeError, UnicodeDecodeError, RequestDataTooBig):
        return recovery.reply({"error": "Enter your current password and a phone number with its country code."}, 400)
    except DatabaseError as error:
        recovery.logger.warning("Recovery phone could not save (%s).", type(error).__name__)
        return recovery.reply({"error": "Recovery phone could not be saved. Please try again later."}, 503)


@sensitive_variables()
def check_code(request, purpose, account=None):
    if not sms_provider.ready():
        return recovery.reply({"error": UNAVAILABLE}, 503)
    if not recovery.rate_allowed("sms-verify-ip", request.META.get("REMOTE_ADDR", ""), 30, 900):
        return recovery.reply({"error": "Too many verification attempts. Please try again later."}, 429)
    try:
        data = recovery.payload(request)
        identity, code = data.get("request_id"), data.get("code")
        if not isinstance(identity, str) or len(identity) != 36:
            raise ValueError()
        identity = UUID(identity)
        if not isinstance(code, str) or not re.fullmatch(r"[0-9]{4,10}", code):
            raise ValueError()
        query = PhoneOTP.objects.filter(request_id=identity, purpose=purpose, status="pending",
                                        consumed_at__isnull=True, expires_at__gt=timezone.now())
        if account:
            query = query.filter(account=account)
        # Atomically claim before the bounded network check; concurrent requests
        # cannot claim a sixth attempt. Do not hold database locks over HTTP.
        if not query.filter(attempts__lt=MAX_ATTEMPTS).update(attempts=F("attempts") + 1):
            return recovery.reply({"error": INVALID_CODE}, 400)
        challenge = query.select_related("account__user").first()
        if not challenge or not challenge.account.user.is_active or not challenge.account.user.has_usable_password():
            return recovery.reply({"error": INVALID_CODE}, 400)
        if not constant_time_compare(challenge.state_digest, state_digest(challenge.account)):
            return recovery.reply({"error": INVALID_CODE}, 400)
        if not sms_provider.approved(challenge.number, challenge.verification_sid, code):
            return recovery.reply({"error": INVALID_CODE}, 400)
        with transaction.atomic():
            # Recheck identity/state after the provider call, then consume once.
            owner = Account.objects.select_related("user").get(pk=challenge.account_id)
            type(owner.user).objects.select_for_update().get(pk=owner.user_id)
            owner.user.refresh_from_db()
            if (not owner.user.is_active or not owner.user.has_usable_password()
                    or not constant_time_compare(challenge.state_digest, state_digest(owner))):
                return recovery.reply({"error": INVALID_CODE}, 400)
            if not query.filter(verification_sid=challenge.verification_sid, expires_at__gt=timezone.now()).update(consumed_at=timezone.now(), status="consumed"):
                return recovery.reply({"error": INVALID_CODE}, 400)
            if purpose == "bind":
                RecoveryPhone.objects.update_or_create(account=owner, defaults={"number": challenge.number, "verified_at": timezone.now()})
                PhoneOTP.objects.filter(account=owner, purpose="reset").update(consumed_at=timezone.now())
                return recovery.reply({"message": "Recovery phone verified. You can use Phone OTP if you forget your password."})
            phone = RecoveryPhone.objects.filter(account=owner, number=challenge.number).first()
            if not phone:
                return recovery.reply({"error": INVALID_CODE}, 400)
            return recovery.reply({"uid": urlsafe_base64_encode(force_bytes(owner.user_id)),
                                   "token": default_token_generator.make_token(owner.user),
                                   "message": "Phone verified. Choose a new password."})
    except (ValueError, TypeError, UnicodeDecodeError, RequestDataTooBig, IntegrityError, Account.DoesNotExist):
        return recovery.reply({"error": INVALID_CODE}, 400)
    except sms_provider.SMSUnavailable as error:
        recovery.logger.warning("Phone recovery verification unavailable (%s).", type(error).__name__)
        return recovery.reply({"error": "Phone verification is temporarily unavailable. Please try again later."}, 503)
    except DatabaseError as error:
        recovery.logger.warning("Phone recovery verification could not save (%s).", type(error).__name__)
        return recovery.reply({"error": "Phone verification could not complete. Please try again later."}, 503)


@sensitive_post_parameters("code")
@csrf_protect
@require_http_methods(["POST"])
def verify_reset(request):
    return check_code(request, "reset")


@sensitive_post_parameters("code")
@csrf_protect
@require_http_methods(["POST"])
def verify_phone(request):
    account = authenticate_request(request)
    if not account:
        return recovery.reply({"error": "Please sign in."}, 401)
    return check_code(request, "bind", account)
