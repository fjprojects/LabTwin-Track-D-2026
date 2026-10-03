"""Explainable course mastery computed from retained learning evidence."""
import logging
import math

from django.db import transaction

from ..models import LearningEvidence, TopicMastery, MasterySnapshot, SourceChunk, CourseTopic
from .sources import citation

logger = logging.getLogger(__name__)


def state_for(score, count):
    return "Not Started" if not count else "Strong" if score >= 80 else "Developing" if score >= 50 else "Needs Practice"


@transaction.atomic
def record_evidence(student, topic, key, kind, score=None, hint_level=0, attempt_number=1, misconception="", verified=True, detail=None):
    if score is not None and (not math.isfinite(float(score)) or not 0 <= float(score) <= 100):
        raise ValueError("Invalid evidence score")
    row, created = LearningEvidence.objects.get_or_create(student=student, topic=topic, key=key, defaults={"kind": kind, "score": score, "hint_level": min(3, max(0, int(hint_level))), "attempt_number": max(1, int(attempt_number)), "misconception": misconception[:4000], "verified": verified, "detail": detail or {}})
    if not created:
        return TopicMastery.objects.get_or_create(student=student, topic=topic)[0]
    from .learner_model import replay, MODEL_VERSION
    evidence = list(LearningEvidence.objects.filter(student=student, topic=topic).order_by("created_at", "id"))
    before = TopicMastery.objects.filter(student=student, topic=topic).first()
    before_score = before.score if before else None
    probability, parameters, traces, observations = replay(topic, evidence)
    score_value = round(probability * 100, 1) if observations else 0
    hints = list(LearningEvidence.objects.filter(student=student, topic=topic).values_list("hint_level", flat=True))
    mastery, _ = TopicMastery.objects.update_or_create(student=student, topic=topic, defaults={"score": score_value, "state": state_for(score_value, observations), "attempts": observations, "knowledge_probability": probability, "model_version": MODEL_VERSION, "model_parameters": parameters, "average_hint_level": round(sum(hints) / len(hints), 2) if hints else 0})
    MasterySnapshot.objects.create(student=student, topic=topic, score=mastery.score, state=mastery.state, evidence={"evidence_id": row.id, "kind": kind, "score": score, "verified": verified, "model": MODEL_VERSION, "parameters": parameters, "previous_score": before_score, "update": next((trace for trace in traces if trace["evidence_id"] == row.id), {})})
    return mastery


def resources(topic, limit=4):
    rows = SourceChunk.objects.filter(course=topic.course, unit__material__status="ready", unit__archived=False).filter(unit__topic_name=topic.name).select_related("unit__material", "course__classroom").order_by("unit__material_id", "unit__number", "position")
    result, materials = [], set()
    for chunk in rows[:200]:
        if chunk.unit.material_id not in materials:
            result.append(citation(chunk)); materials.add(chunk.unit.material_id)
        if len(result) >= limit:
            break
    return result


def mastery_data(student, topic):
    row = TopicMastery.objects.filter(student=student, topic=topic).first()
    return {"topic_id": topic.id, "topic": topic.name, "score": row.score if row else 0, "state": row.state if row else "Not Started", "attempts": row.attempts if row else 0, "knowledge_probability": row.knowledge_probability if row and row.attempts else None, "model": row.model_version if row else "unassessed", "parameters": row.model_parameters if row else {}, "parent_id": topic.parent_id, "concepts": topic.concepts, "average_hint_level": row.average_hint_level if row else 0, "prerequisites": list(topic.prerequisites.values_list("id", flat=True)), "resources": resources(topic)}


def learning_path(student, course):
    rows = [mastery_data(student, topic) for topic in course.topics.prefetch_related("prerequisites")]
    indexed = {row["topic_id"]: row for row in rows}
    pending = sorted([row for row in rows if row["state"] != "Strong"], key=lambda row: (row["state"] == "Not Started", row["score"]))
    tasks = []
    seen = set()
    for row in pending:
        weak = [indexed[pk] for pk in row["prerequisites"] if pk in indexed and indexed[pk]["score"] < 50]
        target = weak[0] if weak else row
        if target["topic_id"] in seen:
            continue
        seen.add(target["topic_id"])
        tasks.append({"topic_id": target["topic_id"], "topic": target["topic"], "current_topic": row["topic"], "prerequisite_weakness": target["topic"] if weak else None, "reason": f"Reinforce {target['topic']} before {row['topic']}." if weak else f"{row['topic']} is {row['state'].lower()} based on {row['attempts']} scored attempts.", "resources": target["resources"], "steps": ["Review the source", "Practise", "Reassess"], "next_topic": row["topic"] if weak else next((other["topic"] for other in pending if other["topic_id"] != row["topic_id"]), "Consolidate strong topics")})
        if len(tasks) >= 3:
            break
    return {"topics": rows, "tasks": tasks, "diagnostic_recommended": any(row["state"] == "Not Started" and row["parent_id"] is None for row in rows), "method": "Bayesian Knowledge Tracing with reliability-weighted evidence. Unassessed topics are unknown; take a diagnostic. Provisional viva evidence has reduced reliability. Activity signals never affect mastery."}


def bridge_assignment(attempt):
    if not attempt.assignment.topic_id or attempt.test_score is None or attempt.status != "submitted":
        return
    try:
        from ..models import CoachingInteraction
        from .coaching import conceptual_mistake
        hint = CoachingInteraction.objects.filter(student=attempt.student, assignment_attempt__assignment=attempt.assignment, assignment_attempt_id__lte=attempt.id).order_by("-level").first()
        record_evidence(attempt.student, attempt.assignment.topic, f"assignment:{attempt.id}", "programming", attempt.test_score, hint.level if hint else 0, attempt.assignment.submissions.filter(student=attempt.student, id__lte=attempt.id).count(), conceptual_mistake(attempt.assignment.topic, attempt.code, attempt.test_score) if attempt.test_score < 100 else "", detail={"assignment_id": attempt.assignment_id, "attempt_id": attempt.id, "hidden_tests_passed": sum(bool(row.get("passed")) for row in attempt.test_results), "hidden_tests_total": len(attempt.test_results)})
    except Exception:
        logger.exception("Assignment mastery update deferred for attempt %s", attempt.id)


def bridge_response(entry):
    if entry.status != "completed" or not entry.test_results or entry.stage == "hint":
        return
    try:
        topics = CourseTopic.objects.filter(course__classroom__enrollments__student=entry.student, name__iexact=entry.topic).distinct()
        score = 100 * sum(bool(row.get("passed")) for row in entry.test_results) / len(entry.test_results)
        for topic in topics:
            record_evidence(entry.student, topic, f"legacy:{entry.id}", "programming", score, entry.context.get("hint_level", 0), misconception=str(entry.result.get("misconception", "")), detail={"response_id": entry.id})
            viva_score = entry.result.get("evaluation", {}).get("score")
            if entry.viva_answer and isinstance(viva_score, (int, float)) and not isinstance(viva_score, bool) and math.isfinite(viva_score) and 0 <= viva_score <= 100:
                record_evidence(entry.student, topic, f"legacy-viva:{entry.id}", "viva", viva_score, verified=False, detail={"response_id": entry.id, "assessment_mode": "legacy_ai_estimate"})
    except Exception:
        logger.exception("Legacy mastery update deferred for response %s", entry.id)
