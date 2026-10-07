"""No real SMS is sent: provider fixtures exercise recovery/security contracts."""
import json
from datetime import timedelta
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError
from uuid import uuid4

from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.test import Client, SimpleTestCase, override_settings
from django.utils import timezone

from . import phone_recovery as phone, password_reset as recovery, sms_provider as provider
from .models import AccessToken, Course, CourseMaterial, Enrollment, PhoneOTP, RecoveryPhone, StudentResponse
from .test_classrooms import ClassroomFixture

SMS_SETTINGS = {
    "LABTWIN_PASSWORD_RESET_SMS_ENABLED": True, "TWILIO_ACCOUNT_SID": "AC" + "1" * 32,
    "TWILIO_AUTH_TOKEN": "fake-provider-test-secret-only-32", "TWILIO_VERIFY_SERVICE_SID": "VA" + "2" * 32,
    "TWILIO_API_KEY_SID": "", "TWILIO_API_KEY_SECRET": "",
    "PASSWORD_HASHERS": ["django.contrib.auth.hashers.MD5PasswordHasher"],
    "ALLOWED_HOSTS": ["testserver"], "CSRF_TRUSTED_ORIGINS": ["https://testserver"],
}
NUMBER = "+15005550006"  # Test fixture only, never passed to an external API.
OTHER_NUMBER = "+15005550007"
SID = "VE" + "3" * 32


