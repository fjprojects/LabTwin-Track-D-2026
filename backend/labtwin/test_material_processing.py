"""Queue/OCR regressions for the normal, non-inline upload workflow."""
import io
import subprocess
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone

from .models import Course, CourseTopic, CourseMaterial, SourceChunk
from .test_classrooms import ClassroomFixture
from .learning.processing import claim_material, progress, reset_material, finish_material, ProcessingInterrupted
from .learning.workers import run_material_job


@override_settings(LABTWIN_PROCESS_INLINE=False, LABTWIN_PROCESS_MODE="external")
class MaterialProcessingTests(ClassroomFixture):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.files = tempfile.TemporaryDirectory(prefix="labtwin-processing-")
        cls.override = override_settings(LABTWIN_MEDIA_ROOT=cls.files.name + "/uploads", LABTWIN_VECTOR_ROOT=cls.files.name + "/vectors")
        cls.override.enable()

    @classmethod
    def tearDownClass(cls):
        cls.override.disable()
        super().tearDownClass()
        cls.files.cleanup()

    def setUp(self):
        super().setUp()
        self.join()
        self.course = Course.objects.create(classroom=self.room, name="Data Structures")
        self.topic = CourseTopic.objects.create(course=self.course, name="Linked Lists")

    def upload(self, name="notes.txt", content=b"Linked lists preserve the previous head."):
        return self.tc.post(f"/api/learning/courses/{self.course.id}/materials/", {"file": SimpleUploadedFile(name, content), "topic_id": self.topic.id})

    def material(self):
        return CourseMaterial.objects.get(pk=self.upload().json()["material"]["id"])

    @override_settings(LABTWIN_PROCESS_MODE="local")
    def test_upload_dispatches_only_after_commit(self):
        with patch("labtwin.learning.workers._submit") as submit:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.upload()
                self.assertEqual(response.status_code, 201)
                self.assertEqual(response.json()["material"]["status"], "queued")
                submit.assert_not_called()
            submit.assert_called_once_with("material", response.json()["material"]["id"])

    def test_only_one_worker_can_claim_an_upload(self):
        material = self.material()
        self.assertTrue(claim_material(material.id))
        self.assertIsNone(claim_material(material.id))
        material.job.refresh_from_db()
        self.assertEqual(material.job.attempts, 1)

    def test_progress_counts_and_lease_are_private(self):
        material = self.material()
        token = claim_material(material.id)
        progress(material.id, token, "pdf_ocr", 3, 8, "pages")
        response = self.tc.get(f"/api/learning/materials/{material.id}/")
        self.assertEqual(response.json()["material"]["processing"]["completed"], 3)
        self.assertEqual(response.json()["material"]["processing"]["total"], 8)
        self.assertNotIn(token, response.content.decode())
        self.assertEqual(self.sc.get(f"/api/learning/materials/{material.id}/").status_code, 409)
        self.assertEqual(self.tc2.get(f"/api/learning/materials/{material.id}/").status_code, 404)

    def test_hung_parser_times_out_without_losing_the_upload(self):
        material = self.material()
        with patch("labtwin.learning.workers.subprocess.run", side_effect=subprocess.TimeoutExpired("worker", 600)):
            run_material_job(material.id)
        material.refresh_from_db()
        self.assertEqual(material.status, "failed")
        self.assertIn("time limit", material.error)
        self.assertTrue(material.file.storage.exists(material.file.name))

    def test_worker_crash_is_visible_and_retryable(self):
        material = self.material()
        with patch("labtwin.learning.workers.subprocess.run", return_value=subprocess.CompletedProcess([], 1)):
            run_material_job(material.id)
        material.refresh_from_db()
        self.assertEqual(material.status, "failed")
        response = self.post(self.tc, f"learning/materials/{material.id}/retry/", {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["material"]["status"], "queued")

    def test_poll_recovers_interrupted_processing_and_retains_file(self):
        material = self.material()
        token = claim_material(material.id)
        material.job.__class__.objects.filter(material=material).update(started_at=timezone.now() - timedelta(hours=1))
        response = self.tc.get(f"/api/learning/courses/{self.course.id}/materials/")
        self.assertEqual(response.json()["materials"][0]["status"], "failed")
        material.refresh_from_db()
        self.assertTrue(material.file.storage.exists(material.file.name))
        with self.assertRaises(ProcessingInterrupted):
            progress(material.id, token, "ready")

    def test_old_lease_cannot_overwrite_a_new_retry(self):
        material = self.material()
        old = claim_material(material.id)
        finish_material(material, old, error="Interrupted")
        material.refresh_from_db()
        reset_material(material)
        current = claim_material(material.id)
        with self.assertRaises(ProcessingInterrupted):
            finish_material(material, old)
        material.refresh_from_db()
        self.assertEqual(material.status, "processing")
        self.assertEqual(material.job.lease_token, current)

    def test_active_upload_cannot_be_retried_or_removed(self):
        material = self.material()
        claim_material(material.id)
        self.assertEqual(self.post(self.tc, f"learning/materials/{material.id}/retry/", {}).status_code, 409)
        self.assertEqual(self.tc.delete(f"/api/learning/materials/{material.id}/").status_code, 409)

    @override_settings(LABTWIN_PROCESS_MODE="local")
    def test_authorized_poll_resumes_queue_but_other_class_does_not(self):
        material = self.material()
        with patch("labtwin.learning.workers._submit") as submit:
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(self.tc2.get(f"/api/learning/courses/{self.course.id}/materials/").status_code, 404)
            submit.assert_not_called()
            with self.captureOnCommitCallbacks(execute=True):
                self.tc.get(f"/api/learning/courses/{self.course.id}/materials/")
            submit.assert_called_once_with("material", material.id)

    @staticmethod
    def scan_pdf():
        from PIL import Image, ImageDraw, ImageFont
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas
        image = Image.new("RGB", (1200, 450), "white")
        font = ImageFont.truetype("DejaVuSans.ttf", 44)
        draw = ImageDraw.Draw(image)
        draw.text((40, 60), "Linked lists preserve the previous head.", font=font, fill="black")
        draw.text((40, 135), "Connect the new node before updating head.", font=font, fill="black")
        result = io.BytesIO(); writer = canvas.Canvas(result, pagesize=(600, 225))
        writer.drawImage(ImageReader(image), 0, 0, 600, 225); writer.showPage(); writer.save()
        return result.getvalue()

    @override_settings(LABTWIN_PROCESS_INLINE=True)
    def test_scanned_pdf_ocr_works_without_poppler(self):
        import shutil
        original = shutil.which
        with patch("labtwin.learning.extraction.shutil.which", side_effect=lambda command: None if command == "pdftoppm" else original(command)):
            response = self.upload("scan.pdf", self.scan_pdf())
        self.assertEqual(response.json()["material"]["status"], "ready", response.content)
        self.assertTrue(SourceChunk.objects.filter(text__icontains="previous head").exists())

    @override_settings(LABTWIN_PROCESS_INLINE=True)
    def test_scan_without_ocr_fails_clearly_instead_of_indexing_empty_labels(self):
        with patch("labtwin.learning.extraction.shutil.which", return_value=None):
            response = self.upload("scan.pdf", self.scan_pdf())
        material = response.json()["material"]
        self.assertEqual(material["status"], "failed")
        self.assertIn("Tesseract", material["error"])
        self.assertFalse(SourceChunk.objects.exists())

    def test_pdf_progress_uses_actual_page_counts(self):
        from reportlab.pdfgen import canvas
        from .learning.extraction import pdf_units
        pdf = io.BytesIO(); writer = canvas.Canvas(pdf)
        for number in range(3):
            writer.drawString(30, 700, f"Linked lists notes page {number + 1}."); writer.showPage()
        writer.save(); path = Path(self.files.name) / "pages.pdf"; path.write_bytes(pdf.getvalue())
        events = []
        units, _ = pdf_units(path, progress=lambda *args: events.append(args))
        self.assertEqual([unit["page_number"] for unit in units], [1, 2, 3])
        self.assertIn(("pdf_text", 3, 3, "pages"), events)

    def test_long_notes_without_prerequisite_claims_do_not_walk_all_topic_pairs(self):
        from .learning.taxonomy import tag_units
        CourseTopic.objects.bulk_create([CourseTopic(course=self.course, name=f"Section {i}") for i in range(80)])
        material = self.material()
        with patch("labtwin.learning.taxonomy.would_cycle") as walk:
            tag_units(material, [{"number": 1, "text": "Linked lists preserve the head."}])
        walk.assert_not_called()
