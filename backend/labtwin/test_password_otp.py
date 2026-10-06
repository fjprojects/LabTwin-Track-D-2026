"""OTP proof is bounded, private and restricted to the existing reset flow."""
import re
from datetime import timedelta
from unittest.mock import patch
from uuid import UUID, uuid4

from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.db import DatabaseError
from django.test import Client, override_settings
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from . import password_otp as otp, password_reset as recovery
from .models import Account, AccessToken, Classroom, Course, CourseMaterial, Enrollment, PasswordResetOTP, StudentResponse
from .test_classrooms import ClassroomFixture


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", DEBUG=True,
    DEFAULT_FROM_EMAIL="labtwin@example.test", LABTWIN_PASSWORD_RESET_EMAIL_ENABLED=True,
    LABTWIN_PASSWORD_RESET_ORIGIN="https://demo.example.test", PASSWORD_RESET_TIMEOUT=1800,
    ALLOWED_HOSTS=["testserver"], CSRF_TRUSTED_ORIGINS=["https://testserver"],
)
class PasswordOTPTests(ClassroomFixture):
    def setUp(self):
        super().setUp()
        cache.clear()
        mail.outbox = []
        for account, email in ((self.student, "learner@example.test"), (self.teacher, "teacher@example.test")):
            account.user.email = email
            account.user.save(update_fields=["email"])

    def request_code(self, email="learner@example.test"):
        with patch.object(recovery, "schedule_delivery", side_effect=lambda action, value: action(value) or True):
            return self.post(Client(), "auth/password-reset/", {"email": email, "method": "otp"})

    def delivered_code(self, index=-1):
        return re.search(r"verification code is: ([0-9]{8})", mail.outbox[index].body).group(1)

    def verify(self, identity, code):
        return self.post(Client(), "auth/password-reset/otp/verify/", {"request_id": identity, "code": code})

    def confirm(self, grant):
        with patch.object(recovery, "schedule_delivery", return_value=True):
            return self.post(Client(), "auth/password-reset/confirm/",
                             {"uid": grant["uid"], "token": grant["token"],
                              "new_password1": "OTP-new-password-94!", "new_password2": "OTP-new-password-94!"})

    def test_known_unknown_inactive_and_legacy_emails_have_uniform_request_responses(self):
        self.teacher.user.is_active = False
        self.teacher.user.save(update_fields=["is_active"])
        for email in ("learner@example.test", "missing@example.test", "teacher@example.test", "legacy@example.test"):
            response = self.request_code(email)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["message"], otp.REQUEST_MESSAGE)
            self.assertEqual(response.json()["expires_in"], 600)
            self.assertEqual(UUID(response.json()["request_id"]).version, 4)
            self.assertEqual(set(response.json()), {"message", "request_id", "expires_in"})
            self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(PasswordResetOTP.objects.count(), 1)
        self.other.user.refresh_from_db()
        self.assertEqual(self.other.user.email, "")

    def test_request_does_not_lookup_accounts_or_wait_for_delivery(self):
        with patch.object(recovery, "schedule_delivery", return_value=True):
            for email in ("learner@example.test", "missing@example.test"):
                with self.assertNumQueries(0):
                    response = self.post(Client(), "auth/password-reset/", {"email": email, "method": "otp"})
                self.assertEqual(response.status_code, 200)
        self.assertEqual(PasswordResetOTP.objects.count(), 0)
        self.assertEqual(mail.outbox, [])

    def test_code_has_leading_zeroes_and_only_keyed_digests_are_stored(self):
        with patch.object(otp.secrets, "randbelow", return_value=123):
            response = self.request_code()
        self.assertEqual(self.delivered_code(), "00000123")
        row = PasswordResetOTP.objects.get(account=self.student)
        self.assertNotEqual(row.code_digest, "00000123")
        self.assertEqual(len(row.code_digest), 64)
        self.assertEqual(len(row.state_digest), 64)
        self.assertNotIn("00000123", response.content.decode())
        self.assertNotIn("#password-reset=", mail.outbox[0].body)

    def test_verification_is_single_use_and_grants_no_login_before_reset(self):
        response = self.request_code()
        identity, code = response.json()["request_id"], self.delivered_code()
        tokens = list(AccessToken.objects.values())
        verified = self.verify(identity, code)
        self.assertEqual(verified.status_code, 200)
        self.assertTrue(default_token_generator.check_token(self.student.user, verified.json()["token"]))
        self.assertEqual(list(AccessToken.objects.values()), tokens)
        self.assertNotIn("account", verified.json())
        self.assertEqual(self.verify(identity, code).status_code, 400)
        self.assertEqual(self.confirm(verified.json()).status_code, 200)
        self.assertEqual(self.confirm(verified.json()).status_code, 400)
        self.assertEqual(self.sc.get("/api/auth/me/").status_code, 401)
        login = self.post(Client(), "auth/login/", {"username": "student-one", "password": "OTP-new-password-94!"})
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json()["account"]["role"], "student")

    def test_expired_code_does_not_change_password_or_sessions(self):
        response = self.request_code()
        row = PasswordResetOTP.objects.get(account=self.student)
        with patch.object(otp.timezone, "now", return_value=row.expires_at):
            result = self.verify(response.json()["request_id"], self.delivered_code())
        self.assertEqual(result.status_code, 400)
        self.student.user.refresh_from_db()
        self.assertTrue(self.student.user.check_password("Correct-Horse-84!"))
        self.assertTrue(AccessToken.objects.filter(account=self.student).exists())

    def test_five_attempts_are_allowed_then_correct_code_is_rejected(self):
        response = self.request_code()
        identity, code = response.json()["request_id"], self.delivered_code()
        wrong = ("1" if code[0] != "1" else "2") + code[1:]
        for _ in range(5):
            self.assertEqual(self.verify(identity, wrong).status_code, 400)
        self.assertEqual(self.verify(identity, code).status_code, 400)
        self.assertIsNone(PasswordResetOTP.objects.get(account=self.student).consumed_at)
        self.assertEqual(self.sc.get("/api/auth/me/").status_code, 200)
        new = self.request_code()
        self.assertEqual(self.verify(new.json()["request_id"], self.delivered_code()).status_code, 200)

    def test_correct_code_on_fifth_attempt_still_works(self):
        response = self.request_code()
        identity, code = response.json()["request_id"], self.delivered_code()
        wrong = ("1" if code[0] != "1" else "2") + code[1:]
        for _ in range(4):
            self.assertEqual(self.verify(identity, wrong).status_code, 400)
        self.assertEqual(self.verify(identity, code).status_code, 200)

    def test_resend_invalidates_the_previous_challenge(self):
        first = self.request_code()
        first_code = self.delivered_code()
        second = self.request_code()
        self.assertNotEqual(first.json()["request_id"], second.json()["request_id"])
        self.assertEqual(PasswordResetOTP.objects.count(), 1)
        self.assertEqual(self.verify(first.json()["request_id"], first_code).status_code, 400)
        self.assertEqual(self.verify(second.json()["request_id"], self.delivered_code()).status_code, 200)

    def test_old_delivery_job_cannot_replace_a_newer_request(self):
        with patch.object(recovery, "schedule_delivery", return_value=True) as scheduled:
            first = self.post(Client(), "auth/password-reset/", {"email": "learner@example.test", "method": "otp"})
            second = self.post(Client(), "auth/password-reset/", {"email": "learner@example.test", "method": "otp"})
        old_values, new_values = [call.args[1] for call in scheduled.call_args_list]
        otp.send_otp(new_values)
        otp.send_otp(old_values)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(str(PasswordResetOTP.objects.get().request_id), second.json()["request_id"])
        self.assertEqual(self.verify(first.json()["request_id"], self.delivered_code()).status_code, 400)

    def test_password_email_and_login_changes_invalidate_unverified_code(self):
        for field, value in (("password", "changed-hash"), ("email", "updated@example.test"), ("last_login", timezone.now())):
            with self.subTest(field=field):
                self.student.user.email = "learner@example.test"
                self.student.user.set_password("Correct-Horse-84!")
                self.student.user.last_login = None
                self.student.user.save()
                cache.clear()
                response = self.request_code()
                type(self.student.user).objects.filter(pk=self.student.user.pk).update(**{field: value})
                self.assertEqual(self.verify(response.json()["request_id"], self.delivered_code()).status_code, 400)

    def test_inactive_or_unusable_user_cannot_verify_an_issued_code(self):
        response = self.request_code()
        self.student.user.is_active = False
        self.student.user.save(update_fields=["is_active"])
        self.assertEqual(self.verify(response.json()["request_id"], self.delivered_code()).status_code, 400)
        self.student.user.is_active = True
        self.student.user.set_unusable_password()
        self.student.user.save(update_fields=["is_active", "password"])
        self.assertEqual(self.verify(response.json()["request_id"], self.delivered_code()).status_code, 400)

    def test_same_email_accounts_keep_separate_roles_and_attempt_limits(self):
        self.teacher.user.email = "learner@example.test"
        self.teacher.user.save(update_fields=["email"])
        with patch.object(otp.secrets, "randbelow", side_effect=[123, 456]):
            response = self.request_code()
        self.assertEqual(PasswordResetOTP.objects.count(), 2)
        # Exclude an exhausted account even if another row can claim attempts.
        PasswordResetOTP.objects.filter(account=self.student).update(attempts=5)
        student_code = next(re.search(r"verification code is: ([0-9]{8})", msg.body).group(1)
                            for msg in mail.outbox if "username student-one." in msg.body)
        self.assertEqual(self.verify(response.json()["request_id"], student_code).status_code, 400)
        teacher_code = next(re.search(r"verification code is: ([0-9]{8})", msg.body).group(1)
                            for msg in mail.outbox if "username teacher-one." in msg.body)
        result = self.verify(response.json()["request_id"], teacher_code)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["uid"], urlsafe_base64_encode(force_bytes(self.teacher.user_id)))

    def test_roles_classrooms_courses_materials_and_work_survive_otp_reset(self):
        course = Course.objects.create(classroom=self.room, name="Preserved course")
        CourseMaterial.objects.create(course=course, uploaded_by=self.teacher, title="Keep notes", filename="keep.pdf",
                                      file="keep.pdf", kind="pdf", status="ready", sha256="a" * 64)
        StudentResponse.objects.create(student=self.student.student, question="Keep work", code="print(7)", stage="analysis")
        models = (Account, Classroom, Enrollment, Course, CourseMaterial, StudentResponse)
        before = {model: list(model.objects.values()) for model in models}
        for account in (self.student, self.teacher):
            response = self.request_code(account.user.email)
            grant = self.verify(response.json()["request_id"], self.delivered_code())
            self.assertEqual(grant.status_code, 200)
            self.assertEqual(self.confirm(grant.json()).status_code, 200)
        for model in models:
            self.assertEqual(list(model.objects.values()), before[model])
        self.assertFalse(AccessToken.objects.filter(account__in=(self.student, self.teacher)).exists())
        self.assertTrue(AccessToken.objects.filter(account=self.other).exists())

    def test_link_reset_invalidates_outstanding_otp(self):
        response = self.request_code()
        grant = {"uid": urlsafe_base64_encode(force_bytes(self.student.user_id)),
                 "token": default_token_generator.make_token(self.student.user)}
        self.assertEqual(self.confirm(grant).status_code, 200)
        self.assertEqual(self.verify(response.json()["request_id"], self.delivered_code()).status_code, 400)

    def test_missing_email_configuration_and_overload_fail_without_disclosure(self):
        with override_settings(LABTWIN_PASSWORD_RESET_EMAIL_ENABLED=False):
            known, unknown = self.request_code(), self.request_code("absent@example.test")
            self.assertEqual(known.status_code, 503)
            self.assertEqual(known.json(), unknown.json())
        with patch.object(recovery, "schedule_delivery", return_value=False):
            response = self.post(Client(), "auth/password-reset/", {"email": "learner@example.test", "method": "otp"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(PasswordResetOTP.objects.count(), 0)

    def test_request_throttling_is_account_independent(self):
        for email in ("learner@example.test", "absent@example.test"):
            statuses = [self.request_code(email).status_code for _ in range(4)]
            self.assertEqual(statuses, [200, 200, 200, 429])
        self.assertEqual(len(mail.outbox), 3)

    def test_malformed_missing_wrong_challenge_and_unicode_codes_are_rejected(self):
        response = self.request_code()
        identity, code = response.json()["request_id"], self.delivered_code()
        for request_id, value in ((str(uuid4()), code), (identity, "１２３４５６７８"), (identity, []),
                                  (identity, "123"), ("invalid", code), (None, code)):
            result = self.verify(request_id, value)
            self.assertEqual(result.status_code, 400)
            self.assertEqual(result.json()["error"], otp.INVALID_CODE)

    def test_verification_requires_csrf_and_rejects_cross_site_requests(self):
        response = self.request_code()
        data = {"request_id": response.json()["request_id"], "code": self.delivered_code()}
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(self.post(client, "auth/password-reset/otp/verify/", data).status_code, 403)
        security = client.get("/api/auth/password-reset/", secure=True).json()
        result = client.post("/api/auth/password-reset/otp/verify/", data, content_type="application/json", secure=True,
                             HTTP_X_CSRFTOKEN=security["csrf_token"], HTTP_ORIGIN="https://attacker.example.test")
        self.assertEqual(result.status_code, 403)
        result = client.post("/api/auth/password-reset/otp/verify/", data, content_type="application/json", secure=True,
                             HTTP_X_CSRFTOKEN=security["csrf_token"], HTTP_ORIGIN="https://testserver")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result["Referrer-Policy"], "no-referrer")
        self.assertEqual(result["Cache-Control"], "no-store")

    def test_database_failure_does_not_consume_code_or_leak_private_details(self):
        response = self.request_code()
        code = self.delivered_code()
        with patch.object(default_token_generator, "make_token", side_effect=DatabaseError("private-database-secret")), self.assertLogs(recovery.logger, "WARNING") as output:
            result = self.verify(response.json()["request_id"], code)
        self.assertEqual(result.status_code, 503)
        row = PasswordResetOTP.objects.get(account=self.student)
        self.assertIsNone(row.consumed_at)
        self.assertEqual(row.attempts, 0)
        self.assertNotIn("private-database-secret", " ".join(output.output))
        self.assertNotIn(code, " ".join(output.output))
        self.assertEqual(self.verify(response.json()["request_id"], code).status_code, 200)

    def test_mail_failure_is_private_and_does_not_change_the_account(self):
        def inline_thread(**kwargs):
            class InlineThread:
                def start(self):
                    kwargs["target"]()
            return InlineThread()
        with patch.object(recovery, "Thread", side_effect=inline_thread), patch.object(recovery, "close_old_connections"), \
                patch.object(otp.EmailMessage, "send", side_effect=TimeoutError("private-provider-credential")), \
                self.assertLogs(recovery.logger, "WARNING") as output:
            response = self.post(Client(), "auth/password-reset/", {"email": "learner@example.test", "method": "otp"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("private-provider-credential", " ".join(output.output))
        self.assertNotIn("learner@example.test", " ".join(output.output))
        self.assertEqual(mail.outbox, [])
        self.student.user.refresh_from_db()
        self.assertTrue(self.student.user.check_password("Correct-Horse-84!"))
        self.assertTrue(AccessToken.objects.filter(account=self.student).exists())
