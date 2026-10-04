"""Deployment-only settings layered over the existing Django configuration."""
import os
import hashlib
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured
from backend.settings import *  # noqa: F403


def required_secret(name, minimum):
    value = os.getenv(name, "")
    if len(value) < minimum or value.startswith("replace-with-"):
        raise ImproperlyConfigured(f"Set a strong {name} in the hosting environment.")
    return value


DEBUG = False
def production_signing_key():
    value = required_secret("DJANGO_SECRET_KEY", 43)
    # Render's generateValue is a base64-encoded 256-bit secret (44 chars).
    # A deterministic expansion satisfies Django's length heuristic without
    # changing its entropy. Longer existing secrets are used unchanged.
    return value if len(value) >= 50 else hashlib.sha256(value.encode()).hexdigest()


SECRET_KEY = production_signing_key()
LABTWIN_DEPLOYMENT_PASSWORD = required_secret("LABTWIN_DEPLOYMENT_PASSWORD", 24)
_render_hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME", "")
_public_url = os.getenv("LABTWIN_PUBLIC_URL", "https://" + _render_hostname if _render_hostname else "")
_origin = urlsplit(_public_url)
if (_origin.scheme != "https" or not _origin.hostname or _origin.username or _origin.password
        or _origin.path not in ("", "/") or _origin.query or _origin.fragment):
    raise ImproperlyConfigured("Set LABTWIN_PUBLIC_URL to the exact HTTPS origin, or use Render's assigned hostname.")
LABTWIN_PUBLIC_URL = f"https://{_origin.netloc}"
LABTWIN_PASSWORD_RESET_ORIGIN = os.getenv("LABTWIN_PASSWORD_RESET_ORIGIN", LABTWIN_PUBLIC_URL)
ALLOWED_HOSTS = [_origin.hostname]
CORS_ALLOWED_ORIGINS = [LABTWIN_PUBLIC_URL]
CSRF_TRUSTED_ORIGINS = [LABTWIN_PUBLIC_URL]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_REDIRECT_EXEMPT = [r"^deployment/health/$"]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# A temporary provider hostname must not be submitted to a permanent browser
# preload list. Django's W021 stays visible in the deployment check output.
SECURE_HSTS_PRELOAD = False
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

LABTWIN_PROJECT_ROOT = Path(__file__).resolve().parents[1]
LABTWIN_DATA_DIR = Path(os.environ.get("LABTWIN_DATA_DIR", "/data"))
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": LABTWIN_DATA_DIR / "db.sqlite3"}}
LABTWIN_MEDIA_ROOT = LABTWIN_DATA_DIR / "private_learning"
LABTWIN_VECTOR_ROOT = LABTWIN_DATA_DIR / "learning_vectors"
LABTWIN_FRONTEND_ROOT = LABTWIN_PROJECT_ROOT / "frontend" / "dist"
STATIC_URL = "/static/"
STATIC_ROOT = LABTWIN_DATA_DIR / "staticfiles"
# Reuse the existing bounded child-process dispatcher, sharing this SQLite DB
# and private volume. No separate Redis queue or new processing system.
LABTWIN_PROCESS_MODE = "local"
LABTWIN_PROCESS_INLINE = False
ROOT_URLCONF = "deployment.urls"
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "deployment.access.PrivateDeploymentMiddleware",
    *[item for item in MIDDLEWARE if item != "django.middleware.security.SecurityMiddleware"],
]
