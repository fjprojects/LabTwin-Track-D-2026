from django.http import JsonResponse
from django.db import transaction

from ..models import AssessmentSession, PracticeAttempt, LearningEvidence, AskExchange
from .access import endpoint, payload, course_for, student_for, require_student, authorized_courses, LearningError
from .assessments import create_session, session_data, assessment_report
from .mastery import record_evidence


@endpoint(["POST"])
def conversation_check(request, exchange_id):
    require_student(request.account)
    exchange = AskExchange.objects.select_related("course").filter(pk=exchange_id, account=request.account,
        course__in=authorized_courses(request.account), grounded=True).first()
    if not exchange:
        raise LearningError("A source-backed conversation is required.", 404)
    names = [c.get("topic") for c in exchange.citations]
    topic = exchange.course.topics.filter(name__in=names).first()
    if not topic:
        raise LearningError("No assessed topic is associated with this conversation yet.", 409)
    from .practice import generate_question, question_data
    question = generate_question(request.account.student, exchange.course, topic, "short_answer", diagnostic=True)
    question.metadata["conversation_exchange_id"] = exchange.id
    question.save(update_fields=["metadata"])
    return JsonResponse({"question": question_data(question)}, status=201)


@endpoint(["GET", "POST"])
def sessions(request, course_id):
    course = course_for(request.account, course_id)
    if request.method == "POST":
        require_student(request.account)
        return JsonResponse({"assessment": session_data(create_session(request.account.student, course, payload(request)))}, status=201)
    student = student_for(request.account, course, request.GET.get("student_id"))
    return JsonResponse({"assessments": [session_data(s) for s in AssessmentSession.objects.filter(student=student, course=course).order_by("-id")[:25]]})


@endpoint(["GET", "POST"])
def detail(request, session_id):
    row = AssessmentSession.objects.select_related("course").filter(pk=session_id, course__in=authorized_courses(request.account)).first()
    if not row or (request.account.role == "student" and row.student_id != request.account.student_id):
        raise LearningError("Assessment not found.", 404)
    student_for(request.account, row.course, row.student_id)
    assessment_report(row)
    return JsonResponse({"assessment": session_data(row)})


@endpoint(["GET", "POST"], teacher=True)
def review(request, attempt_id=None, course_id=None):
    if request.method == "GET":
        course = course_for(request.account, course_id)
        rows = PracticeAttempt.objects.filter(question__topic__course=course, status="pending_review",
            question__student__enrollments__classroom=course.classroom).select_related("question__topic", "question__student")
        return JsonResponse({"attempts": [{"id": a.id, "student": a.question.student.name, "question": a.question.prompt,
            "answer": a.answer, "accepted": a.question.answer, "explanation": a.question.explanation} for a in rows]})
    attempt = PracticeAttempt.objects.select_related("question__topic__course", "question__student").filter(pk=attempt_id,
        question__topic__course__in=authorized_courses(request.account)).first()
    if not attempt:
        raise LearningError("Attempt not found.", 404)
    student_for(request.account, attempt.question.topic.course, attempt.question.student_id)
    data = payload(request)
    score = float(data.get("score"))
    if not 0 <= score <= 100:
        raise LearningError("Use a score from 0 to 100.")
    with transaction.atomic():
        if attempt.status != "pending_review":
            raise LearningError("This answer has already been reviewed.", 409)
        attempt.score, attempt.status = score, "completed"
        attempt.feedback.update(correct=score == 100, status="teacher_reviewed", explanation=str(data.get("feedback", attempt.question.explanation))[:5000])
        attempt.save()
        record_evidence(attempt.question.student, attempt.question.topic, f"practice-review:{attempt.id}", "short_answer", score,
            attempt.hint_level, attempt.question.attempts.count(), detail={"question_id": attempt.question_id, "attempt_id": attempt.id, "teacher_review": True})
    if attempt.question.assessment_id:
        assessment_report(attempt.question.assessment)
    return JsonResponse({"reviewed": True})
