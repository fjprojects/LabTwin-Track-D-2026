"""Start the unchanged application with safe migrations and one web worker."""
import os
import subprocess
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    os.environ["DJANGO_SETTINGS_MODULE"] = "deployment.settings"
    sys.path[:0] = [str(root), str(root / "backend")]
    # Child extraction/evaluation workers inherit exactly the same settings.
    os.environ["PYTHONPATH"] = os.pathsep.join([str(root), str(root / "backend")])
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    from django.conf import settings
    data = settings.LABTWIN_DATA_DIR
    data.mkdir(parents=True, exist_ok=True)
    for name in ("private_learning", "learning_vectors", "student_sessions"):
        (data / name).mkdir(exist_ok=True)
    # Retain the original legacy file layout, backing its writable state with
    # the deployment volume; no changes to the legacy services are needed.
    for name in ("student_sessions", "syllabus_state.json", "student_memory.json", "syllabus_analysis_cache.json"):
        link = root / name
        if not link.is_symlink() and link.exists():
            raise RuntimeError("Refusing to replace existing legacy state. Back it up before deployment.")
        if not link.is_symlink():
            link.symlink_to(data / name, target_is_directory=name == "student_sessions")
    manage = [sys.executable, str(root / "backend/manage.py")]
    subprocess.run([*manage, "migrate", "--noinput"], check=True)
    subprocess.run([*manage, "collectstatic", "--noinput"], check=True)
    subprocess.run([*manage, "check", "--deploy"], check=True)
    if getattr(settings, "LABTWIN_SUPABASE_STORAGE_ENABLED", False):
        # Chroma is disposable on Render Free. The source text and embeddings
        # are already durable in PostgreSQL; hydrate the local index on boot.
        try:
            subprocess.run([*manage, "restore_course_vectors"], check=True, timeout=180)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            print("Vector cache restoration unavailable; SQL-grounded retrieval remains enabled.", file=sys.stderr)
    os.execv(sys.executable, [sys.executable, "-m", "gunicorn", "backend.wsgi:application",
        "--bind", "0.0.0.0:" + os.getenv("PORT", "10000"), "--workers", "1", "--threads", "2",
        "--timeout", "180", "--error-logfile", "-"])


if __name__ == "__main__":
    main()
