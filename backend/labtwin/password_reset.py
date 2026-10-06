"""Email recovery for the existing User/Account/bearer authentication."""
import json
import logging
import uuid
from threading import BoundedSemaphore, Thread
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.core.exceptions import RequestDataTooBig, ValidationError
from django.core.mail import EmailMessage
from django.core.validators import validate_email
from django.db import DatabaseError, close_old_connections, transaction
from django.http import JsonResponse
from django.utils.crypto import salted_hmac
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.middleware.csrf import get_token
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_http_methods

from .models import AccessToken, Account

logger = logging.getLogger(__name__)
delivery_slots = BoundedSemaphore(2)
REQUEST_MESSAGE = "If an eligible account uses that email, a reset link will be sent. Check your inbox and spam folder."
INVALID_LINK = "This reset link is invalid or expired. Please request a new link."
UNAVAILABLE = "Password reset email is unavailable on this deployment. Please contact the administrator."


def reply(data, status=200):
    response = JsonResponse(data, status=status)
    response["Cache-Control"] = "no-store"
    response["Referrer-Policy"] = "no-referrer"
    return response


def reset_origin():
    origin = str(getattr(settings, "LABTWIN_PASSWORD_RESET_ORIGIN", "")).rstrip("/")
    parsed = urlsplit(origin)
    local = settings.DEBUG and parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1")
    if (not parsed.hostname or parsed.username or parsed.password or parsed.path
            or parsed.query or parsed.fragment or (parsed.scheme != "https" and not local)):
        raise ValueError("Configure a trusted password reset origin.")
    return origin


def delivery_ready():
    """Fail closed; never use console/files as a production email fallback."""
    if not getattr(settings, "LABTWIN_PASSWORD_RESET_EMAIL_ENABLED", False):
        return False
    try:
        reset_origin()
        validate_email(settings.DEFAULT_FROM_EMAIL)
        backend = settings.EMAIL_BACKEND
        if backend == "django.core.mail.backends.locmem.EmailBackend":
            return settings.DEBUG  # Disposable tests only; deployment DEBUG is False.
        if backend != "django.core.mail.backends.smtp.EmailBackend":
            return False
        return bool(settings.EMAIL_HOST and settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD
                    and (settings.EMAIL_USE_TLS != settings.EMAIL_USE_SSL))
    except (ValueError, ValidationError):
        return False


def rate_allowed(scope, identity, limit, seconds):
    # Cache identifiers never contain the address or IP. Use a shared Django
    # cache before scaling beyond the current single application worker.
    key = "labtwin-reset:" + salted_hmac(scope, identity).hexdigest()
    if cache.add(key, 1, timeout=seconds):
        return True
    try:
        return cache.incr(key) <= limit
    except ValueError:
        return False


