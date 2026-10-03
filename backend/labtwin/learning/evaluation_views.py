from datetime import timedelta

from django.http import JsonResponse
from django.utils import timezone

from ..models import EvaluationRun
from .access import endpoint, payload, course_for, LearningError
from .evaluation import run_data
from .workers import dispatch_evaluation, resume_course_jobs


@endpoint(["GET", "POST"], teacher=True)
def runs(request, course_id):
    course = course_for(request.account, course_id)
    if request.method == "GET":
        EvaluationRun.objects.filter(owner=request.account, course=course, status="running",
            started_at__lt=timezone.now() - timedelta(seconds=990)).update(status="failed",
            error="The previous evaluation was interrupted. No substitute metrics were saved. Run it again.", finished_at=timezone.now())
        resume_course_jobs(course)
        return JsonResponse({"runs": [run_data(row) for row in EvaluationRun.objects.filter(owner=request.account, course=course).order_by("-id")[:25]]})
    mode = payload(request).get("mode", "deterministic")
    if mode not in ("deterministic", "llm"):
        raise LearningError("Choose deterministic or llm evaluation.")
    row = EvaluationRun.objects.create(owner=request.account, course=course, mode=mode)
    dispatch_evaluation(row)
    return JsonResponse({"run": run_data(row, True)}, status=201)


@endpoint(["GET"], teacher=True)
def detail(request, run_id):
    row = EvaluationRun.objects.filter(pk=run_id, owner=request.account).first()
    if not row or not row.course_id:
        raise LearningError("Evaluation run not found.", 404)
    course_for(request.account, row.course_id)
    response = JsonResponse({"run": run_data(row, True)})
    if request.GET.get("download") == "json":
        response["Content-Disposition"] = f'attachment; filename="labtwin-evaluation-{row.id}.json"'
    return response
