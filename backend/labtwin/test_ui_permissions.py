"""UI role gating complements, and never replaces, real endpoint authorization."""
import tempfile
import uuid
from unittest.mock import patch

from django.test import Client, override_settings

from .test_classrooms import ClassroomFixture
from .models import (Course, CourseTopic, CourseMaterial, SourceUnit, SourceChunk,
                     QuestionBankItem, TopicMastery, LearningEvidence, PracticeAttempt)
from .learning.rag import grounded_answer


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class TutorUIPermissionsTests(ClassroomFixture):
    def setUp(self):
        super().setUp()
        self.join()
        self.files = tempfile.TemporaryDirectory(prefix="labtwin-ui-tests-")
        self.addCleanup(self.files.cleanup)
        self.enterContext(override_settings(LABTWIN_MEDIA_ROOT=self.files.name,
                                           LABTWIN_VECTOR_ROOT=self.files.name + "/vectors"))
        self.course = Course.objects.create(classroom=self.room, name="Java OOP", language="Java")
        self.topic = CourseTopic.objects.create(course=self.course, name="Dynamic Method Dispatch")
        self.material = CourseMaterial.objects.create(
            course=self.course, topic=self.topic, uploaded_by=self.teacher,
            title="Java OOP Notes", filename="java.pdf", file="test-only/java.pdf",
            kind="pdf", status="ready", sha256="a" * 64)
        self.text = "Dynamic method dispatch selects an overridden method at runtime using the actual object."
        self.unit = SourceUnit.objects.create(material=self.material, number=6, page_number=6,
                                              topic_name=self.topic.name, text=self.text)
        self.chunk = SourceChunk.objects.create(unit=self.unit, course=self.course,
                                               position=0, text=self.text, embedding_model="test-only")
        self.ask_route = f"learning/courses/{self.course.id}/ask/"

    def ask(self, client):
        with patch("labtwin.learning.rag.retrieve", return_value=[{"chunk": self.chunk, "score": 1}]):
            response = self.post(client, self.ask_route, {"question": "Dynamic method dispatch"})
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_teacher_can_ask_and_open_page_six_but_cannot_take_a_student_check(self):
        answer = self.ask(self.tc)
        self.assertTrue(answer["grounded"])
        self.assertEqual(answer["mode"], "source_excerpts")
        self.assertEqual(answer["citations"][0]["page_number"], 6)
        self.assertEqual(answer["citations"][0]["href"], f"#source={self.chunk.id}")
        source = self.tc.get(f"/api/learning/sources/{self.chunk.id}/")
        self.assertEqual(source.status_code, 200)
        self.assertEqual(source.json()["source"]["page_number"], 6)
        check = self.post(self.tc, f"learning/exchanges/{answer['id']}/check/", {})
        self.assertEqual(check.status_code, 403)
        self.assertEqual(check.json()["error"], "This action belongs to the signed-in student.")
        self.assertFalse(PracticeAttempt.objects.exists())

    def test_student_check_feedback_and_mastery_persist_without_duplicate_evidence(self):
        QuestionBankItem.objects.create(topic=self.topic, title="Dispatch timing",
            kind="short_answer", prompt="When does dynamic method dispatch select an overridden method?",
            answer={"accepted": ["runtime"]}, source_ids=[self.chunk.id],
            explanation="The actual object determines the overridden method at runtime.")
        answer = self.ask(self.sc)
        self.assertEqual(TopicMastery.objects.get(student=self.student.student, topic=self.topic).attempts, 0)
        check = self.post(self.sc, f"learning/exchanges/{answer['id']}/check/", {})
        self.assertEqual(check.status_code, 201, check.content)
        question = check.json()["question"]
        route = f"learning/questions/{question['id']}/attempts/"
        payload = {"request_id": str(uuid.uuid4()), "answer": "runtime"}
        first = self.post(self.sc, route, payload)
        self.assertEqual(first.status_code, 200, first.content)
        attempt = first.json()["attempt"]
        self.assertEqual(attempt["score"], 100)
        self.assertEqual(attempt["feedback"]["resources"][0]["page_number"], 6)
        score = TopicMastery.objects.get(student=self.student.student, topic=self.topic).score
        again = self.post(self.sc, route, payload)
        self.assertEqual(again.status_code, 200, again.content)
        self.assertEqual(again.json()["attempt"]["id"], attempt["id"])
        self.assertEqual(LearningEvidence.objects.filter(student=self.student.student, kind="conversation", score=100).count(), 1)
        self.assertEqual(TopicMastery.objects.get(student=self.student.student, topic=self.topic).score, score)
        saved = self.sc.get("/api/" + route)
        self.assertEqual(saved.json()["attempts"][0]["score"], 100)

    def test_teacher_and_foreign_students_cannot_submit_student_attempts(self):
        from .models import PracticeQuestion
        question = PracticeQuestion.objects.create(student=self.student.student, topic=self.topic,
            kind="short_answer", difficulty=1, prompt="Dispatch timing?", language="Java",
            answer={"accepted": ["runtime"]}, reason="Test-only question")
        route = f"learning/questions/{question.id}/attempts/"
        for client, status in [(self.tc, 403), (self.oc, 404), (Client(), 401)]:
            with self.subTest(status=status):
                response = self.post(client, route, {"request_id": str(uuid.uuid4()), "answer": "runtime"})
                self.assertEqual(response.status_code, status)
        self.assertFalse(PracticeAttempt.objects.exists())

    def test_sources_and_history_keep_classroom_and_account_isolation(self):
        answer = self.ask(self.sc)
        self.assertEqual(self.post(self.oc, f"learning/exchanges/{answer['id']}/check/", {}).status_code, 404)
        self.assertEqual(self.tc.get("/api/" + self.ask_route + "history/").json()["questions"], [])
        for client in [self.oc, self.tc2]:
            self.assertEqual(self.post(client, self.ask_route, {"question": "Dynamic method dispatch"}).status_code, 404)
            self.assertEqual(client.get(f"/api/learning/sources/{self.chunk.id}/").status_code, 404)

    def test_ai_explanation_excerpts_and_unsupported_modes_keep_real_citations(self):
        valid = {"supported": True, "claims": [{"text": "Selection happens at runtime.",
                 "source_id": self.chunk.id, "quote": "selects an overridden method at runtime"}]}
        cases = [(None, "source_excerpts", True), (valid, "ai_grounded", True),
                 ({"supported": True, "claims": [{"text": "Unverified", "source_id": 999999,
                                                "quote": "selects an overridden method at runtime"}]},
                  "source_excerpts", True),
                 ({"supported": False}, "insufficient_sources", False)]
        for generated, mode, grounded in cases:
            with self.subTest(mode=mode), patch("labtwin.learning.rag.retrieve", return_value=[{"chunk": self.chunk, "score": 1}]), patch("labtwin.learning.rag.structured_completion", return_value=generated):
                result = grounded_answer(self.course, "Dynamic method dispatch")
                self.assertEqual(result["mode"], mode)
                self.assertEqual(result["grounded"], grounded)
                self.assertEqual([c["id"] for c in result["citations"]], [self.chunk.id] if grounded else [])
                if grounded:
                    self.assertEqual(result["citations"][0]["page_number"], 6)

    def test_demo_fallback_is_deliberate_and_does_not_call_remote_ai(self):
        self.course.is_demo = True
        with patch("labtwin.learning.rag.retrieve", return_value=[{"chunk": self.chunk, "score": 1}]), patch("labtwin.learning.rag.structured_completion") as remote:
            result = grounded_answer(self.course, "Dynamic method dispatch")
        remote.assert_not_called()
        self.assertEqual(result["mode"], "source_excerpts")
