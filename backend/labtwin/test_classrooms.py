import hashlib
import importlib.util
import json
import sys
import types
from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.test import Client, TestCase, override_settings
from django.urls import include, path
from django.utils import timezone

from .access import current_student_id
from .models import Account, AccessToken, Classroom, Enrollment, StudentProfile, StudentResponse


def fake_learning_view(request):
    return JsonResponse({"student_id": current_student_id.get()})


class ClassroomFixture(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Keep the new route/service modules outside the temporary sys.modules
        # snapshot so provider/index mocks target the same modules across suites.
        importlib.import_module("labtwin.learning.urls")
        # Load the production URL table and authorization wrappers. Only the
        # expensive AI handlers are replaced; authentication/classroom/history
        # handlers and the database are real.
        fake_views = types.ModuleType("labtwin.views")
        for name in ("upload_syllabus", "next_question", "analyze_code", "tutor_help", "evaluate_code", "student_session"):
            setattr(fake_views, name, fake_learning_view)
        fake_views.activate_student_session = lambda student_id, fresh=False: {"student_id": student_id}
        fake_views.public_student_session = lambda state: state
        cls.fake_views = fake_views
        replacements = {
            "labtwin.views": fake_views,
            "labtwin.memory_views": types.SimpleNamespace(save_attempt=fake_learning_view, progress_dashboard=fake_learning_view),
            "labtwin.adaptive_views": types.SimpleNamespace(adaptive_next_question=fake_learning_view),
            "labtwin.hint_views": types.SimpleNamespace(progressive_hint=fake_learning_view),
        }
        # Restore only the replaced handlers. patch.dict(sys.modules) restores
        # the entire import table, removing real native/vector dependencies
        # loaded during a suite and breaking their later imports.
        cls.missing_module = object()
        cls.original_modules = {name: sys.modules.get(name, cls.missing_module) for name in replacements}
        sys.modules.update(replacements)
        spec = importlib.util.spec_from_file_location("labtwin._classroom_test_routes", Path(__file__).with_name("urls.py"))
        routes = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(routes)
        cls.routes = types.ModuleType("classroom_test_routes")
        cls.routes.urlpatterns = [path("api/", include(routes.urlpatterns))]
        cls.settings_override = override_settings(ROOT_URLCONF=cls.routes)
        cls.settings_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls.settings_override.disable()
        for name, original in cls.original_modules.items():
            if original is cls.missing_module:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original
        super().tearDownClass()

    def setUp(self):
        self.student, self.sc = self.account("student-one", "student")
        self.other, self.oc = self.account("student-two", "student")
        self.teacher, self.tc = self.account("teacher-one", "teacher")
        self.teacher2, self.tc2 = self.account("teacher-two", "teacher")
        self.room = Classroom.objects.create(teacher=self.teacher, name="CSE S3", join_code="ABC123456789")

    def account(self, username, role):
        user = get_user_model().objects.create_user(username, password="Correct-Horse-84!", first_name=username)
        profile = StudentProfile.objects.create(name=username) if role == "student" else None
        account = Account.objects.create(user=user, role=role, student=profile)
        raw = "test-token-" + username
        AccessToken.objects.create(account=account, digest=hashlib.sha256(raw.encode()).hexdigest(), expires_at=timezone.now()+timedelta(hours=1))
        return account, Client(HTTP_AUTHORIZATION="Bearer " + raw)

    def post(self, client, route, data):
        return client.post("/api/"+route, json.dumps(data), content_type="application/json")

    def join(self):
        return self.post(self.sc, "classrooms/join/", {"code": self.room.join_code.lower()})

class ClassroomTests(ClassroomFixture):
    def test_registration_password_hash_and_unclaimed_legacy_profile(self):
        legacy = StudentProfile.objects.create(name="Shared name")
        response = self.post(Client(), "auth/register/", {"username":"new-user", "password":"Safe-Test-Password-94!", "name":"Shared name", "role":"student"})
        self.assertEqual(response.status_code, 200, response.content)
        account = Account.objects.get(user__username="new-user")
        self.assertNotEqual(account.student_id, legacy.id)
        self.assertTrue(account.user.check_password("Safe-Test-Password-94!"))
        token = response.json()["token"]
        self.assertTrue(AccessToken.objects.filter(digest=hashlib.sha256(token.encode()).hexdigest()).exists())
        duplicate = self.post(Client(), "auth/register/", {"username":"NEW-USER", "password":"Safe-Test-Password-94!", "name":"Other", "role":"teacher"})
        self.assertEqual(duplicate.status_code, 400)

    def test_bad_password_and_role_rejected(self):
        for password, role in [("x", "student"), ("Strong-test-83!", "admin")]:
            response = self.post(Client(), "auth/register/", {"username":"new", "password":password, "role":role, "name":"New"})
            self.assertEqual(response.status_code, 400)

    def test_login_logout_and_expired_token(self):
        self.assertEqual(self.post(Client(), "auth/login/", {"username":"student-one", "password":"wrong"}).status_code, 401)
        response = self.post(Client(), "auth/login/", {"username":"STUDENT-ONE", "password":"Correct-Horse-84!"})
        self.assertEqual(response.status_code, 200)
        signed = Client(HTTP_AUTHORIZATION="Bearer " + response.json()["token"])
        self.assertEqual(signed.get("/api/auth/me/").status_code, 200)
        self.assertEqual(self.post(signed, "auth/logout/", {}).status_code, 200)
        self.assertEqual(signed.get("/api/auth/me/").status_code, 401)
        AccessToken.objects.filter(account=self.student).update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.sc.get("/api/auth/me/").status_code, 401)

    def test_all_legacy_endpoints_require_authentication(self):
        for route in ("start-student/", "save-attempt/", "progress/", "student-session/", "upload-syllabus/", "next-question/", "adaptive-next-question/", "analyze/", "tutor/", "progressive-hint/", "evaluate/", "response-history/"):
            with self.subTest(route=route):
                self.assertEqual(self.post(Client(), route, {}).status_code, 401)

    def test_students_cannot_read_or_write_each_other(self):
        for route in ("progress/", "response-history/", "student-session/"):
            self.assertEqual(self.sc.get("/api/"+route, {"student_id":self.other.student_id}).status_code, 403)
        for route in ("save-attempt/", "analyze/", "evaluate/", "tutor/", "next-question/", "adaptive-next-question/", "progressive-hint/"):
            self.assertEqual(self.post(self.sc, route, {"student_id":self.other.student_id}).status_code, 403)
        response = self.post(self.sc, "tutor/", {})
        self.assertEqual(response.json()["student_id"], self.student.student_id)
        self.assertIsNone(current_student_id.get())

    def test_teacher_access_requires_enrollment_and_is_read_only(self):
        student_id = self.student.student_id
        self.assertEqual(self.tc.get("/api/progress/", {"student_id":student_id}).status_code, 403)
        self.assertEqual(self.join().status_code, 200)
        StudentResponse.objects.create(student=self.student.student, question="Q", code="print(7)", stage="analysis")
        self.assertEqual(self.tc.get("/api/progress/", {"student_id":student_id}).status_code, 200)
        response = self.tc.get("/api/response-history/", {"student_id":student_id})
        self.assertEqual(response.json()["responses"][0]["code"], "print(7)")
        self.assertEqual(self.tc2.get("/api/response-history/", {"student_id":student_id}).status_code, 403)
        self.assertEqual(self.post(self.tc, "evaluate/", {"student_id":student_id}).status_code, 403)
        self.assertEqual(self.tc.get("/api/student-session/", {"student_id":student_id}).status_code, 403)

    def test_class_creation_listing_and_roster_ownership(self):
        self.assertEqual(self.post(self.sc, "classrooms/", {"name":"Fake"}).status_code, 403)
        response = self.post(self.tc, "classrooms/", {"name":"Python", "subject":"Lab"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.json()["classroom"]["join_code"]), 12)
        self.assertEqual(self.tc2.get("/api/classrooms/").json()["classrooms"], [])
        self.join()
        self.assertNotIn("join_code", self.sc.get("/api/classrooms/").json()["classrooms"][0])
        self.assertEqual(self.tc.get(f"/api/classrooms/{self.room.id}/students/").json()["students"][0]["student_id"], self.student.student_id)
        self.assertEqual(self.tc2.get(f"/api/classrooms/{self.room.id}/students/").status_code, 404)
        self.assertEqual(self.sc.get(f"/api/classrooms/{self.room.id}/students/").status_code, 404)

    def test_join_is_idempotent_and_invalid_code_fails(self):
        self.join(); self.join()
        self.assertEqual(Enrollment.objects.count(), 1)
        self.assertEqual(self.post(self.sc, "classrooms/join/", {"code":"INVALID"}).status_code, 404)
        self.assertEqual(self.post(self.tc, "classrooms/join/", {"code":self.room.join_code}).status_code, 403)

    def test_removal_revokes_access_without_deleting_work(self):
        self.join()
        StudentResponse.objects.create(student=self.student.student, question="Q", stage="analysis")
        url = f"/api/classrooms/{self.room.id}/students/{self.student.student_id}/"
        self.assertEqual(self.oc.delete(url).status_code, 403)
        self.assertEqual(self.tc2.delete(url).status_code, 403)
        self.assertEqual(self.tc.delete(url).status_code, 200)
        self.assertEqual(self.tc.get("/api/progress/", {"student_id":self.student.student_id}).status_code, 403)
        self.assertEqual(StudentResponse.objects.count(), 1)

    def test_start_uses_owned_profile_not_submitted_name(self):
        response = self.post(self.sc, "start-student/", {"name":"student-two", "mode":"new"})
        self.assertEqual(response.json()["student_id"], self.student.student_id)
        self.assertEqual(StudentProfile.objects.count(), 2)

    def test_leaving_one_of_two_classes_keeps_other_access(self):
        self.join()
        another = Classroom.objects.create(teacher=self.teacher, name="Another", join_code="OTHER12345678")
        Enrollment.objects.create(classroom=another, student=self.student.student)
        self.assertEqual(self.sc.delete(f"/api/classrooms/{self.room.id}/students/{self.student.student_id}/").status_code, 200)
        self.assertEqual(self.tc.get("/api/progress/", {"student_id":self.student.student_id}).status_code, 200)
