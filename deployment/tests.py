"""Regression checks specific to the optional private deployment layer."""
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core import signing
from django.core.exceptions import ImproperlyConfigured
from django.test import Client, SimpleTestCase, override_settings
from django.urls import resolve

from .access import COOKIE, SALT, LIFETIME, password_fingerprint
from .settings import required_secret, production_signing_key


@override_settings(ALLOWED_HOSTS=["demo.example.test"], CSRF_TRUSTED_ORIGINS=["https://demo.example.test"])
class DeploymentTests(SimpleTestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST="demo.example.test")
        self.cookie = signing.dumps({"key": password_fingerprint()}, salt=SALT)

    def authorize(self):
        self.client.cookies[COOKIE] = self.cookie

    def test_production_settings_disable_debug_and_use_private_storage(self):
        self.assertFalse(settings.DEBUG)
        self.assertTrue(settings.SECURE_SSL_REDIRECT)
        self.assertTrue(settings.SESSION_COOKIE_SECURE)
        self.assertTrue(settings.CSRF_COOKIE_SECURE)
        self.assertEqual(settings.LABTWIN_PROCESS_MODE, "local")
        self.assertFalse(settings.LABTWIN_PROCESS_INLINE)
        self.assertEqual(settings.DATABASES["default"]["NAME"].parent, settings.LABTWIN_DATA_DIR)
        self.assertEqual(settings.LABTWIN_MEDIA_ROOT.parent, settings.LABTWIN_DATA_DIR)

    def test_missing_and_placeholder_secrets_fail_closed(self):
        for value in ("", "short", "replace-with-" + "x" * 60):
            with patch.dict(os.environ, {"LABTWIN_TEST_SECRET": value}):
                with self.assertRaises(ImproperlyConfigured):
                    required_secret("LABTWIN_TEST_SECRET", 50)

    def test_render_256_bit_secret_is_expanded_deterministically(self):
        import secrets
        value = secrets.token_urlsafe(32)
        with patch.dict(os.environ, {"DJANGO_SECRET_KEY": value}):
            result = production_signing_key()
            self.assertEqual(len(result), 64)
            self.assertEqual(result, production_signing_key())
        value = secrets.token_urlsafe(48)
        with patch.dict(os.environ, {"DJANGO_SECRET_KEY": value}):
            self.assertEqual(production_signing_key(), value)

    def test_health_is_public_and_discloses_only_status(self):
        response = self.client.get("/deployment/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_unknown_host_is_rejected(self):
        response = self.client.get("/deployment/health/", HTTP_HOST="outsider.example.test", secure=True)
        self.assertEqual(response.status_code, 400)

    def test_http_ui_redirects_to_https(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "https://demo.example.test/")

    def test_unauthenticated_ui_redirects_to_private_gate(self):
        response = self.client.get("/", secure=True)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/deployment/access/")

    def test_unauthenticated_api_register_and_media_are_blocked(self):
        for path in ("/api/auth/register/", "/api/learning/courses/", "/api/learning/media/1/?ticket=untrusted"):
            response = self.client.get(path, secure=True, HTTP_AUTHORIZATION="Bearer untrusted")
            self.assertEqual(response.status_code, 401)
            self.assertIn("Private demo access", response.json()["error"])

    def test_private_login_requires_csrf(self):
        client = Client(enforce_csrf_checks=True, HTTP_HOST="demo.example.test")
        response = client.post("/deployment/access/", {"password": settings.LABTWIN_DEPLOYMENT_PASSWORD}, secure=True)
        self.assertEqual(response.status_code, 403)

    def test_private_login_sets_separate_secure_cookie(self):
        client = Client(enforce_csrf_checks=True, HTTP_HOST="demo.example.test")
        client.get("/deployment/access/", secure=True)
        response = client.post("/deployment/access/", {"password": settings.LABTWIN_DEPLOYMENT_PASSWORD}, secure=True,
                               HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
                               HTTP_ORIGIN="https://demo.example.test")
        self.assertEqual(response.status_code, 302)
        cookie = response.cookies[COOKIE]
        self.assertTrue(cookie["secure"])
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Strict")
        self.assertEqual(cookie["path"], "/")
        self.assertEqual(cookie["max-age"], LIFETIME)
        self.assertNotIn("Authorization", response)

    def test_wrong_private_password_has_clear_error(self):
        response = self.client.post("/deployment/access/", {"password": "wrong"}, secure=True)
        self.assertEqual(response.status_code, 401)
        self.assertContains(response, "not accepted", status_code=401)
        self.assertNotIn(COOKIE, response.cookies)

    def test_private_gate_does_not_replace_labtwin_authentication(self):
        self.authorize()
        response = self.client.get("/api/learning/courses/", secure=True)
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("Private demo access", response.json()["error"])

    def test_tampered_expired_and_rotated_access_are_rejected(self):
        self.client.cookies[COOKIE] = self.cookie + "tampered"
        self.assertEqual(self.client.get("/", secure=True).status_code, 302)
        self.authorize()
        with patch("django.core.signing.time.time", return_value=time.time() + LIFETIME + 2):
            self.assertEqual(self.client.get("/", secure=True).status_code, 302)
        with override_settings(LABTWIN_DEPLOYMENT_PASSWORD="rotated-" + "z" * 32):
            self.assertEqual(self.client.get("/", secure=True).status_code, 302)

    def test_built_assets_are_served_without_exposing_missing_files(self):
        self.authorize()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("<html>Existing LabTwin build</html>")
            (root / "runtime.wasm").write_bytes(b"compiled-wasm")
            (root / ".env").write_text("must-never-be-served")
            with override_settings(LABTWIN_FRONTEND_ROOT=root):
                response = self.client.get("/", secure=True)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(b"".join(response.streaming_content), b"<html>Existing LabTwin build</html>")
                self.assertEqual(self.client.get("/runtime.wasm", secure=True)["Content-Type"], "application/wasm")
                for path in ("/.env", "/../outside.txt", "/missing.js", "/api/missing/"):
                    self.assertEqual(self.client.get(path, secure=True).status_code, 404)

    def test_existing_api_routes_and_camera_permissions_are_preserved(self):
        self.assertEqual(resolve("/api/auth/register/").func.__name__, "register")
        response = self.client.get("/deployment/access/", secure=True)
        self.assertEqual(response["Permissions-Policy"], "camera=(self), microphone=(self), display-capture=(self)")
        self.assertNotIn(settings.LABTWIN_DEPLOYMENT_PASSWORD, response.content.decode())
        self.assertNotIn(settings.SECRET_KEY, response.content.decode())

    def test_password_reset_preserves_private_deployment_gate(self):
        for path in ("/api/auth/password-reset/", "/api/auth/password-reset/confirm/", "/api/auth/password-reset/otp/verify/",
                     "/api/auth/password-reset/sms/", "/api/auth/password-reset/sms/verify/",
                     "/api/auth/recovery-phone/", "/api/auth/recovery-phone/verify/"):
            response = self.client.post(path, {"email": "absent@example.test"}, content_type="application/json", secure=True)
            self.assertEqual(response.status_code, 401)
            self.assertIn("Private demo access", response.json()["error"])
        self.authorize()
        response = self.client.get("/api/auth/password-reset/", secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Referrer-Policy"], "no-referrer")
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertIn("csrf_token", response.json())

    def test_reset_handoff_uses_scoped_nonce_without_exposing_credentials(self):
        import re
        first = self.client.get("/deployment/access/", secure=True)
        second = self.client.get("/deployment/access/", secure=True)
        self.assertNotEqual(first["Content-Security-Policy"], second["Content-Security-Policy"])
        nonce = re.search(r'<script nonce="([\w-]+)">', first.content.decode()).group(1)
        self.assertIn("'nonce-" + nonce + "'", first["Content-Security-Policy"])
        self.assertIn("sessionStorage.setItem('labtwin_password_reset', location.hash)", first.content.decode())
        self.assertIn("default-src 'none'", first["Content-Security-Policy"])
        self.assertNotIn("'unsafe-inline'", first["Content-Security-Policy"])
        self.assertNotIn(settings.LABTWIN_DEPLOYMENT_PASSWORD, first.content.decode())
        self.assertNotIn(settings.SECRET_KEY, first.content.decode())
