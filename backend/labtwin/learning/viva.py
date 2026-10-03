import re

from ..models import VivaTurn, LearningEvidence, SourceChunk
from .ai import structured_completion
from .vectors import tokens
from .mastery import record_evidence, resources


def next_turn(session):
    topic = session.topic
    previous = list(session.turns.order_by("id").values("question", "answer", "feedback"))[-4:]
    evidence = LearningEvidence.objects.filter(student=session.student, topic=topic).exclude(misconception="").order_by("-id").first()
    sources = resources(topic)
    passage = SourceChunk.objects.filter(id__in=[s["id"] for s in sources], course=topic.course).first()
    rubric = [passage.text[:1200]] if passage else [topic.description or topic.name]
    if not previous:
        question = f"Explain the key invariant in your {topic.name} solution. How does your code preserve it?"
    else:
        question = f"Apply your explanation of {topic.name} to an empty input or a boundary case. Which operation changes, and why?" if len(previous) % 2 else f"What would fail if you reversed the order of the main updates in your {topic.name} code?"
    if session.verification and not previous:
        question = f"Fresh conceptual check: trace one important update in your submitted {topic.name} code and explain why it is necessary."
    result = None if topic.course.is_demo else structured_completion("Create one conceptual viva question grounded in the supplied code, teaching passage and prior answers. Follow up on weaknesses without supplying solutions. Return JSON {question:string,rubric:[string]}. Activity is not proof of misconduct.", {"topic": topic.name, "code": session.code[:15000], "passage": rubric, "previous_answers": previous, "weakness": evidence.misconception if evidence else "", "fresh_verification": session.verification}, 700)
    if result and isinstance(result.get("question"), str) and isinstance(result.get("rubric"), list) and all(isinstance(v, str) for v in result["rubric"]):
        question, rubric = result["question"][:2000], result["rubric"][:6]
    return VivaTurn.objects.create(session=session, question=question, rubric=rubric)


def evaluate_turn(turn, answer):
    expected = " ".join(turn.rubric)
    reference_terms = set(tokens(expected))
    overlap = set(tokens(answer)) & reference_terms
    score = min(100, round(100 * len(overlap) / max(1, min(12, len(reference_terms)))))
    feedback = "Provisional source-keyword check: review the cited concept and explain the steps in your own words. Your teacher can review this estimate."
    mode = "source_keyword_estimate"
    result = None if turn.session.topic.course.is_demo else structured_completion("Assess a student's conceptual viva answer against ONLY the source rubric and submitted work. Return JSON {score:number,feedback:string,misconception:string}. Score 0–100. This is provisional educational feedback, not a misconduct judgment. Do not disclose hidden tests or provide a full solution.", {"question": turn.question, "answer": answer, "rubric": turn.rubric, "code": turn.session.code[:12000]}, 700)
    if result and isinstance(result.get("score"), (int, float)) and not isinstance(result["score"], bool) and 0 <= result["score"] <= 100 and isinstance(result.get("feedback"), str):
        score, feedback, mode = result["score"], result["feedback"][:4000], "ai_rubric_estimate"
    turn.answer, turn.score, turn.feedback, turn.assessment_mode = answer, score, feedback, mode
    from django.utils import timezone
    turn.answered_at = timezone.now()
    turn.save()
    record_evidence(turn.session.student, turn.session.topic, f"viva:{turn.id}", "viva", score, verified=False, misconception="Explain the conceptual invariant more clearly." if score < 60 else "", detail={"session_id": turn.session_id, "turn_id": turn.id, "assessment_mode": mode})
    return turn


def session_data(session):
    from .sources import citations_for
    return {"id": session.id, "topic": session.topic.name, "topic_id": session.topic_id, "verification": session.verification, "reason": session.reason, "resources": citations_for(session.topic.course, session.source_ids), "turns": [{"id": t.id, "question": t.question, "answer": t.answer, "score": t.score, "feedback": t.feedback, "assessment_mode": t.assessment_mode} for t in session.turns.order_by("id")]}
