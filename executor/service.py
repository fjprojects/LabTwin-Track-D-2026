"""Authenticated worker. Run on a separate host with Docker installed."""
import hmac
import json
import os
import subprocess
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CAPACITY = threading.BoundedSemaphore(4)


def container_command(name):
    return ["docker", "run", "--rm", "--name", name, "-i", "--network", "none", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--memory", "256m", "--cpus", "1", "--pids-limit", "64", "--tmpfs", "/tmp:rw,exec,nosuid,nodev,size=64m", "--user", "65534:65534", os.environ.get("LABTWIN_RUNNER_IMAGE", "labtwin-code-runtime")]


def valid_job(data):
    return isinstance(data, dict) and data.get("language") in ("Python", "C", "Java") and isinstance(data.get("code"), str) and len(data["code"]) <= 100000 and isinstance(data.get("inputs"), list) and len(data["inputs"]) <= 20 and all(isinstance(v, str) and len(v) <= 10000 for v in data["inputs"])


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", len(body)); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        self.reply(200 if self.path == "/health" else 404, {"service": "labtwin-isolated-runner"})

    def do_POST(self):
        secret = os.environ.get("LABTWIN_RUNNER_SECRET", "")
        if self.path != "/execute" or not secret or not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + secret):
            return self.reply(401, {"error": "Unauthorized."})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 400000:
                return self.reply(400, {"error": "Invalid job size."})
            data = json.loads(self.rfile.read(length))
            if not valid_job(data):
                return self.reply(400, {"error": "Invalid execution job."})
        except (ValueError, TypeError):
            return self.reply(400, {"error": "Invalid JSON."})
        if not CAPACITY.acquire(blocking=False):
            return self.reply(503, {"error": "The execution queue is busy. Retry later."})
        name = "labtwin-job-" + uuid.uuid4().hex
        try:
            result = subprocess.run(container_command(name), input=json.dumps(data), capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                return self.reply(503, {"error": "The isolated job could not finish."})
            output = json.loads(result.stdout)
            return self.reply(200, output)
        except Exception:
            return self.reply(503, {"error": "Execution worker unavailable."})
        finally:
            try:
                subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=15)
            except Exception:
                pass
            CAPACITY.release()


if __name__ == "__main__":
    if not os.environ.get("LABTWIN_RUNNER_SECRET"):
        raise SystemExit("Set LABTWIN_RUNNER_SECRET before starting the worker.")
    ThreadingHTTPServer((os.environ.get("LABTWIN_RUNNER_BIND", "127.0.0.1"), int(os.environ.get("LABTWIN_RUNNER_PORT", "8090"))), Handler).serve_forever()
