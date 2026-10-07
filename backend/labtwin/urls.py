from django.urls import include, path
from .response_history import response_history
from .access import student_access
from . import classroom_views, assessment_views, live_views
from . import password_reset, password_otp, phone_recovery

from .views import (
    upload_syllabus,
    next_question,
    analyze_code,
    tutor_help,
    evaluate_code,
    student_session,
)

from .memory_views import (
    save_attempt,
    progress_dashboard,
)

from .adaptive_views import (
    adaptive_next_question,
)

from .hint_views import (
    progressive_hint,
)


urlpatterns = [
    path("learning/", include("labtwin.learning.urls")),
    path("classrooms/<int:classroom_id>/assignments/", assessment_views.assignments),
    path("assignments/<int:assignment_id>/attempts/", assessment_views.start_attempt),
    path("assignments/<int:assignment_id>/submissions/", assessment_views.my_submissions),
    path("attempts/<int:attempt_id>/", assessment_views.attempt_detail),
    path("attempts/<int:attempt_id>/events/", assessment_views.events),
    path("attempts/<int:attempt_id>/grade/", assessment_views.grade_attempt),
    path("classrooms/<int:classroom_id>/reports/", assessment_views.reports),
    path("attempts/<int:attempt_id>/live/", live_views.live_session),
    path("classrooms/<int:classroom_id>/live/", live_views.classroom_live),
    path("live/<int:session_id>/watch/", live_views.watch),
    path("connections/<int:connection_id>/", live_views.signaling),
    path("auth/register/", classroom_views.register),
    path("auth/login/", classroom_views.login),
    path("auth/me/", classroom_views.me),
    path("auth/logout/", classroom_views.logout),
    path("auth/password-reset/", password_reset.request_reset),
    path("auth/password-reset/confirm/", password_reset.confirm_reset),
    path("auth/password-reset/otp/verify/", password_otp.verify_otp),
    path("auth/password-reset/sms/", phone_recovery.request_reset),
    path("auth/password-reset/sms/verify/", phone_recovery.verify_reset),
    path("auth/recovery-phone/", phone_recovery.setup_phone),
    path("auth/recovery-phone/verify/", phone_recovery.verify_phone),
    path("classrooms/", classroom_views.classrooms),
    path("classrooms/join/", classroom_views.join_classroom),
    path("classrooms/<int:classroom_id>/students/", classroom_views.roster),
    path("classrooms/<int:classroom_id>/students/<int:student_id>/", classroom_views.remove_member),
    path("response-history/", student_access(response_history, read_only=True)),

    path(
        "start-student/",
        classroom_views.start_student
    ),

    path(
        "save-attempt/",
        student_access(save_attempt)
    ),

    path(
        "progress/",
        student_access(progress_dashboard, read_only=True)
    ),

    path(
        "student-session/",
        student_access(student_session)
    ),

    path(
        "upload-syllabus/",
        student_access(upload_syllabus)
    ),

    path(
        "next-question/",
        student_access(next_question)
    ),

    path(
        "adaptive-next-question/",
        student_access(adaptive_next_question)
    ),

    path(
        "analyze/",
        student_access(analyze_code)
    ),

    path(
        "tutor/",
        student_access(tutor_help)
    ),

    path(
        "progressive-hint/",
        student_access(progressive_hint)
    ),

    path(
        "evaluate/",
        student_access(evaluate_code)
    ),
]
