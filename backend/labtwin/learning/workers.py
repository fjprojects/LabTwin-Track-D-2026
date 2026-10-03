"""Small, bounded local dispatcher; production can keep dedicated workers.

Work starts after the upload transaction commits. Child processes provide a
hard deadline even when a PDF parser, model download or native tool hangs.
The SQL queue is authoritative, so a server restart never loses an upload.
"""
import logging
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock

from django.conf import settings
from django.db import close_old_connections, transaction

from ..models import CourseMaterial, EvaluationRun, MaterialProcessJob
from .processing import claim_material, fail_material, material_timeout

logger = logging.getLogger(__name__)
_executor = None
_lock = Lock()
_scheduled = {}


def local_processing():
    return getattr(settings, "LABTWIN_PROCESS_MODE", "local" if settings.DEBUG else "external") == "local"


def command_arguments(command, *arguments):
    return [sys.executable, str(Path(settings.BASE_DIR) / "manage.py"), command, *map(str, arguments),
            "--settings", os.environ.get("DJANGO_SETTINGS_MODULE", "backend.settings")]


def run_material_job(material_id):
    token = claim_material(material_id)
    if not token:
        return
    try:
        child = subprocess.run(command_arguments("process_materials", "--material-id", material_id,
                "--lease-token", token, "--in-process"), stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=material_timeout())
        if child.returncode or MaterialProcessJob.objects.filter(material_id=material_id, status="processing", lease_token=token).exists():
            fail_material(material_id, token, "The extraction worker stopped before finishing. Check the installation and retry; your original file is safe.")
    except subprocess.TimeoutExpired:
        fail_material(material_id, token, "Processing exceeded its time limit. Your original file is safe. Retry, or increase LABTWIN_MATERIAL_TIMEOUT_SECONDS for a large textbook or scanned PDF.")
    except OSError:
        fail_material(material_id, token, "The extraction worker could not start. Install requirements-render.txt in the active Python environment and retry.")


def _run(kind, key):
    close_old_connections()
    try:
        if kind == "material":
            run_material_job(key)
        else:
            run = EvaluationRun.objects.filter(pk=key).first()
            if run and run.status == "queued":
                deadline = 960 if run.mode == "llm" else 300
                try:
                    subprocess.run(command_arguments("process_evaluations", "--run-id", key),
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        timeout=deadline, check=True)
                except (subprocess.SubprocessError, OSError):
                    EvaluationRun.objects.filter(pk=key, status__in=["queued", "running"]).update(
                        status="failed", error="The evaluation worker stopped. No substitute metrics were saved. Check the evaluator environment and run again.")
    except Exception:
        # Keep student text, source contents and provider credentials out of logs.
        logger.warning("Local %s worker unavailable for job %s", kind, key)
    finally:
        close_old_connections()


def _submit(kind, key):
    global _executor
    if not local_processing():
        return
    with _lock:
        for old_key in [k for k, future in _scheduled.items() if future.done()]:
            _scheduled.pop(old_key)
        job_key = (kind, key)
        if job_key in _scheduled or len(_scheduled) >= 12:
            return
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="labtwin-worker")
        _scheduled[job_key] = _executor.submit(_run, kind, key)


def dispatch_material(material):
    if getattr(settings, "LABTWIN_PROCESS_INLINE", False):
        from .ingestion import process_material
        process_material(material)
        material.refresh_from_db()
    else:
        transaction.on_commit(lambda: _submit("material", material.id))


def dispatch_evaluation(run):
    if getattr(settings, "LABTWIN_PROCESS_INLINE", False):
        from .evaluation import process_evaluation
        process_evaluation(run)
    else:
        transaction.on_commit(lambda: _submit("evaluation", run.id))


def resume_course_jobs(course):
    if not getattr(settings, "LABTWIN_PROCESS_INLINE", False) and local_processing():
        for pk in CourseMaterial.objects.filter(course=course, status="queued").values_list("id", flat=True)[:12]:
            transaction.on_commit(lambda pk=pk: _submit("material", pk))
        for pk in EvaluationRun.objects.filter(course=course, status="queued").values_list("id", flat=True)[:3]:
            transaction.on_commit(lambda pk=pk: _submit("evaluation", pk))
