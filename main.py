from crewai import Agent, Task, Crew, Process, LLM
import crewai.llms.cache as _crewai_cache
from dotenv import load_dotenv
from pydantic import BaseModel
from pathlib import Path
from code_runner import run_python_code
import os
import json

_crewai_cache.mark_cache_breakpoint = lambda message: message

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

MEMORY_FILE = Path("student_memory.json")

# ----------------------------
# MEMORY FUNCTIONS
# ----------------------------

def load_memory():
    if not MEMORY_FILE.exists():
        return {
            "student_name": "Francis",
            "weaknesses": []
        }

    with open(MEMORY_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def save_memory(memory):
    with open(MEMORY_FILE, "w", encoding="utf-8") as file:
        json.dump(memory, file, indent=4)


def save_weakness(concept, misconception):
    memory = load_memory()

    for weakness in memory["weaknesses"]:
        if weakness["concept"].lower().strip() == concept.lower().strip():
            weakness["occurrences"] += 1
            weakness["misconception"] = misconception
            weakness["status"] = "Needs Retest"
            save_memory(memory)
            return

    memory["weaknesses"].append({
        "concept": concept,
        "misconception": misconception,
        "occurrences": 1,
        "status": "Needs Retest"
    })

    save_memory(memory)


def update_status(concept, status):
    memory = load_memory()

    for weakness in memory["weaknesses"]:
        if weakness["concept"].lower().strip() == concept.lower().strip():
            weakness["status"] = status

    save_memory(memory)


# ----------------------------
# STRUCTURED OUTPUT MODELS
# ----------------------------

class MisconceptionRecord(BaseModel):
    concept: str
    misconception: str
    needs_retest: bool


class EvaluationResult(BaseModel):
    concept: str
    code_correct: bool
    viva_correct: bool
    status: str
    score: int
    reason: str


# ----------------------------
# LLM
# ----------------------------

llm = LLM(
    model="groq/openai/gpt-oss-20b",
    api_key=GROQ_API_KEY,
    temperature=0.2
)


# ----------------------------
# AGENTS
# ----------------------------

analyzer_agent = Agent(
    role="Programming Lab Code Analyzer",
    goal="Analyze student code and real test results to identify the actual programming misconception.",
    backstory="You are a strict programming lab instructor who focuses on understanding, not memorization.",
    llm=llm,
    verbose=True
)

memory_agent = Agent(
    role="Student Learning Profile Manager",
    goal="Extract the student's main misconception and decide whether it needs retesting.",
    backstory="You maintain a clean learning profile of recurring student weaknesses.",
    llm=llm,
    verbose=True
)

tutor_agent = Agent(
    role="Adaptive Programming Tutor",
    goal="Generate targeted hints, practice problems and viva questions based on identified weaknesses.",
    backstory="You adapt learning activities to the student's mistakes instead of giving generic exercises.",
    llm=llm,
    verbose=True
)

evaluator_agent = Agent(
    role="Programming Lab Evaluator",
    goal="Verify whether the student genuinely corrected the previously identified misconception.",
    backstory="You check both code performance and conceptual understanding before marking a weakness as corrected.",
    llm=llm,
    verbose=True
)


# ----------------------------
# ORIGINAL STUDENT CODE
# ----------------------------

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


# ----------------------------
# RUN TEST CASES
# ----------------------------

test_results = []

for i, test in enumerate(test_cases, start=1):

    execution = run_python_code(
        student_code,
        test["input"]
    )

    actual = execution["stdout"].strip()
    expected = test["expected"].strip()

    passed = execution["success"] and actual == expected

    test_results.append({
        "test_number": i,
        "input": test["input"],
        "expected": expected,
        "actual": actual,
        "passed": passed,
        "error": execution["stderr"]
    })

passed_count = sum(
    1 for r in test_results if r["passed"]
)

test_score = round(
    passed_count / len(test_results) * 100
)


# ----------------------------
# ANALYSIS TASK
# ----------------------------

analysis_task = Task(
    description=f'''
Analyze this student's Python program.

CODE:

{student_code}

REAL TEST RESULTS:

{json.dumps(test_results, indent=2)}

TEST SCORE:
{test_score}%

Identify:
1. Main programming concept
2. Student misconception
3. Why the code fails
4. One hint

Do not give the complete corrected solution.
''',
    expected_output='''
Concept:
Misconception:
Explanation:
Hint:
''',
    agent=analyzer_agent
)


# ----------------------------
# MEMORY TASK
# ----------------------------

memory_task = Task(
    description='''
Read the Code Analyzer result.

Extract:
- concept
- misconception
- needs_retest

Set needs_retest to true if the weakness should be tested again.
''',
    expected_output="Structured misconception record.",
    agent=memory_agent,
    context=[analysis_task],
    output_pydantic=MisconceptionRecord
)


# ----------------------------
# TUTOR TASK
# ----------------------------

current_memory = load_memory()

tutor_task = Task(
    description=f'''
Use the analysis and student history.

STUDENT MEMORY:

{json.dumps(current_memory, indent=2)}

Do:
1. Identify the weakness
2. Give one progressive hint
3. Generate one new Python exercise targeting the same concept
4. Ask one viva question
5. Do not give the complete answer
''',
    expected_output='''
Weakness:
Hint:
Practice Problem:
Viva Question:
''',
    agent=tutor_agent,
    context=[analysis_task, memory_task]
)


# ----------------------------
# FIRST CREW
# ----------------------------

learning_crew = Crew(
    agents=[
        analyzer_agent,
        memory_agent,
        tutor_agent
    ],
    tasks=[
        analysis_task,
        memory_task,
        tutor_task
    ],
    process=Process.sequential,
    verbose=True
)

learning_result = learning_crew.kickoff()


# ----------------------------
# SAVE DETECTED WEAKNESS
# ----------------------------

record = memory_task.output.pydantic

if record.needs_retest:
    save_weakness(
        record.concept,
        record.misconception
    )


print("\n========== TEST RESULTS ==========\n")

for test in test_results:
    print(
        f"Test {test['test_number']}: "
        f"{'PASS' if test['passed'] else 'FAIL'}"
    )

print("Test Score:", test_score, "%")


print("\n========== LABTWIN TUTOR ==========\n")
print(learning_result)


# ----------------------------
# RETEST
# ----------------------------

print("\n========== STUDENT RETEST ==========\n")

corrected_code = '''
a = int(input())
b = int(input())

print(a + b)
'''

viva_answer = '''
Addition uses the + operator.
The original program used subtraction, so the output did not match
the expected sum.
'''


# ----------------------------
# RUN RETEST
# ----------------------------

retest_results = []

for i, test in enumerate(test_cases, start=1):

    execution = run_python_code(
        corrected_code,
        test["input"]
    )

    actual = execution["stdout"].strip()
    expected = test["expected"].strip()

    passed = execution["success"] and actual == expected

    retest_results.append({
        "test_number": i,
        "expected": expected,
        "actual": actual,
        "passed": passed
    })


retest_passed = sum(
    1 for r in retest_results if r["passed"]
)

retest_score = round(
    retest_passed / len(retest_results) * 100
)


# ----------------------------
# EVALUATION TASK
# ----------------------------

evaluation_task = Task(
    description=f'''
The student previously had this misconception:

Concept:
{record.concept}

Misconception:
{record.misconception}

The student attempted a corrected version.

CORRECTED CODE:

{corrected_code}

REAL RETEST RESULTS:

{json.dumps(retest_results, indent=2)}

RETEST SCORE:
{retest_score}%

VIVA ANSWER:

{viva_answer}

Evaluate whether the misconception is:

Corrected
Improving
Needs Retest

Do not mark Corrected unless the code passes the tests and the viva demonstrates understanding.
''',
    expected_output="Structured evaluation result.",
    agent=evaluator_agent,
    output_pydantic=EvaluationResult
)


evaluation_crew = Crew(
    agents=[evaluator_agent],
    tasks=[evaluation_task],
    process=Process.sequential,
    verbose=True
)

evaluation_crew.kickoff()

evaluation = evaluation_task.output.pydantic

update_status(
    evaluation.concept,
    evaluation.status
)


# ----------------------------
# READINESS SCORE
# ----------------------------

readiness_score = round(
    test_score * 0.30
    +
    retest_score * 0.40
    +
    evaluation.score * 0.30
)


# ----------------------------
# FINAL REPORT
# ----------------------------

print("\n========== LABTWIN FINAL REPORT ==========\n")

print("Initial Test Score:", test_score, "%")
print("Retest Score:", retest_score, "%")
print("Concept:", evaluation.concept)
print("Status:", evaluation.status)
print("Evaluator Score:", evaluation.score, "%")
print("Lab Readiness:", readiness_score, "%")

print("\n========== STUDENT MEMORY ==========\n")
print(json.dumps(load_memory(), indent=4))
