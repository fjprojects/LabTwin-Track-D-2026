"""
Django settings for backend project.
"""

import os
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
from dotenv import load_dotenv
load_dotenv(BASE_DIR.parent / ".env")

if os.getenv("RENDER"):
    SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
else:
    SECRET_KEY = os.getenv(
        "DJANGO_SECRET_KEY",
        "django-insecure-local-development-only"
    )
DEBUG = os.getenv("RENDER") is None
_render_host = os.getenv(
    "RENDER_EXTERNAL_HOSTNAME"
)

ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
]

if _render_host:
    ALLOWED_HOSTS.append(
        _render_host
    )
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'corsheaders',
    'labtwin',
]


MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',

    'corsheaders.middleware.CorsMiddleware',

    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]


ROOT_URLCONF = 'backend.urls'


TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',

        'DIRS': [],

        'APP_DIRS': True,

        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]


WSGI_APPLICATION = 'backend.wsgi.application'


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


STATIC_URL = 'static/'


DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


_frontend_url = os.getenv(
    "FRONTEND_URL",
    ""
).rstrip("/")

CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

if _frontend_url:
    CORS_ALLOWED_ORIGINS.append(
        _frontend_url
    )

# Email recovery is explicitly opt-in and has no console/file-link fallback.
PASSWORD_RESET_TIMEOUT = 1800
LABTWIN_PASSWORD_RESET_ORIGIN = os.getenv("LABTWIN_PASSWORD_RESET_ORIGIN", _frontend_url)
LABTWIN_PASSWORD_RESET_EMAIL_ENABLED = os.getenv("LABTWIN_PASSWORD_RESET_EMAIL_ENABLED", "false").lower() == "true"
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "true").lower() == "true"
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "false").lower() == "true"
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "")

CSRF_TRUSTED_ORIGINS = []

if _frontend_url:
    CSRF_TRUSTED_ORIGINS.append(
        _frontend_url
    )


CORS_ALLOW_CREDENTIALS = True


# Render terminates HTTPS before forwarding traffic to Django.
SECURE_PROXY_SSL_HEADER = (
    "HTTP_X_FORWARDED_PROTO",
    "https"
)

# JSON list of STUN/TURN servers. TURN credentials belong in runtime variables.
WEBRTC_ICE_SERVERS = json.loads(os.getenv("WEBRTC_ICE_SERVERS", '[{"urls":"stun:stun.l.google.com:19302"}]'))

# Course files are private; never expose this directory through static/media URLs.
LABTWIN_MEDIA_ROOT = Path(os.getenv("LABTWIN_MEDIA_ROOT", str(BASE_DIR / "private_learning")))
LABTWIN_VECTOR_ROOT = Path(os.getenv("LABTWIN_VECTOR_ROOT", str(BASE_DIR / "learning_vectors")))
LABTWIN_EMBEDDING_BACKEND = os.getenv("LABTWIN_EMBEDDING_BACKEND", "onnx")
LABTWIN_TUTOR_MODEL = os.getenv("LABTWIN_TUTOR_MODEL", "openai/gpt-oss-20b")
LABTWIN_LEGACY_AI_TIMEOUT_SECONDS = max(5, min(120, float(os.getenv("LABTWIN_LEGACY_AI_TIMEOUT_SECONDS", "45"))))
LABTWIN_VERIFIER_MODEL = os.getenv("LABTWIN_VERIFIER_MODEL", "")
LABTWIN_VISION_MODEL = os.getenv("LABTWIN_VISION_MODEL", "")
LABTWIN_MAX_VISUAL_UNITS = int(os.getenv("LABTWIN_MAX_VISUAL_UNITS", "200"))
LABTWIN_EVALUATOR_PYTHON = os.getenv("LABTWIN_EVALUATOR_PYTHON", "")
LABTWIN_EVALUATOR_EXTRA_PATH = os.getenv("LABTWIN_EVALUATOR_EXTRA_PATH", "")
LABTWIN_EVALUATION_JUDGE_MODEL = os.getenv("LABTWIN_EVALUATION_JUDGE_MODEL", "")
LABTWIN_PROJECT_ROOT = Path(os.getenv("LABTWIN_PROJECT_ROOT", str(BASE_DIR.parent)))
LABTWIN_TRANSCRIPTION_MODEL = os.getenv("LABTWIN_TRANSCRIPTION_MODEL", "whisper-large-v3-turbo")
LABTWIN_PROCESS_INLINE = os.getenv("LABTWIN_PROCESS_INLINE", "false").lower() == "true"
# Local uploads start automatically. Hosting can retain dedicated workers.
LABTWIN_PROCESS_MODE = os.getenv("LABTWIN_PROCESS_MODE", "local" if DEBUG else "external")
LABTWIN_MATERIAL_TIMEOUT_SECONDS = int(os.getenv("LABTWIN_MATERIAL_TIMEOUT_SECONDS", "600"))
LABTWIN_DEMO_ENABLED = os.getenv("LABTWIN_DEMO_ENABLED", "false").lower() == "true"
LABTWIN_UPLOAD_MAX_BYTES = int(os.getenv("LABTWIN_UPLOAD_MAX_BYTES", str(100 * 1024 * 1024)))
LABTWIN_MEDIA_MAX_SECONDS = int(os.getenv("LABTWIN_MEDIA_MAX_SECONDS", "7200"))
LABTWIN_VIDEO_OCR = os.getenv("LABTWIN_VIDEO_OCR", "true").lower() == "true"
LABTWIN_RUNNER_URL = os.getenv("LABTWIN_RUNNER_URL", "")
LABTWIN_RUNNER_SECRET = os.getenv("LABTWIN_RUNNER_SECRET", "")
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
