import uuid

from django.test import Client

from .test_classrooms import ClassroomFixture
from .models import (Course, CourseTopic, AssessmentSession, AssessmentCameraEvent, PracticeQuestion,
                     CourseMaterial, SourceUnit, SourceChunk, LearningEvidence, TopicMastery, Assignment)
from .learning.mastery import record_evidence


class AssessmentCameraTests(ClassroomFixture):
    def setUp(self):
        super().setUp(); self.join()
        self.course = Course.objects.create(classroom=self.room, name="Camera course")
        self.topic = CourseTopic.objects.create(course=self.course, name="Linked Lists")
        self.assessment = AssessmentSession.objects.create(course=self.course, student=self.student.student)
        material = CourseMaterial.objects.create(course=self.course, uploaded_by=self.teacher, title="Teacher notes",
            filename="notes.pdf", file="test-only.pdf", kind="pdf", status="ready")
        unit = SourceUnit.objects.create(material=material, number=1, page_number=23, text="Head points to the first node.")
        chunk = SourceChunk.objects.create(course=self.course, unit=unit, text=unit.text, position=0)
        self.question = PracticeQuestion.objects.create(student=self.student.student, topic=self.topic, assessment=self.assessment,
            kind="quiz", difficulty=1, prompt="Which pointer refers to the first node?", source_ids=[chunk.id],
            options=["head", "tail"], answer={"correct_index": 0}, tests=[{"expected": "PRIVATE HIDDEN VALUE"}],
            solution="PRIVATE SOLUTION", rubric=["PRIVATE RUBRIC"], reason="Diagnostic")
        self.route = f"learning/assessments/{self.assessment.id}/camera-events/"

    def event(self, kind, detail=None, **extra):
        return {"event_id": str(uuid.uuid4()), "kind": kind, "question_id": self.question.id, "detail": detail or {}, **extra}

    def send(self, *items, client=None):
        return self.post(client or self.sc, self.route, {"events": list(items)})

    def start(self, **settings):
        return self.send(self.event("camera_started", {"consent": True, "analysis_enabled": True, **settings}))

    def cue(self, **detail):
        return self.event("camera_cue", {"reason": "head_turned", "duration_ms": 8500, **detail})

    def test_camera_off_until_explicit_consent_and_event_gate(self):
        self.assertEqual(self.send(self.event("camera_started")).status_code, 400)
        self.assertEqual(self.send(self.cue()).status_code, 409)
        self.assertEqual(AssessmentCameraEvent.objects.count(), 0)
        self.assertEqual(self.start().status_code, 200)
        self.assertEqual(self.send(self.cue()).status_code, 200)

    def test_classroom_student_teacher_and_anonymous_isolation(self):
        self.start()
        self.assertEqual(Client().get("/api/" + self.route).status_code, 401)
        self.assertEqual(self.oc.get("/api/" + self.route).status_code, 404)
        self.assertEqual(self.tc2.get("/api/" + self.route).status_code, 404)
        self.assertEqual(self.send(self.cue(), client=self.tc).status_code, 403)
        self.post(self.oc, "classrooms/join/", {"code": self.room.join_code})
        self.assertEqual(self.oc.get("/api/" + self.route).status_code, 403)
        self.assertEqual(self.send(self.cue(), client=self.oc).status_code, 403)
        self.assertEqual(self.tc.get("/api/" + self.route).status_code, 200)
        self.assertEqual(self.tc2.get(f"/api/learning/courses/{self.course.id}/assessment-activity/").status_code, 404)

    def test_removal_revokes_timelines_signals_and_responses(self):
        self.start(); row = self.send(self.cue()).json()["events"][0]
        self.tc.delete(f"/api/classrooms/{self.room.id}/students/{self.student.student_id}/")
        self.assertEqual(self.sc.get("/api/" + self.route).status_code, 404)
        self.assertEqual(self.send(self.cue()).status_code, 404)
        self.assertEqual(self.post(self.sc, f"learning/assessment-camera/events/{row['id']}/response/", {"answer": "My reasoning"}).status_code, 404)
        self.assertEqual(self.tc.get("/api/" + self.route).status_code, 404)
        self.assertEqual(self.tc.get(f"/api/learning/courses/{self.course.id}/assessment-activity/").json()["assessments"], [])

    def test_only_minimal_metadata_is_saved_and_keys_are_private(self):
        self.start()
        response = self.send(self.cue(frame="data:image/png;base64,PRIVATE", landmarks=[1, 2, 3],
                                      clipboard="PRIVATE CLIPBOARD", visited_url="https://private.invalid", cheating=True)).json()
        serialized = str(response)
        for private in ("PRIVATE", "landmarks", "clipboard", "visited_url", "cheating", "correct_index", "rubric", "solution"):
            self.assertNotIn(private, serialized)
        row = response["events"][0]
        self.assertEqual(row["detail"]["verification"]["resources"][0]["page_number"], 23)
        self.assertEqual(row["detail"]["method"], "on_device_head_pose_heuristic")

    def test_camera_observations_and_optional_explanations_do_not_grade(self):
        record_evidence(self.student.student, self.topic, "initial-assessment", "quiz", 75)
        before = list(TopicMastery.objects.values()); count = LearningEvidence.objects.count()
        self.start(); response = self.send(self.cue()).json()["events"][0]
        result = self.post(self.sc, f"learning/assessment-camera/events/{response['id']}/response/", {"answer": "I followed the chain of nodes.", "score": 100})
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.json()["event"]["detail"]["verification"]["non_scored"])
        self.assertEqual(result.json()["event"]["detail"]["verification"]["status"], "answered")
        self.assertEqual(list(TopicMastery.objects.values()), before)
        self.assertEqual(LearningEvidence.objects.count(), count)
        self.assertFalse(self.question.attempts.exists())
        self.assessment.refresh_from_db(); self.assertEqual(self.assessment.status, "in_progress")

    def test_eye_closure_requires_teacher_and_student_choice(self):
        self.start(allow_eye_closure=True)
        first = self.send(self.cue()).json()["events"][0]
        self.assertFalse(first["detail"]["verification"]["offer_eye_closure"])
        self.course.camera_eye_closure = True; self.course.save()
        self.send(self.event("camera_stopped")); self.start(allow_eye_closure=False)
        second = self.send(self.cue()).json()["events"][0]
        self.assertFalse(second["detail"]["verification"]["offer_eye_closure"])
        self.send(self.event("camera_stopped")); self.start(allow_eye_closure=True)
        third = self.send(self.cue()).json()["events"][0]
        self.assertTrue(third["detail"]["verification"]["offer_eye_closure"])
        result = self.post(self.sc, f"learning/assessment-camera/events/{third['id']}/response/", {"action": "dismiss"})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["event"]["detail"]["verification"]["status"], "dismissed")

    def test_invalid_and_cross_assessment_events_roll_back(self):
        self.start(); before = AssessmentCameraEvent.objects.count()
        self.assertEqual(self.send(self.cue(duration_ms=1000)).status_code, 400)
        self.assertEqual(self.send(self.cue(reason="cheating")).status_code, 400)
        other = AssessmentSession.objects.create(course=self.course, student=self.student.student)
        q = PracticeQuestion.objects.create(student=self.student.student, topic=self.topic, assessment=other, kind="quiz", prompt="Another question", reason="Diagnostic")
        self.assertEqual(self.send(self.cue(), self.event("camera_cue", {"reason": "face_absent", "duration_ms": 9000}, question_id=q.id)).status_code, 400)
        self.assertEqual(AssessmentCameraEvent.objects.count(), before)
        self.assertEqual(self.send(self.cue(consent="true")).status_code, 400)

    def test_idempotent_signals_and_response_ownership(self):
        self.start(); item = self.cue()
        row = self.send(item).json()["events"][0]
        self.assertEqual(self.send(item).json()["events"][0]["id"], row["id"])
        route = f"learning/assessment-camera/events/{row['id']}/response/"
        self.assertEqual(self.post(self.oc, route, {"answer": "Another student"}).status_code, 404)
        self.assertEqual(self.post(self.tc, route, {"answer": "A teacher"}).status_code, 403)
        for _ in range(2): self.assertEqual(self.post(self.sc, route, {"answer": "My explanation"}).status_code, 200)
        self.assertEqual(self.post(self.sc, route, {"answer": "Changed explanation"}).status_code, 409)
        self.assertEqual(AssessmentCameraEvent.objects.filter(kind="camera_cue").count(), 1)

    def test_teacher_can_disable_analysis_without_blocking_assessment(self):
        response = self.tc.patch(f"/api/learning/courses/{self.course.id}/", '{"camera_cues_enabled": false}', content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["course"]["camera_policy"]["enabled"])
        self.assertEqual(self.start().status_code, 409)
        self.assertEqual(self.send(self.event("camera_started", {"consent": True, "analysis_enabled": False})).status_code, 200)
        self.assertEqual(self.send(self.cue()).status_code, 409)
        self.assertEqual(self.sc.get(f"/api/learning/assessments/{self.assessment.id}/").status_code, 200)
        self.assertEqual(self.sc.patch(f"/api/learning/courses/{self.course.id}/", '{"camera_cues_enabled": true}', content_type="application/json").status_code, 403)

    def test_stop_completion_and_disabled_verification(self):
        self.start(); self.send(self.event("camera_stopped"))
        self.assertEqual(self.send(self.cue()).status_code, 409)
        self.course.activity_verification = False; self.course.save(); self.start()
        row = self.send(self.cue()).json()["events"][0]
        self.assertNotIn("verification", row["detail"])
        self.assessment.status = "completed"; self.assessment.save()
        self.assertEqual(self.send(self.cue()).status_code, 409)
        self.assertEqual(self.send(self.event("camera_stopped")).status_code, 200)

    def test_teacher_evidence_summary_contains_saved_explanations(self):
        self.start(); row = self.send(self.cue()).json()["events"][0]
        self.post(self.sc, f"learning/assessment-camera/events/{row['id']}/response/", {"answer": "Follow each node link."})
        data = self.tc.get(f"/api/learning/courses/{self.course.id}/assessment-activity/").json()
        self.assertEqual(data["assessments"][0]["summary"]["counts"]["camera_cue"], 1)
        self.assertEqual(data["assessments"][0]["summary"]["verification_answers"], 1)
        self.assertIn("not proof", data["interpretation"])
        self.assertEqual(self.tc.get("/api/" + self.route).json()["events"][-1]["detail"]["verification"]["answer"], "Follow each node link.")

    def test_existing_assignment_camera_cues_are_private_review_only(self):
        assignment = Assignment.objects.create(classroom=self.room, title="Code", instructions="Print a value", require_camera=False, tests=[{"input": "", "expected": "5"}])
        attempt = self.post(self.sc, f"assignments/{assignment.id}/attempts/", {}).json()["attempt"]
        response = self.post(self.sc, f"attempts/{attempt['id']}/events/", {"events": [
            {"event_id": "local-analysis", "kind": "camera_analysis_started", "stage": "coding", "detail": {"consent": True, "analysis_enabled": True}},
            {"event_id": "local-cue", "kind": "camera_cue", "stage": "coding", "detail": {"reason": "head_turned", "duration_ms": 8000, "image": "PRIVATE IMAGE"}}]})
        self.assertEqual(response.status_code, 200, response.content)
        events = self.tc.get(f"/api/attempts/{attempt['id']}/events/").json()["events"]
        self.assertEqual(events[0]["kind"], "camera_analysis_started")
        self.assertTrue(events[0]["detail"]["consent"])
        self.assertEqual(events[1]["detail"]["reason"], "head_turned")
        self.assertNotIn("image", events[1]["detail"])
        self.assertEqual(LearningEvidence.objects.count(), 0)
