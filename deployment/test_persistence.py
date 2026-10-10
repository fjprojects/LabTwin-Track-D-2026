"""Offline regression checks for the opt-in Supabase persistence adapter."""
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured, SuspiciousFileOperation
from django.core.files.base import ContentFile
from django.test import SimpleTestCase, override_settings

from deployment.persistence import postgres_database, s3_endpoint
from labtwin.learning.cloud_storage import SupabasePrivateStorage


class DatabaseConfigurationTests(SimpleTestCase):
    def test_session_pooler_uses_postgresql_tls(self):
        result = postgres_database(
            "postgresql://postgres.ref:masked%40value@aws-0-ap-south-1.pooler.supabase.com:5432/postgres"
        )
        self.assertEqual(result["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(result["USER"], "postgres.ref")
        self.assertEqual(result["PASSWORD"], "masked@value")
        self.assertEqual(result["OPTIONS"]["sslmode"], "require")
        self.assertEqual(result["CONN_MAX_AGE"], 0)

    def test_rejects_insecure_or_wrong_database(self):
        for uri in (
            "postgres://postgres:pw@localhost:5432/postgres",
            "postgres://postgres:pw@aws-0-ap-south-1.pooler.supabase.com:5432/postgres?sslmode=disable",
            "postgres://postgres:[YOUR-PASSWORD]@aws-0-ap-south-1.pooler.supabase.com:5432/postgres",
            "sqlite:///tmp/local.db",
        ):
            with self.subTest(uri=uri), self.assertRaises(ImproperlyConfigured):
                postgres_database(uri)

    def test_s3_endpoint_requires_supabase_https(self):
        self.assertEqual(
            s3_endpoint("https://example-ref.storage.supabase.co/storage/v1/s3"),
            "https://example-ref.storage.supabase.co/storage/v1/s3",
        )
        for url in ("http://example-ref.storage.supabase.co/storage/v1/s3",
                    "https://evil.invalid/storage/v1/s3",
                    "https://example-ref.supabase.co/storage/v1/s3?q=1"):
            with self.subTest(url=url), self.assertRaises(ImproperlyConfigured):
                s3_endpoint(url)


class PrivateMaterialStorageTests(SimpleTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings_override = override_settings(LABTWIN_DATA_DIR=Path(self.temp.name))
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.storage = SupabasePrivateStorage()

    def test_hydrates_local_cache_and_can_rehydrate_after_restart(self):
        payload = b"private pdf bytes"
        with patch.object(self.storage, "open", side_effect=lambda *_: ContentFile(payload)) as opened:
            first = Path(self.storage.path("course_1/abc.pdf"))
            self.assertEqual(first.read_bytes(), payload)
            self.assertEqual(Path(self.storage.path("course_1/abc.pdf")), first)
            self.assertEqual(opened.call_count, 1)
            first.unlink()
            self.assertEqual(Path(self.storage.path("course_1/abc.pdf")).read_bytes(), payload)
            self.assertEqual(opened.call_count, 2)

    def test_private_upload_download_delete_without_network(self):
        class MemoryS3:
            def __init__(self):
                self.objects = {}

            def upload_fileobj(self, content, bucket, key):
                self.objects[(bucket, key)] = content.read()

            def download_fileobj(self, bucket, key, output):
                output.write(self.objects[(bucket, key)])

            def head_object(self, *, Bucket, Key):
                return {"ContentLength": len(self.objects[(Bucket, Key)])}

            def delete_object(self, *, Bucket, Key):
                self.objects.pop((Bucket, Key), None)

        fake = MemoryS3()
        self.storage.__dict__["client"] = fake
        with override_settings(LABTWIN_S3_BUCKET="labtwin-private-materials"):
            name = self.storage._save("course_1/document.pdf", ContentFile(b"pdf original"))
            self.assertTrue(self.storage.exists(name))
            self.assertEqual(self.storage.size(name), len(b"pdf original"))
            with self.storage._open(name) as original:
                self.assertEqual(original.read(), b"pdf original")
            self.assertEqual(Path(self.storage.path(name)).read_bytes(), b"pdf original")
            self.storage.delete(name)
            self.assertFalse(self.storage._cache_path(name).exists())

    def test_never_exposes_public_object_urls(self):
        with self.assertRaises(NotImplementedError):
            self.storage.url("course_1/abc.pdf")

    def test_rejects_path_traversal(self):
        for name in ("../secret", "/etc/passwd", "course_1/../secret", "a\\b"):
            with self.subTest(name=name), self.assertRaises(SuspiciousFileOperation):
                self.storage._key(name)

    def test_s3_head_404_is_missing(self):
        from botocore.exceptions import ClientError

        class FakeClient:
            def head_object(self, **kwargs):
                raise ClientError({"Error": {"Code": "404", "Message": "not found"}}, "HeadObject")

        with override_settings(LABTWIN_S3_BUCKET="labtwin-private-materials"):
            self.storage.__dict__["client"] = FakeClient()
            self.assertFalse(self.storage.exists("course_1/missing.pdf"))
