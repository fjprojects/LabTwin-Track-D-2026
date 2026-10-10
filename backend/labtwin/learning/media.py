"""Short-lived private media URLs, re-authorized on every range request."""
import mimetypes
import re

from django.core import signing
from django.conf import settings
from django.views.decorators.clickjacking import xframe_options_exempt
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.urls import reverse
from django.utils import timezone

from ..access import authenticate_request
from ..models import AccessToken
from .access import LearningError, material_for

SALT = "labtwin-private-course-media-v1"
TICKET_LIFETIME = 300


def media_url(request, material, unit=None):
    payload = {"material": material.id, "token": request.access_token.digest, "unit": unit.id if unit else None}
    # The optional private deployment gate can delegate its existing access to
    # this exact file. Native viewers need no cookie/header, but session and
    # classroom checks below still run for every GET/HEAD/range request.
    private_access = getattr(request, "private_deployment_fingerprint", None)
    if private_access:
        payload["deployment_access"] = private_access
    ticket = signing.dumps(payload, salt=SALT)
    route, args = ("learning-visual", [material.id, unit.id]) if unit else ("learning-media", [material.id])
    return request.build_absolute_uri(reverse(route, args=args)) + "?ticket=" + ticket


def stream_bytes(path, start, length):
    with path.open("rb") as stream:
        stream.seek(start)
        while length > 0:
            block = stream.read(min(65536, length))
            if not block:
                break
            length -= len(block)
            yield block


@xframe_options_exempt
def private_media(request, material_id, unit_id=None):
    if request.method not in ("GET", "HEAD"):
        return HttpResponse(status=405)
    try:
        account = authenticate_request(request)
        if not account:
            try:
                data = signing.loads(request.GET.get("ticket", ""), salt=SALT, max_age=TICKET_LIFETIME)
            except signing.BadSignature:
                return JsonResponse({"error": "This source link expired. Reopen the citation."}, status=401)
            token = AccessToken.objects.select_related("account__user").filter(digest=data.get("token"), expires_at__gt=timezone.now(), account__user__is_active=True).first()
            if not token or data.get("material") != material_id or data.get("unit") != unit_id:
                return HttpResponse(status=401)
            account = token.account
        material = material_for(account, material_id)
        from pathlib import Path
        unit = material.units.filter(pk=unit_id).first() if unit_id else None
        if unit_id and (not unit or not unit.visual_file):
            return HttpResponse(status=404)
        try:
            path = Path(unit.visual_file.path if unit else material.file.path)
        except Exception:
            # Never reveal storage credentials, provider responses or file paths.
            return JsonResponse({"error": "The private source is temporarily unavailable. Retry shortly."}, status=503)
        if not path.exists():
            return JsonResponse({"error": "The source file is unavailable."}, status=404)
        size, start, end, status = path.stat().st_size, 0, path.stat().st_size - 1, 200
        byte_range = request.headers.get("Range")
        if byte_range:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", byte_range)
            if not match or not any(match.groups()):
                response = HttpResponse(status=416)
                response["Content-Range"] = f"bytes */{size}"
                return response
            left, right = match.groups()
            if left:
                start, end = int(left), min(int(right) if right else size - 1, size - 1)
            else:
                start = max(0, size - int(right))
            if start > end or start >= size:
                response = HttpResponse(status=416)
                response["Content-Range"] = f"bytes */{size}"
                return response
            status = 206
        length = max(0, end - start + 1)
        filename = "figure.png" if unit else material.filename
        response = StreamingHttpResponse([] if request.method == "HEAD" else stream_bytes(path, start, length), status=status, content_type=mimetypes.guess_type(filename)[0] or "application/octet-stream")
        response["Content-Length"] = length
        response["Accept-Ranges"] = "bytes"
        response["Content-Disposition"] = "inline; filename*=UTF-8''" + __import__("urllib.parse", fromlist=["quote"]).quote(filename)
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        from urllib.parse import urlsplit
        origins = [origin for origin in getattr(settings, "CORS_ALLOWED_ORIGINS", []) if urlsplit(origin).scheme in ("https", "http") and not any(c in origin for c in " ;'\n\r")]
        response["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'self' " + " ".join(origins)
        if status == 206:
            response["Content-Range"] = f"bytes {start}-{end}/{size}"
        return response
    except LearningError as error:
        return JsonResponse({"error": error.message}, status=error.status)
