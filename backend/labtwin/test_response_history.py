import json
from types import SimpleNamespace
from unittest.mock import patch

from django.http import JsonResponse
from django.test import RequestFactory, TestCase

from .models import Attempt, StudentProfile, StudentResponse
from .response_history import record_execution, record_response, response_history


class ResponseHistoryTests(TestCase):
    def setUp(self):
        self.student = StudentProfile.objects.create(name="Student A")
        self.other = StudentProfile.objects.create(name="Student B")
        self.factory = RequestFactory()
        self.question = {"id": "q1", "problem": "Add two numbers", "topic": "Arithmetic", "language": "Python"}
        self.views = SimpleNamespace(get_current_question=lambda *args, **kwargs: self.question)

    def submit(self, view, **data):
        payload = {"student_id": self.student.id, "question_id": "q1", "code": "print(1)\n", **data}
        request = self.factory.post("/analyze/", json.dumps(payload), content_type="application/json")
        with patch.dict("sys.modules", {"labtwin.views": self.views}):
            return view(request)

    def test_repeated_submissions_preserve_code_and_do_not_change_mastery(self):
        @record_response("analysis")
        def view(request):
            self.assertEqual(StudentResponse.objects.latest("id").status, "processing")
            return JsonResponse({"test_score": 100, "diagnosis": {"hint": "Check the sum"}})
        self.submit(view)
        self.submit(view, code="print(2)\n")
        self.assertEqual(list(StudentResponse.objects.order_by("id").values_list("code", flat=True)), ["print(1)\n", "print(2)\n"])
        self.assertEqual(Attempt.objects.count(), 0)

    def test_execution_survives_ai_failure(self):
        tests = [{"test": 1, "stdout": "partial output", "stderr": "ValueError", "passed": False}]
        @record_response("retest")
        def view(request):
            record_execution(request, tests)
            return JsonResponse({"error": "AI unavailable"}, status=503)
        self.submit(view, viva_answer="My answer", viva_question="Why?", hint_level=2)
        row = StudentResponse.objects.get()
        self.assertEqual(row.status, "failed")
        self.assertEqual(row.test_results, tests)
        self.assertEqual(row.viva_answer, "My answer")
        self.assertEqual(row.context["hint_level"], 2)

    def test_hint_text_and_level_are_retained(self):
        @record_response("hint")
        def view(request):
            return JsonResponse({"hint": "Trace the loop", "level": 2})
        self.submit(view, current_hint="Check your loop", level=2)
        row = StudentResponse.objects.get()
        self.assertEqual(row.context["current_hint"], "Check your loop")
        self.assertEqual(row.result["hint"], "Trace the loop")

    def test_uncaught_failure_retains_submission(self):
        @record_response("analysis")
        def view(request):
            raise RuntimeError("upstream failure")
        with self.assertRaises(RuntimeError):
            self.submit(view)
        self.assertEqual(StudentResponse.objects.get().status, "failed")

    def test_invalid_student_and_missing_question_do_not_execute(self):
        @record_response("analysis")
        def view(request):
            self.fail("Invalid requests must not execute student code")
        self.assertEqual(self.submit(view, student_id="bad").status_code, 400)
        self.assertEqual(self.submit(view, student_id=99999).status_code, 404)
        self.question = None
        self.assertEqual(self.submit(view).status_code, 400)
        self.assertFalse(StudentResponse.objects.exists())

    def test_history_is_scoped_paginated_and_retained_after_summary_deletion(self):
        for student in (self.student, self.other):
            StudentResponse.objects.bulk_create([
                StudentResponse(student=student, stage="analysis", question="Question", code=str(i))
                for i in range(23)
            ])
        attempt = Attempt.objects.create(student=self.student, question="Question")
        attempt.delete()
        def get(**params):
            response = response_history(self.factory.get("/response-history/", {"student_id": self.student.id, **params}))
            return json.loads(response.content)
        page = get()
        self.assertEqual(len(page["responses"]), 20)
        expected = set(StudentResponse.objects.filter(student=self.student).values_list("id", flat=True))
        older = get(before=page["next_before"])
        self.assertIsNone(older["next_before"])
        ids = [row["id"] for row in page["responses"] + older["responses"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), expected)

    def test_empty_history_and_invalid_cursor(self):
        request = self.factory.get("/response-history/", {"student_id": self.student.id})
        self.assertEqual(json.loads(response_history(request).content)["responses"], [])
        request = self.factory.get("/response-history/", {"student_id": self.student.id, "before": "bad"})
        self.assertEqual(response_history(request).status_code, 400)
