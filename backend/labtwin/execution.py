"""Optional isolated execution service shared by existing and new lab flows."""
import json
from urllib.request import Request, urlopen

from django.conf import settings


def remote_tests(code, tests, language):
    url = getattr(settings, "LABTWIN_RUNNER_URL", "")
    if not url:
        return None  # Preserve the existing local runner for trusted development.
    secret = getattr(settings, "LABTWIN_RUNNER_SECRET", "")
    if not secret:
        raise RuntimeError("Configure LABTWIN_RUNNER_SECRET for the isolated execution service.")
    request = Request(url.rstrip("/") + "/execute", data=json.dumps({"code": code, "language": language, "inputs": [str(t.get("input", "")) for t in tests]}).encode(), headers={"Content-Type": "application/json", "Authorization": "Bearer " + secret}, method="POST")
    try:
        with urlopen(request, timeout=130) as response:
            data = json.loads(response.read(1024 * 1024))
        executions = data["executions"]
        if not isinstance(executions, list) or len(executions) != len(tests):
            raise ValueError()
        results = []
        for index, (test, execution) in enumerate(zip(tests, executions), 1):
            if not isinstance(execution, dict) or not isinstance(execution.get("success"), bool) or any(not isinstance(execution.get(k), str) for k in ("stdout", "stderr")):
                raise ValueError()
            expected, actual = str(test.get("expected", "")).strip(), execution["stdout"].strip()
            results.append({"test": index, "input": str(test.get("input", "")), "expected": expected, "actual": actual, "passed": execution["success"] and actual == expected, **execution})
        return round(100 * sum(row["passed"] for row in results) / len(results)) if results else 0, results
    except Exception as error:
        raise RuntimeError("The isolated execution service is unavailable. Your submitted work is retained.") from error
