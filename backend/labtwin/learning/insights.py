"""Factual reports with inspectable denominators and retained evidence."""
from collections import Counter
from statistics import mean

from ..models import Enrollment, TopicMastery, LearningEvidence, MasterySnapshot, ResourceStudy, AssignmentAttempt, VivaTurn
from .mastery import learning_path
from .ai import structured_completion


def average(values):
    values = [float(v) for v in values if v is not None]
    return round(mean(values), 1) if values else None


def comparable_history(student, topic):
    current = TopicMastery.objects.filter(student=student, topic=topic).first()
    model = current.model_version if current else "legacy-weighted-v1"
    return [h for h in MasterySnapshot.objects.filter(student=student, topic=topic).order_by("id")
            if h.evidence.get("model", "legacy-weighted-v1") == model and h.state != "Not Started"]


def progress_report(student, course):
    path = learning_path(student, course)
    evidence = LearningEvidence.objects.filter(student=student, topic__course=course)
    improvements = []
    for topic in course.topics.all():
        history = comparable_history(student, topic)
        if len(history) >= 2 and history[-1].score > history[0].score:
            improvements.append({"topic": topic.name, "from": history[0].score, "to": history[-1].score, "change": round(history[-1].score - history[0].score, 1), "evidence_ids": list(evidence.filter(topic=topic).values_list("id", flat=True))})
    visits = ResourceStudy.objects.filter(student=student, unit__material__course=course).select_related("unit__material").order_by("-id")[:30]
    studied = [{"title": v.unit.material.title, "page": v.unit.page_number, "slide": v.unit.slide_number, "timestamp": v.unit.start_seconds, "seconds_viewed": v.seconds_viewed, "opened_at": v.created_at.isoformat(), "source_id": v.unit.chunks.order_by("position").values_list("id", flat=True).first()} for v in visits]
    strongest = [row for row in path["topics"] if row["state"] == "Strong"]
    weak = [row for row in path["topics"] if row["state"] in ("Needs Practice", "Developing")]
    code = list(evidence.filter(kind="programming", score__isnull=False))
    viva = list(evidence.filter(kind="viva", score__isnull=False))
    mode = "evidence_rules"
    result = None if course.is_demo or not path["tasks"] else structured_completion("Prioritize the supplied learning tasks using only their evidence. Return JSON {ordered_topic_ids:[integer]}. Select only provided IDs, each once. Do not invent judgments or topics.", {"tasks": [{"topic_id": t["topic_id"], "reason": t["reason"]} for t in path["tasks"]]}, 300)
    if result and isinstance(result.get("ordered_topic_ids"), list) and all(isinstance(pk, int) and not isinstance(pk, bool) for pk in result["ordered_topic_ids"]) and set(result["ordered_topic_ids"]) == {t["topic_id"] for t in path["tasks"]} and len(result["ordered_topic_ids"]) == len(path["tasks"]):
        indexed = {t["topic_id"]: t for t in path["tasks"]}
        path["tasks"] = [indexed[pk] for pk in result["ordered_topic_ids"]]
        mode = "ai_prioritized_evidence"
    return {"student_id": student.id, "student": student.name, "course": course.name, "topics": path["topics"], "strongest_topics": strongest, "needs_practice": weak, "recent_improvements": improvements, "programming": {"average_score": average([e.score for e in code]), "attempts": len(code)}, "viva": {"average_score": average([e.score for e in viva]), "answers": len(viva), "provisional_answers": sum(not e.verified for e in viva)}, "resources_studied": studied, "next_steps": path["tasks"], "recommendations_mode": mode, "summary": f"{len(strongest)} strong topics, {len(weak)} topics developing or needing practice, and {len(improvements)} topics with recorded improvement. Programming results are based on {len(code)} scored attempts; viva feedback includes provisional estimates.", "resource_note": "Resource entries record openings and self-reported viewing time; they do not establish comprehension.", "method": path["method"]}


