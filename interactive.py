from crewai import Agent, Task, Crew, Process, LLM
import crewai.llms.cache as _crewai_cache
from dotenv import load_dotenv
from pathlib import Path
from code_runner import run_python_code
import os
import json

_crewai_cache.mark_cache_breakpoint = lambda message: message

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

MEMORY_FILE = Path("student_memory.json")


def load_memory():
    if not MEMORY_FILE.exists():
        return {
            "student_name": "Student",
            "weaknesses": []
        }

    return json.loads(
        MEMORY_FILE.read_text(encoding="utf-8")
    )


def save_memory(data):
    MEMORY_FILE.write_text(
        json.dumps(data, indent=4),
        encoding="utf-8"
    )


def save_weakness(key, misconception):
    data = load_memory()

    for weakness in data["weaknesses"]:

        if weakness.get("concept_key") == key:

            weakness["occurrences"] += 1
            weakness["misconception"] = misconception
            weakness["status"] = "Needs Retest"

            save_memory(data)
            return

    data["weaknesses"].append({
        "concept_key": key,
        "misconception": misconception,
        "occurrences": 1,
        "status": "Needs Retest"
    })

    save_memory(data)


def update_status(key, status):
    data = load_memory()

    for weakness in data["weaknesses"]:

        if weakness.get("concept_key") == key:
            weakness["status"] = status

    save_memory(data)


def multiline_input(message):

    print(message)
    print("Type END on a new line when finished:\n")

    lines = []

    while True:

        line = input()

        if line.strip() == "END":
            break

        lines.append(line)

    return "\n".join(lines)


def clean_json_output(text):

    text = str(text).strip()

    if text.startswith("`json"):
        text = text[7:]

    elif text.startswith("`"):
        text = text[3:]

    if text.endswith("`"):
        text = text[:-3]

    text = text.strip()

    return json.loads(text)


llm = LLM(
    model="groq/openai/gpt-oss-20b",
    api_key=GROQ_API_KEY,
    temperature=0.2
)


analyzer = Agent(
    role="Programming Lab Code Analyzer",

    goal="""
    Identify conceptual mistakes using student code
    and real test-case results.
    """,

    backstory="""
    You are a programming lab instructor.

    You diagnose why students make programming mistakes
    instead of simply giving them the correct answer.
    """,

    llm=llm,
    verbose=False
)


tutor = Agent(
    role="Adaptive Programming Tutor",

    goal="""
    Help students correct identified weaknesses using
    hints, targeted exercises and viva questions.
    """,

    backstory="""
    You adapt teaching to each student's misconceptions
    instead of giving generic exercises.
    """,

    llm=llm,
    verbose=False
)


evaluator = Agent(
    role="Programming Lab Evaluator",

    goal="""
    Verify whether the student genuinely corrected
    the previously identified misconception.
    """,

    backstory="""
    You evaluate actual code performance and conceptual
    understanding before marking a weakness as corrected.
    """,

    llm=llm,
    verbose=False
)


print("\n================================")
print("           LABTWIN AI")
print("================================")

print("\nPROBLEM:")
print(
    "Write a Python program that reads "
    "two integers and prints their sum."
)


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


def test_code(code):

    results = []

    for index, test in enumerate(test_cases, start=1):

        execution = run_python_code(
            code,
            test["input"]
        )

        actual = execution["stdout"].strip()

        passed = (
            execution["success"]
            and actual == test["expected"]
        )

        results.append({
            "test": index,
            "expected": test["expected"],
            "actual": actual,
            "passed": passed,
            "error": execution["stderr"]
        })

    return results


# ======================================================
# STUDENT FIRST ATTEMPT
# ======================================================

student_code = multiline_input(
    "\nEnter your Python code:"
)


results = test_code(student_code)

passed_count = sum(
    1 for result in results
    if result["passed"]
)

score = round(
    passed_count / len(results) * 100
)


print("\n========== TEST RESULTS ==========")

for result in results:

    status = (
        "PASS"
        if result["passed"]
        else "FAIL"
    )

    print(
        "Test",
        result["test"],
        ":",
        status
    )


print("Score:", score, "%")


# ======================================================
# ANALYZER AGENT
# ======================================================

analysis_task = Task(

    description=f'''
Analyze this student's Python code.

Problem:
Read two integers and print their sum.

Student code:

{student_code}

Actual test results:

{json.dumps(results, indent=2)}

Choose one concept_key from:

ARITHMETIC_OPERATORS
STRINGS
CONDITIONALS
LOOPS
ARRAYS
FUNCTIONS
OOP
OTHER

Identify the main misconception.

Give one short hint.

Do not provide the complete corrected program.

Return ONLY JSON.
Do not use markdown.
Do not add explanation outside the JSON.
''',

    expected_output='''
Return ONLY valid JSON exactly in this structure:

{
  "concept_key": "ARITHMETIC_OPERATORS",
  "misconception": "short explanation",
  "hint": "short hint"
}
''',

    agent=analyzer
)


