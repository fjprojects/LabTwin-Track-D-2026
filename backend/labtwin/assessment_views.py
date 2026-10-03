"""Teacher assignments, append-only attempt evidence and review reports."""
import csv
import io
import math
from collections import Counter

from django.db import IntegrityError, transaction
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_http_methods

from .access import authenticated
from .classroom_views import body
from .models import Assignment, AssignmentAttempt, Classroom, Enrollment, MonitoringEvent, LiveSession, LiveConnection

EVENT_KINDS = {
    "page_hidden", "page_return", "window_blur", "window_focus", "copy", "cut", "paste",
    "paste_blocked", "screen_started", "screen_stopped", "camera_started", "camera_stopped",
    "permission_denied", "viva_started", "coach_reminder", "page_exit",
    "camera_cue", "camera_calibrated", "camera_analysis_error", "camera_unavailable",
    "camera_analysis_started", "camera_analysis_stopped",
}


def assignment_access(account, assignment):
    if account.role == "teacher":
        return assignment.classroom.teacher_id == account.id
    return Enrollment.objects.filter(classroom=assignment.classroom, student_id=account.student_id).exists()


def attempt_access(account, attempt):
    enrolled = Enrollment.objects.filter(classroom=attempt.assignment.classroom, student_id=attempt.student_id).exists()
    return enrolled and assignment_access(account, attempt.assignment) and (
        account.role == "teacher" or account.student_id == attempt.student_id)


def assignment_data(assignment, teacher=False):
    result = {"id": assignment.id, "classroom_id": assignment.classroom_id, "title": assignment.title,
              "instructions": assignment.instructions, "language": assignment.language,
              "viva_question": assignment.viva_question, "due_at": assignment.due_at.isoformat() if assignment.due_at else None,
              "allow_paste": assignment.allow_paste, "require_screen": assignment.require_screen,
              "require_camera": assignment.require_camera}
    result.update(topic_id=assignment.topic_id, course_id=assignment.topic.course_id if assignment.topic_id else None,
                  starter_code=assignment.starter_code, allow_solution=assignment.allow_solution,
                  camera_cues_enabled=assignment.camera_cues_enabled, camera_eye_closure=assignment.camera_eye_closure)
    if teacher:
        result["tests"] = assignment.tests
    return result


def attempt_data(attempt, teacher=False):
    counts = Counter(attempt.events.values_list("kind", flat=True))
    tests = attempt.test_results if teacher else [
        {key: row.get(key) for key in ("test", "passed", "success")}
        for row in attempt.test_results]
    return {"id": attempt.id, "student_id": attempt.student_id, "student_name": attempt.student.name,
            "assignment": assignment_data(attempt.assignment), "code": attempt.code,
            "viva_answer": attempt.viva_answer, "test_results": tests, "test_score": attempt.test_score,
            "status": attempt.status, "error": attempt.error, "teacher_score": attempt.teacher_score,
            "teacher_feedback": attempt.teacher_feedback, "event_counts": dict(counts),
            "started_at": attempt.started_at.isoformat(),
            "submitted_at": attempt.submitted_at.isoformat() if attempt.submitted_at else None,
            "late": bool(attempt.submitted_at and attempt.assignment.due_at and attempt.submitted_at > attempt.assignment.due_at),
            "needs_review": bool(counts["page_hidden"] or counts["paste"] or counts["paste_blocked"]),
            "review_note": "Browser events are observations, not proof of copying."}


