from django.urls import path, re_path
from backend.urls import urlpatterns as original_patterns
from .access import access, health
from .frontend import frontend, static

urlpatterns = [
    path("deployment/health/", health),
    path("deployment/access/", access),
    *original_patterns,
    path("static/<path:path>", static),
    re_path(r"^(?P<path>.*)$", frontend),
]
