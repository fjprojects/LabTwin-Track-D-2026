from code_runner import run_python_code

student_code = '''
a = int(input())
b = int(input())

print(a + b)
'''

test_cases = [
    {
        "input": "5\n3\n",
        "expected": "8"
    },
    {
        "input": "10\n20\n",
        "expected": "30"
    },
    {
        "input": "-5\n2\n",
        "expected": "-3"
    }
]

passed = 0

print("\n========== TEST CASE RESULTS ==========\n")

for index, test in enumerate(test_cases, start=1):

    result = run_python_code(
        student_code,
        test["input"]
    )

    actual = result["stdout"].strip()
    expected = test["expected"].strip()

    success = (
        result["success"] and
        actual == expected
    )

    if success:
        passed += 1

    print(f"Test {index}")
    print("Input:", repr(test["input"]))
    print("Expected:", expected)
    print("Actual:", actual)
    print("Passed:", success)
    print()

score = round(
    (passed / len(test_cases)) * 100
)

print("Passed:", passed, "/", len(test_cases))
print("Test Case Score:", score, "%")
