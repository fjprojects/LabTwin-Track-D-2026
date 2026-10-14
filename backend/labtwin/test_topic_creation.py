"""Topic creation uses course-owned IDs and actionable, non-destructive errors."""
from django.test import Client, override_settings

from .models import Course, CourseTopic
from .test_classrooms import ClassroomFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class TopicCreationTests(ClassroomFixture):
    def setUp(self):
        super().setUp()
        self.course = Course.objects.create(classroom=self.room, name="Java OOP", language="Java")
        self.topic = CourseTopic.objects.create(course=self.course, name="Polymorphism", description="Existing explanation")
        self.route = f"learning/courses/{self.course.id}/topics/"

    def create_topic(self, data, client=None):
        return self.post(client or self.tc, self.route, data)

    def test_valid_name_is_trimmed_and_default_prerequisites_are_empty(self):
        response = self.create_topic({"name": "  Method overloading  "})
        self.assertEqual(response.status_code, 201, response.content)
        topic = self.course.topics.get(name="Method overloading")
        self.assertEqual(topic.prerequisites.count(), 0)
        self.assertIn(topic.id, [row["id"] for row in response.json()["course"]["topics"]])

    def test_valid_prerequisite_stays_in_its_course(self):
        response = self.create_topic({"name": "Overriding", "prerequisites": [self.topic.id]})
        self.assertEqual(response.status_code, 201, response.content)
        topic = self.course.topics.get(name="Overriding")
        self.assertEqual(list(topic.prerequisites.values_list("id", flat=True)), [self.topic.id])

    def test_duplicate_explains_existing_topic_and_preserves_its_data(self):
        response = self.create_topic({"name": " Polymorphism ", "description": "Replacement", "prerequisites": []})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "A topic with this name already exists in this course. Use a different name.")
        self.assertEqual(self.course.topics.count(), 1)
        self.topic.refresh_from_db()
        self.assertEqual(self.topic.description, "Existing explanation")

    def test_same_name_in_another_owned_course_is_allowed(self):
        course = Course.objects.create(classroom=self.room, name="Another Java course")
        response = self.post(self.tc, f"learning/courses/{course.id}/topics/", {"name": self.topic.name})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(CourseTopic.objects.filter(name=self.topic.name).count(), 2)

    def test_invalid_names_are_rejected_without_creating_records(self):
        for name in [None, False, 42, [], {}, "", "   ", "x" * 201]:
            with self.subTest(name=name):
                response = self.create_topic({"name": name})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["error"], "Enter a topic name of up to 200 characters.")
                self.assertEqual(self.course.topics.count(), 1)

    def test_prerequisites_require_positive_integer_ids(self):
        for ids in [None, {}, "1", [str(self.topic.id)], [True], [False], [0], [-1], [1.5], [{}], [[]]]:
            with self.subTest(ids=ids):
                response = self.create_topic({"name": "Inheritance", "prerequisites": ids})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["error"], "Prerequisites must be a list of positive topic IDs.")
                self.assertEqual(self.course.topics.count(), 1)

    def test_unknown_prerequisite_has_a_specific_error(self):
        response = self.create_topic({"name": "Inheritance", "prerequisites": [999999]})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Choose prerequisites from this course. Refresh the course if a topic is no longer available.")
        self.assertEqual(self.course.topics.count(), 1)

    def test_foreign_prerequisite_is_rejected_without_disclosing_its_name(self):
        room = self.room.__class__.objects.create(teacher=self.teacher2, name="Private class", join_code="PRIVATE987654")
        course = Course.objects.create(classroom=room, name="Private course")
        topic = CourseTopic.objects.create(course=course, name="Private topic")
        response = self.create_topic({"name": "Inheritance", "prerequisites": [topic.id]})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Choose prerequisites from this course. Refresh the course if a topic is no longer available.")
        self.assertNotIn(topic.name, response.content.decode())
        self.assertEqual(self.course.topics.count(), 1)

    def test_topic_creation_remains_teacher_and_classroom_authorized(self):
        for client, status in [(Client(), 401), (self.sc, 403), (self.tc2, 404)]:
            with self.subTest(status=status):
                response = self.create_topic({"name": "Inheritance"}, client)
                self.assertEqual(response.status_code, status)
        self.assertEqual(self.course.topics.count(), 1)
