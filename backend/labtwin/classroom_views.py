import hashlib
import json
import secrets
from datetime import timedelta

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .access import authenticated, student_access
from .models import Account, AccessToken, Classroom, Enrollment, StudentProfile


def body(request):
    data = json.loads(request.body or "{}")
    if not isinstance(data, dict):
        raise ValueError("JSON object required")
    return data


def account_data(account):
    return {"id": account.id, "username": account.user.username,
            "name": account.user.first_name, "role": account.role,
            "student_id": account.student_id}


def signed_in(account):
    raw = secrets.token_urlsafe(32)
    AccessToken.objects.filter(account=account, expires_at__lte=timezone.now()).delete()
    AccessToken.objects.create(account=account, digest=hashlib.sha256(raw.encode()).hexdigest(),
                               expires_at=timezone.now() + timedelta(hours=24))
    return JsonResponse({"token": raw, "account": account_data(account)})


@csrf_exempt
@require_http_methods(["POST"])
def register(request):
    try:
        data = body(request)
        username = str(data.get("username", "")).strip().lower()
        name = str(data.get("name", "")).strip()
        password = data.get("password", "")
        role = data.get("role")
        if not username or not name or len(name) > 100 or role not in ("student", "teacher"):
            return JsonResponse({"error": "Enter a username, name and valid role."}, status=400)
        if not isinstance(password, str):
            raise ValueError("Password must be text")
        user = get_user_model()(username=username, first_name=name)
        user.full_clean(exclude=["password"])
        validate_password(password, user)
        with transaction.atomic():
            user.set_password(password)
            user.save()
            student = StudentProfile.objects.create(name=name) if role == "student" else None
            account = Account.objects.create(user=user, role=role, student=student)
        return signed_in(account)
    except ValidationError as error:
        return JsonResponse({"error": " ".join(error.messages)}, status=400)
    except IntegrityError:
        return JsonResponse({"error": "That username is already taken."}, status=400)
    except (ValueError, TypeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid registration details."}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def login(request):
    try:
        data = body(request)
        user = authenticate(request, username=str(data.get("username", "")).strip().lower(),
                            password=data.get("password", ""))
        account = Account.objects.filter(user=user).first() if user else None
        if account is None:
            return JsonResponse({"error": "Incorrect username or password."}, status=401)
        return signed_in(account)
    except (ValueError, TypeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid sign-in details."}, status=400)


@authenticated
@require_http_methods(["GET"])
def me(request):
    return JsonResponse({"account": account_data(request.account)})


@authenticated
@require_http_methods(["POST"])
def logout(request):
    request.access_token.delete()
    return JsonResponse({"success": True})


@student_access
@require_http_methods(["POST"])
def start_student(request):
    from .views import activate_student_session, public_student_session
    student = request.account.student
    state = activate_student_session(student.id, fresh=False)
    return JsonResponse({"student_id": student.id, "name": student.name,
                         "session": public_student_session(state)})


def class_data(room, teacher=False):
    result = {"id": room.id, "name": room.name, "subject": room.subject,
              "teacher": room.teacher.user.first_name or room.teacher.user.username}
    if teacher:
        result["join_code"] = room.join_code
        result["student_count"] = room.enrollments.count()
    return result


@authenticated
@require_http_methods(["GET", "POST"])
def classrooms(request):
    account = request.account
    if request.method == "POST":
        if account.role != "teacher":
            return JsonResponse({"error": "Only teachers can create classrooms."}, status=403)
        try:
            data = body(request)
            name = str(data.get("name", "")).strip()
            subject = str(data.get("subject", "")).strip()
            if not name or len(name) > 120 or len(subject) > 120:
                raise ValueError()
        except (ValueError, TypeError, UnicodeDecodeError):
            return JsonResponse({"error": "Enter a class name and subject (up to 120 characters)."}, status=400)
        room = Classroom.objects.create(teacher=account, name=name, subject=subject,
                                        join_code=secrets.token_hex(6).upper())
        return JsonResponse({"classroom": class_data(room, True)}, status=201)
    rooms = Classroom.objects.select_related("teacher__user").order_by("-created_at")
    rooms = rooms.filter(teacher=account) if account.role == "teacher" else rooms.filter(enrollments__student=account.student)
    return JsonResponse({"classrooms": [class_data(room, account.role == "teacher") for room in rooms]})


@authenticated
@require_http_methods(["POST"])
def join_classroom(request):
    if request.account.role != "student":
        return JsonResponse({"error": "Only students can join classrooms."}, status=403)
    try:
        code = str(body(request).get("code", "")).strip().upper()
    except (ValueError, TypeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid class code."}, status=400)
    room = Classroom.objects.select_related("teacher__user").filter(join_code=code).first()
    if room is None:
        return JsonResponse({"error": "Class code not found. Ask your teacher for the code."}, status=404)
    Enrollment.objects.get_or_create(classroom=room, student=request.account.student)
    return JsonResponse({"classroom": class_data(room)})


@authenticated
@require_http_methods(["GET"])
def roster(request, classroom_id):
    room = Classroom.objects.filter(id=classroom_id, teacher=request.account).first()
    if request.account.role != "teacher" or room is None:
        return JsonResponse({"error": "Classroom not found."}, status=404)
    students = StudentProfile.objects.filter(enrollments__classroom=room).annotate(
        response_count=Count("responses", distinct=True),
    ).order_by("name", "id")
    return JsonResponse({"classroom": class_data(room, True), "students": [
        {"student_id": s.id, "name": s.name, "username": s.account.user.username,
         "response_count": s.response_count,
         "topics_tested": s.topic_progress.count(),
         "topics_mastered": s.topic_progress.filter(status="Mastered").count()}
        for s in students.select_related("account__user")
    ]})


@authenticated
@require_http_methods(["DELETE"])
def remove_member(request, classroom_id, student_id):
    account = request.account
    member = Enrollment.objects.select_related("classroom").filter(
        classroom_id=classroom_id, student_id=student_id).first()
    if member is None:
        return JsonResponse({"error": "Enrollment not found."}, status=404)
    allowed = (account.role == "teacher" and member.classroom.teacher_id == account.id) or (
        account.role == "student" and account.student_id == student_id)
    if not allowed:
        return JsonResponse({"error": "You cannot remove this enrollment."}, status=403)
    member.delete()
    return JsonResponse({"success": True})