def send_reset(email):
    form = PasswordResetForm({"email": email})
    if not form.is_valid():
        return
    for user in form.get_users(form.cleaned_data["email"]):
        if not Account.objects.filter(user=user).exists():
            continue
        # Fragments are not sent in HTTP requests or Referer headers. The
        # private gate preserves this fragment locally until the UI opens.
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        link = f"{reset_origin()}/#password-reset={uid}:{token}"
        minutes = max(1, settings.PASSWORD_RESET_TIMEOUT // 60)
        EmailMessage(
            "Reset your LabTwin password",
            f"A password reset was requested for your LabTwin account.\n\n{link}\n\n"
            f"This link expires in {minutes} minutes and works once.\n"
            "The private demo may first ask for its separate private access password.\n"
            "If you did not request this, ignore this email; your password has not changed.\n",
            settings.DEFAULT_FROM_EMAIL, [user.email],
        ).send(fail_silently=False)


def send_confirmation(user_id):
    user = get_user_model().objects.filter(pk=user_id, is_active=True).first()
    if user and user.email:
        EmailMessage("Your LabTwin password was reset",
                     "Your password was reset and existing LabTwin sessions were signed out.\n"
                     "Sign in using your new password. If you did not do this, contact your administrator.\n",
                     settings.DEFAULT_FROM_EMAIL, [user.email]).send(fail_silently=False)


def schedule_delivery(action, value):
    # Lookup and network delivery occur AFTER the same response path for every
    # email. Bounded daemon threads prevent an unbounded queue or SMTP spinner.
    if not delivery_slots.acquire(blocking=False):
        return False

    def run():
        try:
            close_old_connections()
            action(value)
        except Exception as error:
            # Provider exception text can contain addresses/credentials/links.
            logger.warning("Password recovery delivery could not complete (%s).", type(error).__name__)
        finally:
            close_old_connections()
            delivery_slots.release()
    try:
        Thread(target=run, daemon=True, name="labtwin-password-email").start()
        return True
    except RuntimeError:
        delivery_slots.release()
        logger.warning("Password recovery delivery could not start.")
        return False


def payload(request):
    if request.content_type != "application/json" or len(request.body) > 8192:
        raise ValueError()
    data = json.loads(request.body)
    if not isinstance(data, dict):
        raise ValueError()
    return data


@ensure_csrf_cookie
@csrf_protect
@require_http_methods(["GET", "POST"])
def request_reset(request):
    if request.method == "GET":
        return reply({"csrf_token": get_token(request)})
    try:
        data = payload(request)
        email = data.get("email", "")
        method = data.get("method", "link")
        if method not in ("link", "otp"):
            raise ValueError()
        if not isinstance(email, str) or len(email) > 254:
            raise ValueError()
        email = email.strip()
        validate_email(email)
    except (ValueError, TypeError, UnicodeDecodeError, ValidationError, RequestDataTooBig):
        return reply({"error": "Enter a valid email address."}, 400)
    if not delivery_ready():
        return reply({"error": UNAVAILABLE}, 503)
    from . import password_otp
    identity, issued_at = uuid.uuid4(), timezone.now()
    allowed = (rate_allowed("reset-request-ip", request.META.get("REMOTE_ADDR", ""), 20, 900)
               and rate_allowed("reset-request-email", email.casefold(), 3, 900))
    if allowed:
        # No account lookup is performed in this HTTP response path.
        action, value = (password_otp.send_otp, (email, identity, issued_at)) if method == "otp" else (send_reset, email)
        if not schedule_delivery(action, value):
            return reply({"error": "Password reset delivery is temporarily busy. Please try again later."}, 503)
    elif method == "otp":
        return reply({"error": "Too many recovery requests. Please try again later."}, 429)
    if method == "otp":
        return reply({"message": password_otp.REQUEST_MESSAGE, "request_id": str(identity), "expires_in": password_otp.OTP_TIMEOUT})
    return reply({"message": REQUEST_MESSAGE})


@sensitive_post_parameters("new_password1", "new_password2", "token")
@sensitive_variables()
@csrf_protect
@require_http_methods(["POST"])
def confirm_reset(request):
    if not rate_allowed("reset-confirm-ip", request.META.get("REMOTE_ADDR", ""), 30, 900):
        return reply({"error": "Too many reset attempts. Please try again later."}, 429)
    try:
        data = payload(request)
        uid, token = data.get("uid", ""), data.get("token", "")
        if not isinstance(uid, str) or not isinstance(token, str) or len(uid) > 64 or len(token) > 100:
            raise ValueError()
        user_id = urlsafe_base64_decode(uid).decode()
        if not user_id.isascii() or not user_id.isdigit() or len(user_id) > 20:
            raise ValueError()
        user = get_user_model().objects.filter(pk=user_id, is_active=True, labtwin_account__isnull=False).first()
        if not user or not user.has_usable_password() or not default_token_generator.check_token(user, token):
            return reply({"error": INVALID_LINK}, 400)
        passwords = [data.get("new_password1"), data.get("new_password2")]
        if any(not isinstance(p, str) or len(p) > 1024 for p in passwords):
            raise ValueError()
        form = SetPasswordForm(user, data)
        if not form.is_valid():
            return reply({"error": " ".join(str(e) for errors in form.errors.values() for e in errors)}, 400)
        previous_hash, previous_login, previous_email = user.password, user.last_login, user.email
        form.save(commit=False)
        with transaction.atomic():
            # Conditional update makes token use atomic even on SQLite, where
            # SELECT FOR UPDATE cannot serialize two simultaneous resets.
            changed = get_user_model().objects.filter(
                pk=user.pk, password=previous_hash, last_login=previous_login,
                email=previous_email, is_active=True,
            ).update(password=user.password)
            if not changed:
                return reply({"error": INVALID_LINK}, 400)
            AccessToken.objects.filter(account__user_id=user.pk).delete()
        if delivery_ready():
            schedule_delivery(send_confirmation, user.pk)
        return reply({"message": "Password reset complete. Please sign in with your new password."})
    except (ValueError, TypeError, UnicodeDecodeError, OverflowError, RequestDataTooBig):
        return reply({"error": INVALID_LINK}, 400)
    except DatabaseError as error:
        logger.warning("Password recovery could not save (%s).", type(error).__name__)
        return reply({"error": "Password reset could not complete. Please try again later."}, 503)
