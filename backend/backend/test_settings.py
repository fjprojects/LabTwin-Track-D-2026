"""Database-only tests that do not need Groq credentials or an AI runtime."""
SECRET_KEY = "response-history-tests-only"
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
INSTALLED_APPS = ["django.contrib.auth", "django.contrib.contenttypes", "labtwin"]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True

AUTH_PASSWORD_VALIDATORS = [{"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"}]
LABTWIN_EMBEDDING_BACKEND = "hash"
LABTWIN_PROCESS_INLINE = True
LABTWIN_DEMO_ENABLED = True
LABTWIN_DISABLE_REMOTE_AI = True
