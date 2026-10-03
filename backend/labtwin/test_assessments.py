from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone

from .models import Assignment, AssignmentAttempt, Enrollment, LiveConnection, LiveSession, MonitoringEvent
from .test_classrooms import ClassroomFixture


class AssessmentTests(ClassroomFixture):
    def setUp(self):
        super().setUp()
        self.join()
        self.assignment = Assignment.objects.create(classroom=self.room, title="Add", instructions="Add two inputs",
            tests=[{"input": "2\n3", "expected": "5"}], require_camera=False)

    def start(self):
        response = self.post(self.sc, f"assignments/{self.assignment.id}/attempts/", {})
        return response.json()["attempt"]["id"]

    def test_teacher_assignment_policy_and_tests_are_hidden_from_students(self):
        payload = {"title":"C lab", "instructions":"Add", "language":"C", "tests":[{"input":"5", "expected":"10"}], "allow_paste":False, "require_screen":True, "require_camera":True}
        response = self.post(self.tc, f"classrooms/{self.room.id}/assignments/", payload)
        self.assertEqual(response.status_code, 201, response.content)
        item = response.json()["assignment"]
        self.assertFalse(item["allow_paste"])
        student = self.sc.get(f"/api/classrooms/{self.room.id}/assignments/").json()["assignments"][0]
        self.assertNotIn("tests", student)
        self.assertEqual(self.post(self.sc, f"classrooms/{self.room.id}/assignments/", payload).status_code, 403)
        self.assertEqual(self.tc2.get(f"/api/classrooms/{self.room.id}/assignments/").status_code, 404)

    def test_start_resume_and_drafts_are_bound_to_the_enrolled_student(self):
        attempt_id = self.start()
        self.assertEqual(self.start(), attempt_id)
        response = self.sc.patch(f"/api/attempts/{attempt_id}/", {"code":"print(5)", "viva_answer":"I add"}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.sc.get(f"/api/attempts/{attempt_id}/").json()["attempt"]["code"], "print(5)")
        self.assertEqual(self.oc.get(f"/api/attempts/{attempt_id}/").status_code, 404)
        self.assertEqual(self.post(self.tc, f"attempts/{attempt_id}/", {"code":"fake"}).status_code, 403)
        self.assertEqual(self.post(self.oc, f"assignments/{self.assignment.id}/attempts/", {}).status_code, 404)

    def test_server_evaluates_teacher_tests_and_keeps_previous_submissions(self):
        attempt_id = self.start()
        results = [{"test":1, "input":"secret input", "expected":"secret answer", "stdout":"5", "stderr":"", "passed":True, "success":True}]
        with patch.object(self.fake_views, "run_tests", return_value=(100, results), create=True) as runner:
            response = self.post(self.sc, f"attempts/{attempt_id}/", {"code":"print(5)\n", "viva_answer":"Add the values", "test_score":0})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["attempt"]["test_score"], 100)
        self.assertNotIn("expected", response.json()["attempt"]["test_results"][0])
        runner.assert_called_once_with("print(5)\n", self.assignment.tests, "Python")
        self.assertEqual(self.post(self.sc, f"attempts/{attempt_id}/", {"code":"changed"}).status_code, 409)
        self.assertNotEqual(self.start(), attempt_id)
        self.assertEqual(AssignmentAttempt.objects.get(pk=attempt_id).code, "print(5)\n")

    def test_failed_execution_retains_response(self):
        attempt_id = self.start()
        with patch.object(self.fake_views, "run_tests", side_effect=RuntimeError(), create=True):
            response = self.post(self.sc, f"attempts/{attempt_id}/", {"code":"bad code", "viva_answer":"My explanation"})
        self.assertEqual(response.json()["attempt"]["status"], "failed")
        self.assertEqual(AssignmentAttempt.objects.get(pk=attempt_id).viva_answer, "My explanation")

    def test_student_submission_history_keeps_feedback_and_hides_teacher_tests(self):
        attempt_id = self.start()
        attempt = AssignmentAttempt.objects.get(pk=attempt_id)
        attempt.status, attempt.teacher_score, attempt.teacher_feedback = "submitted", 92, "Clear explanation"
        attempt.test_results = [{"test": 1, "input": "private", "expected": "secret", "stdout": "5", "passed": True}]
        attempt.save()
        response = self.sc.get(f"/api/assignments/{self.assignment.id}/submissions/")
        row = response.json()["submissions"][0]
        self.assertEqual(row["teacher_score"], 92)
        self.assertEqual(row["teacher_feedback"], "Clear explanation")
        self.assertNotIn("input", row["test_results"][0])
        self.assertNotIn("expected", row["test_results"][0])
        self.assertEqual(self.oc.get(f"/api/assignments/{self.assignment.id}/submissions/").status_code, 404)
        self.assertEqual(self.tc.get(f"/api/assignments/{self.assignment.id}/submissions/").status_code, 404)

    def test_required_camera_and_screen_and_stale_media_are_enforced(self):
        self.assignment.require_screen = self.assignment.require_camera = True; self.assignment.save()
        attempt_id = self.start()
        payload = {"code":"print(5)"}
        self.assertEqual(self.post(self.sc, f"attempts/{attempt_id}/", payload).status_code, 400)
        self.post(self.sc, f"attempts/{attempt_id}/live/", {"screen_active":True, "camera_active":True})
        LiveSession.objects.filter(attempt_id=attempt_id).update(last_seen=timezone.now()-timedelta(minutes=1))
        self.assertEqual(self.post(self.sc, f"attempts/{attempt_id}/", payload).status_code, 400)
        self.sc.patch(f"/api/attempts/{attempt_id}/live/", {"screen_active":True, "camera_active":True}, content_type="application/json")
        with patch.object(self.fake_views, "run_tests", return_value=(100, []), create=True):
            self.assertEqual(self.post(self.sc, f"attempts/{attempt_id}/", payload).status_code, 200)
        self.assertFalse(LiveSession.objects.get(attempt_id=attempt_id).active)

    def test_events_are_scoped_idempotent_and_never_store_clipboard_text(self):
        attempt_id = self.start()
        event = {"event_id":"a", "kind":"paste", "stage":"viva", "detail":{"characters":5, "clipboard":"secret", "url":"private"}}
        route = f"attempts/{attempt_id}/events/"
        self.assertEqual(self.post(self.sc, route, {"events":[event]}).status_code, 200)
        self.post(self.sc, route, {"events":[event]})
        self.assertEqual(MonitoringEvent.objects.count(), 1)
        self.assertEqual(MonitoringEvent.objects.get().detail, {"characters":5})
        self.assertEqual(self.post(self.tc, route, {"events":[event]}).status_code, 403)
        self.assertEqual(self.post(self.oc, route, {"events":[event]}).status_code, 404)
        self.assertEqual(self.post(self.sc, route, {"events":[{**event, "kind":"cheating_confirmed"}]}).status_code, 400)

    def test_reports_show_counts_and_grades_only_to_class_teacher(self):
        attempt_id = self.start()
        self.post(self.sc, f"attempts/{attempt_id}/events/", {"events":[{"event_id":"tab1", "kind":"page_hidden"}, {"event_id":"paste1", "kind":"paste_blocked"}]})
        row = AssignmentAttempt.objects.get(pk=attempt_id); row.status = "submitted"; row.save()
        self.assertEqual(self.post(self.tc2, f"attempts/{attempt_id}/grade/", {"score":90}).status_code, 404)
        self.assertEqual(self.post(self.sc, f"attempts/{attempt_id}/grade/", {"score":90}).status_code, 404)
        self.assertEqual(self.post(self.tc, f"attempts/{attempt_id}/grade/", {"score":90, "feedback":"Explain the loop"}).status_code, 200)
        self.assertEqual(self.post(self.tc, f"attempts/{attempt_id}/grade/", {"score":"nan"}).status_code, 400)
        report = self.tc.get(f"/api/classrooms/{self.room.id}/reports/").json()["reports"][0]
        self.assertEqual(report["event_counts"]["page_hidden"], 1)
        self.assertEqual(report["teacher_score"], 90)
        self.assertTrue(report["needs_review"])
        self.assertEqual(self.tc2.get(f"/api/classrooms/{self.room.id}/reports/").status_code, 404)
        self.assertEqual(self.sc.get(f"/api/classrooms/{self.room.id}/reports/").status_code, 404)

    def test_csv_export_escapes_formula_cells(self):
        self.student.student.name = '=HYPERLINK("x")'; self.student.student.save()
        self.start()
        csv = self.tc.get(f"/api/classrooms/{self.room.id}/reports/?format=csv").content.decode()
        self.assertIn("'=HYPERLINK", csv)

    def test_live_watch_signaling_roles_and_enrollment_revocation(self):
        attempt_id = self.start()
        response = self.post(self.sc, f"attempts/{attempt_id}/live/", {"screen_active":True, "camera_active":True})
        session_id = response.json()["session_id"]
        self.assertEqual(self.post(self.tc2, f"live/{session_id}/watch/", {}).status_code, 404)
        self.assertEqual(self.post(self.sc, f"live/{session_id}/watch/", {}).status_code, 404)
        connection = self.post(self.tc, f"live/{session_id}/watch/", {}).json()["connection_id"]
        self.assertEqual(self.post(self.tc, f"connections/{connection}/", {"offer":{"type":"offer", "sdp":"fake"}}).status_code, 400)
        self.assertEqual(self.post(self.sc, f"connections/{connection}/", {"offer":{"type":"offer", "sdp":"fake"}, "track_sources":{"screen1":"screen"}}).status_code, 200)
        self.assertEqual(self.post(self.tc, f"connections/{connection}/", {"answer":{"type":"answer", "sdp":"reply"}}).status_code, 200)
        self.post(self.sc, f"connections/{connection}/", {"candidate":{"candidate":"ice"}})
        signal = self.tc.get(f"/api/connections/{connection}/").json()
        self.assertEqual(signal["candidates"][0]["value"]["candidate"], "ice")
        self.assertEqual(self.sc.get(f"/api/connections/{connection}/").json()["candidates"], [])
        self.assertEqual(len(self.tc.get(f"/api/classrooms/{self.room.id}/live/").json()["sessions"]), 1)
        Enrollment.objects.filter(classroom=self.room, student=self.student.student).delete()
        self.assertEqual(self.tc.get(f"/api/connections/{connection}/").status_code, 404)

    def test_student_stopping_share_ends_teacher_connection(self):
        attempt_id = self.start()
        session_id = self.post(self.sc, f"attempts/{attempt_id}/live/", {"screen_active":True, "camera_active":False}).json()["session_id"]
        connection = self.post(self.tc, f"live/{session_id}/watch/", {}).json()["connection_id"]
        self.assertEqual(self.sc.delete(f"/api/attempts/{attempt_id}/live/").status_code, 200)
        self.assertEqual(self.tc.get(f"/api/connections/{connection}/").status_code, 410)
        self.assertFalse(LiveConnection.objects.get(pk=connection).active)

    def test_stopping_both_media_tracks_removes_live_session_and_ends_connection(self):
        attempt_id = self.start()
        session_id = self.post(self.sc, f"attempts/{attempt_id}/live/", {"screen_active":True, "camera_active":True}).json()["session_id"]
        connection = self.post(self.tc, f"live/{session_id}/watch/", {}).json()["connection_id"]
        response = self.sc.patch(f"/api/attempts/{attempt_id}/live/", {"screen_active":False, "camera_active":False}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.tc.get(f"/api/classrooms/{self.room.id}/live/").json()["sessions"], [])
        self.assertEqual(self.tc.get(f"/api/connections/{connection}/").status_code, 410)
