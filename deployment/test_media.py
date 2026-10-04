"""Private deployment + real source/media authorization, including new tabs."""
import hashlib
import io
import tempfile
import time
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from django.core import signing
from django.core.files.base import ContentFile
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone
from reportlab.pdfgen import canvas

from deployment.access import COOKIE, SALT as ACCESS_SALT, password_fingerprint
from labtwin.learning.media import SALT as MEDIA_SALT
from labtwin.models import AccessToken, Course, CourseMaterial, Enrollment, SourceChunk, SourceUnit
from labtwin.test_classrooms import ClassroomFixture


class DeploymentMediaTests(ClassroomFixture):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.files = tempfile.TemporaryDirectory(prefix="labtwin-private-media-test-")
        cls.private_settings = override_settings(
            ALLOWED_HOSTS=["testserver"],
            MIDDLEWARE=["deployment.access.PrivateDeploymentMiddleware"],
            LABTWIN_DEPLOYMENT_PASSWORD="private-deployment-test-password-only",
            LABTWIN_MEDIA_ROOT=cls.files.name,
            PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
        )
        cls.private_settings.enable()

    @classmethod
    def tearDownClass(cls):
        cls.private_settings.disable()
        cls.files.cleanup()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        Enrollment.objects.create(classroom=self.room, student=self.student.student)
        self.course = Course.objects.create(classroom=self.room, name="Data Structures", language="C")
        pdf = io.BytesIO()
        writer = canvas.Canvas(pdf)
        writer.drawString(50, 750, "Page 1: Doubly linked lists connect previous and next nodes.")
        writer.showPage()
        writer.drawString(50, 750, "Page 2: This is a different page.")
        writer.showPage()
        writer.save()
        self.pdf_bytes = pdf.getvalue()
        self.material = CourseMaterial.objects.create(
            course=self.course, uploaded_by=self.teacher,
            title="Doubly_Linked_List_Record.pdf", filename="Doubly_Linked_List_Record.pdf",
            kind="pdf", status="ready", sha256=hashlib.sha256(self.pdf_bytes).hexdigest(),
            file=ContentFile(self.pdf_bytes, name="Doubly_Linked_List_Record.pdf"),
        )
        self.unit = SourceUnit.objects.create(
            material=self.material, number=1, page_number=1,
            text="Doubly linked lists connect previous and next nodes.",
        )
        self.chunk = SourceChunk.objects.create(
            unit=self.unit, course=self.course, position=0,
            text=self.unit.text, embedding_model="test",
        )
        cookie = signing.dumps({"key": password_fingerprint()}, salt=ACCESS_SALT)
        for client in (self.sc, self.tc, self.oc, self.tc2):
            client.cookies[COOKIE] = cookie

    def source_data(self, client=None):
        response = (client or self.sc).get(f"/api/learning/sources/{self.chunk.id}/", secure=True)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def target(self, url):
        parsed = urlsplit(url)
        return parsed.path + "?" + parsed.query

    def original_link(self):
        return self.target(self.source_data()["media_url"])

    def test_original_pdf_opens_in_new_tab_without_private_cookie(self):
        source = self.source_data()
        self.assertEqual(source["source"]["filename"], "Doubly_Linked_List_Record.pdf")
        self.assertEqual(source["source"]["page_number"], 1)
        target = self.target(source["media_url"])
        # Native PDF viewers/new tabs can omit the private gate cookie and
        # cannot attach the application's bearer header. Exercise that exact
        # request through BOTH the deployment middleware and real file view.
        new_tab = Client()
        self.assertFalse(new_tab.cookies)
        response = new_tab.get(target, secure=True)
        self.assertEqual(response.status_code, 200, getattr(response, "content", b""))
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("Doubly_Linked_List_Record.pdf", response["Content-Disposition"])
        self.assertEqual(response["Cache-Control"], "private, no-store")
        pdf_bytes = b"".join(response.streaming_content)
        self.assertEqual(pdf_bytes, self.pdf_bytes)
        from pypdf import PdfReader
        self.assertIn("Page 1: Doubly linked lists", PdfReader(io.BytesIO(pdf_bytes)).pages[0].extract_text())
        self.assertNotIn(COOKIE, response.cookies)
        refreshed = Client().get(target, secure=True)
        self.assertEqual(refreshed.status_code, 200)
        self.assertEqual(b"".join(refreshed.streaming_content), self.pdf_bytes)

    def test_pdf_head_and_range_requests_without_private_cookie(self):
        target = self.original_link()
        head = Client().head(target, secure=True)
        self.assertEqual(head.status_code, 200)
        self.assertEqual(int(head["Content-Length"]), len(self.pdf_bytes))
        self.assertEqual(b"".join(head.streaming_content), b"")
        partial = Client().get(target, secure=True, HTTP_RANGE="bytes=0-5")
        self.assertEqual(partial.status_code, 206)
        self.assertEqual(b"".join(partial.streaming_content), self.pdf_bytes[:6])
        self.assertEqual(partial["Content-Range"], f"bytes 0-5/{len(self.pdf_bytes)}")

    def test_teacher_original_material_link_without_private_cookie(self):
        response = self.tc.get(f"/api/learning/materials/{self.material.id}/", secure=True)
        self.assertEqual(response.status_code, 200, response.content)
        opened = Client().get(self.target(response.json()["material"]["media_url"]), secure=True)
        self.assertEqual(opened.status_code, 200)
        self.assertEqual(b"".join(opened.streaming_content), self.pdf_bytes)

    def test_visual_grant_is_bound_to_exact_material_and_unit(self):
        self.unit.visual_file.save("figure.png", ContentFile(b"source-figure"))
        source = self.source_data()
        target = self.target(source["visual_url"])
        response = Client().get(target, secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"source-figure")
        query = urlsplit(target).query
        other = SourceUnit.objects.create(material=self.material, number=2, page_number=2, text="Other page")
        for path in (
            reverse("learning-media", args=[self.material.id]),
            reverse("learning-visual", args=[self.material.id, other.id]),
            reverse("learning-visual", args=[self.material.id + 1, self.unit.id]),
        ):
            with self.subTest(path=path):
                self.assertEqual(Client().get(path + "?" + query, secure=True).status_code, 401)
        original_query = urlsplit(source["media_url"]).query
        self.assertEqual(Client().get(urlsplit(target).path + "?" + original_query, secure=True).status_code, 401)

    def test_media_ticket_cannot_authorize_other_routes_or_writes(self):
        target = self.original_link()
        query = urlsplit(target).query
        for path in (
            f"/api/learning/sources/{self.chunk.id}/",
            "/api/auth/me/", "/api/auth/register/", "/api/learning/courses/",
            reverse("learning-media", args=[self.material.id + 1]),
        ):
            with self.subTest(path=path):
                self.assertEqual(Client().get(path + "?" + query, secure=True).status_code, 401)
        self.assertEqual(Client().post(target, secure=True).status_code, 401)

    def test_private_gate_and_application_auth_are_both_required_to_mint_links(self):
        self.sc.cookies.clear()
        response = self.sc.get(f"/api/learning/sources/{self.chunk.id}/", secure=True)
        self.assertEqual(response.status_code, 401)
        self.assertIn("Private demo access", response.json()["error"])
        client = Client()
        client.cookies[COOKIE] = self.tc.cookies[COOKIE]
        self.assertEqual(client.get(f"/api/learning/sources/{self.chunk.id}/", secure=True).status_code, 401)
        self.assertEqual(client.get(reverse("learning-media", args=[self.material.id]), secure=True).status_code, 401)
        self.assertEqual(self.oc.get(f"/api/learning/sources/{self.chunk.id}/", secure=True).status_code, 404)
        self.assertEqual(self.tc2.get(f"/api/learning/sources/{self.chunk.id}/", secure=True).status_code, 404)

    def test_old_signed_ticket_without_private_access_grant_remains_blocked(self):
        token = AccessToken.objects.get(account=self.student)
        ticket = signing.dumps({"material": self.material.id, "token": token.digest, "unit": None}, salt=MEDIA_SALT)
        target = reverse("learning-media", args=[self.material.id]) + "?ticket=" + ticket
        self.assertEqual(Client().get(target, secure=True).status_code, 401)
        # The original ticket still works if the normal private cookie exists.
        client = Client()
        client.cookies[COOKIE] = self.sc.cookies[COOKIE]
        response = client.get(target, secure=True)
        self.assertEqual(response.status_code, 200)
        response.close()

    def test_invalid_expired_and_rotated_grants_fail_closed(self):
        target = self.original_link()
        for bad in (target + "tampered", urlsplit(target).path, urlsplit(target).path + "?ticket=invalid"):
            self.assertEqual(Client().get(bad, secure=True).status_code, 401)
        with patch("django.core.signing.time.time", return_value=time.time() + 302):
            self.assertEqual(Client().get(target, secure=True).status_code, 401)
            fresh = self.original_link()
            response = Client().get(fresh, secure=True)
            self.assertEqual(response.status_code, 200)
            response.close()
        with override_settings(LABTWIN_DEPLOYMENT_PASSWORD="rotated-private-test-password-only"):
            self.assertEqual(Client().get(target, secure=True).status_code, 401)
        with override_settings(SECRET_KEY="rotated-test-signing-key", SECRET_KEY_FALLBACKS=[]):
            self.assertEqual(Client().get(target, secure=True).status_code, 401)

    def test_malformed_and_wrong_purpose_signed_tickets_fail_closed(self):
        target = self.original_link()
        ticket = parse_qs(urlsplit(target).query)["ticket"][0]
        valid = signing.loads(ticket, salt=MEDIA_SALT)
        for data in ([], "not-a-media-grant", {**valid, "deployment_access": "wrong-private-grant"}):
            bad = urlsplit(target).path + "?ticket=" + signing.dumps(data, salt=MEDIA_SALT)
            self.assertEqual(Client().get(bad, secure=True).status_code, 401)
        wrong_purpose = urlsplit(target).path + "?ticket=" + signing.dumps(valid, salt=ACCESS_SALT)
        self.assertEqual(Client().get(wrong_purpose, secure=True).status_code, 401)

    def test_logout_revokes_new_tab_link(self):
        target = self.original_link()
        self.assertEqual(self.post(self.sc, "auth/logout/", {}).status_code, 200)
        self.assertEqual(Client().get(target, secure=True).status_code, 401)

    def test_expired_session_revokes_new_tab_link(self):
        target = self.original_link()
        AccessToken.objects.filter(account=self.student).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(Client().get(target, secure=True).status_code, 401)

    def test_disabled_user_revokes_new_tab_link(self):
        target = self.original_link()
        self.student.user.is_active = False
        self.student.user.save(update_fields=["is_active"])
        self.assertEqual(Client().get(target, secure=True).status_code, 401)

    def test_classroom_removal_revokes_new_tab_link(self):
        target = self.original_link()
        Enrollment.objects.filter(student=self.student.student, classroom=self.room).delete()
        self.assertEqual(Client().get(target, secure=True).status_code, 404)
