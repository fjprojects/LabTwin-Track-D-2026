from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class PreserveLearningMigrationTests(TransactionTestCase):
    def test_processing_migration_preserves_uploaded_files_and_job_state(self):
        old_target = [("labtwin", "0008_assessment_camera")]
        new_target = [("labtwin", "0009_material_processing_progress")]
        MigrationExecutor(connection).migrate(old_target)
        try:
            old = MigrationExecutor(connection).loader.project_state(old_target).apps
            user = old.get_model("auth", "User").objects.create(username="processing-migration")
            teacher = old.get_model("labtwin", "Account").objects.create(user_id=user.id, role="teacher")
            room = old.get_model("labtwin", "Classroom").objects.create(teacher_id=teacher.id, name="Keep files", join_code="PROCESSKEEP12")
            course = old.get_model("labtwin", "Course").objects.create(classroom_id=room.id, name="Keep course")
            material = old.get_model("labtwin", "CourseMaterial").objects.create(course_id=course.id, uploaded_by_id=teacher.id,
                title="Retained notes", filename="notes.pdf", file="retained/notes.pdf", kind="pdf", sha256="b" * 64, status="processing")
            job = old.get_model("labtwin", "MaterialProcessJob").objects.create(material_id=material.id, status="processing", attempts=2)
            MigrationExecutor(connection).migrate(new_target)
            new = MigrationExecutor(connection).loader.project_state(new_target).apps
            saved = new.get_model("labtwin", "CourseMaterial").objects.get(pk=material.id)
            self.assertEqual(saved.file.name, "retained/notes.pdf")
            self.assertEqual(saved.sha256, "b" * 64)
            retained_job = new.get_model("labtwin", "MaterialProcessJob").objects.get(pk=job.id)
            self.assertEqual(retained_job.status, "processing")
            self.assertEqual(retained_job.attempts, 2)
            self.assertEqual(retained_job.lease_token, "")
        finally:
            MigrationExecutor(connection).migrate(new_target)

    def test_camera_migration_preserves_assessments_answers_sources_and_mastery(self):
        old_target = [("labtwin", "0007_final_track_d")]
        new_target = [("labtwin", "0008_assessment_camera")]
        MigrationExecutor(connection).migrate(old_target)
        try:
            old = MigrationExecutor(connection).loader.project_state(old_target).apps
            user = old.get_model("auth", "User").objects.create(username="camera-migration")
            teacher = old.get_model("labtwin", "Account").objects.create(user_id=user.id, role="teacher")
            student = old.get_model("labtwin", "StudentProfile").objects.create(name="Retained camera learner")
            room = old.get_model("labtwin", "Classroom").objects.create(teacher_id=teacher.id, name="Keep", join_code="CAMERAKEEP123")
            course = old.get_model("labtwin", "Course").objects.create(classroom_id=room.id, name="Keep course")
            topic = old.get_model("labtwin", "CourseTopic").objects.create(course_id=course.id, name="Loops")
            assessment = old.get_model("labtwin", "AssessmentSession").objects.create(course_id=course.id, student_id=student.id, report={"score": 75}, status="completed")
            question = old.get_model("labtwin", "PracticeQuestion").objects.create(student_id=student.id, topic_id=topic.id, assessment_id=assessment.id, kind="quiz", prompt="Old question", answer={"correct_index": 2}, source_ids=[23], reason="Keep")
            attempt = old.get_model("labtwin", "PracticeAttempt").objects.create(question_id=question.id, request_id="retained", answer="2", score=100, status="completed")
            mastery = old.get_model("labtwin", "TopicMastery").objects.create(student_id=student.id, topic_id=topic.id, score=75, state="Developing", model_version="bkt-v1")
            MigrationExecutor(connection).migrate(new_target)
            new = MigrationExecutor(connection).loader.project_state(new_target).apps
            self.assertEqual(new.get_model("labtwin", "AssessmentSession").objects.get(pk=assessment.id).report, {"score": 75})
            self.assertEqual(new.get_model("labtwin", "PracticeQuestion").objects.get(pk=question.id).answer, {"correct_index": 2})
            self.assertEqual(new.get_model("labtwin", "PracticeQuestion").objects.get(pk=question.id).source_ids, [23])
            self.assertEqual(new.get_model("labtwin", "PracticeAttempt").objects.get(pk=attempt.id).answer, "2")
            self.assertEqual(new.get_model("labtwin", "TopicMastery").objects.get(pk=mastery.id).score, 75)
            saved = new.get_model("labtwin", "Course").objects.get(pk=course.id)
            self.assertTrue(saved.camera_cues_enabled); self.assertFalse(saved.camera_eye_closure)
            self.assertEqual(new.get_model("labtwin", "AssessmentCameraEvent").objects.count(), 0)
        finally:
            MigrationExecutor(connection).migrate([("labtwin", "0009_material_processing_progress")])

    def test_final_track_d_migration_retains_source_keys_history_and_legacy_model(self):
        old_target = [("labtwin", "0006_assignment_allow_solution_assignment_starter_code_and_more")]
        new_target = [("labtwin", "0007_final_track_d")]
        executor = MigrationExecutor(connection); executor.migrate(old_target)
        try:
            old = executor.loader.project_state(old_target).apps
            user = old.get_model("auth", "User").objects.create(username="track-d-migration")
            teacher = old.get_model("labtwin", "Account").objects.create(user_id=user.id, role="teacher")
            student = old.get_model("labtwin", "StudentProfile").objects.create(name="Preserved learner")
            classroom = old.get_model("labtwin", "Classroom").objects.create(teacher_id=teacher.id, name="Preserved", join_code="FINALKEEP123")
            course = old.get_model("labtwin", "Course").objects.create(classroom_id=classroom.id, name="Course")
            topic = old.get_model("labtwin", "CourseTopic").objects.create(course_id=course.id, name="Loops")
            material = old.get_model("labtwin", "CourseMaterial").objects.create(course_id=course.id, uploaded_by_id=teacher.id, title="Notes", filename="notes.pdf", file="retained.pdf", kind="pdf", status="ready", sha256="a" * 64)
            unit = old.get_model("labtwin", "SourceUnit").objects.create(material_id=material.id, number=1, page_number=23, text="A loop repeats instructions.")
            chunk = old.get_model("labtwin", "SourceChunk").objects.create(unit_id=unit.id, course_id=course.id, position=0, text=unit.text, embedding_model="hash-384-v1", embedding=[.1, .2])
            question = old.get_model("labtwin", "PracticeQuestion").objects.create(student_id=student.id, topic_id=topic.id, kind="code", difficulty=1, prompt="Repeat", tests=[{"input": "private", "expected": "private-key"}], source_ids=[chunk.id], reason="Prior question")
            mastery = old.get_model("labtwin", "TopicMastery").objects.create(student_id=student.id, topic_id=topic.id, score=64, state="Developing")
            executor = MigrationExecutor(connection); executor.migrate(new_target)
            new = executor.loader.project_state(new_target).apps
            saved = new.get_model("labtwin", "SourceChunk").objects.get(pk=chunk.id)
            self.assertEqual(saved.embedding, [.1, .2]); self.assertEqual(saved.unit.page_number, 23)
            self.assertFalse(saved.unit.archived)
            question = new.get_model("labtwin", "PracticeQuestion").objects.get(pk=question.id)
            self.assertEqual(question.tests[0]["expected"], "private-key")
            self.assertEqual(question.source_ids, [chunk.id])
            self.assertEqual(question.verification_status, "legacy")
            mastery = new.get_model("labtwin", "TopicMastery").objects.get(pk=mastery.id)
            self.assertEqual(mastery.score, 64)
            self.assertEqual(mastery.model_version, "legacy-weighted-v1")
        finally:
            MigrationExecutor(connection).migrate([("labtwin", "0009_material_processing_progress")])

    def test_upgrade_preserves_existing_profiles_classes_responses_and_tests(self):
        executor = MigrationExecutor(connection)
        old_target = [("labtwin", "0005_assignments_and_monitoring")]
        new_target = [("labtwin", "0006_assignment_allow_solution_assignment_starter_code_and_more")]
        executor.migrate(old_target)
        try:
            old = executor.loader.project_state(old_target).apps
            user = old.get_model("auth", "User").objects.create(username="migration-teacher")
            teacher = old.get_model("labtwin", "Account").objects.create(user_id=user.id, role="teacher")
            student = old.get_model("labtwin", "StudentProfile").objects.create(name="Retained student")
            room = old.get_model("labtwin", "Classroom").objects.create(teacher_id=teacher.id, name="Retained classroom", join_code="KEEP12345678")
            old.get_model("labtwin", "Enrollment").objects.create(classroom_id=room.id, student_id=student.id)
            response = old.get_model("labtwin", "StudentResponse").objects.create(student_id=student.id, question="Old question", stage="analysis", code="print(5)")
            assignment = old.get_model("labtwin", "Assignment").objects.create(classroom_id=room.id, title="Old task", instructions="Print 5", tests=[{"input": "", "expected": "5"}])
            executor = MigrationExecutor(connection); executor.migrate(new_target)
            new = executor.loader.project_state(new_target).apps
            self.assertEqual(new.get_model("labtwin", "StudentResponse").objects.get(pk=response.id).code, "print(5)")
            saved = new.get_model("labtwin", "Assignment").objects.get(pk=assignment.id)
            self.assertEqual(saved.tests, [{"input": "", "expected": "5"}])
            self.assertIsNone(saved.topic_id)
            self.assertFalse(saved.allow_solution)
            self.assertEqual(new.get_model("labtwin", "Enrollment").objects.get().student_id, student.id)
            self.assertEqual(new.get_model("labtwin", "Classroom").objects.get(pk=room.id).join_code, "KEEP12345678")
        finally:
            MigrationExecutor(connection).migrate([("labtwin", "0009_material_processing_progress")])
