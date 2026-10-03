"""Exercise the real local queue/API using a disposable database and uploads.

Run with the application Python: python scripts/check_background_uploads.py
Set LABTWIN_TEST_EVALUATOR_PYTHON to also check background DeepEval execution.
No production database, credentials or student records are used. The explicit
hash embedding/offline configuration checks plumbing, not provider quality.
"""
import io
import argparse
import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record-pdf", type=Path, help="Additionally ingest a supplied real PDF and check its page-1 source route (not a browser click).")
    parser.add_argument("--results", type=Path, help="Save measured, disposable acceptance/evaluation evidence as JSON.")
    parser.add_argument("--all-languages", action="store_true", help="Also execute real Python, C and Java; GCC and a full JDK must be on PATH.")
    options = parser.parse_args()
    evidence = {"configuration": {"embedding": "hash", "remote_ai": False, "database": "disposable", "browser_verified": False}}
    with tempfile.TemporaryDirectory(prefix="labtwin-background-check-") as temporary:
        folder = Path(temporary)
        module = folder / "labtwin_background_settings.py"
        module.write_text("from backend.settings import *\n"
            f"DATABASES = {{'default': {{'ENGINE': 'django.db.backends.sqlite3', 'NAME': {str(folder / 'db.sqlite3')!r}}}}}\n"
            f"LABTWIN_MEDIA_ROOT = Path({str(folder / 'uploads')!r})\n"
            f"LABTWIN_VECTOR_ROOT = Path({str(folder / 'vectors')!r})\n"
            "ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']\n"
            "LABTWIN_PROCESS_MODE = 'local'\nLABTWIN_PROCESS_INLINE = False\n"
            "LABTWIN_EMBEDDING_BACKEND = 'hash'\nLABTWIN_DISABLE_REMOTE_AI = True\n"
            "LABTWIN_DEMO_ENABLED = True\nLABTWIN_MATERIAL_TIMEOUT_SECONDS = 120\n"
            f"LABTWIN_EVALUATOR_PYTHON = {os.getenv('LABTWIN_TEST_EVALUATOR_PYTHON', '')!r}\n", encoding="utf-8")
        sys.path[:0] = [temporary, str(ROOT / "backend")]
        os.environ["PYTHONPATH"] = os.pathsep.join([temporary, str(ROOT / "backend"), os.environ.get("PYTHONPATH", "")])
        os.environ["DJANGO_SETTINGS_MODULE"] = "labtwin_background_settings"
        os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
        import django
        django.setup()
        from django.core.management import call_command
        from django.test import Client
        from django.core.files.uploadedfile import SimpleUploadedFile
        from labtwin.models import CourseMaterial
        from labtwin.learning.demo import INSERT_SOLUTION, COUNT_SOLUTION
        call_command("migrate", verbosity=0)

        def post(client, route, data, expected=200):
            response = client.post("/api/" + route, json.dumps(data), content_type="application/json")
            check(response.status_code == expected, f"{route}: {response.status_code}: {response.content[:600]!r}")
            return response.json()

        def register(name, role):
            data = post(Client(), "auth/register/", {"username": name, "name": name,
                "password": "Disposable-Check-Password-89!", "role": role})
            return Client(HTTP_AUTHORIZATION="Bearer " + data["token"])

        teacher, student = register("queue-teacher", "teacher"), register("queue-student", "student")
        outsider = register("queue-outsider", "student")
        room = post(teacher, "classrooms/", {"name": "Queue regression"}, 201)["classroom"]
        post(student, "classrooms/join/", {"code": room["join_code"]})
        course = post(teacher, "learning/courses/", {"classroom_id": room["id"], "name": "Data Structures"}, 201)["course"]
        prefix = f"learning/courses/{course['id']}/"
        assets = ROOT / "backend/labtwin/demo_assets"
        uploads = []
        for filename in ("Data-Structures-Notes.pdf", "Linked-Lists.pptx", "Lecture-4.webm"):
            response = teacher.post("/api/" + prefix + "materials/", {"file": SimpleUploadedFile(filename, (assets / filename).read_bytes())})
            check(response.status_code == 201, response.content[:600])
            uploads.append(response.json()["material"]["id"])
        # A genuinely raster-only PDF must take the OCR path, not native text.
        from PIL import Image, ImageDraw, ImageFont
        from reportlab.pdfgen import canvas
        from reportlab.lib.utils import ImageReader
        image = Image.new("RGB", (1200, 300), "white")
        draw = ImageDraw.Draw(image)
        draw.text((35, 50), "Linked lists preserve the previous head.", fill="black", font=ImageFont.truetype("DejaVuSans.ttf", 44))
        pdf = io.BytesIO(); writer = canvas.Canvas(pdf, pagesize=(600, 150))
        writer.drawImage(ImageReader(image), 0, 0, 600, 150); writer.showPage(); writer.save()
        scanned = teacher.post("/api/" + prefix + "materials/", {"file": SimpleUploadedFile("scanned-notes.pdf", pdf.getvalue())}).json()["material"]["id"]
        uploads.append(scanned)
        broken = teacher.post("/api/" + prefix + "materials/", {"file": SimpleUploadedFile("broken.pdf", b"%PDF-1.7 corrupted")}).json()["material"]["id"]
        uploads.append(broken)
        real_pdf, uploaded_at = None, time.monotonic()
        if options.record_pdf:
            real_pdf = teacher.post("/api/" + prefix + "materials/", {"file": SimpleUploadedFile(options.record_pdf.name, options.record_pdf.read_bytes())}).json()["material"]["id"]
            uploads.append(real_pdf)
        deadline, observed = time.monotonic() + 180, set()
        while time.monotonic() < deadline:
            rows = teacher.get("/api/" + prefix + "materials/").json()["materials"]
            for row in rows:
                observed.add(row.get("processing", {}).get("stage"))
                check("lease_token" not in json.dumps(row), "Private worker lease exposed")
            if all(r["status"] in ("ready", "failed") for r in rows):
                break
            time.sleep(.3)
        states = {m.id: m for m in CourseMaterial.objects.filter(id__in=uploads)}
        check(all(states[pk].status == "ready" for pk in uploads if pk != broken), str([(m.filename, m.status, m.error) for m in states.values()]))
        check(states[broken].status == "failed" and states[broken].file.storage.exists(states[broken].file.name), "Corrupted PDF did not fail with retained upload")
        check(states[scanned].units.filter(text__icontains="previous head").exists(), "Scanned note OCR missing")
        evidence["uploads"] = [{"filename": m.filename, "status": m.status, "units": m.units.filter(archived=False).count(), "warnings": m.warnings} for m in states.values()]
        if real_pdf:
            record_answer = post(student, prefix + "ask/", {"question": "How is a palindrome checked with charAt?", "material_id": real_pdf})
            check(record_answer["grounded"], "Real PDF did not ground the question")
            record_citation = next((row for row in record_answer["citations"] if row["material_id"] == real_pdf and row["page_number"] == 1), None)
            check(record_citation, "Real PDF answer did not cite its page 1")
            record_source = student.get(f"/api/learning/sources/{record_citation['id']}/").json()
            record_media = urlsplit(record_source["media_url"])
            response = student.get(record_media.path + "?" + record_media.query)
            check(response.status_code == 200, "Real PDF source URL failed")
            check(b"".join(response.streaming_content) == options.record_pdf.read_bytes(), "Source URL served the wrong PDF bytes")
            evidence["real_pdf"] = {"filename": options.record_pdf.name, "ready_seconds_observed": round(time.monotonic() - uploaded_at, 2), "citation": record_citation, "source_http": response.status_code, "original_bytes_match": True, "browser_click": "NOT TESTED"}
        check(outsider.get("/api/" + prefix + "materials/").status_code == 404, "Classroom isolation failed")
        answer = post(student, prefix + "ask/", {"question": "Explain insertion at the beginning of a linked list"})
        check(answer["grounded"] and answer["citations"], "PDF/PPTX/video retrieval did not ground an answer")
        citation = answer["citations"][0]
        source_route = f"/api/learning/sources/{citation['id']}/"
        check(outsider.get(source_route).status_code == 404, "Source isolation failed")
        source = student.get(source_route).json()
        media = urlsplit(source["media_url"])
        check(student.get(media.path + "?" + media.query).status_code == 200, "Private source viewer failed")
        unsupported = post(student, prefix + "ask/", {"question": "What is tomorrow's weather in Tokyo?"})
        check(not unsupported["grounded"] and not unsupported["citations"], "Off-material question was falsely grounded")
        print("PASS background PDF, raster PDF OCR, PPTX, video, failed upload, progress, citations and isolation", flush=True)

        # Exercise the existing complete demonstrator against actual API routes.
        demo = post(teacher, "learning/demo/", {}, 201)["demo"]
        preview = post(teacher, f"learning/demo/{demo['id']}/student/", {})
        learner = Client(HTTP_AUTHORIZATION="Bearer " + preview["token"])
        p = f"learning/courses/{demo['course']['id']}/"
        grounded = post(learner, p + "ask/", {"question": "Explain insertion at beginning of linked list"})
        check({s["kind"] for s in grounded["citations"]} == {"pdf", "slides", "video"}, "Multimodal demo citations missing")
        attempt = post(learner, f"assignments/{demo['assignment_id']}/attempts/", {})["attempt"]
        failed = post(learner, f"attempts/{attempt['id']}/", {"code": attempt["code"]})["attempt"]
        check(failed["test_score"] < 100, "Conceptual mistake was not detected")
        for level in (1, 2, 3):
            post(learner, "learning/hint/", {"assignment_attempt_id": attempt["id"], "level": level})
        retry = post(learner, f"assignments/{demo['assignment_id']}/attempts/", {})["attempt"]
        check(post(learner, f"attempts/{retry['id']}/", {"code": INSERT_SOLUTION})["attempt"]["test_score"] == 100, "Corrected C code failed")
        question = post(learner, p + "practice/", {"topic_id": demo["topic_id"]}, 201)["question"]
        check(question["reason"] and question["resources"], "Adaptive reason/source missing")
        result = post(learner, f"learning/questions/{question['id']}/attempts/", {"request_id": str(uuid.uuid4()), "code": COUNT_SOLUTION})
        check(result["attempt"]["score"] == 100, "Adaptive reassessment failed")
        viva = post(learner, p + "vivas/", {"topic_id": demo["topic_id"]}, 201)["session"]
        post(learner, f"learning/vivas/{viva['id']}/answer/", {"turn_id": viva["turns"][0]["id"], "answer": "Connect the new node to the previous head before updating the head pointer."})
        for route in ("path/", "report/"):
            check(learner.get("/api/" + p + route).status_code == 200, route + " failed")
        insights = teacher.get("/api/" + p + "insights/").json()
        check(any("improved" in r["text"] for r in insights["observations"]), "Improvement evidence missing")
        check(teacher.get("/api/" + p + "insights/?format=csv").status_code == 200, "CSV export failed")
        print("PASS actual C execution, hidden-test feedback, progressive hints, retry, BKT, adaptive follow-up, viva, paths, reports and teacher insights", flush=True)
        # Answer keys are inspected only inside this disposable acceptance script.
        # Student question payloads must keep them private.
        from labtwin.models import PracticeQuestion, TopicMastery
        evidence["assessments"] = []
        for kind in ("quiz", "short_answer", "numerical"):
            assessment = post(learner, p + "assessments/", {"formats": [kind], "count": 1, "scope": {"topic_ids": [demo["topic_id"]]}}, 201)["assessment"]
            delivered = assessment["questions"][0]
            check(not {"answer", "tests", "support_quote", "solution"} & delivered.keys(), "Private assessment data exposed")
            q = PracticeQuestion.objects.get(pk=delivered["id"])
            key = q.answer.get("correct_index", q.answer.get("value", (q.answer.get("accepted") or [""])[0]))
            grade = post(learner, f"learning/questions/{q.id}/attempts/", {"request_id": str(uuid.uuid4()), "answer": str(key)})["attempt"]
            check(grade["score"] == 100 and grade["feedback"]["resources"], f"{kind}: grading/cited feedback failed")
            evidence["assessments"].append({"format": kind, "question_id": q.id, "verification": q.verification_status, "score": grade["score"], "feedback_citations": len(grade["feedback"]["resources"])})
        insights = teacher.get("/api/" + p + "insights/").json()
        report = learner.get("/api/" + p + "report/").json()
        evidence["teacher_insights"] = insights
        evidence["student_report"] = report
        evidence["saved_mastery"] = list(TopicMastery.objects.filter(topic__course_id=demo["course"]["id"]).values("student_id", "topic_id", "score", "state", "attempts", "knowledge_probability", "model_version"))
        if options.all_languages:
            from labtwin.views import run_tests
            programs = {"Python": "print(int(input()) + 1)",
                "C": '#include <stdio.h>\nint main(void){int x;scanf("%d",&x);printf("%d\\n",x+1);return 0;}',
                "Java": 'import java.util.Scanner; public class Main {public static void main(String[] a){Scanner s=new Scanner(System.in);System.out.println(s.nextInt()+1);}}'}
            evidence["language_execution"] = []
            for language, code in programs.items():
                score, rows = run_tests(code, [{"input": "2", "expected": "3"}, {"input": "-1", "expected": "0"}], language)
                check(score == 100 and all(r["passed"] for r in rows), f"Real {language} execution failed")
                evidence["language_execution"].append({"language": language, "score": score, "passed": len(rows)})
            print("PASS real Python, C and Java execution", flush=True)
        if os.getenv("LABTWIN_TEST_EVALUATOR_PYTHON"):
            run = post(teacher, p + "evaluations/", {"mode": "deterministic"}, 201)["run"]
            deadline = time.monotonic() + 150
            while time.monotonic() < deadline:
                run = teacher.get(f"/api/learning/evaluations/{run['id']}/").json()["run"]
                if run["status"] in ("completed", "failed"):
                    break
                time.sleep(.4)
            check(run["status"] == "completed" and run["results"], f"Background evaluation failed: {run}")
            evidence["evaluation"] = run
            print("PASS real background DeepEval benchmark; no substitute metrics", flush=True)
        from labtwin.learning.workers import _executor
        if _executor:
            _executor.shutdown(wait=True)
        if options.results:
            options.results.parent.mkdir(parents=True, exist_ok=True)
            options.results.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print("PASS disposable normal-architecture integration check", flush=True)


if __name__ == "__main__":
    main()
