"""Server-graded adaptive questions with explicit selection reasons."""
import json
import re

from ..models import QuestionBankItem, PracticeQuestion, TopicMastery, LearningEvidence, SourceChunk
from .access import LearningError
from .mastery import resources
from .ai import structured_completion


def choose_topic(student, course, requested=None):
    topics = list(course.topics.filter(parent__isnull=True).prefetch_related("prerequisites"))
    if not topics:
        raise LearningError("Your teacher needs to add course topics first.")
    scores = {row.topic_id: row.score for row in TopicMastery.objects.filter(student=student, topic__course=course)}
    available = [t for t in topics if t.question_bank.exists() or SourceChunk.objects.filter(course=course, unit__topic_name=t.name, unit__archived=False, unit__material__status="ready").exists()]
    if not requested and not available:
        raise LearningError("Add sources or teacher questions before starting practice.", 409)
    topic = requested or min(available, key=lambda t: (scores.get(t.id, 35), t.position))
    prerequisites = [t for t in topic.prerequisites.all() if scores.get(t.id, 0) < 50]
    return prerequisites[0] if prerequisites else topic, topic if prerequisites else None


def generate_question(student, course, requested=None, kind=None, assessment=None, diagnostic=False):
    from .question_generation import candidates
    from .question_verification import verify
    from .novelty import signature, vector, equivalent
    from .vectors import embedding_backend
    topic, target = choose_topic(student, course, requested)
    if diagnostic and requested:
        topic, target = requested, None
    mastery = TopicMastery.objects.filter(student=student, topic=topic).first()
    score = mastery.score if mastery else 0
    recent = list(LearningEvidence.objects.filter(student=student, topic=topic, score__isnull=False).order_by("-id")[:3])
    consistent = len(recent) >= 2 and all(e.score >= 80 and e.hint_level <= 1 for e in recent[:2])
    difficulty = 3 if score >= 80 and consistent else 2 if score >= 50 else 1
    previous = next((e for e in recent if e.misconception), None)
    reason = f"You had difficulty with {previous.misconception} LabTwin selected practice in {topic.name}." if previous else f"Your {topic.name} mastery is {mastery.state.lower() if mastery else 'not yet assessed'} ({score:.0f}%). This question checks the next appropriate step."
    if target:
        reason = f"{topic.name} is a prerequisite for {target.name}; strengthen it before moving ahead. " + reason
    if consistent:
        reason += " Two recent independent results support increasing difficulty."
    history = list(PracticeQuestion.objects.filter(student=student, topic__course=course).order_by("id"))
    banks = topic.question_bank.filter(difficulty__lte=difficulty).order_by("-difficulty", "id")
    if kind:
        banks = banks.filter(kind=kind)
    def all_candidates():
        for bank in banks:
            values = {key: getattr(bank, key) for key in ("kind", "difficulty", "prompt", "language", "options", "answer", "tests", "starter_code", "solution", "rubric", "source_ids", "explanation", "metadata")}
            yield values, bank
        chunks = list(SourceChunk.objects.filter(course=course, unit__archived=False, unit__material__status="ready", unit__topic_name=topic.name).select_related("unit__material").order_by("id")[:60])
        for values in candidates(chunks, topic, difficulty, kind):
            yield values, None
    for values, bank in all_candidates():
        if not isinstance(values.get("metadata"), dict) or not isinstance(values.get("answer"), dict):
            continue
        verification = verify(values, course, teacher_reviewed=bool(bank))
        if verification["status"] == "rejected":
            continue
        semantic = vector(values, course)
        if any(equivalent(values, prior, semantic, embedding_backend(course)) for prior in history):
            continue
        if values["difficulty"] != difficulty:
            reason += f" Available verified source questions currently support difficulty {values['difficulty']}; LabTwin does not relabel them as harder."
        return PracticeQuestion.objects.create(student=student, topic=topic, bank_item=bank, assessment=assessment,
            reason=("Diagnostic: establish your starting knowledge using your answers. " if diagnostic else "") + reason,
            verification_status=verification["status"], verification=verification, fingerprint=signature(values), semantic_vector=semantic, **values)
    raise LearningError("No new verified question is available in this scope and format. Choose another topic or ask your teacher to add source material/questions.", 409)


def question_data(question):
    from .sources import citations_for
    return {"id": question.id, "topic_id": question.topic_id, "topic": question.topic.name, "kind": question.kind, "difficulty": question.difficulty, "prompt": question.prompt, "language": question.language, "options": question.options, "starter_code": question.starter_code, "reason": question.reason, "resources": citations_for(question.topic.course, question.source_ids) or resources(question.topic), "solution_available": bool(question.topic.course.allow_solutions and question.solution), "subtopic": question.metadata.get("subtopic", ""), "concepts": question.metadata.get("concepts", []), "verification": {"status": question.verification_status, "method": question.verification.get("method", ""), "checks": question.verification.get("checks", {})}, "assessment_id": question.assessment_id}


