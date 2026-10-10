"""Server-only private Supabase S3 storage with disposable local extraction cache.

Originals and extracted figures live in the private Supabase bucket. A local
copy is materialised only for existing parsers and authenticated PDF streaming;
no public or presigned object URL is exposed to the browser.
"""
import hashlib
import os
import shutil
import tempfile
from functools import cached_property
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.core.files import File
from django.core.files.storage import Storage


class SupabasePrivateStorage(Storage):
    @cached_property
    def client(self):
        import boto3
        from botocore.config import Config

        return boto3.client(
            "s3",
            aws_access_key_id=settings.LABTWIN_S3_ACCESS_KEY_ID,
            aws_secret_access_key=settings.LABTWIN_S3_SECRET_ACCESS_KEY,
            endpoint_url=settings.LABTWIN_S3_ENDPOINT,
            region_name=settings.LABTWIN_S3_REGION,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                connect_timeout=8,
                read_timeout=60,
                retries={"mode": "standard", "max_attempts": 2},
            ),
        )

    @property
    def bucket(self):
        return settings.LABTWIN_S3_BUCKET

    def _key(self, name):
        if not isinstance(name, str) or not name or "\\" in name:
            raise SuspiciousFileOperation("Invalid private file key")
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or name.endswith("/") or not path.parts:
            raise SuspiciousFileOperation("Invalid private file key")
        return str(path)

    def _save(self, name, content):
        key = self._key(name)
        content.seek(0)
        self.client.upload_fileobj(content, self.bucket, key)
        return key

    def _open(self, name, mode="rb"):
        if mode not in ("rb", "r"):
            raise ValueError("Private course files are read-only")
        spooled = tempfile.SpooledTemporaryFile(max_size=2 * 1024 * 1024)
        try:
            self.client.download_fileobj(self.bucket, self._key(name), spooled)
            spooled.seek(0)
            return File(spooled, name=name)
        except Exception:
            spooled.close()
            raise

    def exists(self, name):
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=self.bucket, Key=self._key(name))
            return True
        except ClientError as error:
            code = str(error.response.get("Error", {}).get("Code", ""))
            if code in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def size(self, name):
        return int(self.client.head_object(Bucket=self.bucket, Key=self._key(name))["ContentLength"])

    def _cache_path(self, name):
        key = self._key(name)
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        suffix = Path(key).suffix.lower()
        return Path(settings.LABTWIN_DATA_DIR) / "cloud_file_cache" / (digest + suffix)

    def path(self, name):
        """Hydrate a temporary local path for existing PDF, OCR and FFmpeg code."""
        target = self._cache_path(name)
        if target.is_file():
            return str(target)
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temp_name = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as out:
                temp_name = out.name
                with self.open(name, "rb") as source:
                    shutil.copyfileobj(source, out, length=256 * 1024)
            os.replace(temp_name, target)
        finally:
            if temp_name and os.path.exists(temp_name):
                os.unlink(temp_name)
        return str(target)

    def delete(self, name):
        if not name:
            return
        self.client.delete_object(Bucket=self.bucket, Key=self._key(name))
        self._cache_path(name).unlink(missing_ok=True)

    def url(self, name):
        raise NotImplementedError(
            "Private teaching files must use authenticated LabTwin media URLs, not storage URLs."
        )
