"""Private test evidence is retained on the server, never in student JSON."""


def private_summary(rows):
    return [{"test": row.get("test", index + 1), "passed": bool(row.get("passed")), "success": bool(row.get("success", True)), "hidden": True} for index, row in enumerate(rows) if isinstance(row, dict)]


def student_payload(value):
    if isinstance(value, list):
        return [student_payload(item) for item in value]
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key in ("test_results", "retest_results") and isinstance(item, list):
                result[key] = private_summary(item)
            elif key in ("tests", "hidden_tests"):
                continue
            else:
                result[key] = student_payload(item)
        return result
    return value
