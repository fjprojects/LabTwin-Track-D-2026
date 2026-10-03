"""Durable response history, separate from the deduplicated mastery summaries."""
import json
from functools import wraps

from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .models import StudentProfile, StudentResponse


def record_response(stage):
    def decorate(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.method != "POST":
                return view(request, *args, **kwargs)
            try:
                data = json.loads(request.body or "{}")
                if not isinstance(data, dict):
                    raise ValueError()
                student_id = int(data.get("student_id"))
                if isinstance(data.get("student_id"), bool) or student_id <= 0:
                    raise ValueError()
                for field in ("code", "viva_answer", "viva_question", "current_hint"):
                    if field in data and not isinstance(data[field], str):
                        raise ValueError()
            except (ValueError, TypeError, UnicodeDecodeError):
                return JsonResponse({"error": "A valid student_id and JSON response are required."}, status=400)
            student = StudentProfile.objects.filter(pk=student_id).first()
            if student is None:
                return JsonResponse({"error": "Student not found"}, status=404)

            from .views import get_current_question
            question = get_current_question(data.get("question_id"), student_id=student_id)
            if not question:
                return JsonResponse({"error": "Question not found."}, status=400)
            # Persist before code execution or an AI request, even if it later fails.
            entry = StudentResponse.objects.create(
                student=student, stage=stage,
                question_id=str(question.get("id", "")),
                question=question.get("problem", ""),
                topic=question.get("topic", "General"),
                language=question.get("language", ""),
                code=data.get("code", ""),
                viva_answer=data.get("viva_answer", ""),
                context={key: data[key] for key in (
                    "viva_question", "hint_level", "level", "current_hint", "first_hint", "misconception"
                ) if key in data},
            )
            request.student_response = entry
            try:
                response = view(request, *args, **kwargs)
                entry.result = json.loads(response.content)
                entry.status = "completed" if response.status_code < 400 else "failed"
                entry.save(update_fields=["result", "status", "updated_at"])
                from .learning.mastery import bridge_response
                bridge_response(entry)
                return response
            except Exception:
                entry.status = "failed"
                entry.result = {"error": "Processing failed; the submitted response was retained."}
                entry.save(update_fields=["result", "status", "updated_at"])
                raise
        return wrapped
    return decorate


def record_execution(request, results):
    """Keep compiler errors/output even when subsequent AI evaluation fails."""
    entry = getattr(request, "student_response", None)
    if entry is not None:
        entry.test_results = results
        entry.save(update_fields=["test_results", "updated_at"])


@require_GET
def response_history(request):
    try:
        student_id = int(request.GET.get("student_id", ""))
        before = int(request.GET["before"]) if request.GET.get("before") else None
        if student_id <= 0 or (before is not None and before <= 0):
            raise ValueError()
    except (ValueError, TypeError):
        return JsonResponse({"error": "Invalid student_id or history cursor."}, status=400)
    if not StudentProfile.objects.filter(pk=student_id).exists():
        return JsonResponse({"error": "Student not found"}, status=404)
    rows = StudentResponse.objects.filter(student_id=student_id).order_by("-id")
    if before is not None:
        rows = rows.filter(id__lt=before)
    entries = list(rows[:21])
    return JsonResponse({
        "responses": [{
            "id": row.id, "stage": row.stage, "status": row.status,
            "question": row.question, "topic": row.topic, "language": row.language,
            "code": row.code, "viva_answer": row.viva_answer,
            "context": row.context, "result": row.result, "test_results": row.test_results,
            "created_at": row.created_at.isoformat(),
        } for row in entries[:20]],
        "next_before": entries[19].id if len(entries) > 20 else None,
    })
