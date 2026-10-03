"""Course-scoped learning data; existing lab records are kept unchanged."""
import uuid
import os
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models


class PrivateLearningStorage(FileSystemStorage):
    @property
    def base_location(self):
        return str(getattr(settings, "LABTWIN_MEDIA_ROOT", Path(settings.BASE_DIR) / "private_learning"))

    @property
    def location(self):
        return os.path.abspath(self.base_location)


def private_learning_storage():
    return PrivateLearningStorage()


def material_path(instance, filename):
    suffix = Path(filename).suffix.lower()
    return f"course_{instance.course_id}/{uuid.uuid4().hex}{suffix}"


def visual_path(instance, filename):
    return f"course_{instance.material.course_id}/visuals/{uuid.uuid4().hex}.png"


class Course(models.Model):
    classroom = models.ForeignKey("Classroom", on_delete=models.CASCADE, related_name="courses")
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    language = models.CharField(max_length=10, default="Python")
    allow_solutions = models.BooleanField(default=False)
    activity_verification = models.BooleanField(default=True)
    camera_cues_enabled = models.BooleanField(default=True)
    camera_eye_closure = models.BooleanField(default=False)
    is_demo = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class CourseTopic(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="topics")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    position = models.PositiveIntegerField(default=0)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="subtopics")
    concepts = models.JSONField(default=list)
    taxonomy_evidence = models.JSONField(default=dict)
    learner_parameters = models.JSONField(default=dict)
    prerequisites = models.ManyToManyField("self", symmetrical=False, blank=True, related_name="unlocks")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["course", "name"], name="unique_course_topic")]
        ordering = ["position", "id"]


class CourseMaterial(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="materials")
    topic = models.ForeignKey(CourseTopic, null=True, blank=True, on_delete=models.SET_NULL, related_name="materials")
    uploaded_by = models.ForeignKey("Account", on_delete=models.PROTECT)
    title = models.CharField(max_length=200)
    filename = models.CharField(max_length=240)
    file = models.FileField(storage=private_learning_storage, upload_to=material_path)
    preview_file = models.FileField(storage=private_learning_storage, upload_to=material_path, blank=True)
    kind = models.CharField(max_length=20)
    sha256 = models.CharField(max_length=64)
    byte_size = models.PositiveBigIntegerField(default=0)
    status = models.CharField(max_length=20, default="queued")
    error = models.TextField(blank=True)
    warnings = models.JSONField(default=list)
    transcript = models.JSONField(default=list)
    transcript_origin = models.CharField(max_length=40, blank=True)
    summary = models.TextField(blank=True)
    chapters = models.JSONField(default=list)
    key_topics = models.JSONField(default=list)
    duration_seconds = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)


class MaterialProcessJob(models.Model):
    material = models.OneToOneField(CourseMaterial, on_delete=models.CASCADE, related_name="job")
    status = models.CharField(max_length=20, default="queued")
    attempts = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    # A lease fences off interrupted workers after a retry. Progress counts
    # describe the current stage, not an invented end-to-end percentage.
    lease_token = models.CharField(max_length=32, blank=True)
    stage = models.CharField(max_length=40, default="queued")
    completed_units = models.PositiveIntegerField(default=0)
    total_units = models.PositiveIntegerField(default=0)
    unit_label = models.CharField(max_length=40, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)


class SourceUnit(models.Model):
    material = models.ForeignKey(CourseMaterial, on_delete=models.CASCADE, related_name="units")
    number = models.PositiveIntegerField()
    title = models.CharField(max_length=200, blank=True)
    text = models.TextField()
    page_number = models.PositiveIntegerField(null=True, blank=True)
    slide_number = models.PositiveIntegerField(null=True, blank=True)
    start_seconds = models.FloatField(null=True, blank=True)
    end_seconds = models.FloatField(null=True, blank=True)
    topic_name = models.CharField(max_length=200, blank=True)
    layout = models.JSONField(default=dict)
    content_type = models.CharField(max_length=30, default="text")
    subtopic = models.CharField(max_length=200, blank=True)
    concepts = models.JSONField(default=list)
    prerequisite_names = models.JSONField(default=list)
    visual_description = models.TextField(blank=True)
    visual_file = models.FileField(storage=private_learning_storage, upload_to=visual_path, blank=True)
    analysis_method = models.CharField(max_length=80, blank=True)
    archived = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["material", "number"], name="unique_source_unit")]
        ordering = ["number"]


