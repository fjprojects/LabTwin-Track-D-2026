"""An isolated, reproducible demo using real uploads, execution and evidence."""
import hashlib
import json
import secrets
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files import File
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.test.utils import override_settings

from ..classroom_views import account_data
from ..models import Account, AccessToken, StudentProfile, Classroom, Enrollment, Course, CourseTopic, CourseMaterial, MaterialProcessJob, Assignment, QuestionBankItem, DemoSession, AskExchange, AssignmentAttempt, CoachingInteraction, PracticeQuestion, PracticeAttempt, AssessmentSession, EvaluationRun, TopicMastery
from .access import endpoint, LearningError
from .ingestion import process_material
from .material_views import course_data, material_data
from .mastery import resources

INSERT_STARTER = '''#include <stdio.h>
#include <stdlib.h>
typedef struct Node { int value; struct Node *next; } Node;
void insert(Node **head, int value) {
    Node *node = malloc(sizeof(Node));
    node->value = value;
    node->next = NULL; /* Check this connection. */
    *head = node;
}
int main(void) {
    int n, value; Node *head = NULL;
    if (scanf("%d", &n) != 1) return 0;
    for (int i = 0; i < n; i++) { scanf("%d", &value); insert(&head, value); }
    for (Node *p = head; p; p = p->next) printf("%d ", p->value);
    return 0;
}'''
INSERT_SOLUTION = INSERT_STARTER.replace("node->next = NULL; /* Check this connection. */", "node->next = *head;")
COUNT_SOLUTION = '''#include <stdio.h>
#include <stdlib.h>
typedef struct Node { int value; struct Node *next; } Node;
int count(Node *head) {
    int result = 0;
    for (Node *p = head; p; p = p->next) result++;
    return result;
}
int main(void) {
    int n, value; Node *head = NULL;
    if (scanf("%d", &n) != 1) return 0;
    for (int i = 0; i < n; i++) {
        scanf("%d", &value); Node *p = malloc(sizeof(Node));
        p->value = value; p->next = head; head = p;
    }
    printf("%d", count(head)); return 0;
}'''
COUNT_STARTER = COUNT_SOLUTION.replace("for (Node *p = head; p; p = p->next) result++;", "/* Traverse the list and count each visited node. */")


def enabled():
    if not getattr(settings, "LABTWIN_DEMO_ENABLED", False):
        raise LearningError("Demo mode is disabled. Set LABTWIN_DEMO_ENABLED=true to enable it.", 403)


def demo_data(demo, account):
    teacher = account.role == "teacher"
    ready = demo.course.materials.filter(status="ready").count() == 3
    attempts = AssignmentAttempt.objects.filter(assignment=demo.assignment, student=demo.student_account.student)
    questions = PracticeQuestion.objects.filter(student=demo.student_account.student, topic__course=demo.course)
    progress = [ready, ready, AskExchange.objects.filter(account=demo.student_account, course=demo.course, grounded=True).exists(), attempts.filter(status="submitted", test_score__lt=100).exists(), CoachingInteraction.objects.filter(assignment_attempt__in=attempts).exists(), attempts.filter(test_score=100, status="submitted").exists(), questions.exists(), PracticeAttempt.objects.filter(question__in=questions, status="completed", score=100).exists()]
    off = AskExchange.objects.filter(account=demo.student_account, course=demo.course, grounded=False).exists()
    assessed = AssessmentSession.objects.filter(student=demo.student_account.student, course=demo.course).exists()
    figures = demo.course.chunks.filter(unit__content_type="visual", unit__archived=False).count() >= 2
    followups = questions.filter(kind="code")
    improved = PracticeAttempt.objects.filter(question__in=followups, status="completed", score=100).exists()
    detailed = [True, ready, ready and figures, progress[2], progress[2], off, off, assessed,
        questions.filter(verification_status__in=["verified", "teacher_reviewed"]).exists(), progress[3], progress[4],
        TopicMastery.objects.filter(student=demo.student_account.student, topic__course=demo.course, attempts__gt=0).exists(),
        followups.exists(), followups.exclude(reason="").exists(), improved, improved,
        EvaluationRun.objects.filter(owner=demo.teacher, course=demo.course, status="completed").exists()]
    return {"id": demo.id, "course": course_data(demo.course), "assignment_id": demo.assignment_id, "materials": [material_data(m) for m in demo.course.materials.all()], "topic_id": demo.assignment.topic_id, "progress": progress, "detailed_progress": detailed, "corrected_code": INSERT_SOLUTION if demo.assignment.allow_solution else "", "followup_code": COUNT_SOLUTION if demo.course.allow_solutions else "", "mode_note": "The demo automatically extracts embedded lecture captions and native PDF/slide diagram relationships, using local retrieval. Source locations, code execution, BKT updates and evaluation runs are real. General raster vision, speech transcription and neural embeddings require their configured providers/models.", "teacher_preview": teacher}


