from django.urls import path
from . import material_views as m, learning_views as l, report_views as r
from .media import private_media
from . import demo
from . import assessment_views as a
from . import evaluation_views as e
from . import camera_views as c

urlpatterns = [
    path("demo/", demo.demos),
    path("demo/<int:demo_id>/student/", demo.student_preview),
    path("courses/", m.courses),
    path("courses/<int:course_id>/", m.course_settings),
    path("courses/<int:course_id>/topics/", m.topics),
    path("courses/<int:course_id>/materials/", m.materials),
    path("materials/<int:material_id>/", m.material_detail),
    path("materials/<int:material_id>/retry/", m.retry_material),
    path("materials/<int:material_id>/media/", private_media, name="learning-media"),
    path("materials/<int:material_id>/visuals/<int:unit_id>/media/", private_media, name="learning-visual"),
    path("sources/<int:chunk_id>/", m.source),
    path("courses/<int:course_id>/ask/", m.ask),
    path("courses/<int:course_id>/ask/history/", m.ask_history),
    path("courses/<int:course_id>/path/", l.path_view),
    path("topics/<int:topic_id>/", l.topic_detail),
    path("topics/<int:topic_id>/bank/", l.bank),
    path("courses/<int:course_id>/practice/", l.practice),
    path("courses/<int:course_id>/assessments/", a.sessions),
    path("assessments/<int:session_id>/", a.detail),
    path("assessments/<int:session_id>/camera-events/", c.events),
    path("assessment-camera/events/<int:event_id>/response/", c.response),
    path("courses/<int:course_id>/assessment-activity/", c.review),
    path("courses/<int:course_id>/assessment-review/", a.review),
    path("practice-attempts/<int:attempt_id>/review/", a.review),
    path("exchanges/<int:exchange_id>/check/", a.conversation_check),
    path("courses/<int:course_id>/evaluations/", e.runs),
    path("evaluations/<int:run_id>/", e.detail),
    path("questions/<int:question_id>/attempts/", l.practice_attempts),
    path("questions/<int:question_id>/solution/", l.solution),
    path("hint/", l.hint),
    path("courses/<int:course_id>/vivas/", l.vivas),
    path("vivas/<int:session_id>/answer/", l.answer_viva),
    path("courses/<int:course_id>/report/", r.report),
    path("courses/<int:course_id>/insights/", r.insights),
    path("evidence/<int:evidence_id>/", r.evidence_detail),
    path("courses/<int:course_id>/viva-review/", r.teacher_vivas),
    path("viva-turns/<int:turn_id>/review/", r.review_viva),
]
