"""WebRTC signaling; screen/camera content travels directly to the teacher."""
import json
from datetime import timedelta

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .access import authenticated
from .assessment_views import attempt_access
from .classroom_views import body
from .models import AssignmentAttempt, IceCandidate, LiveConnection, LiveSession


def ice_servers():
    # Configure TURN for users on networks where direct connections are blocked.
    return getattr(settings, "WEBRTC_ICE_SERVERS", [{"urls": "stun:stun.l.google.com:19302"}])


def is_live(session):
    return session.active and session.last_seen > timezone.now() - timedelta(seconds=30)


@authenticated
@require_http_methods(["POST", "PATCH", "DELETE"])
def live_session(request, attempt_id):
    attempt = AssignmentAttempt.objects.select_related("assignment__classroom").filter(pk=attempt_id).first()
    if request.account.role != "student" or not attempt or request.account.student_id != attempt.student_id or not attempt_access(request.account, attempt):
        return JsonResponse({"error": "Attempt not found."}, status=404)
    if request.method == "DELETE":
        LiveSession.objects.filter(attempt=attempt).update(active=False, screen_active=False, camera_active=False)
        LiveConnection.objects.filter(session__attempt=attempt).update(active=False)
        return JsonResponse({"stopped": True})
    if attempt.status not in ("in_progress", "processing"):
        return JsonResponse({"error": "This assessment has ended."}, status=409)
    try:
        data = body(request)
        if not all(isinstance(data.get(key), bool) for key in ("screen_active", "camera_active")):
            raise ValueError()
    except (ValueError, TypeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid media status."}, status=400)
    session, _ = LiveSession.objects.get_or_create(attempt=attempt)
    if request.method == "POST":
        session.connections.update(active=False)
    session.active = data["screen_active"] or data["camera_active"]
    session.screen_active, session.camera_active = data["screen_active"], data["camera_active"]
    if not session.active:
        session.connections.update(active=False)
    session.save()
    peers = [{"id": c.id, "answer": c.answer,
              "teacher_name": c.teacher.user.first_name or c.teacher.user.username}
             for c in session.connections.filter(active=True).select_related("teacher__user")]
    return JsonResponse({"session_id": session.id, "connections": peers, "ice_servers": ice_servers()})


@authenticated
@require_http_methods(["GET"])
def classroom_live(request, classroom_id):
    if request.account.role != "teacher" or not request.account.classrooms.filter(pk=classroom_id).exists():
        return JsonResponse({"error": "Classroom not found."}, status=404)
    sessions = LiveSession.objects.filter(active=True, last_seen__gt=timezone.now()-timedelta(seconds=30),
        attempt__assignment__classroom_id=classroom_id,
        attempt__student__enrollments__classroom_id=classroom_id,
        attempt__status__in=["in_progress", "processing"]).select_related("attempt__student", "attempt__assignment")
    return JsonResponse({"sessions": [{"id": s.id, "attempt_id": s.attempt_id,
        "student_name": s.attempt.student.name, "assignment_title": s.attempt.assignment.title,
        "screen_active": s.screen_active, "camera_active": s.camera_active} for s in sessions]})


@authenticated
@require_http_methods(["POST"])
def watch(request, session_id):
    session = LiveSession.objects.select_related("attempt__assignment__classroom").filter(pk=session_id).first()
    if request.account.role != "teacher" or not session or not attempt_access(request.account, session.attempt):
        return JsonResponse({"error": "Live session not found."}, status=404)
    if not is_live(session):
        return JsonResponse({"error": "Student sharing has stopped."}, status=409)
    session.connections.filter(teacher=request.account, active=True).update(active=False)
    connection = LiveConnection.objects.create(session=session, teacher=request.account)
    return JsonResponse({"connection_id": connection.id, "ice_servers": ice_servers()})


@authenticated
@require_http_methods(["GET", "POST", "DELETE"])
def signaling(request, connection_id):
    connection = LiveConnection.objects.select_related("session__attempt__assignment__classroom").filter(pk=connection_id).first()
    if not connection or not attempt_access(request.account, connection.session.attempt):
        return JsonResponse({"error": "Connection not found."}, status=404)
    student = request.account.role == "student" and request.account.student_id == connection.session.attempt.student_id
    teacher = request.account.role == "teacher" and connection.teacher_id == request.account.id
    if not (student or teacher):
        return JsonResponse({"error": "You cannot access this connection."}, status=403)
    if request.method == "DELETE":
        connection.active = False
        connection.save(update_fields=["active"])
        return JsonResponse({"stopped": True})
    if not connection.active or not is_live(connection.session):
        return JsonResponse({"error": "Sharing has stopped."}, status=410)
    if request.method == "GET":
        try:
            after = int(request.GET.get("after", 0))
        except ValueError:
            return JsonResponse({"error": "Invalid cursor."}, status=400)
        remote = "teacher" if student else "student"
        candidates = list(connection.candidates.filter(sender=remote, id__gt=after).order_by("id")[:200])
        return JsonResponse({"offer": connection.offer, "answer": connection.answer,
            "track_sources": connection.track_sources, "candidates": [{"id": c.id, "value": c.value} for c in candidates]})
    try:
        data = body(request)
        allowed = {"offer", "track_sources", "candidate"} if student else {"answer", "candidate"}
        if set(data) - allowed or len(json.dumps(data)) > 100000:
            raise ValueError()
        if "offer" in data or "answer" in data:
            key = "offer" if student else "answer"
            sdp = data.get(key)
            if not isinstance(sdp, dict) or sdp.get("type") != key or not isinstance(sdp.get("sdp"), str):
                raise ValueError()
            setattr(connection, key, sdp)
            sources = data.get("track_sources", {})
            if student:
                if not isinstance(sources, dict) or any(v not in ("screen", "camera", "microphone") for v in sources.values()):
                    raise ValueError()
                connection.track_sources = sources
            connection.save(update_fields=[key, "track_sources"] if student else [key])
        if "candidate" in data:
            if not isinstance(data["candidate"], dict) or connection.candidates.count() >= 400:
                raise ValueError()
            IceCandidate.objects.create(connection=connection, sender="student" if student else "teacher", value=data["candidate"])
        return JsonResponse({"saved": True})
    except (ValueError, TypeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid signaling message."}, status=400)
