"""Run private-deployment checks with disposable secrets and a fresh database.

Never reads a production environment file or a production SQLite database.
Secrets are generated in memory and never printed or written to source.
"""
import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="labtwin-deployment-check-") as fixture:
        env = {**os.environ, "DJANGO_SETTINGS_MODULE": "deployment.settings",
               "DJANGO_SECRET_KEY": secrets.token_urlsafe(48),
               "LABTWIN_DEPLOYMENT_PASSWORD": secrets.token_urlsafe(32),
               "LABTWIN_PUBLIC_URL": "https://demo.example.test",
               "LABTWIN_DATA_DIR": fixture, "LITELLM_LOCAL_MODEL_COST_MAP": "True",
               "PYTHONPATH": os.pathsep.join([str(root), str(root / "backend")])}
        return subprocess.run([sys.executable, "-m", "django", "test", "deployment.tests",
                               "deployment.test_media", "--noinput"], cwd=root, env=env).returncode


if __name__ == "__main__":
    raise SystemExit(main())
