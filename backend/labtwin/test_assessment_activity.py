"""Regression tests for student-visible tab-change and paste counters.

Browser observations are metadata, not cheating determinations or grades.
"""
import uuid
from datetime import timedelta
from django.test import Client
from django.utils import timezone
from .test_classrooms import ClassroomFixture
from .models import Course, AssessmentSession, AssessmentCameraEvent, LearningEvidence, TopicMastery


class AssessmentBrowserActivityTests(ClassroomFixture):
    def setUp(self):
        super().setUp()
        self.join()
        self.course = Course.objects.create(classroom=self.room, name="Student test course")
        self.assessment = AssessmentSession.objects.create(course=self.course, student=self.student.student)
        self.url = f"learning/assessments/{self.assessment.id}/activity-events/"

    def event(self, kind, **detail):
        return {"event_id": str(uuid.uuid4()), "kind": kind, "detail": detail}

    def test_camera_off_can_record_activity_and_not_grade(self):
        tab = self.event("tab_hidden", visited_url="https://private.invalid", cheating=True)
        pasted = self.event("paste_blocked", characters=14, clipboard="PRIVATE ANSWER")
        response = self.post(self.sc, self.url, {"events": [tab, pasted]})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["tab_switches"], 1)
        self.assertEqual(response.json()["blocked_pastes"], 1)
        self.assertNotIn("PRIVATE ANSWER", response.content.decode())
        self.assertNotIn("private.invalid", response.content.decode())
        self.assertNotIn("cheating", response.content.decode())
        self.assertEqual(AssessmentCameraEvent.objects.count(), 2)
        self.assertEqual(LearningEvidence.objects.count(), 0)
        self.assertEqual(TopicMastery.objects.count(), 0)
        self.assertEqual(self.assessment.status, "in_progress")

    def test_duplicate_events_are_not_double_counted(self):
        item = self.event("tab_hidden")
        for _ in range(2):
            response = self.post(self.sc, self.url, {"events": [item]})
            self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tab_switches"], 1)
        self.assertEqual(AssessmentCameraEvent.objects.count(), 1)
        self.assertEqual(self.sc.get("/api/" + self.url).json()["tab_switches"], 1)

    def test_other_students_and_teachers_cannot_submit_observations(self):
        item = self.event("tab_hidden")
        self.assertEqual(self.post(Client(), self.url, {"events": [item]}).status_code, 401)
        self.assertEqual(self.post(self.oc, self.url, {"events": [item]}).status_code, 404)
        self.assertEqual(self.post(self.tc, self.url, {"events": [item]}).status_code, 403)
        self.assertEqual(self.tc2.get("/api/" + self.url).status_code, 404)
        self.assertEqual(self.tc.get("/api/" + self.url).status_code, 200)
        self.assertEqual(AssessmentCameraEvent.objects.count(), 0)

    def test_camera_or_arbitrary_activity_kinds_are_rejected(self):
        for kind in ("camera_started", "cheating_confirmed", "page_return", "clipboard_text"):
            self.assertEqual(self.post(self.sc, self.url, {"events": [self.event(kind)]}).status_code, 400)
        self.assertEqual(AssessmentCameraEvent.objects.count(), 0)

    def test_teacher_review_shows_count_but_not_cheating_verdict(self):
        self.post(self.sc, self.url, {"events": [self.event("tab_hidden"), self.event("paste_blocked", characters=2)]})
        report = self.tc.get(f"/api/learning/courses/{self.course.id}/assessment-activity/").json()
        summary = report["assessments"][0]["summary"]
        self.assertEqual(summary["tab_switches"], 1)
        self.assertEqual(summary["blocked_pastes"], 1)
        self.assertIn("not proof", summary["interpretation"])
        self.assertNotIn("cheating", str(report).lower())

    def test_completed_assessment_does_not_accept_new_activity(self):
        self.assessment.status = "completed"
        self.assessment.save(update_fields=["status"])
        result = self.post(self.sc, self.url, {"events": [self.event("tab_hidden")]})
        self.assertEqual(result.status_code, 409)
        self.assertEqual(AssessmentCameraEvent.objects.count(), 0)

    def test_focus_changes_are_distinct_from_tab_departures(self):
        response = self.post(self.sc, self.url, {"events": [self.event("window_blur"), self.event("window_focus"), self.event("tab_hidden")]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["focus_losses"], 1)
        self.assertEqual(response.json()["focus_returns"], 1)
        self.assertEqual(response.json()["tab_switches"], 1)
        summary = self.tc.get(f"/api/learning/courses/{self.course.id}/assessment-activity/").json()["assessments"][0]["summary"]
        self.assertEqual(summary["focus_losses"], 1)

    def test_allowed_paste_does_not_require_camera_or_expose_content(self):
        response = self.post(self.sc, self.url, {"events": [self.event("paste_allowed", characters=17, clipboard="sensitive contents")]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["allowed_pastes"], 1)
        self.assertEqual(response.json()["blocked_pastes"], 0)
        self.assertNotIn("sensitive contents", response.content.decode())
        self.assertFalse(LearningEvidence.objects.exists())
        self.assertFalse(TopicMastery.objects.exists())

    def complete(self, minutes_ago=0):
        self.assessment.created_at = timezone.now() - timedelta(minutes=20)
        self.assessment.completed_at = timezone.now() - timedelta(minutes=minutes_ago)
        self.assessment.status = "completed"
        self.assessment.save(update_fields=["created_at", "completed_at", "status"])

    def test_offline_precompletion_events_can_sync_briefly_after_submission(self):
        self.complete()
        item = self.event("tab_hidden", observed_at=(self.assessment.completed_at - timedelta(seconds=2)).isoformat())
        for _ in range(2):
            response = self.post(self.sc, self.url, {"events": [item]})
            self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["tab_switches"], 1)
        self.assertFalse(LearningEvidence.objects.exists())

    def test_late_events_cannot_reopen_assessment_or_extend_sync_window(self):
        self.complete()
        for observed in (self.assessment.completed_at + timedelta(seconds=1), self.assessment.created_at - timedelta(seconds=1)):
            self.assertEqual(self.post(self.sc, self.url, {"events": [self.event("tab_hidden", observed_at=observed.isoformat())]}).status_code, 409)
        self.complete(minutes_ago=16)
        self.assertEqual(self.post(self.sc, self.url, {"events": [self.event("tab_hidden", observed_at=(self.assessment.completed_at - timedelta(seconds=1)).isoformat())]}).status_code, 409)
        self.assertFalse(AssessmentCameraEvent.objects.exists())

    def test_idempotent_replay_succeeds_at_event_limit(self):
        AssessmentCameraEvent.objects.bulk_create([AssessmentCameraEvent(assessment=self.assessment, event_id=f"saved-{i}", kind="tab_hidden") for i in range(2000)])
        response = self.post(self.sc, self.url, {"events": [{"event_id": "saved-0", "kind": "tab_hidden"}]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tab_switches"], 2000)
        self.assertEqual(self.post(self.sc, self.url, {"events": [self.event("tab_hidden")]}).status_code, 409)
        self.assertEqual(AssessmentCameraEvent.objects.count(), 2000)
