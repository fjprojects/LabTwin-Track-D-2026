import csv
import io
import math

from django.db import transaction
from django.http import HttpResponse, JsonResponse

from ..models import VivaTurn, LearningEvidence, Enrollment, PracticeAttempt, AssignmentAttempt, StudentResponse
from .access import endpoint, course_for, student_for, payload, LearningError, authorized_courses
from .insights import progress_report, teacher_insights
from .mastery import record_evidence
from .sources import citations_for


@endpoint(["GET"])
def report(request, course_id):
    course = course_for(request.account, course_id)
    student = student_for(request.account, course, request.GET.get("student_id"))
    return JsonResponse(progress_report(student, course))


@endpoint(["GET"], teacher=True)
def insights(request, course_id):
    course = course_for(request.account, course_id)
    data = teacher_insights(course)
    if request.GET.get("format") == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["student", "topic", "kind", "score", "hint_level", "attempt", "provisional", "misconception", "created_at", "evidence_id"])
        for e in data["evidence"]:
            def cell(value):
                return "'" + value if isinstance(value, str) and value.startswith(("=", "+", "-", "@")) else value
            writer.writerow([cell(e["student"]), cell(e["topic"]), e["kind"], e["score"], e["hint_level"], e["attempt_number"], not e["verified"], cell(e["misconception"]), e["created_at"], e["id"]])
        response = HttpResponse(buffer.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="labtwin-learning-evidence.csv"'
        return response
    return JsonResponse(data)


@endpoint(["GET"], teacher=True)
def teacher_vivas(request, course_id):
    course = course_for(request.account, course_id)
    rows = VivaTurn.objects.filter(session__topic__course=course, session__student__enrollments__classroom=course.classroom).select_related("session__student", "session__topic").order_by("-id")[:100]
    return JsonResponse({"answers": [{"id": t.id, "student": t.session.student.name, "student_id": t.session.student_id, "topic": t.session.topic.name, "question": t.question, "answer": t.answer, "score": t.score, "feedback": t.feedback, "assessment_mode": t.assessment_mode, "verification": t.session.verification} for t in rows]})


@endpoint(["GET"], teacher=True)
def evidence_detail(request, evidence_id):
    evidence = LearningEvidence.objects.select_related("topic__course__classroom", "student").filter(pk=evidence_id, topic__course__in=authorized_courses(request.account)).first()
    if not evidence or not Enrollment.objects.filter(classroom=evidence.topic.course.classroom, student=evidence.student).exists():
        raise LearningError("Evidence not found in this classroom.", 404)
    detail = evidence.detail
    result = {"id": evidence.id, "student": evidence.student.name, "topic": evidence.topic.name, "score": evidence.score, "misconception": evidence.misconception, "kind": evidence.kind}
    if detail.get("assignment_id"):
        attempt = AssignmentAttempt.objects.filter(pk=detail.get("attempt_id"), student=evidence.student, assignment__topic=evidence.topic).select_related("student", "assignment__classroom").first()
        if attempt:
            from ..assessment_views import attempt_data
            result["assignment_attempt"] = attempt_data(attempt, teacher=True)
    elif detail.get("question_id"):
        attempt = PracticeAttempt.objects.select_related("question").filter(pk=detail.get("attempt_id"), question__student=evidence.student, question__topic=evidence.topic).first()
        if attempt:
            result.update(prompt=attempt.question.prompt, code=attempt.code, answer=attempt.answer, tests=attempt.test_results, reason=attempt.question.reason, resources=citations_for(evidence.topic.course, attempt.question.source_ids))
    elif detail.get("turn_id"):
        turn = VivaTurn.objects.filter(pk=detail["turn_id"], session__student=evidence.student, session__topic=evidence.topic).first()
        if turn:
            result.update(prompt=turn.question, answer=turn.answer, feedback=turn.feedback, assessment_mode=turn.assessment_mode, rubric=turn.rubric)
    elif detail.get("response_id"):
        row = StudentResponse.objects.filter(pk=detail["response_id"], student=evidence.student).first()
        if row:
            result.update(prompt=row.question, code=row.code, answer=row.viva_answer, feedback=row.result, tests=row.test_results)
    return JsonResponse(result)


@endpoint(["POST"], teacher=True)
def review_viva(request, turn_id):
    turn = VivaTurn.objects.select_related("session__topic__course", "session__student").filter(pk=turn_id, session__topic__course__in=authorized_courses(request.account), session__student__enrollments__classroom__teacher=request.account).distinct().first()
    if not turn or turn.score is None or not Enrollment.objects.filter(classroom=turn.session.topic.course.classroom, student=turn.session.student).exists():
        raise LearningError("Answered viva turn not found.", 404)
    data = payload(request)
    score, feedback = float(data.get("score")), str(data.get("feedback", ""))[:4000]
    if not math.isfinite(score) or not 0 <= score <= 100:
        raise LearningError("Use a score from 0 to 100.")
    with transaction.atomic():
        turn.score, turn.feedback, turn.assessment_mode = score, feedback, "teacher_reviewed"
        turn.save()
        # Supersede provisional evidence; preserve its audit detail.
        LearningEvidence.objects.filter(student=turn.session.student, topic=turn.session.topic, key=f"viva:{turn.id}").update(score=None)
        LearningEvidence.objects.filter(student=turn.session.student, topic=turn.session.topic, key__startswith=f"viva-review:{turn.id}:").update(score=None)
        record_evidence(turn.session.student, turn.session.topic, f"viva-review:{turn.id}:{turn.session.topic.evidence.count()}", "viva", score, verified=True, detail={"turn_id": turn.id, "reviewed_by": request.account.id})
    return JsonResponse({"reviewed": True})
