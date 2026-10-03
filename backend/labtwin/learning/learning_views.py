import uuid

from django.db import IntegrityError, transaction
from django.http import JsonResponse

from ..models import PracticeQuestion, PracticeAttempt, QuestionBankItem, AssignmentAttempt, LearningEvidence, MasterySnapshot, VivaSession, VivaTurn
from ..assessment_views import attempt_access
from .access import endpoint, payload, LearningError, authorized_courses, course_for, topic_for, student_for, require_student, validate_sources
from .coaching import make_hint, conceptual_mistake
from .mastery import learning_path, mastery_data, resources, record_evidence
from .practice import generate_question, question_data, safe_test_results, grade, validate_bank
from .viva import next_turn, evaluate_turn, session_data


def own_question(account, question_id):
    question = PracticeQuestion.objects.select_related("topic__course").filter(pk=question_id, student=account.student, topic__course__in=authorized_courses(account)).first()
    if not question:
        raise LearningError("Practice question not found.", 404)
    return question


def own_assignment(account, attempt_id):
    attempt = AssignmentAttempt.objects.select_related("assignment__topic__course", "student").filter(pk=attempt_id, student=account.student).first()
    if not attempt or not attempt_access(account, attempt) or not attempt.assignment.topic_id:
        raise LearningError("Choose an assignment linked to a course topic.", 404)
    return attempt


@endpoint(["GET"])
def path_view(request, course_id):
    course = course_for(request.account, course_id)
    student = student_for(request.account, course, request.GET.get("student_id"))
    return JsonResponse(learning_path(student, course))


@endpoint(["GET"])
def topic_detail(request, topic_id):
    topic = topic_for(request.account, topic_id)
    student = student_for(request.account, topic.course, request.GET.get("student_id"))
    evidence = LearningEvidence.objects.filter(student=student, topic=topic).order_by("-id")[:40]
    history = MasterySnapshot.objects.filter(student=student, topic=topic).order_by("created_at", "id")
    return JsonResponse({**mastery_data(student, topic), "history": [{"score": h.score, "state": h.state, "created_at": h.created_at.isoformat(), "evidence": h.evidence} for h in history[:100]], "evidence": [{"id": e.id, "kind": e.kind, "score": e.score, "hint_level": e.hint_level, "misconception": e.misconception, "verified": e.verified, "detail": e.detail, "created_at": e.created_at.isoformat()} for e in evidence], "completed_questions": [{"id": q.id, "prompt": q.prompt} for q in PracticeQuestion.objects.filter(student=student, topic=topic, attempts__status="completed").distinct()[:30]]})


@endpoint(["GET", "POST"], teacher=True)
def bank(request, topic_id):
    topic = topic_for(request.account, topic_id)
    if request.method == "GET":
        return JsonResponse({"questions": [{"id": q.id, "title": q.title, "prompt": q.prompt, "kind": q.kind, "difficulty": q.difficulty, "language": q.language, "options": q.options, "answer": q.answer, "tests": q.tests, "starter_code": q.starter_code, "source_ids": q.source_ids} for q in topic.question_bank.all()]})
    data = payload(request)
    values = validate_bank(data)
    ids = validate_sources(topic.course, data.get("source_ids", []))
    item = QuestionBankItem.objects.create(topic=topic, source_ids=ids, **values)
    return JsonResponse({"id": item.id}, status=201)


@endpoint(["GET", "POST"])
def practice(request, course_id):
    require_student(request.account)
    course = course_for(request.account, course_id)
    if request.method == "GET":
        return JsonResponse({"questions": [question_data(q) for q in PracticeQuestion.objects.filter(student=request.account.student, topic__course=course).select_related("topic__course").order_by("-id")[:30]]})
    data = payload(request)
    topic = topic_for(request.account, data["topic_id"]) if data.get("topic_id") else None
    if topic and topic.course_id != course.id:
        raise LearningError("Choose a topic from this course.")
    kind = data.get("kind") or None
    if kind not in (None, "quiz", "code", "short_answer", "numerical"):
        raise LearningError("Choose a supported question format.")
    return JsonResponse({"question": question_data(generate_question(request.account.student, course, topic, kind))}, status=201)


