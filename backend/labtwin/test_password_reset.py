"""Recovery must prove email possession without changing learning ownership."""
from datetime import timedelta
from threading import BoundedSemaphore
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.db import DatabaseError
from django.test import Client, override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from . import password_reset as recovery
from .models import AccessToken, Account, Course, CourseMaterial, Enrollment, StudentResponse
from .test_classrooms import ClassroomFixture


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEBUG=True, DEFAULT_FROM_EMAIL="labtwin@example.test",
    LABTWIN_PASSWORD_RESET_EMAIL_ENABLED=True,
    LABTWIN_PASSWORD_RESET_ORIGIN="https://demo.example.test",
    PASSWORD_RESET_TIMEOUT=1800,
    ALLOWED_HOSTS=["testserver", "untrusted.example.test"],
    CSRF_TRUSTED_ORIGINS=["https://testserver"],
)
class PasswordResetTests(ClassroomFixture):
    def setUp(self):
        super().setUp()
        cache.clear()
        mail.outbox = []
        self.student.user.email = "learner@example.test"
        self.student.user.save(update_fields=["email"])
        self.teacher.user.email = "teacher@example.test"
        self.teacher.user.save(update_fields=["email"])

    def request_link(self, email="learner@example.test"):
        # Execute delivery deterministically in this test connection only.
        with patch.object(recovery, "schedule_delivery", side_effect=lambda action, value: action(value) or True):
            return self.post(Client(), "auth/password-reset/", {"email": email})

    def credentials(self, user=None):
        user = user or self.student.user
        user.refresh_from_db()
        return {"uid": urlsafe_base64_encode(force_bytes(user.pk)), "token": default_token_generator.make_token(user)}

    def confirm(self, credentials=None, **kwargs):
        data = {**(credentials or self.credentials()), "new_password1": "New-Correct-Horse-94!", "new_password2": "New-Correct-Horse-94!", **kwargs}
        with patch.object(recovery, "schedule_delivery", side_effect=lambda action, value: action(value) or True):
            return self.post(Client(), "auth/password-reset/confirm/", data)

    def test_known_unknown_and_inactive_addresses_have_identical_response(self):
        self.teacher.user.is_active = False
        self.teacher.user.save(update_fields=["is_active"])
        results = [self.request_link(email) for email in ("learner@example.test", "absent@example.test", "teacher@example.test")]
        self.assertEqual([r.status_code for r in results], [200, 200, 200])
        self.assertTrue(all(r.json() == results[0].json() for r in results))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["learner@example.test"])
        for response in results:
            self.assertNotIn("token", response.content.decode())
            self.assertNotIn("learner@example.test", response.content.decode())
            self.assertEqual(response["Cache-Control"], "no-store")

    def test_response_does_not_lookup_accounts_or_wait_for_email_delivery(self):
        with patch.object(recovery, "schedule_delivery") as schedule:
            with self.assertNumQueries(0):
                first = self.post(Client(), "auth/password-reset/", {"email": "learner@example.test"})
            with self.assertNumQueries(0):
                second = self.post(Client(), "auth/password-reset/", {"email": "absent@example.test"})
        self.assertEqual(first.json(), second.json())
        self.assertEqual(schedule.call_count, 2)
        self.assertEqual(mail.outbox, [])

    def test_email_link_uses_configured_https_origin_and_not_request_host(self):
        with patch.object(recovery, "schedule_delivery", side_effect=lambda action, value: action(value) or True):
            response = Client(HTTP_HOST="untrusted.example.test").post("/api/auth/password-reset/", {"email": "LEARNER@EXAMPLE.TEST"}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        body = mail.outbox[0].body
        link = next(line for line in body.splitlines() if line.startswith("https://"))
        self.assertTrue(link.startswith("https://demo.example.test/#password-reset="))
        self.assertNotIn("untrusted.example.test", body)
        uid, token = link.split("#password-reset=")[1].split(":")
        self.assertTrue(default_token_generator.check_token(self.student.user, token))
        self.assertEqual(uid, self.credentials()["uid"])
        self.assertNotIn(token, response.content.decode())

    def test_email_disabled_missing_smtp_and_unsafe_backends_fail_closed(self):
        cases = [
            {"LABTWIN_PASSWORD_RESET_EMAIL_ENABLED": False},
            {"EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend", "EMAIL_HOST": "", "EMAIL_HOST_USER": "", "EMAIL_HOST_PASSWORD": ""},
            {"EMAIL_BACKEND": "django.core.mail.backends.console.EmailBackend"},
            {"EMAIL_BACKEND": "django.core.mail.backends.filebased.EmailBackend"},
            {"EMAIL_BACKEND": "django.core.mail.backends.dummy.EmailBackend"},
            {"DEBUG": False},  # In-memory backend is forbidden on deployments.
            {"LABTWIN_PASSWORD_RESET_ORIGIN": "https://demo.example.test/unsafe"},
            {"LABTWIN_PASSWORD_RESET_ORIGIN": "http://demo.example.test"},
        ]
        for settings in cases:
            with self.subTest(settings=settings), override_settings(**settings), patch.object(recovery, "schedule_delivery") as schedule:
                known = self.post(Client(), "auth/password-reset/", {"email": "learner@example.test"})
                unknown = self.post(Client(), "auth/password-reset/", {"email": "absent@example.test"})
                self.assertEqual(known.status_code, 503)
                self.assertEqual(known.json(), unknown.json())
                schedule.assert_not_called()
        self.assertEqual(mail.outbox, [])

    def test_email_validation_and_old_clients_without_email(self):
        for value in ("", "not-an-email", [], {"email": "nested@example.test"}, "a" * 255):
            with self.subTest(value=value):
                response = self.request_link(value)
                self.assertEqual(response.status_code, 400)
        result = self.post(Client(), "auth/register/", {"username": "legacy-compatible", "password": "Legacy-test-pass-94!", "name": "Legacy", "role": "student"})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(Account.objects.get(user__username="legacy-compatible").user.email, "")

    def test_registration_saves_valid_recovery_email_without_changing_roles(self):
        for role in ("student", "teacher"):
            result = self.post(Client(), "auth/register/", {"username": "email-" + role, "password": "Registered-test-pass-94!", "name": "Email test", "role": role, "email": role + "@example.test"})
            self.assertEqual(result.status_code, 200, result.content)
            account = Account.objects.get(user__username="email-" + role)
            self.assertEqual(account.user.email, role + "@example.test")
            self.assertEqual(account.role, role)
        result = self.post(Client(), "auth/register/", {"username": "bad-email", "password": "Registered-test-pass-94!", "name": "Bad", "role": "student", "email": "not-an-email"})
        self.assertEqual(result.status_code, 400)
        self.assertFalse(Account.objects.filter(user__username="bad-email").exists())

    def test_accounts_without_saved_email_are_not_assigned_an_email(self):
        response = self.request_link("student-two@example.test")
        self.assertEqual(response.status_code, 200)
        self.other.user.refresh_from_db()
        self.assertEqual(self.other.user.email, "")
        self.assertEqual(mail.outbox, [])

    def test_inactive_unusable_and_non_labtwin_users_receive_no_reset(self):
        self.student.user.set_unusable_password()
        self.student.user.save(update_fields=["password"])
        get_user_model().objects.create_user("admin-only", email="only@example.test", password="Only-test-password-94!")
        for email in ("learner@example.test", "only@example.test"):
            self.assertEqual(self.request_link(email).status_code, 200)
        self.assertEqual(mail.outbox, [])

    def test_request_throttling_does_not_reveal_account_existence(self):
        results = [self.request_link() for _ in range(5)]
        self.assertTrue(all(r.status_code == 200 and r.json() == results[0].json() for r in results))
        self.assertEqual(len(mail.outbox), 3)

    def test_delivery_overload_has_clear_account_independent_failure(self):
        with patch.object(recovery, "schedule_delivery", return_value=False):
            known = self.post(Client(), "auth/password-reset/", {"email": "learner@example.test"})
            unknown = self.post(Client(), "auth/password-reset/", {"email": "absent@example.test"})
        self.assertEqual(known.status_code, 503)
        self.assertEqual(known.json(), unknown.json())
        self.assertIn("temporarily busy", known.json()["error"])

    def test_database_failure_rolls_back_password_and_session_revocation(self):
        credentials = self.credentials()
        with patch("django.db.models.query.QuerySet.delete", side_effect=DatabaseError("private database detail")), self.assertLogs(recovery.logger, "WARNING") as output:
            response = self.confirm(credentials)
        self.assertEqual(response.status_code, 503)
        self.student.user.refresh_from_db()
        self.assertTrue(self.student.user.check_password("Correct-Horse-84!"))
        self.assertTrue(AccessToken.objects.filter(account=self.student).exists())
        self.assertTrue(default_token_generator.check_token(self.student.user, credentials["token"]))
        self.assertNotIn("private database detail", " ".join(output.output))

    def test_student_reset_preserves_account_classroom_course_material_and_work(self):
        Enrollment.objects.create(classroom=self.room, student=self.student.student)
        course = Course.objects.create(classroom=self.room, name="Preserved course")
        material = CourseMaterial.objects.create(course=course, uploaded_by=self.teacher, title="Keep notes", filename="keep.pdf", file="keep.pdf", kind="pdf", status="ready", sha256="a" * 64)
        work = StudentResponse.objects.create(student=self.student.student, question="Keep work", code="print(7)", stage="analysis")
        before = {model: list(model.objects.values()) for model in (Account, Enrollment, Course, CourseMaterial, StudentResponse)}
        credentials = self.credentials()
        response = self.confirm(credentials, role="teacher", email="attacker@example.test", student_id=self.other.student_id)
        self.assertEqual(response.status_code, 200, response.content)
        for model, rows in before.items():
            self.assertEqual(list(model.objects.values()), rows)
        self.student.user.refresh_from_db()
        self.assertEqual(self.student.user.email, "learner@example.test")
        self.assertTrue(self.student.user.check_password("New-Correct-Horse-94!"))
        self.assertEqual(material.course_id, course.id)
        self.assertEqual(work.student_id, self.student.student_id)
        self.assertFalse(AccessToken.objects.filter(account=self.student).exists())
        self.assertTrue(AccessToken.objects.filter(account=self.teacher).exists())
        self.assertEqual(self.sc.get("/api/auth/me/").status_code, 401)
        self.assertEqual(self.post(Client(), "auth/login/", {"username": "student-one", "password": "Correct-Horse-84!"}).status_code, 401)
        login = self.post(Client(), "auth/login/", {"username": "student-one", "password": "New-Correct-Horse-94!"})
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json()["account"]["id"], self.student.id)
        self.assertEqual(login.json()["account"]["role"], "student")
        self.assertEqual(login.json()["account"]["student_id"], self.student.student_id)
        self.assertNotIn("token", response.json())  # Normal sign-in required.

    def test_teacher_reset_preserves_classroom_ownership(self):
        response = self.confirm(self.credentials(self.teacher.user))
        self.assertEqual(response.status_code, 200)
        self.room.refresh_from_db()
        self.teacher.refresh_from_db()
        self.assertEqual(self.room.teacher_id, self.teacher.id)
        self.assertEqual(self.teacher.role, "teacher")
        self.assertEqual(self.tc.get("/api/auth/me/").status_code, 401)
        login = self.post(Client(), "auth/login/", {"username": "teacher-one", "password": "New-Correct-Horse-94!"})
        self.assertEqual(login.json()["account"]["role"], "teacher")

    def test_reset_is_single_use_and_invalidates_other_outstanding_links(self):
        first = self.credentials()
        with patch.object(default_token_generator, "_now", return_value=default_token_generator._now() + timedelta(seconds=10)):
            second = self.credentials()
        self.assertEqual(self.confirm(first).status_code, 200)
        for credentials in (first, second):
            response = self.confirm(credentials)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["error"], recovery.INVALID_LINK)

    def test_expired_link_does_not_change_password_or_sessions(self):
        credentials = self.credentials()
        with patch.object(default_token_generator, "_now", return_value=default_token_generator._now() + timedelta(seconds=1801)):
            response = self.confirm(credentials)
        self.assertEqual(response.status_code, 400)
        self.student.user.refresh_from_db()
        self.assertTrue(self.student.user.check_password("Correct-Horse-84!"))
        self.assertTrue(AccessToken.objects.filter(account=self.student).exists())

    def test_tampered_wrong_user_missing_and_malformed_links_are_rejected(self):
        valid = self.credentials()
        candidates = [{**valid, "token": valid["token"] + "0"}, {**valid, "uid": self.credentials(self.teacher.user)["uid"]}, {**valid, "uid": "invalid"}, {**valid, "token": []}, {"uid": "", "token": ""}]
        for data in candidates:
            with self.subTest(data_keys=list(data)):
                response = self.confirm(data)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["error"], recovery.INVALID_LINK)

    def test_weak_or_mismatched_passwords_do_not_consume_link(self):
        credentials = self.credentials()
        for first, second in (("short", "short"), ("Strong-test-password-94!", "Different-password-84!")):
            self.assertEqual(self.confirm(credentials, new_password1=first, new_password2=second).status_code, 400)
        self.student.user.refresh_from_db()
        self.assertTrue(default_token_generator.check_token(self.student.user, credentials["token"]))
        self.assertEqual(self.confirm(credentials).status_code, 200)

    def test_changed_email_and_disabled_user_invalidate_link(self):
        credentials = self.credentials()
        for changes in ({"email": "updated@example.test"}, {"is_active": False}):
            get_user_model().objects.filter(pk=self.student.user_id).update(**changes)
            self.assertEqual(self.confirm(credentials).status_code, 400)

    def test_atomic_reset_does_not_overwrite_a_concurrent_password_change(self):
        credentials = self.credentials()
        original = recovery.SetPasswordForm.save
        def competing_update(form, commit=False):
            rival = get_user_model().objects.get(pk=form.user.pk)
            rival.set_password("Concurrent-password-84!")
            rival.save(update_fields=["password"])
            return original(form, commit=commit)
        with patch.object(recovery.SetPasswordForm, "save", competing_update):
            response = self.confirm(credentials)
        self.assertEqual(response.status_code, 400)
        self.student.user.refresh_from_db()
        self.assertTrue(self.student.user.check_password("Concurrent-password-84!"))

    def test_both_mutations_require_csrf_and_reject_cross_site_requests(self):
        client = Client(enforce_csrf_checks=True)
        credentials = self.credentials()
        self.assertEqual(self.post(client, "auth/password-reset/", {"email": "learner@example.test"}).status_code, 403)
        self.assertEqual(self.post(client, "auth/password-reset/confirm/", credentials).status_code, 403)
        security = client.get("/api/auth/password-reset/", secure=True).json()
        with patch.object(recovery, "schedule_delivery"):
            response = client.post("/api/auth/password-reset/", {"email": "learner@example.test"}, content_type="application/json", secure=True, HTTP_X_CSRFTOKEN=security["csrf_token"], HTTP_ORIGIN="https://testserver")
        self.assertEqual(response.status_code, 200)
        response = client.post("/api/auth/password-reset/", {"email": "learner@example.test"}, content_type="application/json", secure=True, HTTP_X_CSRFTOKEN=security["csrf_token"], HTTP_ORIGIN="https://attacker.example.test")
        self.assertEqual(response.status_code, 403)

    def test_confirmation_email_contains_neither_password_nor_reset_token(self):
        credentials = self.credentials()
        self.assertEqual(self.confirm(credentials).status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn("New-Correct-Horse-94!", mail.outbox[0].body)
        self.assertNotIn(credentials["token"], mail.outbox[0].body)

    def test_delivery_capacity_is_bounded_and_failure_logs_no_provider_secrets(self):
        with patch.object(recovery, "delivery_slots", BoundedSemaphore(2)), patch.object(recovery, "Thread"):
            self.assertTrue(recovery.schedule_delivery(recovery.send_reset, "absent@example.test"))
            self.assertTrue(recovery.schedule_delivery(recovery.send_reset, "absent@example.test"))
            self.assertFalse(recovery.schedule_delivery(recovery.send_reset, "absent@example.test"))
        def start_inline(**kwargs):
            class InlineThread:
                def start(self): kwargs["target"]()
            return InlineThread()
        with patch.object(recovery, "Thread", side_effect=start_inline), patch.object(recovery, "close_old_connections"), self.assertLogs(recovery.logger, "WARNING") as output:
            def failed_delivery(_): raise TimeoutError("provider-secret-and-private-link")
            recovery.schedule_delivery(failed_delivery, "private-address@example.test")
        self.assertNotIn("provider-secret", " ".join(output.output))
        self.assertNotIn("private-address", " ".join(output.output))
