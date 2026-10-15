"""Saved assessments survive refresh without accepting duplicate graded work."""
import uuid
from datetime import timedelta

from django.utils import timezone

from .models import AssessmentSession, Course, CourseTopic, LearningEvidence, PracticeAttempt, PracticeQuestion
from .test_classrooms import ClassroomFixture


class AssessmentRecoveryTests(ClassroomFixture):
    def setUp(self):
        super().setUp()
        self.join()
        self.course = Course.objects.create(classroom=self.room, name="Recovery fixture")
        self.topic = CourseTopic.objects.create(course=self.course, name="Pointers")
        self.session = AssessmentSession.objects.create(course=self.course, student=self.student.student)
        self.question = self.make_question(self.session)

    def make_question(self, assessment=None):
        return PracticeQuestion.objects.create(student=self.student.student, topic=self.topic,
            assessment=assessment, kind="quiz", prompt="Which pointer refers to the first node?",
            options=["Head", "Tail"], answer={"correct_index": 0}, explanation="Head refers to the first node.")

    def submit(self, answer="0", request_id=None, question=None):
        return self.post(self.sc, f"learning/questions/{(question or self.question).id}/attempts/",
            {"request_id": request_id or str(uuid.uuid4()), "answer": answer})

    def report(self, client=None):
        return (client or self.sc).get(f"/api/learning/assessments/{self.session.id}/")

    def test_reopening_saved_assessment_restores_answer_and_feedback_only_to_owner(self):
        saved = self.submit().json()["attempt"]
        response = self.report()
        self.assertEqual(response.status_code, 200)
        assessment = response.json()["assessment"]
        self.assertIn("attempts", assessment)
        restored = assessment["attempts"][0]
        self.assertEqual(restored["id"], saved["id"])
        self.assertEqual(restored["question_id"], self.question.id)
        self.assertEqual(restored["answer"], "0")
        self.assertEqual(restored["feedback"], saved["feedback"])
        self.assertNotIn("correct_index", assessment["questions"][0])
        self.assertNotIn("answer", assessment["questions"][0])
        self.assertEqual(self.report(self.oc).status_code, 404)
        self.assertEqual(self.report(self.tc2).status_code, 404)
        self.assertEqual(self.report(self.tc).json()["assessment"]["attempts"][0]["id"], saved["id"])

    def test_opening_report_preserves_the_original_completion_time(self):
        self.submit()
        completed = timezone.now() - timedelta(minutes=20)
        AssessmentSession.objects.filter(pk=self.session.pk).update(completed_at=completed)
        self.report()
        self.report()
        self.session.refresh_from_db()
        self.assertEqual(self.session.completed_at, completed)

    def test_report_response_uses_the_completion_status_it_just_computed(self):
        PracticeAttempt.objects.create(question=self.question, request_id=str(uuid.uuid4()),
            answer="0", score=100, status="completed")
        self.assertEqual(self.report().json()["assessment"]["status"], "completed")

    def test_refresh_cannot_extend_the_offline_activity_sync_window(self):
        self.submit()
        completed = timezone.now() - timedelta(minutes=20)
        AssessmentSession.objects.filter(pk=self.session.pk).update(
            created_at=completed - timedelta(minutes=5), completed_at=completed)
        self.report()
        response = self.post(self.sc, f"learning/assessments/{self.session.id}/activity-events/", {
            "events": [{"event_id": "old-offline-event", "kind": "tab_hidden",
                "detail": {"observed_at": (completed - timedelta(seconds=1)).isoformat()}}]})
        self.assertEqual(response.status_code, 409)
        self.assertFalse(self.session.camera_events.exists())

    def test_completed_assessment_rejects_new_request_ids_without_more_evidence(self):
        self.submit("1")
        response = self.submit("0")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.question.attempts.count(), 1)
        self.assertEqual(LearningEvidence.objects.filter(topic=self.topic).count(), 1)
        self.assertEqual(self.report().json()["assessment"]["report"]["score"], 0)

    def test_answered_question_is_locked_while_other_questions_remain(self):
        self.make_question(self.session)
        self.submit("1")
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "in_progress")
        self.assertEqual(self.submit("0").status_code, 409)
        self.assertEqual(self.question.attempts.count(), 1)

    def test_processing_assessment_answer_cannot_start_a_second_runner(self):
        PracticeAttempt.objects.create(question=self.question, request_id=str(uuid.uuid4()), answer="1")
        self.assertEqual(self.submit("0").status_code, 409)
        self.assertEqual(self.question.attempts.count(), 1)
        self.assertFalse(LearningEvidence.objects.filter(topic=self.topic).exists())

    def test_same_request_replay_is_safe_but_cannot_change_saved_payload(self):
        request_id = str(uuid.uuid4())
        saved = self.submit("1", request_id).json()["attempt"]
        replay = self.submit("1", request_id)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json()["attempt"]["id"], saved["id"])
        self.assertEqual(self.submit("0", request_id).status_code, 409)
        self.assertEqual(self.question.attempts.count(), 1)

    def test_failed_assessment_work_can_be_corrected_and_practice_retests_still_work(self):
        failed = self.submit("not-an-option")
        self.assertEqual(failed.status_code, 400)
        self.assertEqual(failed.json()["attempt"]["status"], "failed")
        self.assertEqual(self.submit("0").status_code, 200)
        practice = self.make_question()
        self.assertEqual(self.submit("1", question=practice).status_code, 200)
        self.assertEqual(self.submit("0", question=practice).status_code, 200)
        self.assertEqual(practice.attempts.count(), 2)
