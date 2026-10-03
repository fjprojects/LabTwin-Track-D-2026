import hashlib
import json
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse

from ..models import Classroom, Course, CourseTopic, CourseMaterial, MaterialProcessJob, SourceChunk, ResourceStudy, AskExchange
from .access import endpoint, payload, LearningError, authorized_courses, course_for, material_for, topic_for, validate_sources
from .extraction import KINDS
from .processing import recover_expired_materials, reset_material
from .workers import dispatch_material, resume_course_jobs, local_processing
from .media import media_url
from .rag import grounded_answer
from .sources import citation
from .vectors import remove_vectors


def course_data(course):
    # The camera stays off until a student explicitly opts in and grants permission.
    from .camera import camera_policy
    return {"id": course.id, "name": course.name, "description": course.description, "classroom_id": course.classroom_id, "classroom_name": course.classroom.name, "language": course.language, "allow_solutions": course.allow_solutions, "activity_verification": course.activity_verification, "camera_policy": camera_policy(course), "is_demo": course.is_demo, "topics": [{"id": t.id, "name": t.name, "description": t.description, "parent_id": t.parent_id, "concepts": t.concepts, "taxonomy_evidence": t.taxonomy_evidence, "prerequisites": list(t.prerequisites.values_list("id", flat=True))} for t in course.topics.prefetch_related("prerequisites")], "material_count": course.materials.filter(status="ready").count()}


@endpoint(["GET", "POST"])
def courses(request):
    if request.method == "GET":
        return JsonResponse({"courses": [course_data(c) for c in authorized_courses(request.account)]})
    if request.account.role != "teacher":
        raise LearningError("Only teachers can create courses.", 403)
    data = payload(request)
    room = Classroom.objects.filter(pk=data.get("classroom_id"), teacher=request.account).first()
    name, language = str(data.get("name", "")).strip(), data.get("language", "Python")
    if not room or not name or len(name) > 160 or language not in ("Python", "C", "Java"):
        raise LearningError("Choose your classroom and enter a course name and supported language.")
    course = Course.objects.create(classroom=room, name=name, description=str(data.get("description", ""))[:12000], language=language)
    return JsonResponse({"course": course_data(course)}, status=201)


@endpoint(["PATCH"], teacher=True)
def course_settings(request, course_id):
    course, data = course_for(request.account, course_id), payload(request)
    for field in ("allow_solutions", "activity_verification", "camera_cues_enabled", "camera_eye_closure"):
        if field in data:
            if not isinstance(data[field], bool):
                raise LearningError("Course settings must be true or false.")
            setattr(course, field, data[field])
    course.save()
    return JsonResponse({"course": course_data(course)})


@endpoint(["POST"], teacher=True)
def topics(request, course_id):
    course, data = course_for(request.account, course_id), payload(request)
    name = str(data.get("name", "")).strip()
    ids = data.get("prerequisites", [])
    if not name or len(name) > 200 or not isinstance(ids, list):
        raise LearningError("Enter a topic name and prerequisite IDs.")
    dependencies = list(course.topics.filter(id__in=ids))
    if set(ids) != {t.id for t in dependencies} or course.topics.filter(name=name).exists():
        raise LearningError("Use unique topics and prerequisites from this course.")
    with transaction.atomic():
        topic = CourseTopic.objects.create(course=course, name=name, description=str(data.get("description", ""))[:6000], position=course.topics.count())
        topic.prerequisites.set(dependencies)
    return JsonResponse({"course": course_data(course)}, status=201)


def material_data(material, details=False):
    result = {"id": material.id, "course_id": material.course_id, "topic_id": material.topic_id, "title": material.title, "filename": material.filename, "kind": material.kind, "status": material.status, "error": material.error, "warnings": material.warnings, "summary": material.summary, "key_topics": material.key_topics, "chapters": material.chapters, "duration_seconds": material.duration_seconds, "transcript_origin": material.transcript_origin, "created_at": material.created_at.isoformat(), "unit_count": material.units.filter(archived=False).count()}
    job = MaterialProcessJob.objects.filter(material=material).first()
    if job:
        result["processing"] = {"stage": job.stage, "completed": job.completed_units, "total": job.total_units,
            "unit": job.unit_label, "started_at": job.started_at.isoformat() if job.started_at else None,
            "updated_at": job.heartbeat_at.isoformat() if job.heartbeat_at else None,
            "mode": "local" if local_processing() else "external"}
    if details:
        result["transcript"] = material.transcript
        result["units"] = [{"id": u.id, "number": u.number, "page": u.page_number, "slide": u.slide_number, "start": u.start_seconds, "end": u.end_seconds, "title": u.title, "text": u.text, "content_type": u.content_type, "subtopic": u.subtopic, "concepts": u.concepts, "prerequisites": u.prerequisite_names, "analysis_method": u.analysis_method, "source_id": u.chunks.order_by("position").values_list("id", flat=True).first()} for u in material.units.filter(archived=False)]
    return result


