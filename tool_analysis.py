from crewai import Agent, Task, Crew, Process, LLM
import crewai.llms.cache as _crewai_cache
from dotenv import load_dotenv
from code_runner import run_python_code
import os
import json

_crewai_cache.mark_cache_breakpoint = lambda message: message

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

llm = LLM(
    model="groq/openai/gpt-oss-20b",
    api_key=GROQ_API_KEY,
    temperature=0.2
)

student_code = '''
a = int(input())
b = int(input())

print(a - b)
'''

test_cases = [
    {"input": "5\n3\n", "expected": "8"},
    {"input": "10\n20\n", "expected": "30"},
    {"input": "-5\n2\n", "expected": "-3"}
]

test_results = []

for i, test in enumerate(test_cases, start=1):

    execution = run_python_code(
        student_code,
        test["input"]
    )

    actual = execution["stdout"].strip()
    expected = test["expected"].strip()

    passed = (
        execution["success"]
        and actual == expected
    )

    test_results.append({
        "test_number": i,
        "input": test["input"],
        "expected": expected,
        "actual": actual,
        "passed": passed,
        "error": execution["stderr"]
    })

passed_count = sum(
    1 for result in test_results
    if result["passed"]
)

test_score = round(
    passed_count / len(test_results) * 100
)

analyzer = Agent(
    role="Programming Lab Code Analyzer",

    goal="""
    Analyze student code together with real execution results
    and identify the underlying programming misconception.
    """,

    backstory="""
    You are a programming lab instructor.
    You do not guess whether code works.
    You use the supplied test-case evidence to understand
    why the student's solution is failing.
    """,

    llm=llm,
    verbose=True
)

analysis_task = Task(
    description=f'''
Analyze this student's Python program.

STUDENT CODE:

{student_code}

REAL TEST CASE RESULTS:

{json.dumps(test_results, indent=2)}

TEST CASE SCORE:
{test_score}%

Determine:

1. What the student was probably trying to do.
2. What is incorrect in the program.
3. The main programming concept involved.
4. Whether this looks like a conceptual mistake or simple coding mistake.
5. Give one hint without providing the complete solution.

Base your judgment on the actual test results.
''',

    expected_output='''
Test Score:
Concept:
Mistake Type:
Misconception:
Evidence:
Hint:
''',

    agent=analyzer
)

crew = Crew(
    agents=[analyzer],
    tasks=[analysis_task],
    process=Process.sequential,
    verbose=True
)

result = crew.kickoff()

print("\n========== TEST RESULTS ==========\n")

for test in test_results:
    print(
        f"Test {test['test_number']}: "
        f"{'PASS' if test['passed'] else 'FAIL'}"
    )

print("\nTest Case Score:", test_score, "%")

print("\n========== LABTWIN ANALYSIS ==========\n")
print(result)
