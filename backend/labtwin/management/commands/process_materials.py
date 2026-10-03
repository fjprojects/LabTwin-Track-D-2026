import time

from django.core.management.base import BaseCommand, CommandError

from labtwin.models import CourseMaterial
from labtwin.learning.ingestion import process_material
from labtwin.learning.processing import recover_expired_materials
from labtwin.learning.workers import run_material_job


class Command(BaseCommand):
    help = "Process private course materials with a bounded extraction worker."
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("--watch", action="store_true")
        parser.add_argument("--recover-stale", action="store_true", help="Recover interrupted uploads without deleting them.")
        parser.add_argument("--material-id", type=int)
        parser.add_argument("--lease-token", default="")
        parser.add_argument("--in-process", action="store_true", help="Synchronous execution for tests/internal child workers.")

    def handle(self, *args, **options):
        if options["lease_token"] and (not options["material_id"] or not options["in_process"]):
            raise CommandError("A lease is only valid for one internal material worker.")
        while True:
            if not options["lease_token"]:
                recover_expired_materials()
            rows = CourseMaterial.objects.select_related("course__classroom", "topic")
            if options["material_id"]:
                rows = rows.filter(pk=options["material_id"])
            else:
                rows = rows.filter(job__status="queued").order_by("id")[:10]
            materials = list(rows)
            for material in materials:
                if options["in_process"]:
                    process_material(material, lease_token=options["lease_token"] or None)
                else:
                    run_material_job(material.id)
                material.refresh_from_db()
                self.stdout.write(f"Processed material {material.id}: {material.status}")
            if not options["watch"] or options["material_id"]:
                break
            if not materials:
                time.sleep(2)