@endpoint(["GET", "POST"])
def materials(request, course_id):
    course = course_for(request.account, course_id)
    if request.method == "GET":
        if request.account.role == "teacher":
            recover_expired_materials(course)
            resume_course_jobs(course)
        rows = course.materials.all() if request.account.role == "teacher" else course.materials.filter(status="ready")
        return JsonResponse({"materials": [material_data(m) for m in rows.order_by("-id")]})
    if request.account.role != "teacher":
        raise LearningError("Only teachers can upload course materials.", 403)
    upload = request.FILES.get("file")
    if not upload or not 0 < upload.size <= getattr(settings, "LABTWIN_UPLOAD_MAX_BYTES", 100 * 1024 * 1024):
        raise LearningError("Select a non-empty file within the configured upload limit.")
    filename = Path(upload.name.replace("\\", "/")).name[:240]
    kind = KINDS.get(Path(filename).suffix.lower())
    if not kind:
        raise LearningError("Use PDF, PPT/PPTX, UTF-8 text, or a supported audio/video format.")
    topic = topic_for(request.account, request.POST["topic_id"]) if request.POST.get("topic_id") else None
    if topic and topic.course_id != course.id:
        raise LearningError("The topic belongs to a different course.")
    digest = hashlib.sha256()
    for block in upload.chunks():
        digest.update(block)
    upload.seek(0)
    captions = json.loads(request.POST["captions"]) if request.POST.get("captions") else None
    if captions is not None and (kind not in ("audio", "video") or not isinstance(captions, list)):
        raise LearningError("Timestamped captions are only used with lectures.")
    material = CourseMaterial.objects.create(course=course, topic=topic, uploaded_by=request.account, title=str(request.POST.get("title") or filename)[:200], filename=filename, file=upload, kind=kind, sha256=digest.hexdigest(), byte_size=upload.size, transcript=captions or [], transcript_origin="teacher_captions" if captions is not None else "")
    MaterialProcessJob.objects.create(material=material)
    dispatch_material(material)
    return JsonResponse({"material": material_data(material)}, status=201)


@endpoint(["GET", "DELETE"])
def material_detail(request, material_id):
    material = material_for(request.account, material_id)
    if request.account.role == "teacher":
        recover_expired_materials(material.course)
        material.refresh_from_db()
    if request.method == "DELETE":
        if request.account.role != "teacher":
            raise LearningError("Only teachers can remove materials.", 403)
        if material.status == "processing":
            raise LearningError("Wait for processing to finish before removing this file.", 409)
        remove_vectors(list(material.units.values_list("chunks__id", flat=True)))
        material.file.delete(save=False)
        material.delete()
        return JsonResponse({"deleted": True})
    if request.account.role == "student" and material.status != "ready":
        raise LearningError("The material is still being processed.", 409)
    result = material_data(material, True)
    result["media_url"] = media_url(request, material)
    return JsonResponse({"material": result})


@endpoint(["POST"], teacher=True)
def retry_material(request, material_id):
    material = material_for(request.account, material_id)
    recover_expired_materials(material.course)
    material.refresh_from_db()
    data = payload(request)
    if "captions" in data:
        if material.kind not in ("audio", "video") or not isinstance(data["captions"], list):
            raise LearningError("Supply timestamped captions for a lecture.")
        material.transcript, material.transcript_origin = data["captions"], "teacher_captions"
    reset_material(material)
    dispatch_material(material)
    return JsonResponse({"material": material_data(material)})


@endpoint(["POST"])
def ask(request, course_id):
    course, data = course_for(request.account, course_id), payload(request)
    question = str(data.get("question", "")).strip()
    if not question or len(question) > 3000:
        raise LearningError("Enter a question of up to 3,000 characters.")
    material = material_for(request.account, data["material_id"]) if data.get("material_id") else None
    if material and material.course_id != course.id:
        raise LearningError("Choose a lecture from this course.")
    ids = validate_sources(course, [data["source_id"]]) if data.get("source_id") else []
    answer = grounded_answer(course, question, material.id if material else None, request.account.student if request.account.role == "student" else None, ids[0] if ids else None)
    exchange = AskExchange.objects.create(account=request.account, course=course, material=material, question=question, answer=answer["answer"], citations=answer["citations"], grounded=answer["grounded"], mode=answer["mode"])
    if request.account.role == "student" and answer.get("tutoring_policy", {}).get("topic_id"):
        from .mastery import record_evidence
        record_evidence(request.account.student, topic_for(request.account, answer["tutoring_policy"]["topic_id"]), f"conversation:{exchange.id}", "conversation", detail={"exchange_id": exchange.id, "grounded": answer["grounded"], "note": "Asked a question; no correctness inferred."})
    return JsonResponse({"id": exchange.id, **answer})


@endpoint(["GET"])
def ask_history(request, course_id):
    course = course_for(request.account, course_id)
    rows = AskExchange.objects.filter(account=request.account, course=course).order_by("-id")[:30]
    return JsonResponse({"questions": [{"id": row.id, "question": row.question, "answer": row.answer, "citations": row.citations, "grounded": row.grounded, "mode": row.mode} for row in rows]})


@endpoint(["GET", "POST"])
def source(request, chunk_id):
    chunk = SourceChunk.objects.select_related("unit__material__course").filter(pk=chunk_id, course__in=authorized_courses(request.account), unit__material__status="ready").first()
    if not chunk:
        raise LearningError("Source not found or classroom access has ended.", 404)
    if request.method == "POST":
        if request.account.role == "student":
            seconds = int(payload(request).get("seconds_viewed", 0))
            if not 0 <= seconds <= 14400:
                raise LearningError("Invalid study duration.")
            ResourceStudy.objects.create(student=request.account.student, unit=chunk.unit, seconds_viewed=seconds)
        return JsonResponse({"recorded": True})
    return JsonResponse({"source": citation(chunk), "text": chunk.unit.text, "layout": chunk.unit.layout,
                         "content_type": chunk.unit.content_type, "visual_description": chunk.unit.visual_description,
                         "analysis_method": chunk.unit.analysis_method, "concepts": chunk.unit.concepts,
                         "visual_url": media_url(request, chunk.unit.material, chunk.unit) if chunk.unit.visual_file else None,
                         "media_url": media_url(request, chunk.unit.material)})
