"""Durable material leases, real stage progress and interrupted-job recovery."""
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from ..models import CourseMaterial, MaterialProcessJob


class ProcessingInterrupted(Exception):
    """This worker no longer owns the material. It must not publish a result."""


def material_timeout():
    return max(30, int(getattr(settings, "LABTWIN_MATERIAL_TIMEOUT_SECONDS", 600)))


def claim_material(material_id):
    token, now = uuid.uuid4().hex, timezone.now()
    with transaction.atomic():
        claimed = MaterialProcessJob.objects.filter(material_id=material_id, status="queued").update(
            status="processing", lease_token=token, stage="starting", started_at=now,
            heartbeat_at=now, finished_at=None, completed_units=0, total_units=0,
            unit_label="", attempts=F("attempts") + 1)
        if not claimed:
            return None
        CourseMaterial.objects.filter(pk=material_id).update(status="processing", error="")
    return token


def progress(material_id, token, stage, completed=0, total=0, unit=""):
    if not MaterialProcessJob.objects.filter(material_id=material_id, status="processing", lease_token=token).update(
            stage=stage, completed_units=max(0, completed), total_units=max(0, total),
            unit_label=unit, heartbeat_at=timezone.now()):
        raise ProcessingInterrupted()


def finish_material(material, token, *, error=""):
    with transaction.atomic():
        owned = MaterialProcessJob.objects.filter(material_id=material.id, status="processing", lease_token=token).update(
            status="failed" if error else "ready", stage="failed" if error else "ready",
            finished_at=timezone.now(), heartbeat_at=timezone.now(), lease_token="")
        if not owned:
            raise ProcessingInterrupted()
        if error:
            CourseMaterial.objects.filter(pk=material.id).update(status="failed", error=error)
        else:
            material.status, material.error, material.processed_at = "ready", "", timezone.now()
            material.save()


def fail_material(material_id, token, message):
    material = CourseMaterial.objects.filter(pk=material_id).first()
    if material:
        try:
            finish_material(material, token, error=message)
        except ProcessingInterrupted:
            pass


def recover_expired_materials(course=None):
    """Invalidate old leases; retain uploads and all previously cited sources."""
    cutoff = timezone.now() - timedelta(seconds=material_timeout() + 30)
    rows = MaterialProcessJob.objects.filter(status="processing").filter(
        Q(started_at__lt=cutoff) | Q(started_at__isnull=True, material__created_at__lt=cutoff))
    if course is not None:
        rows = rows.filter(material__course=course)
    count = 0
    for job in rows:
        # Legacy jobs have no lease. The conditional terminal update still
        # prevents an expired worker from overwriting a newer attempt.
        fail_material(job.material_id, job.lease_token,
            "Processing was interrupted or exceeded its time limit. The original upload is safe. Retry processing; large scans may need a longer configured limit.")
        count += 1
    return count


def reset_material(material):
    with transaction.atomic():
        job, _ = MaterialProcessJob.objects.get_or_create(material=material)
        if job.status == "processing":
            from .access import LearningError
            raise LearningError("This upload is still processing. Its current stage is shown below.", 409)
        changed = MaterialProcessJob.objects.filter(pk=job.pk).exclude(status="processing").update(status="queued", stage="queued", lease_token="",
            completed_units=0, total_units=0, unit_label="", started_at=None, finished_at=None, heartbeat_at=None)
        if not changed:
            from .access import LearningError
            raise LearningError("This upload has started processing. Wait for it to finish before retrying.", 409)
        material.status, material.error = "queued", ""
        material.save()
