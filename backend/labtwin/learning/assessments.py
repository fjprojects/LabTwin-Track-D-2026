"""Scoped diagnostic/quiz sessions and evidence-backed post-assessment reports."""
from django.db import transaction
from django.utils import timezone

from ..models import AssessmentSession, TopicMastery, PracticeAttempt
from .access import LearningError
from .mastery import mastery_data
from .novelty import repetition_rate
from .practice import generate_question, question_data
from .vectors import embedding_backend


def scoped_topics(course, student, scope):
    topics = list(course.topics.all())
    selection = scope.get("selection", "all")
    if selection == "weak":
        strong = set(TopicMastery.objects.filter(student=student, topic__course=course, state="Strong").values_list("topic_id", flat=True))
        return [t for t in topics if t.id not in strong and t.parent_id is None]
    ids = scope.get("topic_ids", [])
    if ids:
        if not isinstance(ids, list) or any(type(pk) is not int for pk in ids) or not set(ids).issubset({t.id for t in topics}):
            raise LearningError("Assessment topics must belong to this course.")
        selected = set(ids)
        changed = True
        while changed:
            before = len(selected)
            selected.update(t.id for t in topics if t.parent_id in selected)
            changed = len(selected) != before
        return [t for t in topics if t.id in selected]
    label = str(scope.get("label", "")).strip()
    if label:
        return [t for t in topics if label.casefold() in t.name.casefold() or label.casefold() in t.description.casefold()]
    return [t for t in topics if t.parent_id is None]


@transaction.atomic
def create_session(student, course, data):
    kind = data.get("kind", "quiz")
    if kind not in ("quiz", "mock_exam", "diagnostic"):
        raise LearningError("Choose quiz, mock exam or diagnostic.")
    scope = data.get("scope", {})
    if not isinstance(scope, dict):
        raise LearningError("Choose a valid assessment scope.")
    topics = scoped_topics(course, student, scope)
    if not topics:
        raise LearningError("No topics match this scope.", 409)
    count = int(data.get("count", 3))
    if not 1 <= count <= 20:
        raise LearningError("Choose 1–20 questions.")
    formats = data.get("formats", ["quiz", "short_answer", "numerical"])
    if not isinstance(formats, list) or not formats or any(f not in ("quiz", "short_answer", "numerical", "code") for f in formats):
        raise LearningError("Choose supported question formats.")
    session = AssessmentSession.objects.create(student=student, course=course, kind=kind, scope=scope,
        report={"initial_mastery": [mastery_data(student, topic) for topic in topics], "requested_count": count})
    unavailable = []
    for index in range(count):
        delivered = False
        for shift in range(len(topics)):
            topic = topics[(index + shift) % len(topics)]
            for offset in range(len(formats)):
                try:
                    generate_question(student, course, topic, formats[(index + offset) % len(formats)], session, diagnostic=kind == "diagnostic")
                    delivered = True
                    break
                except LearningError as error:
                    if error.status != 409:
                        raise
            if delivered:
                break
        if not delivered:
            unavailable.append(f"Question {index + 1}: no remaining verified candidate in the chosen scope.")
            break
    if not session.questions.exists():
        raise LearningError("No verified questions are available for this assessment. Add source material or teacher questions.", 409)
    session.report["generation_notes"] = unavailable
    session.save(update_fields=["report"])
    return session


def session_data(session):
    from .camera import camera_policy, camera_summary
    return {"id": session.id, "kind": session.kind, "scope": session.scope, "status": session.status,
            "created_at": session.created_at.isoformat(), "camera_policy": camera_policy(session.course), "camera_summary": camera_summary(session), "questions": [question_data(q) for q in session.questions.select_related("topic__course").order_by("id")],
            "report": session.report if session.status == "completed" else {"generation_notes": session.report.get("generation_notes", [])}}


def assessment_report(session):
    questions = list(session.questions.select_related("topic__course").order_by("id"))
    attempts = [q.attempts.exclude(status="failed").order_by("-id").first() for q in questions]
    scored = [a for a in attempts if a and a.status == "completed" and a.score is not None]
    topic_ids = {q.topic_id for q in questions}
    topics = list(session.course.topics.filter(pk__in=topic_ids))
    current = [mastery_data(session.student, t) for t in topics]
    initial = {row["topic_id"]: row for row in session.report.get("initial_mastery", [])}
    report = {**session.report, "score": round(sum(a.score for a in scored) / len(scored), 1) if scored else None,
        "answered": sum(a is not None for a in attempts), "scored": len(scored), "total": len(questions),
        "pending_review": sum(bool(a and a.status == "pending_review") for a in attempts),
        "strong_topics": [r["topic"] for r in current if r["state"] == "Strong"],
        "weak_topics": [r["topic"] for r in current if r["state"] != "Strong"],
        "misconceptions": list(dict.fromkeys(a.misconception for a in scored if a.misconception)),
        "recommended_revision": [r for r in current if r["state"] != "Strong"],
        "mastery_changes": [{"topic": r["topic"], "before": initial.get(r["topic_id"], {}).get("score") if initial.get(r["topic_id"], {}).get("state") != "Not Started" else None, "after": r["score"], "state": r["state"], "model": r["model"]} for r in current],
        "question_repetition": repetition_rate(questions, embedding_backend(session.course)),
        "interpretation": "Mastery is a model estimate from scored evidence; a percentage gain is not proof of a causal learning effect."}
    complete = all(a and a.status in ("completed", "pending_review") for a in attempts)
    session.status = "completed" if complete else "in_progress"
    session.completed_at = timezone.now() if complete else None
    session.report = report
    session.save(update_fields=["status", "completed_at", "report"])
    return report
