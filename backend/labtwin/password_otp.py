"""Email OTP proof grants only the existing password-reset permission."""
import json
import secrets
from datetime import timedelta
from uuid import UUID

from django.conf import settings
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import RequestDataTooBig
from django.core.mail import EmailMessage
from django.db import DatabaseError, transaction
from django.db.models import F
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_http_methods

from . import password_reset as recovery
from .models import Account, PasswordResetOTP

OTP_TIMEOUT = 600
OTP_MAX_ATTEMPTS = 5
REQUEST_MESSAGE = "If an eligible account uses that email, a verification code will be sent. Check your inbox and spam folder."
INVALID_CODE = "This code is invalid, expired or has reached its attempt limit. Please request a new code."


def code_digest(request_id, account_id, code):
    # A keyed digest prevents offline guessing of the small numeric code space
    # from a database copy without the server's signing secret.
    return salted_hmac("labtwin-reset-otp-code", f"{request_id}:{account_id}:{code}", algorithm="sha256").hexdigest()


def state_digest(user):
    state = [user.pk, user.password, user.email, str(user.last_login)]
    return salted_hmac("labtwin-reset-otp-state", json.dumps(state), algorithm="sha256").hexdigest()


@sensitive_variables()
def send_otp(values):
    email, request_id, issued_at = values
    if not recovery.delivery_ready() or issued_at + timedelta(seconds=OTP_TIMEOUT) <= timezone.now():
        return
    form = PasswordResetForm({"email": email})
    if not form.is_valid():
        return
    for user in form.get_users(form.cleaned_data["email"]):
        account = Account.objects.filter(user=user).first()
        if not account:
            continue
        code = f"{secrets.randbelow(100_000_000):08d}"
        fields = {"request_id": request_id, "code_digest": code_digest(request_id, account.pk, code),
                  "state_digest": state_digest(user), "issued_at": issued_at,
                  "expires_at": issued_at + timedelta(seconds=OTP_TIMEOUT),
                  "attempts": 0, "consumed_at": None}
        with transaction.atomic():
            _, created = PasswordResetOTP.objects.get_or_create(account=account, defaults=fields)
            if not created:
                # HTTP issue time, rather than delivery completion order, decides
                # which resend is newest even when mail workers overlap.
                changed = PasswordResetOTP.objects.filter(account=account, issued_at__lt=issued_at).update(**fields)
                if not changed:
                    continue
        EmailMessage("Your LabTwin password reset code",
                     f"A password reset was requested for LabTwin username {user.username}.\n\n"
                     f"Your verification code is: {code}\n\n"
                     "Use it in the Forgot password form where you requested it.\n"
                     "It expires 10 minutes after the request, allows five attempts and works once.\n"
                     "Only the most recently requested code works. Do not share it.\n"
                     "If you did not request this, ignore this email; your password has not changed.\n",
                     settings.DEFAULT_FROM_EMAIL, [user.email]).send(fail_silently=False)


@sensitive_post_parameters("code")
@sensitive_variables()
@csrf_protect
@require_http_methods(["POST"])
def verify_otp(request):
    if not recovery.rate_allowed("reset-otp-verify-ip", request.META.get("REMOTE_ADDR", ""), 30, 900):
        return recovery.reply({"error": "Too many verification attempts. Please try again later."}, 429)
    try:
        data = recovery.payload(request)
        identity, code = data.get("request_id"), data.get("code")
        if not isinstance(identity, str) or len(identity) != 36:
            raise ValueError()
        request_id = UUID(identity)
        if not isinstance(code, str) or len(code) != 8 or not code.isascii() or not code.isdigit():
            raise ValueError()
        now = timezone.now()
        with transaction.atomic():
            challenges = PasswordResetOTP.objects.filter(request_id=request_id, consumed_at__isnull=True, expires_at__gt=now)
            # Claim an attempt with a write before reading. This serializes
            # verification on SQLite as well as databases with row locks.
            # Move an exhausted row beyond the acceptance threshold, too. A
            # different account sharing this email must not reopen its limit.
            claimed = challenges.filter(attempts__lte=OTP_MAX_ATTEMPTS).update(attempts=F("attempts") + 1)
            if claimed:
                for challenge in challenges.filter(attempts__lte=OTP_MAX_ATTEMPTS).select_related("account__user"):
                    user = challenge.account.user
                    if (constant_time_compare(challenge.code_digest, code_digest(request_id, challenge.account_id, code))
                            and user.is_active and user.has_usable_password()
                            and constant_time_compare(challenge.state_digest, state_digest(user))):
                        used = PasswordResetOTP.objects.filter(pk=challenge.pk, request_id=request_id,
                                                               consumed_at__isnull=True).update(consumed_at=now)
                        if used:
                            # This is a reset-only credential, never an AccessToken
                            # or sign-in. The existing confirm route validates it.
                            return recovery.reply({"uid": urlsafe_base64_encode(force_bytes(user.pk)),
                                                   "token": default_token_generator.make_token(user),
                                                   "message": "Code verified. Choose a new password."})
        return recovery.reply({"error": INVALID_CODE}, 400)
    except (ValueError, TypeError, UnicodeDecodeError, RequestDataTooBig):
        return recovery.reply({"error": INVALID_CODE}, 400)
    except DatabaseError as error:
        recovery.logger.warning("Password recovery verification could not complete (%s).", type(error).__name__)
        return recovery.reply({"error": "Code verification could not complete. Please try again later."}, 503)
