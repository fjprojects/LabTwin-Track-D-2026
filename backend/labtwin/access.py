"""Bearer authentication and ownership checks for every student endpoint."""
import hashlib
import json
from contextvars import ContextVar
from functools import wraps

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import AccessToken, Enrollment

current_student_id = ContextVar("current_student_id", default=None)


def authenticate_request(request):
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    digest = hashlib.sha256(header[7:].encode()).hexdigest()
    token = AccessToken.objects.select_related("account__user", "account__student").filter(
        digest=digest, expires_at__gt=timezone.now(), account__user__is_active=True,
    ).first()
    if token:
        request.access_token = token
        request.account = token.account
        return token.account
    return None


def authenticated(view):
    @csrf_exempt
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if authenticate_request(request) is None:
            return JsonResponse({"error": "Please sign in."}, status=401)
        return view(request, *args, **kwargs)
    return wrapped


def student_access(view, read_only=False):
    @authenticated
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        account = request.account
        if read_only and request.method != "GET":
            return JsonResponse({"error": "GET required"}, status=405)
        try:
            if request.method == "GET":
                data = request.GET.copy()
            elif request.content_type == "application/json":
                data = json.loads(request.body or "{}")
                if not isinstance(data, dict):
                    raise ValueError()
            else:
                data = request.POST.copy()
            target = data.get("student_id") or account.student_id
            student_id = int(target)
            if student_id <= 0 or isinstance(target, bool):
                raise ValueError()
        except (ValueError, TypeError, UnicodeDecodeError):
            return JsonResponse({"error": "A valid student_id is required."}, status=400)

        own = account.role == "student" and account.student_id == student_id
        teacher_read = read_only and account.role == "teacher" and Enrollment.objects.filter(
            classroom__teacher=account, student_id=student_id,
        ).exists()
        if not (own or teacher_read):
            return JsonResponse({"error": "You do not have access to this student."}, status=403)

        data["student_id"] = student_id
        if request.method == "GET":
            request.GET = data
        elif request.content_type == "application/json":
            request._body = json.dumps(data).encode()
        else:
            request.POST = data
        # Older AI helpers read load_state() without an ID. Scope those reads
        # to this request, never to the last student who used the server.
        context = current_student_id.set(student_id)
        try:
            response = view(request, *args, **kwargs)
            if account.role == "student" and response.headers.get("Content-Type", "").startswith("application/json"):
                from .hidden_results import student_payload
                sanitized = student_payload(json.loads(response.content))
                response.content = json.dumps(sanitized).encode()
            return response
        finally:
            current_student_id.reset(context)
    return wrapped
