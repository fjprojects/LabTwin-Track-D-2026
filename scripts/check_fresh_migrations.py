"""Verify the unchanged migration chain on an isolated, empty SQLite DB."""
import os
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend"))
os.environ["DJANGO_SETTINGS_MODULE"] = "backend.test_settings"
import django
from django.conf import settings

with tempfile.TemporaryDirectory(prefix="labtwin-migration-check-") as fixture:
    settings.DATABASES["default"]["NAME"] = str(Path(fixture) / "fresh.sqlite3")
    django.setup()
    from django.core.management import call_command
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    call_command("makemigrations", check=True, dry_run=True, verbosity=1)
    call_command("migrate", interactive=False, verbosity=1)
    executor = MigrationExecutor(connection)
    assert not executor.migration_plan(executor.loader.graph.leaf_nodes())
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA integrity_check")
        assert cursor.fetchone()[0] == "ok"
        cursor.execute("SELECT COUNT(*) FROM django_migrations WHERE app='labtwin'")
        print(f"PASS: {cursor.fetchone()[0]} LabTwin migrations applied; fresh database integrity OK")
    connection.close()