@endpoint(["GET", "POST"])
def demos(request):
    if request.method == "GET":
        allowed = DemoSession.objects.filter(teacher=request.account) if request.account.role == "teacher" else DemoSession.objects.filter(student_account=request.account)
        demo = allowed.select_related("course__classroom", "assignment__topic").first()
        return JsonResponse({"enabled": getattr(settings, "LABTWIN_DEMO_ENABLED", False), "demo": demo_data(demo, request.account) if demo else None})
    enabled()
    if request.account.role != "teacher":
        raise LearningError("Your teacher prepares this demo.", 403)
    existing = DemoSession.objects.filter(teacher=request.account).select_related("course__classroom", "assignment__topic").first()
    if existing:
        with override_settings(LABTWIN_DISABLE_REMOTE_AI=True):
            for material in existing.course.materials.filter(status__in=["failed", "queued"]):
                material.status = "queued"; material.save(update_fields=["status"])
                MaterialProcessJob.objects.filter(material=material).update(status="queued")
                process_material(material)
        return JsonResponse({"demo": demo_data(existing, request.account)})
    asset_dir = Path(__file__).resolve().parent.parent / "demo_assets"
    if not (asset_dir / "Lecture-4.webm").exists():
        raise LearningError("Demo assets are missing. Run scripts/create_demo_assets.py.", 503)
    with transaction.atomic():
        room = Classroom.objects.create(teacher=request.account, name="Hackathon Demo Classroom", subject="Data Structures", join_code=secrets.token_hex(6).upper())
        user = get_user_model().objects.create(username="demo-" + secrets.token_hex(12), first_name="Demo Learner")
        user.set_unusable_password(); user.save()
        student = StudentProfile.objects.create(name="Demo Learner")
        account = Account.objects.create(user=user, student=student, role="student")
        Enrollment.objects.create(classroom=room, student=student)
        course = Course.objects.create(classroom=room, name="Data Structures · Guided Demo", language="C", is_demo=True, allow_solutions=True)
        topic = CourseTopic.objects.create(course=course, name="Linked Lists", description="Preserve the old chain when changing the head pointer.")
        trees = CourseTopic.objects.create(course=course, name="Trees", position=1)
        trees.prerequisites.add(topic)
        assignment = Assignment.objects.create(classroom=room, topic=topic, title="Insert at the beginning", instructions="Read n and n integers, insert each value at the beginning of a linked list, then print the list separated by spaces. Preserve the previous nodes.", language="C", starter_code=INSERT_STARTER, allow_solution=True, require_camera=False, require_screen=False, tests=[{"input": "1\n7\n", "expected": "7"}, {"input": "3\n1 2 3\n", "expected": "3 2 1"}, {"input": "0\n", "expected": ""}])
        demo = DemoSession.objects.create(teacher=request.account, student_account=account, course=course, assignment=assignment)
        for filename, kind, title in [("Data-Structures-Notes.pdf", "pdf", "Data Structures Notes"), ("Linked-Lists.pptx", "slides", "Linked Lists Slides"), ("Lecture-4.webm", "video", "Lecture 4")]:
            path = asset_dir / filename
            with path.open("rb") as stream:
                material = CourseMaterial.objects.create(course=course, topic=topic, uploaded_by=request.account, title=title, filename=filename, kind=kind, file=File(stream, name=filename), sha256=hashlib.sha256(path.read_bytes()).hexdigest(), byte_size=path.stat().st_size)
            MaterialProcessJob.objects.create(material=material)
    # No long-running extraction inside the database transaction.
    with override_settings(LABTWIN_DISABLE_REMOTE_AI=True):
        for material in course.materials.all():
            process_material(material)
    QuestionBankItem.objects.create(topic=topic, title="Count list nodes", kind="code", difficulty=1, prompt="Reassessment: read n values into the supplied linked list, implement count(head), and print the number of reachable nodes. Check the empty list as well.", language="C", starter_code=COUNT_STARTER, solution=COUNT_SOLUTION, tests=[{"input": "3\n8 4 1\n", "expected": "3"}, {"input": "0\n", "expected": "0"}, {"input": "1\n9\n", "expected": "1"}], source_ids=[s["id"] for s in resources(topic)])
    return JsonResponse({"demo": demo_data(demo, request.account)}, status=201)


@endpoint(["POST"], teacher=True)
def student_preview(request, demo_id):
    enabled()
    demo = DemoSession.objects.select_related("student_account__user").filter(pk=demo_id, teacher=request.account).first()
    if not demo:
        raise LearningError("Demo not found.", 404)
    raw = secrets.token_urlsafe(32)
    AccessToken.objects.create(account=demo.student_account, digest=hashlib.sha256(raw.encode()).hexdigest(), expires_at=timezone.now() + timedelta(minutes=30))
    return JsonResponse({"token": raw, "account": account_data(demo.student_account)})
