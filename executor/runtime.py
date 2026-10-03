"""Runs inside a fresh restricted container, with no application files/secrets."""
import json
import os
import re
import resource
import subprocess
import sys
import tempfile
from pathlib import Path


def limits():
    resource.setrlimit(resource.RLIMIT_FSIZE, (512 * 1024, 512 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))


def run(command, directory, stdin="", timeout=5):
    with tempfile.TemporaryFile(dir=directory) as stdout, tempfile.TemporaryFile(dir=directory) as stderr:
        try:
            process = subprocess.run(command, input=stdin.encode(), stdout=stdout, stderr=stderr, cwd=directory, timeout=timeout, preexec_fn=limits, env={"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": directory, "LANG": "C.UTF-8"})
            stdout.seek(0); stderr.seek(0)
            return {"success": process.returncode == 0, "stdout": stdout.read(10000).decode(errors="replace").strip(), "stderr": stderr.read(10000).decode(errors="replace").strip()}
        except subprocess.TimeoutExpired:
            return {"success": False, "stdout": "", "stderr": "Execution timed out."}


def execute(data):
    language, code, inputs = data["language"], data["code"], data["inputs"]
    with tempfile.TemporaryDirectory(prefix="labtwin-job-") as directory:
        folder = Path(directory)
        compile_result = None
        if language == "Python":
            (folder / "main.py").write_text(code)
            command = [sys.executable, "-I", str(folder / "main.py")]
        elif language == "C":
            (folder / "main.c").write_text(code)
            compile_result = run(["gcc", "main.c", "-o", "program", "-std=c11", "-lm"], directory, timeout=15)
            command = [str(folder / "program")]
        elif language == "Java":
            match = re.search(r"public\s+class\s+(\w+)", code)
            name = match.group(1) if match else "Main"
            (folder / (name + ".java")).write_text(code)
            compile_result = run(["javac", "-J-Xmx128m", name + ".java"], directory, timeout=15)
            command = ["java", "-Xmx96m", "-XX:ActiveProcessorCount=1", "-cp", directory, name]
        else:
            raise ValueError("Unsupported language")
        if compile_result and not compile_result["success"]:
            return [compile_result for _ in inputs]
        return [run(command, directory, value) for value in inputs]


if __name__ == "__main__":
    try:
        result = execute(json.loads(sys.stdin.read(400000)))
        print(json.dumps({"executions": result}))
    except Exception:
        print(json.dumps({"error": "The isolated job could not finish."}))
        sys.exit(1)
