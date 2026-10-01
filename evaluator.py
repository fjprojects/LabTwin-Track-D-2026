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

def update_status(concept, new_status):
    memory = load_memory()

    for weakness in memory["weaknesses"]:
        if weakness["concept"].lower().strip() == concept.lower().strip():
            weakness["status"] = new_status

    save_memory(memory)

class EvaluationResult(BaseModel):
    concept: str
    code_correct: bool
    viva_correct: bool
    status: str
    score: int
    reason: str

llm = LLM(
    model="groq/openai/gpt-oss-20b",
    api_key=GROQ_API_KEY,
    temperature=0.2
)

evaluator = Agent(
    role="Programming Lab Evaluator",
    goal="Verify whether a student has genuinely corrected a previously identified programming misconception.",
    backstory="You are a strict programming lab evaluator. You check both code application and conceptual understanding before marking a weakness as corrected.",
    llm=llm,
    verbose=True
)

memory = load_memory()

new_student_code = '''
public class Login {
    public static void main(String[] args) {
        String password = "admin";

        if(password.equals("admin")) {
            System.out.println("Login successful");
        }
    }
}
'''

viva_answer = '''
== compares references for objects, while equals() is used to compare
the actual contents of Strings.
'''

evaluation_task = Task(
    description=f'''
Previous student learning profile:

{json.dumps(memory, indent=2)}

The student has now attempted a new problem.

NEW CODE:

{new_student_code}

VIVA ANSWER:

{viva_answer}

Evaluate the student carefully.

Check:
1. Whether the relevant concept is now applied correctly in the code.
2. Whether the viva answer shows actual conceptual understanding.
3. Whether the previous weakness should be marked:
   - Corrected
   - Improving
   - Needs Retest

Give a score from 0 to 100.

Do not mark Corrected unless both the code and viva demonstrate understanding.
''',
    expected_output="A structured evaluation result.",
    agent=evaluator,
    output_pydantic=EvaluationResult
)

crew = Crew(
    agents=[evaluator],
    tasks=[evaluation_task],
    process=Process.sequential,
    verbose=True
)

crew.kickoff()

result = evaluation_task.output.pydantic

update_status(
    result.concept,
    result.status
)

print("\n========== EVALUATION RESULT ==========\n")
print("Concept:", result.concept)
print("Code Correct:", result.code_correct)
print("Viva Correct:", result.viva_correct)
print("Status:", result.status)
print("Score:", result.score)
print("Reason:", result.reason)

print("\n========== UPDATED MEMORY ==========\n")
print(json.dumps(load_memory(), indent=4))