@authenticated
@require_http_methods(["GET", "POST"])
def assignments(request, classroom_id):
    account = request.account
    room = Classroom.objects.filter(id=classroom_id).first()
    allowed = room and ((account.role == "teacher" and room.teacher_id == account.id) or (
        account.role == "student" and Enrollment.objects.filter(classroom=room, student=account.student).exists()))
    if not allowed:
        return JsonResponse({"error": "Classroom not found."}, status=404)
    if request.method == "GET":
        return JsonResponse({"assignments": [assignment_data(item, account.role == "teacher")
                            for item in room.assignments.order_by("-id")]})
    if account.role != "teacher":
        return JsonResponse({"error": "Only teachers can set assignments."}, status=403)
    try:
        data = body(request)
        title = str(data.get("title", "")).strip()
        instructions = str(data.get("instructions", "")).strip()
        language = data.get("language", "Python")
        tests = data.get("tests", [])
        due = parse_datetime(data["due_at"]) if data.get("due_at") else None
        if not title or len(title) > 160 or not instructions or len(instructions) > 20000 or language not in ("Python", "C", "Java"):
            raise ValueError()
        if not isinstance(tests, list) or not 1 <= len(tests) <= 20:
            raise ValueError()
        if any(not isinstance(t, dict) or not all(isinstance(t.get(k), str) and len(t[k]) <= 10000 for k in ("input", "expected")) for t in tests):
            raise ValueError()
        if data.get("due_at") and (due is None or timezone.is_naive(due)):
            raise ValueError()
        if any(key in data and not isinstance(data[key], bool) for key in ("allow_paste", "require_screen", "require_camera", "allow_solution", "camera_cues_enabled", "camera_eye_closure")):
            raise ValueError()
        from .models import CourseTopic
        topic = CourseTopic.objects.filter(pk=data.get("topic_id"), course__classroom=room).first() if data.get("topic_id") else None
        if data.get("topic_id") and not topic:
            raise ValueError()
        item = Assignment.objects.create(classroom=room, title=title, instructions=instructions,
            language=language, tests=tests, due_at=due, viva_question=str(data.get("viva_question", ""))[:20000],
            allow_paste=data.get("allow_paste", True), require_screen=data.get("require_screen", False),
            require_camera=data.get("require_camera", True), topic=topic,
            camera_cues_enabled=data.get("camera_cues_enabled", True), camera_eye_closure=data.get("camera_eye_closure", False),
            starter_code=str(data.get("starter_code", ""))[:100000], allow_solution=data.get("allow_solution", False))
        return JsonResponse({"assignment": assignment_data(item, True)}, status=201)
    except (ValueError, TypeError, UnicodeDecodeError):
        return JsonResponse({"error": "Enter a title, instructions, language and 1–20 input/output test cases. Use a valid due date."}, status=400)


@authenticated
@require_http_methods(["POST"])
def start_attempt(request, assignment_id):
    assignment = Assignment.objects.select_related("classroom").filter(pk=assignment_id).first()
    if request.account.role != "student" or not assignment or not assignment_access(request.account, assignment):
        return JsonResponse({"error": "Assignment not found."}, status=404)
    try:
        with transaction.atomic():
            attempt, _ = AssignmentAttempt.objects.get_or_create(
                assignment=assignment, student=request.account.student, status="in_progress", defaults={"code": assignment.starter_code})
    except IntegrityError:
        attempt = AssignmentAttempt.objects.get(assignment=assignment, student=request.account.student, status="in_progress")
    return JsonResponse({"attempt": attempt_data(attempt)})


@authenticated
@require_http_methods(["GET"])
def my_submissions(request, assignment_id):
    assignment = Assignment.objects.select_related("classroom").filter(pk=assignment_id).first()
    if request.account.role != "student" or not assignment or not assignment_access(request.account, assignment):
        return JsonResponse({"error": "Assignment not found."}, status=404)
    rows = assignment.submissions.filter(student=request.account.student).select_related("student", "assignment__classroom").order_by("-id")
    return JsonResponse({"submissions": [attempt_data(row) for row in rows]})