Crew(
    agents=[analyzer],
    tasks=[analysis_task],
    process=Process.sequential
).kickoff()


diagnosis = clean_json_output(
    analysis_task.output.raw
)


save_weakness(
    diagnosis["concept_key"],
    diagnosis["misconception"]
)


print("\n========== LABTWIN DIAGNOSIS ==========")

print(
    "Concept:",
    diagnosis["concept_key"]
)

print(
    "Misconception:",
    diagnosis["misconception"]
)

print(
    "Hint:",
    diagnosis["hint"]
)


# ======================================================
# ADAPTIVE TUTOR AGENT
# ======================================================

tutor_task = Task(

    description=f'''
The student's weakness is:

Concept:
{diagnosis["concept_key"]}

Misconception:
{diagnosis["misconception"]}

Student learning memory:

{json.dumps(load_memory(), indent=2)}

Generate:

1. One short progressive hint
2. One new Python practice problem
3. One short viva question

The new problem should test the same concept.

Do not provide the solution.
''',

    expected_output='''
Hint:
Practice Problem:
Viva Question:
''',

    agent=tutor
)


tutor_result = Crew(
    agents=[tutor],
    tasks=[tutor_task],
    process=Process.sequential
).kickoff()


print("\n========== ADAPTIVE TUTOR ==========")

print(tutor_result)


# ======================================================
# STUDENT RETEST
# ======================================================

corrected_code = multiline_input(
    "\nNow enter your corrected solution:"
)


viva_answer = input(
    "\nExplain what was wrong "
    "with your original code: "
)


retest_results = test_code(
    corrected_code
)


retest_passed = sum(
    1 for result in retest_results
    if result["passed"]
)


retest_score = round(
    retest_passed
    / len(retest_results)
    * 100
)


print("\n========== RETEST RESULTS ==========")

for result in retest_results:

    status = (
        "PASS"
        if result["passed"]
        else "FAIL"
    )

    print(
        "Test",
        result["test"],
        ":",
        status
    )


print(
    "Retest Score:",
    retest_score,
    "%"
)


# ======================================================
# EVALUATOR AGENT
# ======================================================

evaluation_task = Task(

    description=f'''
The student previously had this weakness:

Concept:
{diagnosis["concept_key"]}

Misconception:
{diagnosis["misconception"]}

Corrected code:

{corrected_code}

Actual retest results:

{json.dumps(retest_results, indent=2)}

Retest score:
{retest_score}%

Student viva answer:

{viva_answer}

Evaluate whether the weakness is:

Corrected
Improving
Needs Retest

Rules:

- Corrected:
  code passes the tests AND viva shows understanding.

- Improving:
  partial improvement but understanding is incomplete.

- Needs Retest:
  code or conceptual understanding is still weak.

Give an understanding score from 0 to 100.

Return ONLY JSON.
Do not use markdown.
Do not add text outside JSON.
''',

    expected_output='''
Return ONLY valid JSON exactly in this structure:

{
  "status": "Corrected",
  "score": 100,
  "reason": "short explanation"
}
''',

    agent=evaluator
)


Crew(
    agents=[evaluator],
    tasks=[evaluation_task],
    process=Process.sequential
).kickoff()


evaluation = clean_json_output(
    evaluation_task.output.raw
)


update_status(
    diagnosis["concept_key"],
    evaluation["status"]
)


# ======================================================
# LAB READINESS SCORE
# ======================================================

readiness = round(
    retest_score * 0.6
    +
    evaluation["score"] * 0.4
)


# ======================================================
# FINAL REPORT
# ======================================================

print("\n================================")
print("       LABTWIN FINAL REPORT")
print("================================")

print(
    "Initial Score:",
    score,
    "%"
)

print(
    "Retest Score:",
    retest_score,
    "%"
)

print(
    "Concept:",
    diagnosis["concept_key"]
)

print(
    "Status:",
    evaluation["status"]
)

print(
    "Understanding Score:",
    evaluation["score"],
    "%"
)

print(
    "Lab Readiness:",
    readiness,
    "%"
)

print(
    "Reason:",
    evaluation["reason"]
)


print("\n========== STUDENT MEMORY ==========")

print(
    json.dumps(
        load_memory(),
        indent=2
    )
)
