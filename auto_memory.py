from crewai import Agent, Task, Crew, Process, LLM
import crewai.llms.cache as _crewai_cache
from dotenv import load_dotenv
from pydantic import BaseModel
import os
import json
from pathlib import Path

_crewai_cache.mark_cache_breakpoint = lambda message: message

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

MEMORY_FILE = Path("student_memory.json")

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

class MisconceptionRecord(BaseModel):
    concept: str
    misconception: str
    needs_retest: bool

llm = LLM(
    model="groq/openai/gpt-oss-20b",
    api_key=GROQ_API_KEY,
    temperature=0.3
)

code_analyzer = Agent(
    role="Programming Lab Code Analyzer",
    goal="Identify the student's underlying programming misconception.",
    backstory="You are an experienced programming lab instructor focused on conceptual understanding.",
    llm=llm,
    verbose=True
)

memory_agent = Agent(
    role="Student Learning Profile Manager",
    goal="Convert coding mistakes into clean student misconception records.",
    backstory="You maintain a student's learning profile and identify which weaknesses need future retesting.",
    llm=llm,
    verbose=True
)

student_code = '''
public class Login {
    public static void main(String[] args) {
        String password = "admin";

        if(password == "admin") {
            System.out.println("Login successful");
        }
    }
}
'''

analysis_task = Task(
    description=f'''
Analyze this Java code:

{student_code}

Identify the main conceptual mistake and explain what the student misunderstood.
''',
    expected_output='''
Concept:
Misconception:
Explanation:
''',
    agent=code_analyzer
)

memory_task = Task(
    description='''
Read the Code Analyzer's result.

Extract the main student misconception.

Return:
- concept
- misconception
- needs_retest

Set needs_retest to true if the concept should be tested again.
''',
    expected_output="A structured misconception record.",
    agent=memory_agent,
    context=[analysis_task],
    output_pydantic=MisconceptionRecord
)

crew = Crew(
    agents=[
        code_analyzer,
        memory_agent
    ],
    tasks=[
        analysis_task,
        memory_task
    ],
    process=Process.sequential,
    verbose=True
)

crew.kickoff()

record = memory_task.output.pydantic

if record.needs_retest:
    save_weakness(
        record.concept,
        record.misconception
    )

print("\n========== DETECTED WEAKNESS ==========\n")
print("Concept:", record.concept)
print("Misconception:", record.misconception)
print("Needs Retest:", record.needs_retest)

print("\n========== UPDATED STUDENT MEMORY ==========\n")
print(json.dumps(load_memory(), indent=4))