@authenticated
@require_http_methods(["GET", "PATCH", "POST"])
def attempt_detail(request, attempt_id):
    attempt = AssignmentAttempt.objects.select_related("assignment__classroom", "student").filter(pk=attempt_id).first()
    if not attempt or not attempt_access(request.account, attempt):
        return JsonResponse({"error": "Attempt not found."}, status=404)
    if request.method == "GET":
        return JsonResponse({"attempt": attempt_data(attempt, request.account.role == "teacher")})
    if request.account.role != "student":
        return JsonResponse({"error": "Teachers review submissions; they cannot submit for students."}, status=403)
    try:
        data = body(request)
        code = data.get("code", attempt.code)
        viva = data.get("viva_answer", attempt.viva_answer)
        if not isinstance(code, str) or not isinstance(viva, str) or len(code) > 100000 or len(viva) > 20000:
            raise ValueError()
    except (ValueError, TypeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid code or viva answer."}, status=400)

    with transaction.atomic():
        attempt = AssignmentAttempt.objects.select_for_update().select_related("assignment", "student").get(pk=attempt_id)
        if attempt.status != "in_progress":
            return JsonResponse({"error": "This attempt is already submitted. Start a new attempt to try again."}, status=409)
        if request.method == "POST":
            live = getattr(attempt, "live_session", None)
            fresh = live and live.active and (timezone.now() - live.last_seen).total_seconds() < 30
            if attempt.assignment.require_screen and not (fresh and live.screen_active):
                return JsonResponse({"error": "Your teacher requires screen sharing. Start sharing before submitting."}, status=400)
            if attempt.assignment.require_camera and not (fresh and live.camera_active):
                return JsonResponse({"error": "Your teacher requires a camera during viva. Turn it on before submitting."}, status=400)
            if not code.strip():
                return JsonResponse({"error": "Enter your code."}, status=400)
            attempt.status = "processing"
            attempt.submitted_at = timezone.now()
        attempt.code, attempt.viva_answer = code, viva
        attempt.save()
    if request.method == "PATCH":
        return JsonResponse({"saved": True})
    try:
        from .views import run_tests
        score, results = run_tests(code, attempt.assignment.tests, attempt.assignment.language)
        attempt.test_score, attempt.test_results, attempt.status = score, results, "submitted"
    except Exception:
        attempt.status, attempt.error = "failed", "Execution failed. Your submitted code and answer were retained."
    attempt.save(update_fields=["test_score", "test_results", "status", "error"])
    from .learning.mastery import bridge_assignment
    bridge_assignment(attempt)
    LiveSession.objects.filter(attempt=attempt).update(active=False, screen_active=False, camera_active=False)
    LiveConnection.objects.filter(session__attempt=attempt).update(active=False)
    return JsonResponse({"attempt": attempt_data(attempt)})


@authenticated
@require_http_methods(["POST", "GET"])
def events(request, attempt_id):
    attempt = AssignmentAttempt.objects.select_related("assignment__classroom", "student").filter(pk=attempt_id).first()
    if not attempt or not attempt_access(request.account, attempt):
        return JsonResponse({"error": "Attempt not found."}, status=404)
    if request.method == "GET":
        return JsonResponse({"events": [{"kind": e.kind, "stage": e.stage, "detail": e.detail,
            "created_at": e.created_at.isoformat()} for e in attempt.events.order_by("created_at", "id")[:2000]]})
    if request.account.role != "student" or attempt.status not in ("in_progress", "processing"):
        return JsonResponse({"error": "Only the student can log activity during an active attempt."}, status=403)
    try:
        items = body(request).get("events")
        if not isinstance(items, list) or not 1 <= len(items) <= 50:
            raise ValueError()
        prepared = []
        for item in items:
            if not isinstance(item, dict) or item.get("kind") not in EVENT_KINDS or item.get("stage", "coding") not in ("coding", "viva"):
                raise ValueError()
            event_id = item.get("event_id")
            if not isinstance(event_id, str) or not 1 <= len(event_id) <= 64:
                raise ValueError()
            detail = item.get("detail", {})
            if not isinstance(detail, dict):
                raise ValueError()
            # Never retain clipboard contents, visited URLs or camera images.
            detail = {k: v for k, v in detail.items() if k in ("duration_ms", "characters", "field", "message", "surface", "observed_at", "reason", "method", "consent", "allow_eye_closure", "analysis_enabled")
                      and isinstance(v, (str, int, float)) and len(str(v)) <= 300}
            prepared.append(MonitoringEvent(attempt=attempt, event_id=event_id, kind=item["kind"], stage=item.get("stage", "coding"), detail=detail))
        if attempt.events.count() + len(prepared) > 2000:
            return JsonResponse({"error": "Activity log limit reached."}, status=400)
        MonitoringEvent.objects.bulk_create(prepared, ignore_conflicts=True)
        return JsonResponse({"saved": True})
    except (ValueError, TypeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid activity events."}, status=400)


@authenticated
@require_http_methods(["POST"])
def grade_attempt(request, attempt_id):
    attempt = AssignmentAttempt.objects.select_related("assignment__classroom").filter(pk=attempt_id).first()
    if request.account.role != "teacher" or not attempt or not attempt_access(request.account, attempt):
        return JsonResponse({"error": "Submission not found."}, status=404)
    if attempt.status not in ("submitted", "failed"):
        return JsonResponse({"error": "Wait for the student to submit."}, status=409)
    try:
        data = body(request)
        score = float(data["score"]) if data.get("score") not in (None, "") else None
        if score is not None and (not math.isfinite(score) or not 0 <= score <= 100):
            raise ValueError()
        feedback = data.get("feedback", "")
        if not isinstance(feedback, str) or len(feedback) > 20000:
            raise ValueError()
        attempt.teacher_score, attempt.teacher_feedback = score, feedback
        attempt.save(update_fields=["teacher_score", "teacher_feedback"])
        return JsonResponse({"attempt": attempt_data(attempt, True)})
    except (ValueError, TypeError, UnicodeDecodeError):
        return JsonResponse({"error": "Use a score from 0 to 100 and text feedback."}, status=400)


@authenticated
@require_http_methods(["GET"])
def reports(request, classroom_id):
    room = Classroom.objects.filter(pk=classroom_id, teacher=request.account).first()
    if request.account.role != "teacher" or room is None:
        return JsonResponse({"error": "Classroom not found."}, status=404)
    rows = AssignmentAttempt.objects.filter(assignment__classroom=room,
        student__enrollments__classroom=room).select_related("assignment__classroom", "student").prefetch_related("events").order_by("-id")
    try:
        if request.GET.get("assignment_id"):
            rows = rows.filter(assignment_id=int(request.GET["assignment_id"]))
    except ValueError:
        return JsonResponse({"error": "Invalid assignment filter."}, status=400)
    records = [attempt_data(row, True) for row in rows]
    students = [{"id": e.student_id, "name": e.student.name} for e in room.enrollments.select_related("student")]
    if request.GET.get("format") == "csv":
        text = io.StringIO()
        writer = csv.writer(text)
        writer.writerow(["Student", "Assignment", "Status", "Test score", "Teacher score", "Page hidden events", "Paste events", "Blocked pastes", "Window blur events", "Late", "Submitted", "Viva answer", "Teacher feedback"])
        def safe(value):
            value = str(value if value is not None else "")
            return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value
        for row in records:
            counts = row["event_counts"]
            writer.writerow([safe(value) for value in [row["student_name"], row["assignment"]["title"], row["status"], row["test_score"], row["teacher_score"], counts.get("page_hidden", 0), counts.get("paste", 0), counts.get("paste_blocked", 0), counts.get("window_blur", 0), row["late"], row["submitted_at"], row["viva_answer"], row["teacher_feedback"]]])
        response = HttpResponse(text.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="classroom-reports.csv"'
        return response
    return JsonResponse({"reports": records, "students": students,
        "note": "A hidden page or pasted code needs human review; it does not establish cheating."})
