"""Strict opt-in settings for durable PostgreSQL and private Supabase S3."""
from urllib.parse import unquote, urlsplit, parse_qs

from django.core.exceptions import ImproperlyConfigured


def postgres_database(url):
    """Parse the private Session Pooler URI without leaking credentials in errors."""
    try:
        parsed = urlsplit(url)
        query = parse_qs(parsed.query, strict_parsing=True) if parsed.query else {}
        if (parsed.scheme not in ("postgres", "postgresql")
                or not parsed.hostname or not parsed.username or not parsed.password
                or parsed.password == "[YOUR-PASSWORD]" or parsed.fragment
                or parsed.path != "/postgres" or parsed.port not in (5432, 6543)
                or not parsed.hostname.endswith((".pooler.supabase.com", ".supabase.co"))
                or any(key not in ("sslmode",) for key in query)
                or ("sslmode" in query and query["sslmode"] not in (["require"], ["verify-full"]))):
            raise ValueError("invalid")
        sslmode = query.get("sslmode", ["require"])[0]
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": "postgres",
            "HOST": parsed.hostname,
            "PORT": parsed.port,
            "USER": unquote(parsed.username),
            "PASSWORD": unquote(parsed.password),
            "CONN_MAX_AGE": 0,
            "CONN_HEALTH_CHECKS": True,
            "OPTIONS": {"sslmode": sslmode, "connect_timeout": 10},
        }
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ImproperlyConfigured(
            "Set LABTWIN_DATABASE_URL to a valid private Supabase Postgres Session Pooler URI."
        ) from exc


def s3_endpoint(value):
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or not parsed.hostname
                or not parsed.hostname.endswith(".supabase.co")
                or parsed.path != "/storage/v1/s3"
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ValueError("invalid")
        return value.rstrip("/")
    except (ValueError, TypeError) as exc:
        raise ImproperlyConfigured("Set LABTWIN_S3_ENDPOINT to the private Supabase HTTPS S3 endpoint.") from exc
