"""Local test server. Stubs original remote AI only; auth, learning and code runners are real.
Never expose this server publicly or point it at a production database.
"""
import ast
import json
import mimetypes
import os
import subprocess
import sys
import tempfile
import shutil
import types
from pathlib import Path
from wsgiref.simple_server import make_server

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
os.environ['DJANGO_SETTINGS_MODULE'] = 'backend.test_settings'
from django.conf import settings
settings.DATABASES['default']['NAME'] = os.getenv('LABTWIN_E2E_DATABASE', '/tmp/labtwin-e2e.sqlite3')
settings.LABTWIN_MEDIA_ROOT = Path('/tmp/labtwin-e2e-uploads')
settings.LABTWIN_VECTOR_ROOT = Path(os.getenv('LABTWIN_E2E_VECTOR_ROOT', '/tmp/labtwin-e2e-vectors-v1.1'))
settings.PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
settings.ALLOWED_HOSTS = ['127.0.0.1', 'localhost']
settings.DEBUG = True
settings.WEBRTC_ICE_SERVERS = []
settings.LABTWIN_EVALUATOR_PYTHON = os.getenv('LABTWIN_TEST_EVALUATOR_PYTHON', sys.executable)
settings.LABTWIN_EVALUATOR_EXTRA_PATH = os.getenv('LABTWIN_TEST_EVALUATOR_EXTRA_PATH', '')

views = types.ModuleType('labtwin.views')
def dummy(request):
    from django.http import JsonResponse
    return JsonResponse({'error': 'AI runtime is not part of this local classroom check.'}, status=503)
for name in ('upload_syllabus', 'next_question', 'analyze_code', 'tutor_help', 'evaluate_code', 'student_session'):
    setattr(views, name, dummy)
views.default_state = lambda: {'topics': [], 'student_id': None}
views.load_state = lambda: views.default_state()
views.load_student_snapshot = lambda sid: {'student_id': str(sid), 'topics': []}
views.activate_student_session = lambda sid, fresh=False: {'student_id': str(sid), 'topics': []}
views.public_student_session = lambda state: {'has_syllabus': False, 'current_question': None, **state}
source = ast.parse((ROOT / 'backend/labtwin/views.py').read_text())
functions = [node for node in source.body if isinstance(node, ast.FunctionDef) and node.name in ('run_tests', 'run_python_code', 'run_c_code', 'run_java_code')]
views.__dict__.update(subprocess=subprocess, tempfile=tempfile, os=os, sys=sys, shutil=shutil)
exec(compile(ast.Module(body=functions, type_ignores=[]), '<actual-runners>', 'exec'), views.__dict__)
sys.modules['labtwin.views'] = views
sys.modules['labtwin.adaptive_views'] = types.SimpleNamespace(adaptive_next_question=dummy)
sys.modules['labtwin.hint_views'] = types.SimpleNamespace(progressive_hint=dummy)
import django
django.setup()
from django.core.management import call_command
call_command('migrate', verbosity=0)
from django.urls import include, path
urls = types.ModuleType('e2e_urls')
urls.urlpatterns = [path('api/', include('labtwin.urls'))]
sys.modules['e2e_urls'] = urls
settings.ROOT_URLCONF = 'e2e_urls'
from django.core.wsgi import get_wsgi_application
app = get_wsgi_application()
dist = ROOT / 'frontend/dist'

def application(environ, start_response):
    route = environ.get('PATH_INFO', '/')
    if route.startswith('/api/'):
        return app(environ, start_response)
    target = (dist / route.lstrip('/')).resolve()
    if not target.is_relative_to(dist.resolve()) or not target.is_file():
        target = dist / 'index.html'
    content = target.read_bytes()
    start_response('200 OK', [('Content-Type', mimetypes.guess_type(str(target))[0] or 'application/octet-stream'), ('Content-Length', str(len(content)))])
    return [content]

print('Classroom test server ready at http://127.0.0.1:8000', flush=True)
make_server('127.0.0.1', 8000, application).serve_forever()