def practice_attempt_data(attempt):
    return {"id": attempt.id, "status": attempt.status, "score": attempt.score, "code": attempt.code, "answer": attempt.answer, "test_results": safe_test_results(attempt.test_results), "error": attempt.error, "mistake": attempt.misconception, "hint_level": attempt.hint_level, "feedback": attempt.feedback}


@endpoint(["GET", "POST"])
def practice_attempts(request, question_id):
    require_student(request.account)
    question = own_question(request.account, question_id)
    if request.method == "GET":
        return JsonResponse({"attempts": [practice_attempt_data(a) for a in question.attempts.order_by("-id")]})
    data = payload(request)
    request_id = str(data.get("request_id", ""))
    try:
        uuid.UUID(request_id)
    except ValueError as exc:
        raise LearningError("A unique request_id UUID is required to safely save your attempt.") from exc
    code, answer = data.get("code", ""), data.get("answer", "")
    if not isinstance(code, str) or len(code) > 100000 or not isinstance(answer, (str, int)) or len(str(answer)) > 20000:
        raise LearningError("Invalid code or answer.")
    with transaction.atomic():
        # Serialize request IDs on the question; duplicate network retries never
        # execute code twice or create duplicate mastery evidence.
        PracticeQuestion.objects.select_for_update().get(pk=question.pk)
        attempt, created = PracticeAttempt.objects.get_or_create(question=question, request_id=request_id, defaults={"code": code, "answer": str(answer), "hint_level": question.hints.order_by("-level").values_list("level", flat=True).first() or 0})
    if not created:
        return JsonResponse({"attempt": practice_attempt_data(attempt)})
    try:
        score, results = grade(question, code, answer)
        from ..models import TopicMastery
        from .sources import citations_for
        before = TopicMastery.objects.filter(student=request.account.student, topic=question.topic).first()
        before_score = before.score if before else None
        attempt.score, attempt.test_results, attempt.status = score, results, "completed" if score is not None else "pending_review"
        attempt.misconception = conceptual_mistake(question.topic, code, score) if score is not None and score < 100 and question.kind == "code" else ""
        attempt.feedback = {"correct": score == 100 if score is not None else None, "status": attempt.status,
            "explanation": question.explanation or ("Hidden checks assess observable program behavior; use the progressive hints to investigate the likely concept." if question.kind == "code" else "Compare your answer with the cited course explanation."),
            "resources": citations_for(question.topic.course, question.source_ids) or resources(question.topic),
            "misconception": attempt.misconception, "review_note": "Your teacher will review this open-ended answer." if score is None else ""}
        attempt.save()
        evidence_kind = "conversation" if question.metadata.get("conversation_exchange_id") else "programming" if question.kind == "code" else question.kind
        mastery = record_evidence(request.account.student, question.topic, f"practice:{attempt.id}", evidence_kind, score, attempt.hint_level, question.attempts.count(), attempt.misconception,
            detail={"question_id": question.id, "attempt_id": attempt.id, "difficulty": question.difficulty, "option_count": len(question.options) if question.kind == "quiz" else None, "assessment_id": question.assessment_id})
        attempt.feedback["mastery_impact"] = {"before": before_score, "after": mastery.score, "state": mastery.state, "model": mastery.model_version}
        attempt.save(update_fields=["feedback"])
        if question.assessment_id:
            from .assessments import assessment_report
            assessment_report(question.assessment)
        return JsonResponse({"attempt": practice_attempt_data(attempt), "mastery": {"score": mastery.score, "state": mastery.state}})
    except Exception as error:
        attempt.status = "failed"
        attempt.error = error.message if isinstance(error, LearningError) else "Execution could not finish. Your code and answer were saved; submit a new attempt when the runner is available."
        attempt.save(update_fields=["status", "error"])
        return JsonResponse({"attempt": practice_attempt_data(attempt)}, status=error.status if isinstance(error, LearningError) else 503)


