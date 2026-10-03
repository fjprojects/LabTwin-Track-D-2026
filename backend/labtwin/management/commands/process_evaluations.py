import time
from django.core.management.base import BaseCommand
from labtwin.models import EvaluationRun
from labtwin.learning.evaluation import process_evaluation


class Command(BaseCommand):
    help = "Execute isolated queued DeepEval benchmarks. Use a dedicated worker."
    requires_system_checks = []
    def add_arguments(self, parser):
        parser.add_argument("--watch", action="store_true")
        parser.add_argument("--run-id", type=int)
    def handle(self, *args, **options):
        while True:
            queued = EvaluationRun.objects.filter(status="queued").order_by("id")
            if options["run_id"]:
                queued = queued.filter(pk=options["run_id"])
            rows = list(queued[:5])
            for row in rows:
                process_evaluation(row)
                self.stdout.write(f"Evaluation {row.id}: {row.status}")
            if not options["watch"] or options["run_id"]:
                break
            if not rows:
                time.sleep(2)
