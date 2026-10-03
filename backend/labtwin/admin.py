from django.contrib import admin
from .models import Account, Classroom, Enrollment, StudentProfile, StudentResponse, Assignment, AssignmentAttempt

@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'student')
    raw_id_fields = ('user', 'student')

admin.site.register([Classroom, Enrollment, StudentProfile, Assignment, AssignmentAttempt])

@admin.register(StudentResponse)
class StudentResponseAdmin(admin.ModelAdmin):
    list_display = ('student', 'stage', 'topic', 'status', 'created_at')
    readonly_fields = ('student', 'stage', 'question_id', 'question', 'topic', 'language', 'code', 'viva_answer', 'context', 'test_results', 'result', 'status', 'created_at', 'updated_at')
