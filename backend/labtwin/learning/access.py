import json
import logging
from functools import wraps

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from ..access import authenticated
from ..models import Course, CourseTopic, CourseMaterial, Enrollment, StudentProfile

logger = logging.getLogger(__name__)


class LearningError(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status
        super().__init__(message)


def endpoint(methods, teacher=False):
    def decorate(view):
        @authenticated
        @require_http_methods(methods)
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if teacher and request.account.role != "teacher":
                return JsonResponse({"error": "Only the classroom teacher can do this."}, status=403)
            try:
                return view(request, *args, **kwargs)
            except LearningError as error:
                return JsonResponse({"error": error.message}, status=error.status)
            except (json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError):
                return JsonResponse({"error": "Invalid request. Check the supplied fields."}, status=400)
            except Exception:
                logger.exception("Learning request failed")
                return JsonResponse({"error": "This request could not finish. Your existing work was retained. Please retry."}, status=503)
        return wrapped
    return decorate


def payload(request):
    data = json.loads(request.body or "{}")
    if not isinstance(data, dict):
        raise LearningError("A JSON object is required.")
    return data


def authorized_courses(account):
    rows = Course.objects.select_related("classroom__teacher__user")
    if account.role == "teacher":
        return rows.filter(classroom__teacher=account)
    return rows.filter(classroom__enrollments__student_id=account.student_id).distinct()


def course_for(account, course_id):
    course = authorized_courses(account).filter(pk=course_id).first()
    if not course:
        raise LearningError("Course not found or classroom access has ended.", 404)
    return course


def topic_for(account, topic_id):
    topic = CourseTopic.objects.select_related("course__classroom").filter(
        pk=topic_id, course__in=authorized_courses(account)).first()
    if not topic:
        raise LearningError("Topic not found.", 404)
    return topic


def material_for(account, material_id):
    material = CourseMaterial.objects.select_related("course__classroom", "topic").filter(
        pk=material_id, course__in=authorized_courses(account)).first()
    if not material:
        raise LearningError("Material not found or classroom access has ended.", 404)
    return material


def student_for(account, course, student_id=None):
    if account.role == "student":
        if student_id and int(student_id) != account.student_id:
            raise LearningError("You can only inspect your own learning data.", 403)
        return account.student
    if not student_id:
        raise LearningError("Choose a student.")
    student = StudentProfile.objects.filter(pk=student_id, enrollments__classroom=course.classroom).first()
    if not student or course.classroom.teacher_id != account.id:
        raise LearningError("Student not found in this classroom.", 404)
    return student


def require_student(account):
    if account.role != "student":
        raise LearningError("This action belongs to the signed-in student.", 403)


def validate_sources(course, ids):
    from ..models import SourceChunk
    if not isinstance(ids, list) or len(ids) > 12 or any(not isinstance(value, int) or isinstance(value, bool) for value in ids):
        raise LearningError("Invalid source references.")
    valid = list(SourceChunk.objects.filter(id__in=ids, course=course, unit__material__status="ready").values_list("id", flat=True))
    if set(ids) != set(valid):
        raise LearningError("All sources must belong to this course and be ready.")
    return valid
