"""Execute fixed synthetic programs through the existing Python/C/Java runners.

No credentials, production data, student code or hidden classroom cases are
used. --require-all is the release/CI gate; missing native tools fail that gate.
"""
import argparse
import ast
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-all", action="store_true")
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1] / "backend/labtwin/views.py"
    sys.path.insert(0, str(source.parents[1]))
    os.environ["DJANGO_SETTINGS_MODULE"] = "backend.test_settings"
    from django.conf import settings
    settings.LABTWIN_RUNNER_URL = ""  # Fixed trusted fixtures execute locally.
    parsed = ast.parse(source.read_text())
    names = {"run_tests", "run_python_code", "run_c_code", "run_java_code"}
    functions = [node for node in parsed.body if isinstance(node, ast.FunctionDef) and node.name in names]
    namespace = dict(__name__="labtwin.views", os=os, shutil=shutil, subprocess=subprocess, sys=sys, tempfile=tempfile)
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), "exec"), namespace)
    examples = {
        "Python": (None, "a, b = map(int, input().split())\nprint(a + b)\n"),
        "C": ("gcc", '#include <stdio.h>\nint main(void) { int a,b; if(scanf("%d %d",&a,&b)!=2) return 1; printf("%d\\n",a+b); return 0; }'),
        "Java": ("javac", 'import java.util.Scanner;\npublic class Main { public static void main(String[] args) { Scanner s=new Scanner(System.in); int a=s.nextInt(),b=s.nextInt(); System.out.println(a+b); } }'),
    }
    failures = 0
    for language, (tool, program) in examples.items():
        if tool and not shutil.which(tool):
            print(f"{language}: BLOCKED — {tool} is unavailable in this test environment")
            failures += 1
            continue
        score, rows = namespace["run_tests"](program, [{"input": "2 3", "expected": "5"}, {"input": "-4 9", "expected": "5"}], language)
        passed = score == 100 and len(rows) == 2 and all(row["passed"] for row in rows)
        print(f"{language}: {'PASS' if passed else 'FAIL'} — {len(rows)} real execution cases")
        failures += not passed
    return 1 if failures and args.require_all else 0


if __name__ == "__main__":
    raise SystemExit(main())