class SourceChunk(models.Model):
    unit = models.ForeignKey(SourceUnit, on_delete=models.CASCADE, related_name="chunks")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="chunks")
    position = models.PositiveIntegerField()
    text = models.TextField()
    metadata = models.JSONField(default=dict)
    embedding = models.JSONField(default=list)
    embedding_model = models.CharField(max_length=120)


class AskExchange(models.Model):
    account = models.ForeignKey("Account", on_delete=models.CASCADE, related_name="learning_questions")
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    material = models.ForeignKey(CourseMaterial, null=True, blank=True, on_delete=models.SET_NULL)
    question = models.TextField()
    answer = models.TextField()
    citations = models.JSONField(default=list)
    grounded = models.BooleanField(default=False)
    mode = models.CharField(max_length=40)
    created_at = models.DateTimeField(auto_now_add=True)


class TopicMastery(models.Model):
    student = models.ForeignKey("StudentProfile", on_delete=models.CASCADE, related_name="course_mastery")
    topic = models.ForeignKey(CourseTopic, on_delete=models.CASCADE, related_name="student_mastery")
    score = models.FloatField(default=0)
    state = models.CharField(max_length=30, default="Not Started")
    attempts = models.PositiveIntegerField(default=0)
    average_hint_level = models.FloatField(default=0)
    knowledge_probability = models.FloatField(default=0.35)
    model_version = models.CharField(max_length=40, default="legacy-weighted-v1")
    model_parameters = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["student", "topic"], name="unique_student_course_mastery")]


class LearningEvidence(models.Model):
    student = models.ForeignKey("StudentProfile", on_delete=models.CASCADE, related_name="learning_evidence")
    topic = models.ForeignKey(CourseTopic, on_delete=models.CASCADE, related_name="evidence")
    key = models.CharField(max_length=200)
    kind = models.CharField(max_length=30)
    score = models.FloatField(null=True, blank=True)
    hint_level = models.PositiveSmallIntegerField(default=0)
    attempt_number = models.PositiveIntegerField(default=1)
    misconception = models.TextField(blank=True)
    verified = models.BooleanField(default=True)
    detail = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["student", "topic", "key"], name="unique_learning_evidence")]
        ordering = ["created_at", "id"]


class MasterySnapshot(models.Model):
    student = models.ForeignKey("StudentProfile", on_delete=models.CASCADE)
    topic = models.ForeignKey(CourseTopic, on_delete=models.CASCADE, related_name="history")
    score = models.FloatField()
    state = models.CharField(max_length=30)
    evidence = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class ResourceStudy(models.Model):
    student = models.ForeignKey("StudentProfile", on_delete=models.CASCADE, related_name="resource_visits")
    unit = models.ForeignKey(SourceUnit, on_delete=models.CASCADE)
    seconds_viewed = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)


class QuestionBankItem(models.Model):
    topic = models.ForeignKey(CourseTopic, on_delete=models.CASCADE, related_name="question_bank")
    title = models.CharField(max_length=200)
    kind = models.CharField(max_length=20, default="quiz")
    difficulty = models.PositiveSmallIntegerField(default=1)
    prompt = models.TextField()
    language = models.CharField(max_length=10, default="Python")
    options = models.JSONField(default=list)
    answer = models.JSONField(default=dict)
    tests = models.JSONField(default=list)
    starter_code = models.TextField(blank=True)
    solution = models.TextField(blank=True)
    rubric = models.JSONField(default=list)
    source_ids = models.JSONField(default=list)
    explanation = models.TextField(blank=True)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class PracticeQuestion(models.Model):
    student = models.ForeignKey("StudentProfile", on_delete=models.CASCADE, related_name="adaptive_questions")
    topic = models.ForeignKey(CourseTopic, on_delete=models.CASCADE)
    bank_item = models.ForeignKey(QuestionBankItem, null=True, blank=True, on_delete=models.SET_NULL)
    kind = models.CharField(max_length=20)
    difficulty = models.PositiveSmallIntegerField(default=1)
    prompt = models.TextField()
    language = models.CharField(max_length=10, default="Python")
    options = models.JSONField(default=list)
    answer = models.JSONField(default=dict)
    tests = models.JSONField(default=list)
    starter_code = models.TextField(blank=True)
    solution = models.TextField(blank=True)
    rubric = models.JSONField(default=list)
    source_ids = models.JSONField(default=list)
    reason = models.TextField()
    explanation = models.TextField(blank=True)
    metadata = models.JSONField(default=dict)
    verification_status = models.CharField(max_length=40, default="legacy")
    verification = models.JSONField(default=dict)
    fingerprint = models.CharField(max_length=64, blank=True, db_index=True)
    semantic_vector = models.JSONField(default=list)
    assessment = models.ForeignKey("AssessmentSession", null=True, blank=True, on_delete=models.SET_NULL, related_name="questions")
    created_at = models.DateTimeField(auto_now_add=True)


