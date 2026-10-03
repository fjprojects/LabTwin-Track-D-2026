from django.db import models


class StudentProfile(models.Model):
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class ConceptProgress(models.Model):
    """
    Broad concept memory kept for compatibility and high-level analytics.
    Example concept_key values: POINTERS, ARRAYS, FUNCTIONS.
    """
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="concept_progress",
    )

    concept_key = models.CharField(max_length=100)

    attempts = models.IntegerField(default=0)
    mastered = models.IntegerField(default=0)
    failures = models.IntegerField(default=0)

    misconception_count = models.IntegerField(default=0)

    last_misconception = models.TextField(
        blank=True,
        default="",
    )

    total_score = models.FloatField(default=0)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (
            "student",
            "concept_key",
        )

    def __str__(self):
        return f"{self.student.name} - {self.concept_key}"

    @property
    def average_score(self):
        if self.attempts == 0:
            return 0

        return round(
            self.total_score / self.attempts,
            1,
        )


class TopicProgress(models.Model):
    """
    Exact syllabus-topic memory.

    This is the main personalization layer used by LabTwin V2.
    Example topic: "Pointer to Function"
    Broad concept: "POINTERS"
    """
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="topic_progress",
    )

    topic = models.CharField(max_length=200)
    concept_key = models.CharField(
        max_length=100,
        default="OTHER",
    )

    attempts = models.IntegerField(default=0)

    mastery_score = models.FloatField(default=0)

    status = models.CharField(
        max_length=50,
        default="Not Tested",
    )

    verification_required = models.BooleanField(default=False)
    verification_passed = models.BooleanField(default=False)

    misconception_count = models.IntegerField(default=0)

    last_misconception = models.TextField(
        blank=True,
        default="",
    )

    average_hint_level = models.FloatField(default=0)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (
            "student",
            "topic",
        )

    def __str__(self):
        return f"{self.student.name} - {self.topic}"


class Attempt(models.Model):
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="attempts",
    )

    question = models.TextField()

    topic = models.CharField(
        max_length=200,
        default="General",
    )

    concept_key = models.CharField(
        max_length=100,
        default="OTHER",
    )

    initial_score = models.FloatField(
        default=0,
    )

    final_score = models.FloatField(
        null=True,
        blank=True,
    )

    viva_score = models.FloatField(
        null=True,
        blank=True,
    )

    misconception = models.TextField(
        blank=True,
        default="",
    )

    status = models.CharField(
        max_length=50,
        default="Attempted",
    )

    # 0 = independent, 1 = light hint, 2 = structural hint,
    # 3 = near-solution guidance.
    hint_level = models.IntegerField(default=0)

    # True only when this question was intentionally generated as
    # an independent verification problem for a previously weak topic.
    verification = models.BooleanField(default=False)

    independent = models.BooleanField(default=False)

    mastery_score = models.FloatField(default=0)

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    def __str__(self):
        return f"{self.student.name} - {self.topic}"


class StudentResponse(models.Model):
    """One immutable submission/hint event; never replaced by mastery saves."""
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name="responses")
    stage = models.CharField(max_length=20)
    question_id = models.CharField(max_length=200, blank=True)
    question = models.TextField()
    topic = models.CharField(max_length=200, default="General")
    language = models.CharField(max_length=40, blank=True)
    code = models.TextField(blank=True)
    viva_answer = models.TextField(blank=True)
    context = models.JSONField(default=dict)
    test_results = models.JSONField(default=list)
    result = models.JSONField(default=dict)
    status = models.CharField(max_length=20, default="processing")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]


class Account(models.Model):
    user = models.OneToOneField('auth.User', on_delete=models.CASCADE, related_name='labtwin_account')
    role = models.CharField(max_length=10, choices=[('student', 'Student'), ('teacher', 'Teacher')])
    student = models.OneToOneField(StudentProfile, null=True, blank=True, on_delete=models.PROTECT, related_name='account')


class AccessToken(models.Model):
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    digest = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()


class Classroom(models.Model):
    teacher = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='classrooms')
    name = models.CharField(max_length=120)
    subject = models.CharField(max_length=120, blank=True)
    join_code = models.CharField(max_length=16, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Enrollment(models.Model):
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name='enrollments')
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='enrollments')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['classroom', 'student'], name='unique_class_student')]


class Assignment(models.Model):
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name='assignments')
    title = models.CharField(max_length=160)
    instructions = models.TextField()
    language = models.CharField(max_length=10, default='Python')
    tests = models.JSONField(default=list)
    viva_question = models.TextField(blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    allow_paste = models.BooleanField(default=True)
    require_screen = models.BooleanField(default=False)
    require_camera = models.BooleanField(default=True)
    camera_cues_enabled = models.BooleanField(default=True)
    camera_eye_closure = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    topic = models.ForeignKey('CourseTopic', null=True, blank=True, on_delete=models.SET_NULL, related_name='assignments')
    starter_code = models.TextField(blank=True)
    allow_solution = models.BooleanField(default=False)


class AssignmentAttempt(models.Model):
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='submissions')
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='assignment_attempts')
    code = models.TextField(blank=True)
    viva_answer = models.TextField(blank=True)
    test_results = models.JSONField(default=list)
    test_score = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=20, default='in_progress')
    error = models.TextField(blank=True)
    teacher_score = models.FloatField(null=True, blank=True)
    teacher_feedback = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['assignment', 'student'], condition=models.Q(status='in_progress'), name='one_active_assignment_attempt')]


class MonitoringEvent(models.Model):
    attempt = models.ForeignKey(AssignmentAttempt, on_delete=models.CASCADE, related_name='events')
    event_id = models.CharField(max_length=64)
    kind = models.CharField(max_length=40)
    stage = models.CharField(max_length=10, default='coding')
    detail = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['attempt', 'event_id'], name='unique_monitoring_event')]


class LiveSession(models.Model):
    attempt = models.OneToOneField(AssignmentAttempt, on_delete=models.CASCADE, related_name='live_session')
    active = models.BooleanField(default=True)
    screen_active = models.BooleanField(default=False)
    camera_active = models.BooleanField(default=False)
    last_seen = models.DateTimeField(auto_now=True)


class LiveConnection(models.Model):
    session = models.ForeignKey(LiveSession, on_delete=models.CASCADE, related_name='connections')
    teacher = models.ForeignKey(Account, on_delete=models.CASCADE)
    offer = models.JSONField(default=dict)
    answer = models.JSONField(default=dict)
    track_sources = models.JSONField(default=dict)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class IceCandidate(models.Model):
    connection = models.ForeignKey(LiveConnection, on_delete=models.CASCADE, related_name='candidates')
    sender = models.CharField(max_length=10)
    value = models.JSONField(default=dict)


# Keep the course architecture separate while registering its models with this app.
from .learning_models import (  # noqa: E402,F401
    Course, CourseTopic, CourseMaterial, MaterialProcessJob, SourceUnit, SourceChunk,
    AskExchange, TopicMastery, LearningEvidence, MasterySnapshot, ResourceStudy,
    QuestionBankItem, PracticeQuestion, PracticeAttempt, CoachingInteraction,
    VivaSession, VivaTurn, DemoSession, AssessmentSession, AssessmentCameraEvent, EvaluationRun,
)
