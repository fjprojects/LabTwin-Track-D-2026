"""Low-confidence source labels must never be promoted to trusted assessment facts."""
from django.test import TestCase, override_settings

from .models import Course, CourseTopic, CourseMaterial, SourceUnit, SourceChunk, Account, Classroom, StudentProfile
from .learning.taxonomy import clean_heading, assessment_topic_eligible
from .learning.assessments import scoped_topics
from .learning.question_generation import candidates, readable_source_sentence
from .learning.question_verification import verify


class AssessmentQuestionQualityTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user("teacher_quality", password="Quality-test-password-85!")
        student_user = get_user_model().objects.create_user("student_quality", password="Quality-test-password-85!")
        teacher = Account.objects.create(user=user, role="teacher")
        profile = StudentProfile.objects.create(name="Student quality")
        Account.objects.create(user=student_user, role="student", student=profile)
        classroom = Classroom.objects.create(teacher=teacher, name="Question quality", join_code="QUAL01234567")
        self.course = Course.objects.create(classroom=classroom, name="Data Structures", is_demo=True)
        self.topic = CourseTopic.objects.create(course=self.course, name="Linked Lists")
        self.student = profile
        self.material = CourseMaterial.objects.create(course=self.course, uploaded_by=teacher,
            title="Course notes", filename="notes.pdf", kind="pdf", file="test-only.pdf", status="ready")

    def chunk(self, text):
        unit = SourceUnit.objects.create(material=self.material, number=self.material.units.count() + 1,
            topic_name=self.topic.name, text=text)
        return SourceChunk.objects.create(course=self.course, unit=unit, text=text, position=0)

    def test_ocr_index_labels_are_not_assessment_topics(self):
        self.assertEqual(clean_heading("SNO| TITLE OF THE TOPIC PAE NO"), "")
        self.assertEqual(clean_heading("Angortmms Ano _Agergact Data Tyees"), "")
        self.assertEqual(clean_heading("Head update"), "Head update")
        bad = CourseTopic.objects.create(course=self.course, name="SNO| TITLE OF THE TOPIC PAE NO",
            taxonomy_evidence={"method": "source_heading", "quote": "SNO| TITLE OF THE TOPIC PAE NO"})
        self.assertFalse(assessment_topic_eligible(bad))
        self.assertTrue(assessment_topic_eligible(self.topic))
        self.assertEqual([t.name for t in scoped_topics(self.course, self.student, {})], ["Linked Lists"])
        self.assertTrue(CourseTopic.objects.filter(pk=bad.pk).exists(), "Existing OCR evidence must not be deleted")

    def test_noisy_handwriting_does_not_create_automatically_verified_question(self):
        text = "| Datastructuve Intuduchon\nSNO| TITLE OF THE TOPIC PAE NO\nAngortmms Ano _Agergact Data Tyees"
        chunk = self.chunk(text)
        self.assertFalse(readable_source_sentence("| Datastructuve Intuduchon was clear data"))
        self.assertEqual(list(candidates([chunk], self.topic, difficulty=1, kind="quiz")), [])

    def test_fact_mcq_has_real_subject_and_multiple_source_backed_choices(self):
        text = ("The head pointer is the reference to the first node. "
                "A linked list is a chain of nodes. "
                "The node count worked example is 3 + 4 = 7.")
        chunk = self.chunk(text)
        questions = list(candidates([chunk], self.topic, difficulty=1, kind="quiz"))
        self.assertGreaterEqual(len(questions), 2)
        for item in questions:
            self.assertEqual(item["metadata"]["template"], "concept_mcq")
            self.assertNotIn("appears in the uploaded source", item["prompt"])
            self.assertNotIn("absent from the supplied source passage", " ".join(item["options"]).lower())
            self.assertEqual(verify(item, self.course)["status"], "verified")
            self.assertEqual(item["options"][item["answer"]["correct_index"]], item["metadata"]["support_quote"])

    def test_wrong_mcq_key_is_rejected(self):
        chunk = self.chunk("The head pointer is the reference to the first node. A linked list is a chain of nodes.")
        item = list(candidates([chunk], self.topic, difficulty=1, kind="quiz"))[0]
        item["answer"]["correct_index"] = (item["answer"]["correct_index"] + 1) % len(item["options"])
        self.assertEqual(verify(item, self.course)["status"], "rejected")