class PracticeAttempt(models.Model):
    question = models.ForeignKey(PracticeQuestion, on_delete=models.CASCADE, related_name="attempts")
    request_id = models.CharField(max_length=64)
    code = models.TextField(blank=True)
    answer = models.TextField(blank=True)
    score = models.FloatField(null=True, blank=True)
    test_results = models.JSONField(default=list)
    status = models.CharField(max_length=20, default="processing")
    error = models.TextField(blank=True)
    hint_level = models.PositiveSmallIntegerField(default=0)
    misconception = models.TextField(blank=True)
    feedback = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["question", "request_id"], name="unique_practice_request")]


class CoachingInteraction(models.Model):
    student = models.ForeignKey("StudentProfile", on_delete=models.CASCADE)
    topic = models.ForeignKey(CourseTopic, on_delete=models.CASCADE)
    question = models.ForeignKey(PracticeQuestion, null=True, blank=True, on_delete=models.CASCADE, related_name="hints")
    assignment_attempt = models.ForeignKey("AssignmentAttempt", null=True, blank=True, on_delete=models.CASCADE, related_name="coaching")
    level = models.PositiveSmallIntegerField(default=1)
    message = models.TextField()
    misconception = models.TextField(blank=True)
    source_ids = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)


class VivaSession(models.Model):
    student = models.ForeignKey("StudentProfile", on_delete=models.CASCADE, related_name="course_vivas")
    topic = models.ForeignKey(CourseTopic, on_delete=models.CASCADE)
    question = models.ForeignKey(PracticeQuestion, null=True, blank=True, on_delete=models.SET_NULL)
    assignment_attempt = models.ForeignKey("AssignmentAttempt", null=True, blank=True, on_delete=models.SET_NULL)
    code = models.TextField(blank=True)
    source_ids = models.JSONField(default=list)
    verification = models.BooleanField(default=False)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class VivaTurn(models.Model):
    session = models.ForeignKey(VivaSession, on_delete=models.CASCADE, related_name="turns")
    question = models.TextField()
    answer = models.TextField(blank=True)
    score = models.FloatField(null=True, blank=True)
    feedback = models.TextField(blank=True)
    rubric = models.JSONField(default=list)
    assessment_mode = models.CharField(max_length=40, blank=True)
    answered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class DemoSession(models.Model):
    teacher = models.ForeignKey("Account", on_delete=models.CASCADE, related_name="learning_demos")
    student_account = models.OneToOneField("Account", on_delete=models.CASCADE, related_name="demo_session")
    course = models.OneToOneField(Course, on_delete=models.CASCADE)
    assignment = models.ForeignKey("Assignment", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)


class AssessmentSession(models.Model):
    student = models.ForeignKey("StudentProfile", on_delete=models.CASCADE, related_name="assessments")
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    kind = models.CharField(max_length=30, default="quiz")
    scope = models.JSONField(default=dict)
    status = models.CharField(max_length=30, default="in_progress")
    report = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)


class AssessmentCameraEvent(models.Model):
    """Student-reported observations; never scored evidence or stored camera media."""
    assessment = models.ForeignKey(AssessmentSession, on_delete=models.CASCADE, related_name="camera_events")
    question = models.ForeignKey(PracticeQuestion, null=True, blank=True, on_delete=models.SET_NULL)
    event_id = models.CharField(max_length=64)
    kind = models.CharField(max_length=40)
    detail = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [models.UniqueConstraint(fields=["assessment", "event_id"], name="unique_assessment_camera_event")]


class EvaluationRun(models.Model):
    owner = models.ForeignKey("Account", on_delete=models.CASCADE, related_name="evaluation_runs")
    course = models.ForeignKey(Course, null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=30, default="queued")
    mode = models.CharField(max_length=30, default="deterministic")
    framework = models.CharField(max_length=60, default="DeepEval")
    dataset_version = models.CharField(max_length=100, blank=True)
    results = models.JSONField(default=dict)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
