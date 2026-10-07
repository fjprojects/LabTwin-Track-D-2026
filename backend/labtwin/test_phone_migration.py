from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class PhoneMigrationTests(TransactionTestCase):
    def test_phone_migration_is_additive_and_preserves_existing_auth_learning_data(self):
        executor = MigrationExecutor(connection)
        leaves = executor.loader.graph.leaf_nodes()
        old_target = [node for node in leaves if node[0] != "labtwin"] + [("labtwin", "0010_password_reset_otp")]
        executor.migrate(old_target)
        try:
            old = MigrationExecutor(connection).loader.project_state(old_target).apps
            user = old.get_model("auth", "User").objects.create(username="kept-phone-migration", email="kept@example.test", password="retained-password-hash", last_login=None)
            account = old.get_model("labtwin", "Account").objects.create(user_id=user.pk, role="teacher")
            room = old.get_model("labtwin", "Classroom").objects.create(teacher_id=account.pk, name="Kept", join_code="KEPTPHONE0011")
            course = old.get_model("labtwin", "Course").objects.create(classroom_id=room.pk, name="Kept course")
            material = old.get_model("labtwin", "CourseMaterial").objects.create(course_id=course.pk, uploaded_by_id=account.pk, title="Kept notes", filename="kept.pdf", file="retained/kept.pdf", kind="pdf", status="ready", sha256="a"*64)
            otp = old.get_model("labtwin", "PasswordResetOTP").objects.create(account_id=account.pk, request_id="00000000-0000-4000-8000-000000000001", code_digest="b"*64, state_digest="c"*64, issued_at=timezone.now(), expires_at=timezone.now())
            entries = (("auth", "User", user.pk), ("labtwin", "Account", account.pk),
                       ("labtwin", "Classroom", room.pk), ("labtwin", "Course", course.pk),
                       ("labtwin", "CourseMaterial", material.pk), ("labtwin", "PasswordResetOTP", otp.pk))
            before = [old.get_model(app, name).objects.filter(pk=pk).values().get() for app, name, pk in entries]
            MigrationExecutor(connection).migrate(leaves)
            new = MigrationExecutor(connection).loader.project_state(leaves).apps
            after = [new.get_model(app, name).objects.filter(pk=pk).values().get() for app, name, pk in entries]
            self.assertEqual(before, after)
            self.assertFalse(new.get_model("labtwin", "RecoveryPhone").objects.exists())
            self.assertFalse(new.get_model("labtwin", "PhoneOTP").objects.exists())
        finally:
            MigrationExecutor(connection).migrate(leaves)