@endpoint(["POST"])
def hint(request):
    require_student(request.account)
    data = payload(request)
    level = int(data.get("level", 1))
    if not 1 <= level <= 3:
        raise LearningError("Choose hint 1, 2 or 3.")
    if data.get("question_id"):
        question = own_question(request.account, data["question_id"])
        attempt = question.attempts.order_by("-id").first()
        topic, assignment, code, score = question.topic, None, str(data.get("code", attempt.code if attempt else ""))[:100000], attempt.score if attempt else None
    else:
        assignment = own_assignment(request.account, data.get("assignment_attempt_id"))
        question, topic, code, score = None, assignment.assignment.topic, assignment.code, assignment.test_score
    return JsonResponse(make_hint(request.account.student, topic, code, score, level, question, assignment))


@endpoint(["GET"])
def solution(request, question_id):
    require_student(request.account)
    question = own_question(request.account, question_id)
    if not question.topic.course.allow_solutions or not question.solution:
        raise LearningError("Full solutions are disabled by your teacher.", 403)
    return JsonResponse({"solution": question.solution})


@endpoint(["GET", "POST"])
def vivas(request, course_id):
    require_student(request.account)
    course = course_for(request.account, course_id)
    if request.method == "GET":
        return JsonResponse({"sessions": [session_data(s) for s in VivaSession.objects.filter(student=request.account.student, topic__course=course).select_related("topic__course").order_by("-id")[:20]]})
    data = payload(request)
    question, assignment = None, None
    if data.get("assignment_attempt_id"):
        assignment = own_assignment(request.account, data["assignment_attempt_id"])
        topic, code = assignment.assignment.topic, assignment.code
    elif data.get("question_id"):
        question = own_question(request.account, data["question_id"])
        topic = question.topic
        latest = question.attempts.order_by("-id").first()
        code = latest.code if latest else question.starter_code
    else:
        topic, code = topic_for(request.account, data.get("topic_id")), ""
    if topic.course_id != course.id:
        raise LearningError("Choose a topic from this course.")
    activity = bool(assignment and assignment.events.filter(kind__in=["page_hidden", "paste", "paste_blocked", "window_blur"]).exists())
    verification = bool(course.activity_verification and activity)
    sources = resources(topic)
    session = VivaSession.objects.create(student=request.account.student, topic=topic, question=question, assignment_attempt=assignment, code=code, source_ids=[s["id"] for s in sources], verification=verification, reason="A fresh conceptual question checks understanding. Browser observations are available for teacher review and do not prove misconduct." if verification else "Questions use your submitted work, course materials and previous conceptual evidence.")
    next_turn(session)
    return JsonResponse({"session": session_data(session)}, status=201)


@endpoint(["POST"])
def answer_viva(request, session_id):
    require_student(request.account)
    session = VivaSession.objects.select_related("topic__course").filter(pk=session_id, student=request.account.student, topic__course__in=authorized_courses(request.account)).first()
    if not session:
        raise LearningError("Viva not found.", 404)
    data = payload(request)
    answer = str(data.get("answer", "")).strip()
    if not answer or len(answer) > 20000:
        raise LearningError("Enter an answer of up to 20,000 characters.")
    with transaction.atomic():
        turn = VivaTurn.objects.select_for_update().filter(pk=data.get("turn_id"), session=session).first()
        if not turn or turn.answered_at:
            raise LearningError("This viva question has already been answered or is unavailable.", 409)
        evaluate_turn(turn, answer)
    if session.turns.count() < 5:
        next_turn(session)
    return JsonResponse({"session": session_data(session)})
