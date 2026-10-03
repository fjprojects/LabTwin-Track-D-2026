"""Serve the existing compiled Vite UI without exposing source or private media."""
import mimetypes
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, HttpResponse


def file_response(root, name):
    root = Path(root).resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root) or any(part.startswith(".") for part in Path(name).parts) or not path.is_file():
        return HttpResponse(status=404)
    response = FileResponse(path.open("rb"), content_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream")
    response["Cache-Control"] = "private, no-store" if path.name == "index.html" else "private, max-age=3600"
    return response


def frontend(request, path=""):
    if request.method not in ("GET", "HEAD"):
        return HttpResponse(status=405)
    if path.startswith(("api/", "admin/", "deployment/")):
        return HttpResponse(status=404)
    # The current UI uses state/hash navigation. Unknown asset paths must be
    # 404s rather than HTML mistaken for JS, WASM or a PDF.
    return file_response(settings.LABTWIN_FRONTEND_ROOT, path or "index.html")


def static(request, path):
    if request.method not in ("GET", "HEAD"):
        return HttpResponse(status=405)
    return file_response(settings.STATIC_ROOT, path)
