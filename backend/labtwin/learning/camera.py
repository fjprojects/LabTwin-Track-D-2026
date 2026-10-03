"""Assessment camera observations and voluntary checks, independent of grading.

Frames and face geometry stay on the student's device. These client-reported,
fallible observations cannot establish intent, understanding or misconduct.
"""
from collections import Counter
from django.db import transaction
from django.utils.dateparse import parse_datetime

from ..models import AssessmentCameraEvent
from .access import LearningError
from .sources import citations_for

OBSERVATION_NOTE = "Camera and browser observations are fallible student-device reports, not proof of copying. They do not change grades or mastery."
KINDS = {"camera_started", "camera_stopped", "camera_calibrated", "camera_cue",
         "permission_denied", "camera_unavailable", "camera_analysis_error", "page_return", "paste"}
REASONS = {"head_turned", "face_absent"}


def camera_policy(course):
    return {"enabled": course.camera_cues_enabled, "offer_eye_closure": course.camera_eye_closure,
            "verification_enabled": course.activity_verification, "sustain_ms": 8000,
            "cooldown_ms": 60000, "model": "mediapipe-face-landmarker-v1",
            "interpretation": OBSERVATION_NOTE}


def camera_summary(session):
    rows = list(session.camera_events.all())
    counts = Counter(row.kind for row in rows)
    cues = Counter(row.detail.get("reason") for row in rows if row.kind == "camera_cue")
    return {"counts": dict(counts), "cues": dict(cues), "total": len(rows),
            "verification_answers": sum(row.detail.get("verification", {}).get("status") == "answered" for row in rows),
            "interpretation": OBSERVATION_NOTE}


def event_data(row):
    return {"id": row.id, "event_id": row.event_id, "kind": row.kind, "question_id": row.question_id,
            "detail": row.detail, "created_at": row.created_at.isoformat()}


def safe_detail(item):
    detail = item.get("detail", {})
    if not isinstance(detail, dict):
        raise LearningError("Use an object for camera event details.")
    # Allowlisted scalar facts only: never frames, landmark arrays, device IDs,
    # clipboard text, visited URLs or caller-supplied cheating judgments.
    clean = {}
    observed = detail.get("observed_at")
    if isinstance(observed, str) and len(observed) <= 40 and parse_datetime(observed):
        clean["observed_at"] = observed
    for key, limit in (("duration_ms", 600000), ("characters", 1000000)):
        value = detail.get(key)
        if type(value) is int and 0 <= value <= limit:
            clean[key] = value
    for key in ("consent", "allow_eye_closure", "analysis_enabled"):
        if key in detail:
            if type(detail[key]) is not bool:
                raise LearningError("Camera consent settings must be true or false.")
            clean[key] = detail[key]
    if item["kind"] == "camera_cue":
        if detail.get("reason") not in REASONS or clean.get("duration_ms", 0) < 8000:
            raise LearningError("Use a sustained head-turn or face-absence observation.")
        clean.update(reason=detail["reason"], method="on_device_head_pose_heuristic")
    return clean


def instruction(kind, detail):
    if kind == "camera_cue" and detail["reason"] == "face_absent":
        return "Your face has not been visible for several seconds. If you want camera cues, adjust the lighting or framing. You can stop the camera at any time."
    if kind == "camera_cue":
        return "Your head appears turned away for several seconds. When ready, return to the assessment and explain your reasoning in your own words."
    return "When ready, return to your answer and explain the reasoning in your own words."


@transaction.atomic
def save_events(session, items):
    if not isinstance(items, list) or not 1 <= len(items) <= 20:
        raise LearningError("Send 1–20 camera events.")
    session = type(session).objects.select_for_update().select_related("course").get(pk=session.pk)
    if session.camera_events.count() + len(items) > 2000:
        raise LearningError("Assessment camera event limit reached.", 409)
    rows = []
    for item in items:
        if not isinstance(item, dict) or item.get("kind") not in KINDS:
            raise LearningError("Unknown camera event.")
        eid = item.get("event_id")
        if not isinstance(eid, str) or not 1 <= len(eid) <= 64:
            raise LearningError("Use a valid camera event ID.")
        existing = session.camera_events.filter(event_id=eid).first()
        if existing:
            rows.append(existing)
            continue
        if session.status != "in_progress" and item["kind"] != "camera_stopped":
            raise LearningError("This assessment has finished.", 409)
        detail = safe_detail(item)
        question = None
        if item.get("question_id") is not None:
            pk = item["question_id"]
            if type(pk) is not int:
                raise LearningError("Use a valid assessment question.")
            question = session.questions.select_related("topic").filter(pk=pk).first()
            if not question:
                raise LearningError("The question must belong to this assessment.")
        previous = session.camera_events.filter(kind__in=("camera_started", "camera_stopped")).last()
        if item["kind"] == "camera_started":
            if detail.get("consent") is not True:
                raise LearningError("Explicit student camera consent is required.")
            if detail.get("analysis_enabled") and not session.course.camera_cues_enabled:
                raise LearningError("Your teacher has disabled camera cues.", 409)
        if item["kind"] in ("camera_cue", "camera_calibrated", "page_return", "paste"):
            if not previous or previous.kind != "camera_started" or not previous.detail.get("consent"):
                raise LearningError("Camera observations require an active, consented camera session.", 409)
        if item["kind"] in ("camera_cue", "camera_calibrated"):
            if not session.course.camera_cues_enabled or not previous.detail.get("analysis_enabled"):
                raise LearningError("Camera cue analysis is disabled.", 409)
        if item["kind"] in ("camera_cue", "page_return", "paste"):
            detail["instruction"] = instruction(item["kind"], detail)
            if session.course.activity_verification and question:
                # A non-scored reasoning check. Never send the answer key, hidden
                # test, rubric or teacher solution as part of this prompt.
                detail["verification"] = {"prompt": f"Explain in your own words how you would approach this question about {question.topic.name}. What is the reason for your answer?",
                    "question_prompt": question.prompt, "resources": citations_for(session.course, question.source_ids),
                    "status": "offered", "answer": "", "non_scored": True,
                    "offer_eye_closure": bool(session.course.camera_eye_closure and previous.detail.get("allow_eye_closure"))}
        rows.append(AssessmentCameraEvent.objects.create(assessment=session, question=question, event_id=eid,
                                                       kind=item["kind"], detail=detail))
    return rows


@transaction.atomic
def respond(event, data):
    event = AssessmentCameraEvent.objects.select_for_update().get(pk=event.pk)
    check = event.detail.get("verification")
    if not check:
        raise LearningError("This observation has no reasoning check.", 409)
    action = data.get("action", "answer")
    if action not in ("answer", "dismiss"):
        raise LearningError("Choose answer or dismiss.")
    answer = data.get("answer", "")
    if not isinstance(answer, str) or len(answer) > 5000 or (action == "answer" and not answer.strip()):
        raise LearningError("Enter an explanation of 1–5,000 characters.")
    if check["status"] != "offered":
        if check["status"] == ("answered" if action == "answer" else "dismissed") and check["answer"] == answer.strip():
            return event
        raise LearningError("This reasoning check has already been saved.", 409)
    check.update(status="answered" if action == "answer" else "dismissed", answer=answer.strip() if action == "answer" else "")
    event.save(update_fields=["detail"])
    return event
