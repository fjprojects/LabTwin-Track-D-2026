"""An additional private access gate for trusted acceptance-test accounts.

LabTwin's own bearer authentication and classroom authorization still apply.
Using a separate secure cookie avoids conflicting with bearer Authorization
headers. This is not a substitute for the isolated public code worker.
"""
import hashlib
import hmac

from django.conf import settings
from django.core import signing
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.middleware.csrf import get_token
from django.urls import Resolver404, resolve
from django.utils.html import escape
from django.views.decorators.csrf import csrf_protect

COOKIE = "__Host-labtwin-deployment"
SALT = "labtwin-temporary-private-deployment-v1"
LIFETIME = 12 * 60 * 60


def password_fingerprint():
    return hashlib.sha256(settings.LABTWIN_DEPLOYMENT_PASSWORD.encode()).hexdigest()


def permitted(request):
    try:
        value = signing.loads(request.COOKIES.get(COOKIE, ""), salt=SALT, max_age=LIFETIME)
        return isinstance(value, dict) and hmac.compare_digest(str(value.get("key", "")), password_fingerprint())
    except signing.BadSignature:
        return False


def permitted_media(request):
    """Honor private access delegated to one short-lived, read-only file URL.

    A native PDF viewer/new tab can omit the Strict cookie and bearer header.
    Only tickets minted after private access may pass this gate; the original
    media view still rechecks the live session and classroom on every request.
    """
    if request.method not in ("GET", "HEAD") or not request.GET.get("ticket"):
        return False
    from labtwin.learning.media import SALT as MEDIA_SALT, TICKET_LIFETIME, private_media
    try:
        match = resolve(request.path_info)
        if match.func is not private_media or match.url_name not in ("learning-media", "learning-visual"):
            return False
        value = signing.loads(request.GET["ticket"], salt=MEDIA_SALT, max_age=TICKET_LIFETIME)
        return (isinstance(value, dict)
                and value.get("material") == match.kwargs["material_id"]
                and value.get("unit") == match.kwargs.get("unit_id")
                and hmac.compare_digest(str(value.get("deployment_access", "")).encode(), password_fingerprint().encode()))
    except (Resolver404, signing.BadSignature):
        return False


class PrivateDeploymentMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Validate even a simple health request, which need not otherwise call
        # get_host(). The reverse proxy still forwards the original host.
        request.get_host()
        public = request.path_info in ("/deployment/access/", "/deployment/health/")
        private_access = permitted(request)
        if private_access:
            # Request-local proof, never accepted from headers/query input.
            request.private_deployment_fingerprint = password_fingerprint()
        if not public and not private_access and not permitted_media(request):
            response = (JsonResponse({"error": "Private demo access is required. Open /deployment/access/ first."}, status=401)
                        if request.path_info.startswith("/api/") else HttpResponseRedirect("/deployment/access/"))
        else:
            response = self.get_response(request)
        response["Permissions-Policy"] = "camera=(self), microphone=(self), display-capture=(self)"
        response["Referrer-Policy"] = "same-origin"
        return response


@csrf_protect
def access(request):
    if request.method not in ("GET", "POST"):
        return HttpResponse(status=405)
    wrong = False
    if request.method == "POST":
        submitted = request.POST.get("password", "")
        if hmac.compare_digest(submitted.encode(), settings.LABTWIN_DEPLOYMENT_PASSWORD.encode()):
            response = HttpResponseRedirect("/")
            response.set_cookie(COOKIE, signing.dumps({"key": password_fingerprint()}, salt=SALT),
                                max_age=LIFETIME, secure=True, httponly=True, samesite="Strict", path="/")
            response["Cache-Control"] = "no-store"
            return response
        wrong = True
    token = escape(get_token(request))
    message = "<p role='alert'>The private access password was not accepted.</p>" if wrong else ""
    response = HttpResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1"><title>LabTwin private demo</title></head>
      <body><main><h1>LabTwin private demo</h1><p>Enter the temporary deployment password, then sign in to LabTwin.</p>
      <p>This deployment is for trusted acceptance testing. Use test accounts and test materials.</p>{message}
      <form method="post" action="/deployment/access/"><input type="hidden" name="csrfmiddlewaretoken" value="{token}">
      <label>Private access password <input type="password" name="password" required autocomplete="current-password"></label>
      <button type="submit">Open LabTwin</button></form></main></body></html>""", status=401 if wrong else 200)
    response["Cache-Control"] = "no-store"
    response["Content-Security-Policy"] = "default-src 'none'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
    return response


def health(request):
    # Deliberately disclose no version, credentials, records or filesystem paths.
    return JsonResponse({"status": "ok"})