def safe_test_results(results):
    return [{"test": i + 1, "passed": bool(row.get("passed")), "success": bool(row.get("success", True))} for i, row in enumerate(results)]


def grade(question, code, answer):
    if question.kind == "code":
        if not code.strip():
            raise LearningError("Enter code before submitting.")
        from ..views import run_tests
        score, results = run_tests(code, question.tests, question.language)
        return score, results
    if question.kind == "numerical":
        from .question_verification import numerical_answer
        result = numerical_answer(answer, question.answer)
        if result is None:
            raise LearningError("Enter a finite number, optionally followed by the specified unit.")
        return (100 if result else 0), []
    if question.kind == "short_answer":
        from .question_verification import normalized
        if not str(answer).strip():
            raise LearningError("Enter your answer.")
        if normalized(answer) in [normalized(a) for a in question.answer.get("accepted", [])]:
            return 100, []
        # Objective fill-in answers can be marked wrong. Open-ended teacher
        # questions need review instead of a fabricated automatic judgment.
        if question.metadata.get("template") == "definition_blank" or question.answer.get("exact_match"):
            return 0, []
        return None, []
    expected = question.answer.get("correct_index")
    if not isinstance(expected, int):
        raise LearningError("This assessment has no valid answer key. Ask your teacher to review it.", 409)
    try:
        chosen = int(answer)
    except (ValueError, TypeError) as exc:
        raise LearningError("Choose an answer.") from exc
    if not 0 <= chosen < len(question.options):
        raise LearningError("Choose a valid option.")
    return (100 if chosen == expected else 0), []


def validate_bank(data):
    kind = data.get("kind", "quiz")
    if kind not in ("quiz", "code", "short_answer", "numerical") or not isinstance(data.get("prompt"), str) or not 1 <= len(data["prompt"]) <= 12000:
        raise LearningError("Choose MCQ, code, short answer or numerical and enter a question.")
    difficulty = int(data.get("difficulty", 1))
    if not 1 <= difficulty <= 3:
        raise LearningError("Difficulty must be 1, 2 or 3.")
    values = {"kind": kind, "difficulty": difficulty, "title": str(data.get("title", "Assessment"))[:200], "prompt": data["prompt"], "language": data.get("language", "Python"), "options": data.get("options", []), "answer": data.get("answer", {}), "tests": data.get("tests", []), "starter_code": str(data.get("starter_code", ""))[:100000], "solution": str(data.get("solution", ""))[:100000], "rubric": data.get("rubric", [])}
    if values["language"] not in ("Python", "C", "Java") or not isinstance(values["rubric"], list):
        raise LearningError("Use a supported language and a rubric list.")
    if kind == "quiz":
        options, answer = values["options"], values["answer"]
        if not isinstance(options, list) or not 2 <= len(options) <= 8 or any(not isinstance(v, str) or len(v) > 3000 for v in options) or not isinstance(answer, dict) or isinstance(answer.get("correct_index"), bool) or not isinstance(answer.get("correct_index"), int) or not 0 <= answer["correct_index"] < len(options):
            raise LearningError("A quiz needs 2–8 options and a valid correct_index answer key.")
        values["tests"] = []
    elif kind == "code":
        tests = values["tests"]
        if not isinstance(tests, list) or not 1 <= len(tests) <= 20 or any(not isinstance(t, dict) or any(not isinstance(t.get(k), str) or len(t[k]) > 10000 for k in ("input", "expected")) for t in tests):
            raise LearningError("Code assessments need 1–20 hidden input/output test cases.")
        values["options"], values["answer"] = [], {}
    elif kind == "short_answer":
        if not isinstance(values["answer"], dict) or not isinstance(values["answer"].get("accepted"), list) or not values["answer"]["accepted"] or any(not isinstance(a, str) or not a.strip() or len(a) > 5000 for a in values["answer"]["accepted"]):
            raise LearningError("Provide accepted short-answer examples.")
        values["tests"], values["options"] = [], []
    else:
        from .question_verification import numerical_answer
        if not isinstance(values["answer"], dict) or numerical_answer(values["answer"].get("value"), values["answer"]) is not True:
            raise LearningError("Provide a finite numerical value and a nonnegative tolerance.")
        values["tests"], values["options"] = [], []
    values["explanation"] = str(data.get("explanation", ""))[:5000]
    values["metadata"] = {"teacher_authored": True, "subtopic": str(data.get("subtopic", ""))[:200]}
    return values
