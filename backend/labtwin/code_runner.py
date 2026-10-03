import subprocess
import tempfile
import os

def run_python_code(code, test_input=""):
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".py",
        delete=False,
        encoding="utf-8"
    ) as temp_file:
        temp_file.write(code)
        temp_path = temp_file.name

    try:
        result = subprocess.run(
            ["python", temp_path],
            input=test_input,
            capture_output=True,
            text=True,
            timeout=5
        )

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip()
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": "Execution timed out"
        }

    finally:
        os.remove(temp_path)


if __name__ == "__main__":

    student_code = '''
a = int(input())
b = int(input())

print(a + b)
'''

    result = run_python_code(
        student_code,
        "5\n3\n"
    )

    print("\n========== CODE EXECUTION ==========\n")
    print("Success:", result["success"])
    print("Output:", result["stdout"])
    print("Error:", result["stderr"])