@override_settings(**SMS_SETTINGS)
class PhoneRecoveryTests(ClassroomFixture):
    def setUp(self):
        super().setUp()
        cache.clear()

    def registered_phone(self, account=None, number=NUMBER):
        return RecoveryPhone.objects.create(account=account or self.student, number=number, verified_at=timezone.now())

    def request_code(self, number=NUMBER, client=None):
        with patch.object(recovery, "schedule_delivery", side_effect=lambda action, value: action(value) or True), \
                patch.object(provider, "send", return_value=SID):
            if client:
                return self.post(client, "auth/recovery-phone/", {"phone": number, "password": "Correct-Horse-84!"})
            return self.post(Client(), "auth/password-reset/sms/", {"phone": number})

    def verify(self, identity, client=None, approved=True, code="123456"):
        with patch.object(provider, "approved", return_value=approved):
            return self.post(client or Client(), "auth/recovery-phone/verify/" if client else "auth/password-reset/sms/verify/",
                             {"request_id": identity, "code": code})

    def test_known_unknown_and_legacy_numbers_have_uniform_responses(self):
        self.registered_phone()
        for number in (NUMBER, OTHER_NUMBER, "+15005550008"):
            response = self.request_code(number)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(set(response.json()), {"message", "request_id", "expires_in"})
            self.assertEqual(response.json()["message"], phone.REQUEST_MESSAGE)
            self.assertEqual(response.json()["expires_in"], 600)
            self.assertEqual(response["Cache-Control"], "no-store")
            self.assertNotIn(number, response.content.decode())
        self.assertEqual(PhoneOTP.objects.count(), 1)

    def test_public_request_does_not_query_accounts_or_wait_for_network(self):
        with patch.object(recovery, "schedule_delivery", return_value=True), patch.object(provider, "send") as send:
            with self.assertNumQueries(0):
                response = self.post(Client(), "auth/password-reset/sms/", {"phone": NUMBER})
        self.assertEqual(response.status_code, 200)
        send.assert_not_called()

    def test_unconfigured_sms_fails_closed_without_a_provider_call(self):
        with override_settings(LABTWIN_PASSWORD_RESET_SMS_ENABLED=False), patch.object(provider, "send") as send:
            self.assertEqual(self.request_code().status_code, 503)
            self.assertEqual(self.verify(str(uuid4())).status_code, 503)
            self.assertFalse(self.sc.get("/api/auth/recovery-phone/").json()["available"])
            send.assert_not_called()
        self.assertEqual(PhoneOTP.objects.count(), 0)

    def test_invalid_phone_and_body_are_rejected(self):
        for number in ("9876543210", "+000123456789", "+12", NUMBER + "1234567890", "https://example.test", 123, None):
            with self.subTest(number=number):
                self.assertEqual(self.post(Client(), "auth/password-reset/sms/", {"phone": number}).status_code, 400)
        self.assertEqual(Client().post("/api/auth/password-reset/sms/", "[]", content_type="application/json").status_code, 400)

    def test_phone_binding_requires_login_current_password_and_sms_proof(self):
        self.assertEqual(self.post(Client(), "auth/recovery-phone/", {"phone": NUMBER}).status_code, 401)
        self.assertEqual(self.post(self.sc, "auth/recovery-phone/", {"phone": NUMBER, "password": "wrong"}).status_code, 400)
        response = self.request_code(client=self.sc)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(RecoveryPhone.objects.exists())
        self.assertEqual(self.verify(response.json()["request_id"], self.sc, approved=False).status_code, 400)
        self.assertFalse(RecoveryPhone.objects.exists())
        self.assertEqual(self.verify(response.json()["request_id"], self.sc).status_code, 200)
        self.assertEqual(RecoveryPhone.objects.get().account_id, self.student.pk)
        self.assertEqual(RecoveryPhone.objects.get().number, NUMBER)

    def test_binding_is_account_and_purpose_bound(self):
        response = self.request_code(client=self.sc)
        identity = response.json()["request_id"]
        self.assertEqual(self.verify(identity, self.oc).status_code, 400)
        self.assertEqual(self.verify(identity).status_code, 400)
        self.assertEqual(self.verify(identity, Client()).status_code, 401)
        self.assertEqual(self.verify(identity, self.sc).status_code, 200)

    def test_reset_cannot_bind_a_number_or_create_a_login_session(self):
        self.registered_phone()
        response = self.request_code()
        identity = response.json()["request_id"]
        tokens = list(AccessToken.objects.values())
        self.assertEqual(self.verify(identity, self.sc).status_code, 400)
        result = self.verify(identity)
        self.assertEqual(result.status_code, 200)
        self.assertTrue(default_token_generator.check_token(self.student.user, result.json()["token"]))
        self.assertEqual(list(AccessToken.objects.values()), tokens)
        self.assertEqual(set(result.json()), {"uid", "token", "message"})

    def test_sms_reset_is_single_use_and_revokes_existing_sessions(self):
        self.registered_phone()
        identity = self.request_code().json()["request_id"]
        proof = self.verify(identity).json()
        self.assertEqual(self.verify(identity).status_code, 400)
        data = {**proof, "new_password1": "New-SMS-password-984!", "new_password2": "New-SMS-password-984!"}
        self.assertEqual(self.post(Client(), "auth/password-reset/confirm/", data).status_code, 200)
        self.assertEqual(self.post(Client(), "auth/password-reset/confirm/", data).status_code, 400)
        self.assertEqual(self.sc.get("/api/auth/me/").status_code, 401)
        self.student.user.refresh_from_db()
        self.assertTrue(self.student.user.check_password("New-SMS-password-984!"))
        self.assertEqual(self.student.role, "student")

    def test_uncertain_or_failed_proof_never_changes_password_or_progress(self):
        self.registered_phone()
        identity = self.request_code().json()["request_id"]
        before = list(AccessToken.objects.values())
        self.assertEqual(self.verify(identity, approved=False).status_code, 400)
        with patch.object(provider, "approved", side_effect=provider.SMSUnavailable("credentials-private-details")):
            response = self.post(Client(), "auth/password-reset/sms/verify/", {"request_id": identity, "code": "123456"})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("credentials-private-details", response.content.decode())
        self.assertEqual(list(AccessToken.objects.values()), before)
        self.student.user.refresh_from_db()
        self.assertTrue(self.student.user.check_password("Correct-Horse-84!"))
        self.assertIsNone(PhoneOTP.objects.get().consumed_at)

    def test_five_attempts_then_correct_code_cannot_reopen_limit(self):
        self.registered_phone()
        identity = self.request_code().json()["request_id"]
        for _ in range(5):
            self.assertEqual(self.verify(identity, approved=False).status_code, 400)
        self.assertEqual(self.verify(identity).status_code, 400)
        self.assertEqual(PhoneOTP.objects.get().attempts, 5)

    def test_fifth_attempt_can_succeed(self):
        self.registered_phone()
        identity = self.request_code().json()["request_id"]
        for _ in range(4):
            self.assertEqual(self.verify(identity, approved=False).status_code, 400)
        self.assertEqual(self.verify(identity).status_code, 200)

    def test_expired_challenge_does_not_call_provider(self):
        self.registered_phone()
        identity = self.request_code().json()["request_id"]
        row = PhoneOTP.objects.get()
        with patch.object(phone.timezone, "now", return_value=row.expires_at), patch.object(provider, "approved") as check:
            self.assertEqual(self.post(Client(), "auth/password-reset/sms/verify/", {"request_id": identity, "code": "123456"}).status_code, 400)
            check.assert_not_called()

    def test_expiry_during_network_check_cannot_issue_a_reset_grant(self):
        self.registered_phone()
        identity = self.request_code().json()["request_id"]
        row = PhoneOTP.objects.get()
        def late(*args):
            PhoneOTP.objects.filter(pk=row.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
            return True
        with patch.object(provider, "approved", side_effect=late):
            self.assertEqual(self.post(Client(), "auth/password-reset/sms/verify/", {"request_id": identity, "code": "123456"}).status_code, 400)

    def test_password_change_during_network_check_invalidates_proof(self):
        self.registered_phone()
        identity = self.request_code().json()["request_id"]
        def changed(*args):
            type(self.student.user).objects.filter(pk=self.student.user.pk).update(password="changed-hash")
            return True
        with patch.object(provider, "approved", side_effect=changed):
            self.assertEqual(self.post(Client(), "auth/password-reset/sms/verify/", {"request_id": identity, "code": "123456"}).status_code, 400)

    def test_account_removed_during_network_check_returns_safe_invalid_proof(self):
        self.registered_phone()
        identity = self.request_code().json()["request_id"]
        def removed(*args):
            self.student.delete()
            return True
        with patch.object(provider, "approved", side_effect=removed):
            self.assertEqual(self.post(Client(), "auth/password-reset/sms/verify/", {"request_id": identity, "code": "123456"}).status_code, 400)

    def test_password_login_email_or_phone_change_invalidates_challenge(self):
        self.registered_phone()
        for field, value in (("password", "changed-hash"), ("email", "changed@example.test"), ("last_login", timezone.now())):
            with self.subTest(field=field):
                self.student.user.email = ""
                self.student.user.last_login = None
                self.student.user.set_password("Correct-Horse-84!")
                self.student.user.save()
                cache.clear()
                identity = self.request_code().json()["request_id"]
                type(self.student.user).objects.filter(pk=self.student.user.pk).update(**{field: value})
                self.assertEqual(self.verify(identity).status_code, 400)
        self.student.user.refresh_from_db()
        cache.clear()
        identity = self.request_code().json()["request_id"]
        RecoveryPhone.objects.filter(account=self.student).update(number=OTHER_NUMBER)
        self.assertEqual(self.verify(identity).status_code, 400)

    def test_inactive_and_unusable_accounts_are_not_sent_sms(self):
        self.registered_phone()
        for inactive in (True, False):
            cache.clear()
            self.student.user.is_active = not inactive
            if not inactive:
                self.student.user.set_unusable_password()
            self.student.user.save()
            self.assertEqual(self.request_code().status_code, 200)
        self.assertFalse(PhoneOTP.objects.exists())

    def test_phone_already_owned_by_another_account_cannot_be_transferred(self):
        self.registered_phone(self.other)
        identity = self.request_code(client=self.sc).json()["request_id"]
        self.assertEqual(self.verify(identity, self.sc).status_code, 400)
        self.assertEqual(RecoveryPhone.objects.get().account_id, self.other.pk)
        self.assertIsNone(PhoneOTP.objects.get().consumed_at)

    def test_only_owner_can_inspect_masked_phone_and_roster_has_no_phone(self):
        self.registered_phone()
        own = self.sc.get("/api/auth/recovery-phone/")
        self.assertEqual(own.json()["masked_phone"], "••••0006")
        self.assertNotIn(NUMBER, own.content.decode())
        self.assertFalse(self.oc.get("/api/auth/recovery-phone/").json()["verified"])
        self.assertEqual(Client().get("/api/auth/recovery-phone/").status_code, 401)
        self.join()
        self.assertNotIn(NUMBER, self.tc.get(f"/api/classrooms/{self.room.pk}/students/").content.decode())

    def test_remove_phone_requires_password_and_invalidates_pending_reset(self):
        self.registered_phone()
        identity = self.request_code().json()["request_id"]
        self.assertEqual(self.sc.delete("/api/auth/recovery-phone/", json.dumps({"password": "wrong"}), content_type="application/json").status_code, 400)
        self.assertEqual(self.sc.delete("/api/auth/recovery-phone/", json.dumps({"password": "Correct-Horse-84!"}), content_type="application/json").status_code, 200)
        self.assertFalse(RecoveryPhone.objects.exists())
        self.assertEqual(self.verify(identity).status_code, 400)
        self.assertEqual(self.sc.get("/api/auth/me/").status_code, 200)

    def test_send_timeout_preserves_account_and_terminates_challenge(self):
        with patch.object(provider, "send", side_effect=provider.SMSUnavailable("private-provider-body")), \
                patch.object(recovery, "schedule_delivery", side_effect=lambda action, value: action(value) or True):
            response = self.post(self.sc, "auth/recovery-phone/", {"phone": NUMBER, "password": "Correct-Horse-84!"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PhoneOTP.objects.get().status, "failed")
        self.assertFalse(RecoveryPhone.objects.exists())
        self.assertEqual(self.verify(response.json()["request_id"], self.sc).status_code, 400)

    def test_cooldown_applies_to_known_unknown_and_both_purposes(self):
        self.registered_phone()
        for number in (NUMBER, OTHER_NUMBER):
            self.assertEqual(self.request_code(number).status_code, 200)
            self.assertEqual(self.request_code(number).status_code, 429)
            self.assertEqual(self.request_code(number, self.sc).status_code, 429)

    def test_delivery_busy_and_verify_rate_limit_have_bounded_errors(self):
        with patch.object(recovery, "schedule_delivery", return_value=False):
            self.assertEqual(self.post(Client(), "auth/password-reset/sms/", {"phone": NUMBER}).status_code, 503)
        cache.clear()
        for _ in range(30):
            self.assertEqual(self.verify(str(uuid4())).status_code, 400)
        self.assertEqual(self.verify(str(uuid4())).status_code, 429)

    def test_older_delivery_job_cannot_replace_a_newer_phone_challenge(self):
        with patch.object(recovery, "schedule_delivery", return_value=True) as scheduled:
            old = self.post(self.sc, "auth/recovery-phone/", {"phone": NUMBER, "password": "Correct-Horse-84!"})
            new = self.post(self.sc, "auth/recovery-phone/", {"phone": OTHER_NUMBER, "password": "Correct-Horse-84!"})
        with patch.object(provider, "send", return_value=SID) as send:
            phone.send_code(scheduled.call_args_list[1].args[1])
            phone.send_code(scheduled.call_args_list[0].args[1])
            self.assertEqual(send.call_count, 1)
        self.assertEqual(PhoneOTP.objects.get().number, OTHER_NUMBER)
        self.assertEqual(self.verify(old.json()["request_id"], self.sc).status_code, 400)
        self.assertEqual(self.verify(new.json()["request_id"], self.sc).status_code, 200)

    def test_malformed_codes_cannot_reach_provider(self):
        for code in (123456, "１２３４５６", "123", "x23456", "12345678901", None):
            with patch.object(provider, "approved") as check:
                self.assertEqual(self.verify(str(uuid4()), code=code).status_code, 400)
                check.assert_not_called()

    def test_all_new_mutating_routes_require_csrf(self):
        secure = Client(enforce_csrf_checks=True, HTTP_AUTHORIZATION="Bearer test-token-student-one")
        for route in ("auth/password-reset/sms/", "auth/password-reset/sms/verify/", "auth/recovery-phone/", "auth/recovery-phone/verify/"):
            self.assertEqual(self.post(secure, route, {}).status_code, 403)
        self.assertEqual(secure.delete("/api/auth/recovery-phone/", "{}", content_type="application/json").status_code, 403)
        csrf = secure.get("/api/auth/password-reset/", secure=True).json()["csrf_token"]
        with patch.object(recovery, "schedule_delivery", return_value=True):
            response = secure.post("/api/auth/password-reset/sms/", json.dumps({"phone": NUMBER}),
                                   content_type="application/json", secure=True, HTTP_X_CSRFTOKEN=csrf,
                                   HTTP_ORIGIN="https://testserver")
        self.assertEqual(response.status_code, 200)

    def test_reset_preserves_roles_classes_courses_materials_and_saved_work(self):
        self.join()
        course = Course.objects.create(classroom=self.room, name="Kept course")
        CourseMaterial.objects.create(course=course, uploaded_by=self.teacher, title="Kept", filename="kept.pdf", kind="pdf", status="ready", sha256="a"*64)
        StudentResponse.objects.create(student=self.student.student, stage="analysis", question="Kept work", code="print(7)")
        models = (Course, CourseMaterial, Enrollment, StudentResponse)
        before = {model: list(model.objects.values()) for model in models}
        self.registered_phone(self.teacher)
        identity = self.request_code().json()["request_id"]
        proof = self.verify(identity).json()
        self.assertEqual(self.post(Client(), "auth/password-reset/confirm/", {**proof, "new_password1": "Teacher-SMS-pass-94!", "new_password2": "Teacher-SMS-pass-94!"}).status_code, 200)
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.role, "teacher")
        for model in models:
            self.assertEqual(list(model.objects.values()), before[model])


@override_settings(**SMS_SETTINGS)
class SMSProviderTests(SimpleTestCase):
    def result(self, **changes):
        return {"sid": SID, "account_sid": SMS_SETTINGS["TWILIO_ACCOUNT_SID"],
                "service_sid": SMS_SETTINGS["TWILIO_VERIFY_SERVICE_SID"], "to": NUMBER,
                "channel": "sms", "status": "approved", "valid": True, **changes}

    def test_only_bound_approved_sms_proofs_are_accepted(self):
        with patch.object(provider, "post", return_value=self.result()) as post:
            self.assertTrue(provider.approved(NUMBER, SID, "123456"))
            self.assertEqual(post.call_args.args, ("VerificationCheck", {"VerificationSid": SID, "Code": "123456"}))
        for change in ({"sid": "VE" + "4"*32}, {"account_sid": "AC" + "4"*32}, {"service_sid": "VA" + "4"*32},
                       {"to": OTHER_NUMBER}, {"channel": "email"}, {"status": "pending"}, {"valid": False}, {"valid": "true"}):
            with patch.object(provider, "post", return_value=self.result(**change)):
                self.assertFalse(provider.approved(NUMBER, SID, "123456"))

    def test_send_accepts_only_a_bound_pending_verification(self):
        with patch.object(provider, "post", return_value=self.result(status="pending")) as post:
            self.assertEqual(provider.send(NUMBER), SID)
            self.assertEqual(post.call_args.args, ("Verifications", {"To": NUMBER, "Channel": "sms"}))
        with patch.object(provider, "post", return_value=self.result()):
            with self.assertRaises(provider.SMSUnavailable):
                provider.send(NUMBER)

    def test_fixed_https_timeout_no_redirect_or_automatic_send_retry(self):
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value = json.dumps(self.result(status="pending")).encode()
        with patch.object(provider, "build_opener", return_value=opener):
            self.assertEqual(provider.send(NUMBER), SID)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, f"https://verify.twilio.com/v2/Services/{SMS_SETTINGS['TWILIO_VERIFY_SERVICE_SID']}/Verifications")
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 10)
        self.assertIsNone(provider.NoRedirect().redirect_request(None, None, 302, "", {}, "https://untrusted.test"))
        opener.open.reset_mock()
        opener.open.side_effect = TimeoutError("private secret")
        with patch.object(provider, "build_opener", return_value=opener):
            with self.assertRaises(provider.SMSUnavailable) as raised:
                provider.send(NUMBER)
        self.assertNotIn("private secret", str(raised.exception))
        self.assertEqual(opener.open.call_count, 1)

    def test_check_expired_and_invalid_errors_are_not_provider_success(self):
        for code in (400, 404):
            opener = MagicMock()
            opener.open.side_effect = HTTPError("https://verify.twilio.com", code, "private", {}, None)
            with patch.object(provider, "build_opener", return_value=opener):
                self.assertFalse(provider.approved(NUMBER, SID, "123456"))

    def test_invalid_large_or_failed_provider_responses_fail_closed(self):
        for body in (b"not-json", b"[]", b"x" * 65537):
            opener = MagicMock()
            opener.open.return_value.__enter__.return_value.read.return_value = body
            with patch.object(provider, "build_opener", return_value=opener), self.assertRaises(provider.SMSUnavailable):
                provider.send(NUMBER)
        opener.open.side_effect = URLError("private error")
        with patch.object(provider, "build_opener", return_value=opener), self.assertRaises(provider.SMSUnavailable):
            provider.send(NUMBER)

    def test_missing_and_invalid_credentials_are_never_used(self):
        for settings in ({"LABTWIN_PASSWORD_RESET_SMS_ENABLED": False}, {"TWILIO_ACCOUNT_SID": "bad"},
                         {"TWILIO_VERIFY_SERVICE_SID": "bad"}, {"TWILIO_AUTH_TOKEN": ""},
                         {"TWILIO_API_KEY_SID": "SK" + "5"*32, "TWILIO_API_KEY_SECRET": ""}):
            with override_settings(**settings), patch.object(provider, "build_opener") as open_http:
                self.assertFalse(provider.ready())
                with self.assertRaises(provider.SMSUnavailable):
                    provider.send(NUMBER)
                open_http.assert_not_called()

    def test_api_key_authentication_is_supported_without_auth_token(self):
        with override_settings(TWILIO_API_KEY_SID="SK" + "5"*32, TWILIO_API_KEY_SECRET="fake-api-key-test-secret", TWILIO_AUTH_TOKEN=""):
            self.assertTrue(provider.ready())
            self.assertEqual(provider.credentials(), ("SK" + "5"*32, "fake-api-key-test-secret"))