def teacher_insights(course):
    students = list(Enrollment.objects.filter(classroom=course.classroom).select_related("student"))
    student_ids = [entry.student_id for entry in students]
    names = {e.student_id: e.student.name for e in students}
    mastery = list(TopicMastery.objects.filter(topic__course=course, student_id__in=student_ids).select_related("topic"))
    evidence = list(LearningEvidence.objects.filter(topic__course=course, student_id__in=student_ids).select_related("topic", "student").order_by("id"))
    topics, observations = [], []
    for topic in course.topics.all():
        rows = [m for m in mastery if m.topic_id == topic.id]
        assessed = [m for m in rows if m.state != "Not Started"]
        struggling = [m for m in assessed if m.score < 50]
        topic_evidence = [e for e in evidence if e.topic_id == topic.id]
        support = [{"student_id": m.student_id, "student": names[m.student_id], "score": m.score, "state": m.state, "attempts": m.attempts, "hint_level": m.average_hint_level, "evidence_ids": [e.id for e in topic_evidence if e.student_id == m.student_id]} for m in rows]
        topics.append({"id": topic.id, "name": topic.name, "average_mastery": average([m.score for m in assessed]), "assessed_students": len(assessed), "enrolled_students": len(students), "needs_practice": len(struggling), "strong": sum(m.state == "Strong" for m in assessed), "support": support})
        if assessed and struggling:
            percent = round(100 * len(struggling) / len(assessed))
            observations.append({"id": f"weak-{topic.id}", "topic_id": topic.id, "text": f"{percent}% of assessed students ({len(struggling)}/{len(assessed)}) need practice in {topic.name}.", "support": [row for row in support if row["score"] < 50]})
        improved = []
        for row in rows:
            snapshots = comparable_history(row.student_id, topic)
            if len(snapshots) >= 2 and snapshots[-1].score > snapshots[0].score:
                visits = ResourceStudy.objects.filter(student_id=row.student_id, unit__material__course=course, created_at__gte=snapshots[0].created_at, created_at__lte=snapshots[-1].created_at).select_related("unit__material")
                improved.append({"student_id": row.student_id, "student": names[row.student_id], "from": snapshots[0].score, "to": snapshots[-1].score, "resources_opened": sorted(set(v.unit.material.title for v in visits)), "evidence_ids": [e.id for e in topic_evidence if e.student_id == row.student_id]})
        if improved:
            observations.append({"id": f"improved-{topic.id}", "topic_id": topic.id, "text": f"{len(improved)} student(s) improved in {topic.name}. Inspect the before/after scores and resources opened during that period; this association does not establish a cause.", "support": improved})
    code = [e for e in evidence if e.kind == "programming" and e.score is not None]
    viva = [e for e in evidence if e.kind == "viva" and e.score is not None]
    quiz = [e for e in evidence if e.kind in ("quiz", "short_answer", "numerical", "diagnostic") and e.score is not None]
    hint_rows = [e for e in evidence if e.score is not None]
    misconceptions = Counter(e.misconception for e in code if e.misconception)
    assignments = list(course.classroom.assignments.filter(topic__course=course))
    expected = len(assignments) * len(students)
    completed = AssignmentAttempt.objects.filter(assignment__in=assignments, student_id__in=student_ids, status="submitted").values("assignment_id", "student_id").distinct().count()
    return {"course_id": course.id, "enrolled_students": len(students), "topics": topics, "observations": observations, "students_needing_support": [{"student_id": pk, "student": names[pk], "topics": [m.topic.name for m in mastery if m.student_id == pk and m.state == "Needs Practice"]} for pk in student_ids if any(m.student_id == pk and m.state == "Needs Practice" for m in mastery)], "common_misconceptions": [{"concept": text, "count": count, "evidence_ids": [e.id for e in code if e.misconception == text]} for text, count in misconceptions.most_common(10)], "average_attempts": average([m.attempts for m in mastery if m.attempts]), "hint_dependency": round(100 * sum(e.hint_level > 0 for e in hint_rows) / len(hint_rows), 1) if hint_rows else None, "assignment_completion": {"completed": completed, "expected": expected, "percent": round(100 * completed / expected, 1) if expected else None}, "assessment_performance": {"average_score": average([e.score for e in quiz]), "answers": len(quiz), "evidence_ids": [e.id for e in quiz]}, "programming_performance": {"average_score": average([e.score for e in code]), "attempts": len(code), "evidence_ids": [e.id for e in code]}, "viva_performance": {"average_score": average([e.score for e in viva]), "answers": len(viva), "provisional": sum(not e.verified for e in viva)}, "evidence": [{"id": e.id, "student_id": e.student_id, "student": e.student.name, "topic_id": e.topic_id, "topic": e.topic.name, "kind": e.kind, "score": e.score, "hint_level": e.hint_level, "attempt_number": e.attempt_number, "misconception": e.misconception, "verified": e.verified, "detail": e.detail, "created_at": e.created_at.isoformat()} for e in evidence[-200:]], "method": "Only currently enrolled students and this course's retained evidence are included. No activity-based misconduct judgments or mastery penalties."}
