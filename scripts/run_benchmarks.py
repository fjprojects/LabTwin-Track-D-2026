"""Reproducible end-to-end benchmark in a disposable database and private store."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import math
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))


def location(chunk):
    unit = chunk.unit
    place = f"page:{unit.page_number}" if unit.page_number else f"slide:{unit.slide_number}" if unit.slide_number else f"time:{int(unit.start_seconds)}" if unit.start_seconds is not None else f"section:{unit.number}"
    return unit.material.filename + "|" + place


def personalization(course, teacher, topics):
    from django.contrib.auth import get_user_model
    from labtwin.models import StudentProfile, Account, Enrollment, QuestionBankItem, TopicMastery, PracticeQuestion, SourceChunk
    from labtwin.learning.mastery import record_evidence, learning_path
    from labtwin.learning.practice import generate_question, grade
    from labtwin.learning.novelty import repetition_rate
    from labtwin.learning.learner_model import tutoring_policy
    from labtwin.learning.access import LearningError
    # Human-authored, source-cited banks give a fixed labelled test pool. They
    # are not presented as model-generated or independently LLM-verified.
    prompts = {
        "Programming Fundamentals": [
            ("What does a variable store?", ["A value", "A loop"], 0),
            ("What repeats a block of instructions?", ["A loop", "A variable"], 0),
            ("Choose the source-backed description of a conditional.", ["It selects a branch based on a condition", "It always repeats forever"], 0),
            ("A counter begins at zero and is incremented once. What is its value?", ["1", "0"], 0),
            ("A program must select one of two branches after a comparison. Which construct fits?", ["A conditional", "A variable name alone"], 0),
            ("Repeated processing of four values needs which source construct?", ["A loop", "A constant output"], 0),
            ("After a loop increments a zero counter four times, what remains?", ["4", "0"], 0),
            ("Which source concept preserves an intermediate count for later use?", ["A variable", "An unused branch"], 0)
        ],
        "Linked Lists": [
            ("Which pointer identifies the first list node?", ["Head", "The last node's next"], 0),
            ("Which value represents an empty list's head?", ["NULL", "An allocated node"], 0),
            ("What must a new node connect to before head is updated?", ["Previous head", "Always NULL"], 0),
            ("What becomes unreachable if insertion severs the old chain?", ["Old nodes", "Only a counter"], 0),
            ("A non-empty list receives a front insertion. Which step preserves its earlier nodes?", ["Set new next to previous head", "Discard previous head first"], 0),
            ("Choose the stopping condition for counting reachable nodes.", ["Current pointer is NULL", "After exactly one node"], 0),
            ("Why can a broken insertion still pass a single-node example?", ["There are no older nodes to preserve", "NULL means every node is preserved"], 0),
            ("How can traversal count include every earlier insertion?", ["Follow every next link until NULL", "Read head once and stop"], 0)
        ]}
    for topic in topics:
        for index, (prompt, options, expected) in enumerate(prompts[topic.name]):
            sources = SourceChunk.objects.filter(course=course, unit__archived=False)
            if topic.name == "Linked Lists":
                # Cite the actual supporting page for each concept, rather than
                # attaching every question to the first page of the textbook.
                page = [1, 1, 2, 3, 2, 4, 3, 4][index]
                source = sources.filter(unit__material__filename="Data-Structures-Notes.pdf", unit__page_number=page, unit__content_type="text").first()
            else:
                source = sources.filter(unit__topic_name=topic.name).first()
            if not source:
                raise RuntimeError("The benchmark question's supporting source is missing.")
            QuestionBankItem.objects.create(topic=topic, title=f"Benchmark item {index + 1}", prompt=prompt,
                difficulty=1 if index < 2 else 2 if index < 5 else 3, options=options,
                answer={"correct_index": expected}, explanation=options[expected], source_ids=[source.id],
                metadata={"team_authored_benchmark": True, "support_quote": source.text})
    profiles = [
        ("A · Strong fundamentals, weak linked lists", [True, False], [[False, True], [True, True], [True, True], [True, True]]),
        ("B · Weak fundamentals", [False, False], [[False, False], [False, True], [True, True], [True, True]]),
        ("C · Strong overall", [True, True], [[True, True], [True, True], [True, True], [True, True]])]
    outputs = []
    for index, (name, diagnostic, sessions) in enumerate(profiles):
        user = get_user_model().objects.create(username=f"benchmark-student-{index}")
        student = StudentProfile.objects.create(name=name)
        Account.objects.create(user=user, student=student, role="student")
        Enrollment.objects.create(classroom=course.classroom, student=student)
        for topic, correct in zip(topics, diagnostic):
            record_evidence(student, topic, f"diagnostic:{topic.id}", "diagnostic", 100 if correct else 0,
                detail={"simulated": True, "option_count": 2})
        before = {topic.name: TopicMastery.objects.get(student=student, topic=topic).score for topic in topics}
        history = []
        for session_index, outcomes in enumerate(sessions, 1):
            delivered = []
            for turn, correct in enumerate(outcomes):
                rows = {m.topic_id: m for m in TopicMastery.objects.filter(student=student, topic__in=topics)}
                selected = min(topics, key=lambda t: rows[t.id].score)
                try:
                    question = generate_question(student, course, selected, "quiz")
                except LearningError:
                    continue
                old = rows[question.topic_id].score
                # Proper scoring rule on the next observed response, before
                # updating the model. Compare with an unchanged prior baseline.
                p = rows[question.topic_id].knowledge_probability
                guessing = 1 / len(question.options)
                predicted_correct = p * .9 + (1 - p) * guessing
                static_correct = .35 * .9 + .65 * guessing
                answer = question.answer["correct_index"] if correct else 1 - question.answer["correct_index"]
                score, _ = grade(question, "", answer)
                updated = record_evidence(student, question.topic, f"simulation:{session_index}:{turn}", "quiz", score,
                    misconception="Needs source concept review" if not correct else "", detail={"question_id": question.id, "simulated": True, "option_count": len(question.options)})
                delivered.append({"topic": question.topic.name, "question": question.prompt, "difficulty": question.difficulty,
                    "correct": correct, "mastery_before": old, "mastery_after": updated.score, "reason": question.reason,
                    "predicted_correct_before_answer": round(predicted_correct, 6),
                    "brier_loss": (predicted_correct - int(correct)) ** 2,
                    "static_prior_brier_loss": (static_correct - int(correct)) ** 2,
                    "verification": question.verification_status})
            path = learning_path(student, course)
            probabilities = [m.knowledge_probability for m in TopicMastery.objects.filter(student=student, topic__in=topics)]
            entropy = [-p * math.log2(p) - (1 - p) * math.log2(1 - p) for p in probabilities]
            history.append({"session": session_index, "questions": delivered,
                "scored_evidence_count": sum(m.attempts for m in TopicMastery.objects.filter(student=student, topic__in=topics)),
                "mean_model_uncertainty_bits": round(sum(entropy) / len(entropy), 4),
                "mean_question_difficulty": sum(q["difficulty"] for q in delivered) / len(delivered) if delivered else None,
                "prediction_brier": sum(q["brier_loss"] for q in delivered) / len(delivered) if delivered else None,
                "recommendations": [{"topic": task["topic"], "reason": task["reason"]} for task in path["tasks"]],
                "tutoring_policy": tutoring_policy(student, course, "Explain linked lists"),
                "mastery": {topic.name: TopicMastery.objects.get(student=student, topic=topic).score for topic in topics}})
        final = {topic.name: TopicMastery.objects.get(student=student, topic=topic).score for topic in topics}
        delivered_questions = [q for session in history for q in session["questions"]]
        outputs.append({"profile": name, "initial_mastery": before, "final_mastery": final,
            "prediction_brier": sum(q["brier_loss"] for q in delivered_questions) / len(delivered_questions) if delivered_questions else None,
            "static_prior_prediction_brier": sum(q["static_prior_brier_loss"] for q in delivered_questions) / len(delivered_questions) if delivered_questions else None,
            "session1_to4_brier_reduction": history[0]["prediction_brier"] - history[-1]["prediction_brier"] if history[0]["prediction_brier"] is not None and history[-1]["prediction_brier"] is not None else None,
            "mastery_gain": {key: round(final[key] - before[key], 1) for key in before}, "sessions": history,
            "question_repetition": repetition_rate(list(PracticeQuestion.objects.filter(student=student).order_by("id")))})
    return {"profiles": outputs, "sessions_per_profile": 4, "method": "Controlled synthetic diagnostic and answer outcomes, actual LabTwin selection/grading/BKT updates.",
        "limitation": "This measures model response to accumulating evidence. Controlled improving answers do not establish causal learning benefit in real students; parameters and difficulty labels are not fitted to a population."}


def run(config, temp):
    os.environ["DJANGO_SETTINGS_MODULE"] = "backend.test_settings"
    import django
    from django.conf import settings
    settings.DATABASES["default"]["NAME"] = str(Path(temp) / "benchmark.sqlite3")
    settings.LABTWIN_MEDIA_ROOT = Path(temp) / "uploads"
    settings.LABTWIN_VECTOR_ROOT = Path(temp) / "vectors"
    settings.LABTWIN_EMBEDDING_BACKEND = config.get("embedding_backend", "hash")
    settings.LABTWIN_DISABLE_REMOTE_AI = config.get("mode") != "llm"
    settings.LABTWIN_TUTOR_MODEL = config.get("tutor_model", "openai/gpt-oss-20b")
    settings.LABTWIN_VERIFIER_MODEL = config.get("verifier_model", "")
    settings.LABTWIN_VISION_MODEL = config.get("vision_model", "")
    django.setup()
    from django.core.management import call_command
    call_command("migrate", verbosity=0)
    from django.contrib.auth import get_user_model
    from django.core.files import File
    from labtwin.models import Account, Classroom, Course, CourseTopic, CourseMaterial, MaterialProcessJob, SourceChunk
    from labtwin.learning.ingestion import process_material
    from labtwin.learning.rag import grounded_answer
    from labtwin.learning.vectors import retrieve
    teacher = Account.objects.create(user=get_user_model().objects.create(username="benchmark-teacher"), role="teacher")
    room = Classroom.objects.create(teacher=teacher, name="Benchmark only", join_code="BENCHMARKONLY")
    course = Course.objects.create(classroom=room, name="Team benchmark", is_demo=config.get("mode") != "llm")
    topic = CourseTopic.objects.create(course=course, name="Linked Lists")
    assets = ROOT / "backend/labtwin/demo_assets"
    if not assets.is_dir():
        assets = ROOT / "labtwin/demo_assets"  # Docker's existing backend layout
    materials = {}
    for name, kind in [("Data-Structures-Notes.pdf", "pdf"), ("Linked-Lists.pptx", "slides"), ("Lecture-4.webm", "video")]:
        path = assets / name
        with path.open("rb") as file:
            material = CourseMaterial.objects.create(course=course, topic=topic, uploaded_by=teacher, title=path.stem, filename=name,
                kind=kind, file=File(file, name=name), byte_size=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        MaterialProcessJob.objects.create(material=material)
        if not process_material(material):
            raise RuntimeError(f"Benchmark ingestion failed for {name}: {material.error}")
        materials[name] = material
    dataset_path = ROOT / "evaluation/benchmark.json"
    dataset = json.loads(dataset_path.read_text())
    rows = []
    chunks = list(SourceChunk.objects.select_related("unit__material", "course__classroom"))
    for case in dataset["cases"]:
        material_id = materials[case["material"]].id if case.get("material") else None
        matches = retrieve([course], case["question"], material_id)
        answer = grounded_answer(course, case["question"], material_id)
        rows.append({**case, "answer": answer["answer"], "grounded": answer["grounded"], "answer_mode": answer["mode"], "claims": answer["claims"],
            "citations": answer["citations"], "contexts": [m["chunk"].text for m in matches], "retrieved_locations": [location(m["chunk"]) for m in matches],
            "gold_locations": case["gold"], "gold_contexts": [c.text for c in chunks if location(c) in case["gold"]]})
    env = os.environ.copy()
    if config.get("evaluator_extra_path"):
        env["PYTHONPATH"] = config["evaluator_extra_path"]
    else:
        env.pop("PYTHONPATH", None)
    worker = subprocess.run([config["evaluator_python"], str(ROOT / "scripts/evaluate_metrics.py")],
        input=json.dumps({"cases": rows, "mode": config.get("mode"), "judge_model": config.get("judge_model")}), text=True,
        capture_output=True, timeout=600 if config.get("mode") == "llm" else 120, env=env, cwd=temp)
    marker = next((line[len("LABTWIN_RESULT="):] for line in reversed(worker.stdout.splitlines()) if line.startswith("LABTWIN_RESULT=")), None)
    if worker.returncode or not marker:
        # Exceptions are useful for local debugging, but never log provider keys.
        raise RuntimeError("DeepEval worker failed: " + worker.stderr[-1600:])
    metrics = json.loads(marker)
    for row in rows:
        row["evaluation"] = next((r["metrics"] for r in metrics["cases"] if r["id"] == row["id"]), [])
    off = [r for r in rows if not r["supported"]]
    handled = sum(not r["grounded"] and not r["citations"] for r in off)
    # Add an original fundamentals source for the independent learner experiment.
    foundation = CourseTopic.objects.create(course=course, name="Programming Fundamentals", position=0)
    from django.core.files.base import ContentFile
    content = b"Programming Fundamentals\nA variable stores a value. A loop repeats a block of instructions. A conditional selects a branch based on a condition. A counter starts at zero and increments once for every processed item. Four increments produce a count of four."
    primer = CourseMaterial.objects.create(course=course, topic=foundation, uploaded_by=teacher, title="Fundamentals Primer", filename="Fundamentals.txt", kind="text", file=ContentFile(content, name="Fundamentals.txt"), sha256=hashlib.sha256(content).hexdigest(), byte_size=len(content))
    MaterialProcessJob.objects.create(material=primer)
    if not process_material(primer):
        raise RuntimeError("Benchmark fundamentals ingestion failed")
    topic.prerequisites.add(foundation)
    profiles = personalization(course, teacher, [foundation, topic])
    return {"executed_at": datetime.now(timezone.utc).isoformat(), "pipeline_version": "track-d-v1",
        "source_hashes": {name: material.sha256 for name, material in materials.items()},
        "dataset_version": dataset["version"], "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "framework": metrics["framework"], "framework_version": metrics["framework_version"], "mode": metrics["mode"],
        "metric_interpretation": metrics["metric_interpretation"], "metrics": metrics["metrics"], "judge_model": metrics["judge_model"],
        "unsupported_queries": {"correct": handled, "total": len(off), "rate": handled / len(off) if off else None},
        "cases": rows, "personalization": profiles, "embedding_backend": settings.LABTWIN_EMBEDDING_BACKEND,
        "isolated_from_production": True, "limitations": ["Small, original teaching corpus, not a broad academic benchmark.", "Native figures tested; configured vision and automatic speech providers require live-provider validation.", profiles["limitation"]]}


if __name__ == "__main__":
    output = None
    if len(sys.argv) > 1:
        import argparse
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
        parser = argparse.ArgumentParser(description="Execute the isolated LabTwin/DeepEval benchmark and save measured results.")
        parser.add_argument("--output", type=Path, required=True)
        parser.add_argument("--mode", choices=["deterministic", "llm"], default="deterministic")
        parser.add_argument("--evaluator-python", default=os.getenv("LABTWIN_EVALUATOR_PYTHON", str(ROOT / ".venv-evaluation/bin/python")))
        parser.add_argument("--embedding-backend", choices=["hash", "onnx"], default="hash")
        parser.add_argument("--judge-model", default=os.getenv("LABTWIN_EVALUATION_JUDGE_MODEL", ""))
        args = parser.parse_args()
        output = args.output
        config = {"mode": args.mode, "evaluator_python": args.evaluator_python,
            "embedding_backend": args.embedding_backend, "judge_model": args.judge_model,
            "tutor_model": os.getenv("LABTWIN_TUTOR_MODEL", "openai/gpt-oss-20b"),
            "vision_model": os.getenv("LABTWIN_VISION_MODEL", ""), "verifier_model": os.getenv("LABTWIN_VERIFIER_MODEL", ""),
            "evaluator_extra_path": os.getenv("LABTWIN_EVALUATOR_EXTRA_PATH", "")}
    else:
        # The authenticated worker retains the existing structured stdin protocol.
        config = json.load(sys.stdin)
    with tempfile.TemporaryDirectory(prefix="labtwin-benchmark-") as temp:
        result = run(config, temp)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n")
        print(f"Saved actual {result['framework']} {result['framework_version']} {result['mode']} results to {output}")
    else:
        print("LABTWIN_RESULT=" + json.dumps(result))
