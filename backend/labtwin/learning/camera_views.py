"""Owned assessment camera timelines; no camera media ingestion endpoints."""
from django.http import JsonResponse

from ..models import AssessmentSession, AssessmentCameraEvent
from .access import endpoint, course_for, authorized_courses, student_for, require_student, payload, LearningError
from .camera import event_data, camera_policy, camera_summary, save_events, respond, OBSERVATION_NOTE


def session_for(account, session_id):
    session = AssessmentSession.objects.select_related("course", "student").filter(
        pk=session_id, course__in=authorized_courses(account)).first()
    if not session:
        raise LearningError("Assessment not found.", 404)
    student_for(account, session.course, session.student_id)
    return session


@endpoint(["GET", "POST"])
def events(request, session_id):
    session = session_for(request.account, session_id)
    if request.method == "POST":
        require_student(request.account)
        if len(request.body) > 65536:
            raise LearningError("Camera event request is too large.", 413)
        rows = save_events(session, payload(request).get("events"))
    else:
        rows = session.camera_events.select_related("question").all()[:2000]
    return JsonResponse({"events": [event_data(row) for row in rows],
                         "policy": camera_policy(session.course), "summary": camera_summary(session), "status": session.status})


@endpoint(["POST"])
def response(request, event_id):
    require_student(request.account)
    event = AssessmentCameraEvent.objects.select_related("assessment__course").filter(
        pk=event_id, assessment__student_id=request.account.student_id,
        assessment__course__in=authorized_courses(request.account)).first()
    if not event:
        raise LearningError("Camera reasoning check not found.", 404)
    if len(request.body) > 24000:
        raise LearningError("Explanation is too large.", 413)
    return JsonResponse({"event": event_data(respond(event, payload(request))), "interpretation": OBSERVATION_NOTE})


@endpoint(["GET"], teacher=True)
def review(request, course_id):
    course = course_for(request.account, course_id)
    sessions = AssessmentSession.objects.filter(course=course, student__enrollments__classroom=course.classroom).select_related("student").prefetch_related("camera_events").order_by("-id")[:50]
    return JsonResponse({"assessments": [{"id": row.id, "student": row.student.name, "student_id": row.student_id,
        "kind": row.kind, "status": row.status, "created_at": row.created_at.isoformat(), "summary": camera_summary(row)} for row in sessions],
        "policy": camera_policy(course), "interpretation": OBSERVATION_NOTE})
