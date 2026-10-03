"""Critical Track D regressions, using real original multimodal fixtures."""
import io
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

from django.test import Client, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile

from .test_classrooms import ClassroomFixture
from .models import Course, CourseTopic, SourceChunk, SourceUnit, CourseMaterial, TopicMastery, LearningEvidence, QuestionBankItem, PracticeQuestion, EvaluationRun, Enrollment, MasterySnapshot
from .learning.mastery import record_evidence
from .learning.practice import generate_question, question_data, grade
from .learning.access import LearningError

ASSETS = Path(__file__).with_name("demo_assets")


class TrackDTests(ClassroomFixture):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.files = tempfile.TemporaryDirectory(prefix="labtwin-track-d-tests-")
        cls.learning_override = override_settings(LABTWIN_MEDIA_ROOT=cls.files.name + "/uploads", LABTWIN_VECTOR_ROOT=cls.files.name + "/vectors", LABTWIN_VIDEO_OCR=False)
        cls.learning_override.enable()
    @classmethod
    def tearDownClass(cls):
        cls.learning_override.disable()
        super().tearDownClass()
        cls.files.cleanup()
    def setUp(self):
        super().setUp(); self.join()
        self.course = Course.objects.create(classroom=self.room, name="Track D", is_demo=True)
        self.topic = CourseTopic.objects.create(course=self.course, name="Linked Lists")
    def upload(self, filename="concepts.txt", content=None, **extra):
        content = content if content is not None else b"Linked Lists\nThe head pointer is the reference to the first node. A linked list is a chain of nodes. The node count worked example is 3 + 4 = 7."
        response = self.tc.post(f"/api/learning/courses/{self.course.id}/materials/", {"file": SimpleUploadedFile(filename, content), "topic_id": self.topic.id, **extra})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["material"]["status"], "ready", response.content)
        return CourseMaterial.objects.get(pk=response.json()["material"]["id"])
    def submit(self, question, answer):
        return self.post(self.sc, f"learning/questions/{question.id}/attempts/", {"request_id": str(uuid.uuid4()), "answer": answer})

    def test_pdf_visual_relationships_and_authorized_image_media(self):
        self.upload("notes.pdf", (ASSETS / "Data-Structures-Notes.pdf").read_bytes())
        unit = SourceUnit.objects.get(content_type="visual")
        self.assertEqual(unit.page_number, 2)
        self.assertIn("new node points to previous head", unit.visual_description)
        self.assertEqual(unit.analysis_method, "native_geometry")
        chunk = unit.chunks.first()
        response = self.sc.get(f"/api/learning/sources/{chunk.id}/").json()
        image = response["visual_url"].replace("http://testserver", "")
        self.assertEqual(Client().get(image).status_code, 200)
        self.assertEqual(Client().get(image, HTTP_RANGE="bytes=0-9").status_code, 206)
        self.assertEqual(self.oc.get(f"/api/learning/sources/{chunk.id}/").status_code, 404)
        self.assertEqual(Client().get(f"/api/learning/materials/{unit.material_id}/visuals/{unit.id}/media/").status_code, 401)
        self.tc.delete(f"/api/classrooms/{self.room.id}/students/{self.student.student_id}/")
        self.assertEqual(Client().get(image).status_code, 404)

    def test_slide_diagram_retrieval_uses_edges_not_only_text(self):
        self.upload("nodes.pptx", (ASSETS / "Linked-Lists.pptx").read_bytes())
        answer = self.post(self.sc, f"learning/courses/{self.course.id}/ask/", {"question": "Explain the diagram on slide 2"}).json()
        self.assertTrue(answer["grounded"])
        self.assertIn("new node points to previous head", answer["answer"])
        self.assertTrue(all(c["content_type"] == "visual" and c["slide_number"] == 2 for c in answer["citations"]))
        self.assertEqual(len(SourceUnit.objects.get(content_type="visual").layout["analysis"]["graph"]["nodes"]), 4)

    def test_optional_vision_sends_actual_image_pixels_and_keeps_source(self):
        from PIL import Image
        from types import SimpleNamespace
        from .learning.visuals import interpret_image
        buffer = io.BytesIO(); Image.new("RGB", (10, 10), "green").save(buffer, format="PNG")
        result = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({"description": "A green block", "uncertainty": "No readable label"})))])
        with override_settings(LABTWIN_VISION_MODEL="configured-vision", LABTWIN_DISABLE_REMOTE_AI=False), patch.dict(os.environ, {"GROQ_API_KEY": "test-only"}), patch("groq.Groq") as provider:
            provider.return_value.chat.completions.create.return_value = result
            analysis = interpret_image(buffer.getvalue(), "Nearby source caption")
            payload = provider.return_value.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        self.assertTrue(payload[1]["image_url"]["url"].startswith("data:image/png;base64,iVBOR"))
        self.assertEqual(analysis["semantic_status"], "model_interpreted")

    def test_video_ingestion_automatically_reads_embedded_timestamps(self):
        material = self.upload("lecture.webm", (ASSETS / "Lecture-4.webm").read_bytes())
        self.assertEqual(material.transcript_origin, "embedded_captions")
        for row, expected in zip(material.transcript, [0, 10, 20, 30]):
            self.assertAlmostEqual(row["start"], expected, delta=.02)
        self.assertEqual(len(material.chapters), 4)
        self.assertAlmostEqual(material.units.last().start_seconds, 30, delta=.02)

    def test_auto_concepts_subtopics_and_source_supported_prerequisites(self):
        base = CourseTopic.objects.create(course=self.course, name="Variables")
        material = self.upload(content=b"Head update\nLinked Lists requires Variables. A pointer is a reference to a memory location.")
        self.topic.refresh_from_db()
        unit = material.units.get()
        self.assertEqual(unit.subtopic, "Head update")
        self.assertIn("A pointer", unit.concepts)
        self.assertIn(base.id, self.topic.prerequisites.values_list("id", flat=True))
        self.assertIn("Variables", unit.prerequisite_names)
        self.assertTrue(self.topic.taxonomy_evidence["prerequisites"][str(base.id)]["quote"])

    def test_verified_three_formats_and_private_keys(self):
        self.upload()
        for kind in ("quiz", "short_answer", "numerical"):
            question = generate_question(self.student.student, self.course, self.topic, kind)
            self.assertEqual(question.verification_status, "verified")
            data = question_data(question)
            self.assertTrue(data["resources"])
            for private in ("answer", "tests", "solution", "explanation", "support_quote"):
                self.assertNotIn(private, data)
            answer = question.answer.get("correct_index", question.answer.get("value", (question.answer.get("accepted") or [""])[0]))
            result = self.submit(question, str(answer))
            self.assertEqual(result.json()["attempt"]["score"], 100, result.content)
            self.assertTrue(result.json()["attempt"]["feedback"]["resources"])

    def test_arithmetic_is_checked_and_does_not_execute_code(self):
        from .learning.question_verification import arithmetic
        self.assertEqual(arithmetic("3 * (4 + 2)"), 18)
        for expression in ("__import__('os').system('touch /tmp/unwanted')", "2 ** 100000", "1/0"):
            with self.assertRaises((ValueError, ArithmeticError)):
                arithmetic(expression)

    def test_bad_generated_keys_sources_and_difficulty_are_rejected(self):
        from .learning.question_verification import verify
        self.upload(); source = SourceChunk.objects.first()
        base = {"kind": "quiz", "prompt": "Q", "options": [source.text, "No"], "answer": {"correct_index": 1}, "source_ids": [source.id], "difficulty": 1, "metadata": {"support_quote": source.text, "template": "verbatim_mcq"}}
        self.assertEqual(verify(base, self.course)["status"], "rejected")
        base["answer"]["correct_index"] = 0; base["source_ids"] = [99999]
        self.assertEqual(verify(base, self.course)["status"], "rejected")
        base["source_ids"] = [source.id]; base["difficulty"] = 3
        self.assertEqual(verify(base, self.course)["status"], "rejected")
        base["difficulty"] = 1
        for malformed in ({"options": "not a choice list"}, {"answer": None}, {"source_ids": [[source.id]]},
                          {"difficulty": True}, {"prompt": None}, {"metadata": {"support_quote": source.text, "template": []}}):
            with self.subTest(malformed=malformed):
                self.assertEqual(verify({**base, **malformed}, self.course)["status"], "rejected")

    def test_no_duplicate_bank_fallback_and_measured_repetition(self):
        from .learning.novelty import repetition_rate
        for options, index in [(["Head", "Tail"], 0), (["Tail", "Head"], 1)]:
            QuestionBankItem.objects.create(topic=self.topic, title="Q", prompt="Which pointer identifies the first node?", options=options, answer={"correct_index": index})
        question = generate_question(self.student.student, self.course, self.topic)
        with self.assertRaises(LearningError):
            generate_question(self.student.student, self.course, self.topic)
        duplicate = PracticeQuestion.objects.create(**{k: v for k, v in question.__dict__.items() if k not in ("_state", "id", "created_at")})
        measured = repetition_rate([question, duplicate])
        self.assertEqual(measured["rate"], .5)
        self.assertEqual(measured["repeated"], 1)

    def test_short_open_answer_is_pending_until_authorized_teacher_review(self):
        QuestionBankItem.objects.create(topic=self.topic, title="Explain", kind="short_answer", prompt="Explain why head must change last.", answer={"accepted": ["Preserve old chain"]})
        question = generate_question(self.student.student, self.course, self.topic, "short_answer")
        response = self.submit(question, "I would retain a link to every earlier node.")
        attempt = response.json()["attempt"]
        self.assertIsNone(attempt["score"])
        self.assertEqual(attempt["status"], "pending_review")
        self.assertEqual(TopicMastery.objects.get().attempts, 0)
        route = f"learning/practice-attempts/{attempt['id']}/review/"
        self.assertEqual(self.post(self.sc, route, {"score": 90}).status_code, 403)
        self.assertEqual(self.post(self.tc2, route, {"score": 90}).status_code, 404)
        self.assertEqual(self.post(self.tc, route, {"score": 90, "feedback": "Good reasoning"}).status_code, 200)
        self.assertEqual(self.post(self.tc, route, {"score": 90}).status_code, 409)
        self.assertEqual(TopicMastery.objects.get().attempts, 1)

    def test_diagnostic_scope_authorization_report_and_mastery(self):
        self.upload()
        route = f"learning/courses/{self.course.id}/assessments/"
        self.assertEqual(self.post(self.oc, route, {}).status_code, 404)
        self.assertEqual(self.post(self.tc, route, {}).status_code, 403)
        response = self.post(self.sc, route, {"kind": "diagnostic", "scope": {"topic_ids": [self.topic.id]}, "formats": ["quiz"], "count": 2})
        self.assertEqual(response.status_code, 201, response.content)
        session = response.json()["assessment"]
        self.assertTrue(all("Diagnostic" in q["reason"] for q in session["questions"]))
        self.assertEqual(self.oc.get(f"/api/learning/assessments/{session['id']}/").status_code, 404)
        for data in session["questions"]:
            question = PracticeQuestion.objects.get(pk=data["id"])
            self.submit(question, str(question.answer["correct_index"]))
        report = self.sc.get(f"/api/learning/assessments/{session['id']}/").json()["assessment"]
        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["report"]["score"], 100)
        self.assertEqual(report["report"]["question_repetition"]["rate"], 0)
        self.assertTrue(report["report"]["mastery_changes"])

    def test_cold_start_is_unknown_then_diagnostic_answers_differ(self):
        from .learning.mastery import mastery_data
        self.assertIsNone(mastery_data(self.student.student, self.topic)["knowledge_probability"])
        self.assertEqual(mastery_data(self.student.student, self.topic)["state"], "Not Started")
        high = record_evidence(self.student.student, self.topic, "diagnostic", "diagnostic", 100)
        low = record_evidence(self.other.student, self.topic, "diagnostic", "diagnostic", 0)
        self.assertGreater(high.knowledge_probability, low.knowledge_probability)

    def test_bkt_formula_and_assistance_reliability(self):
        from .learning.learner_model import update_probability, DEFAULT_PARAMETERS
        after, posterior = update_probability(.35, 1, DEFAULT_PARAMETERS)
        expected = .35 * .9 / (.35 * .9 + .65 * .15)
        self.assertAlmostEqual(posterior, expected)
        self.assertAlmostEqual(after, expected + (1 - expected) * .08)
        independent = record_evidence(self.student.student, self.topic, "a", "quiz", 100)
        assisted = record_evidence(self.other.student, self.topic, "a", "quiz", 100, hint_level=3, verified=False)
        self.assertGreater(independent.score, assisted.score)
        self.assertEqual(MasterySnapshot.objects.filter(student=self.student.student).get().evidence["model"], "bkt-reliability-v1")

    def test_conversation_reading_is_not_mastery_but_check_is_scored(self):
        self.upload()
        response = self.post(self.sc, f"learning/courses/{self.course.id}/ask/", {"question": "Explain linked lists"}).json()
        self.assertEqual(TopicMastery.objects.get().attempts, 0)
        self.assertEqual(self.post(self.oc, f"learning/exchanges/{response['id']}/check/", {}).status_code, 404)
        check = self.post(self.sc, f"learning/exchanges/{response['id']}/check/", {}).json()["question"]
        question = PracticeQuestion.objects.get(pk=check["id"])
        self.submit(question, question.answer["accepted"][0])
        self.assertEqual(LearningEvidence.objects.filter(kind="conversation", score=100).count(), 1)
        self.assertEqual(TopicMastery.objects.get().attempts, 1)

    def test_tutor_behavior_changes_observably_with_mastery(self):
        self.upload()
        first = self.post(self.sc, f"learning/courses/{self.course.id}/ask/", {"question": "Explain linked lists"}).json()
        for number in range(4):
            record_evidence(self.student.student, self.topic, str(number), "quiz", 100)
        final = self.post(self.sc, f"learning/courses/{self.course.id}/ask/", {"question": "Explain linked lists"}).json()
        self.assertEqual(first["tutoring_policy"]["style"], "foundation")
        self.assertEqual(final["tutoring_policy"]["style"], "advanced")
        self.assertNotEqual(first["learning_steps"], final["learning_steps"])

    def test_missing_numerical_support_is_explicit_not_invented(self):
        self.upload(content=b"Linked Lists\nA pointer is a reference to the first node.")
        response = self.post(self.sc, f"learning/courses/{self.course.id}/practice/", {"kind": "numerical"})
        self.assertEqual(response.status_code, 409)
        self.assertFalse(PracticeQuestion.objects.exists())

    def test_source_retry_preserves_previously_cited_units(self):
        material = self.upload(); chunk = SourceChunk.objects.first()
        self.post(self.tc, f"learning/materials/{material.id}/retry/", {})
        chunk.refresh_from_db(); self.assertTrue(chunk.unit.archived)
        self.assertEqual(self.sc.get(f"/api/learning/sources/{chunk.id}/").status_code, 200)
        from .learning.vectors import retrieve
        self.assertNotIn(chunk.id, [row["chunk"].id for row in retrieve([self.course], "linked lists")])
        from django.core.management import call_command
        from .learning.vectors import vector_collection
        call_command("reindex_materials", stdout=io.StringIO())
        self.assertEqual(vector_collection("hash").get(ids=[f"c-{chunk.id}"])["ids"], [])

    def test_evaluation_missing_environment_saves_failure_without_metrics(self):
        with override_settings(LABTWIN_EVALUATOR_PYTHON=""):
            response = self.post(self.tc, f"learning/courses/{self.course.id}/evaluations/", {})
        row = response.json()["run"]
        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["results"], {})
        self.assertEqual(self.sc.get(f"/api/learning/evaluations/{row['id']}/").status_code, 403)
        self.assertEqual(self.tc2.get(f"/api/learning/evaluations/{row['id']}/").status_code, 404)

    def test_real_deepeval_benchmark_and_simulations_are_executed(self):
        from django.conf import settings
        evaluator = os.getenv("LABTWIN_TEST_EVALUATOR_PYTHON", sys.executable)
        extra = os.getenv("LABTWIN_TEST_EVALUATOR_EXTRA_PATH", "")
        with override_settings(LABTWIN_EVALUATOR_PYTHON=evaluator, LABTWIN_EVALUATOR_EXTRA_PATH=extra):
            response = self.post(self.tc, f"learning/courses/{self.course.id}/evaluations/", {})
        row = response.json()["run"]
        self.assertEqual(row["status"], "completed", row)
        results = row["results"]
        self.assertEqual(results["framework"], "DeepEval")
        self.assertEqual(len(results["cases"]), 20)
        self.assertEqual(results["unsupported_queries"]["total"], 6)
        self.assertTrue(results["isolated_from_production"])
        self.assertEqual(len(results["personalization"]["profiles"]), 3)
        self.assertEqual(len(results["personalization"]["profiles"][0]["sessions"]), 4)
        self.assertEqual(CourseMaterial.objects.count(), 0)
        self.assertTrue(all(0 <= v <= 1 for v in results["metrics"].values()))
        self.assertEqual(EvaluationRun.objects.get().dataset_version, "labtwin-team-gold-v1")

    def test_legacy_replay_preserves_history_and_never_counts_model_transition_as_gain(self):
        from django.core.management import call_command
        from .learning.insights import progress_report
        LearningEvidence.objects.create(student=self.student.student, topic=self.topic, key="old", kind="quiz", score=100)
        TopicMastery.objects.create(student=self.student.student, topic=self.topic, score=40, state="Needs Practice", attempts=1)
        MasterySnapshot.objects.create(student=self.student.student, topic=self.topic, score=40, state="Needs Practice")
        call_command("rebuild_mastery", stdout=io.StringIO())
        self.assertEqual(LearningEvidence.objects.count(), 1)
        self.assertEqual(MasterySnapshot.objects.count(), 2)
        self.assertEqual(TopicMastery.objects.get().model_version, "bkt-reliability-v1")
        self.assertEqual(progress_report(self.student.student, self.course)["recent_improvements"], [])
        call_command("rebuild_mastery", stdout=io.StringIO())
        self.assertEqual(MasterySnapshot.objects.count(), 2)
