"""Queue and retain real framework executions; benchmark data stays isolated."""
import json
import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from ..models import EvaluationRun
from .access import LearningError


def process_evaluation(run):
    if not EvaluationRun.objects.filter(pk=run.pk, status="queued").update(status="running", started_at=timezone.now()):
        return False
    try:
        evaluator = getattr(settings, "LABTWIN_EVALUATOR_PYTHON", "")
        if not evaluator or not Path(evaluator).is_file():
            raise LearningError("Configure LABTWIN_EVALUATOR_PYTHON with the separate requirements-evaluation.txt environment. No metrics were generated.", 503)
        root = Path(getattr(settings, "LABTWIN_PROJECT_ROOT", Path(settings.BASE_DIR).parent))
        config = {"mode": run.mode, "evaluator_python": evaluator,
            "evaluator_extra_path": getattr(settings, "LABTWIN_EVALUATOR_EXTRA_PATH", ""),
            "embedding_backend": getattr(settings, "LABTWIN_EMBEDDING_BACKEND", "hash") if run.mode == "llm" else "hash",
            "judge_model": getattr(settings, "LABTWIN_EVALUATION_JUDGE_MODEL", ""),
            "tutor_model": getattr(settings, "LABTWIN_TUTOR_MODEL", "openai/gpt-oss-20b"),
            "verifier_model": getattr(settings, "LABTWIN_VERIFIER_MODEL", ""), "vision_model": getattr(settings, "LABTWIN_VISION_MODEL", "")}
        child = subprocess.run([sys.executable, str(root / "scripts/run_benchmarks.py")], input=json.dumps(config), text=True,
            capture_output=True, timeout=900 if run.mode == "llm" else 240, cwd=root, env=os.environ.copy())
        marker = next((line[len("LABTWIN_RESULT="):] for line in reversed(child.stdout.splitlines()) if line.startswith("LABTWIN_RESULT=")), None)
        if child.returncode or not marker:
            raise LearningError("Evaluation failed; no substitute scores were saved. Check the worker log and evaluator dependencies.", 503)
        run.results = json.loads(marker)
        run.dataset_version = run.results["dataset_version"]
        run.status, run.error = "completed", ""
    except Exception as error:
        run.status = "failed"
        run.error = error.message if isinstance(error, LearningError) else "The benchmark worker could not finish. Check its environment and retry."
    run.finished_at = timezone.now()
    run.save(update_fields=["status", "results", "dataset_version", "error", "finished_at"])
    return run.status == "completed"


def run_data(run, detail=False):
    result = {"id": run.id, "status": run.status, "mode": run.mode, "framework": run.framework,
        "dataset_version": run.dataset_version, "created_at": run.created_at.isoformat(), "error": run.error}
    result["results"] = run.results if detail else {k: v for k, v in run.results.items() if k not in ("cases", "personalization")}
    return result
