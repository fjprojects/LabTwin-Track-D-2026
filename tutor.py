from crewai import Agent, Task, Crew, Process, LLM
import crewai.llms.cache as _crewai_cache
from dotenv import load_dotenv
import os

_crewai_cache.mark_cache_breakpoint = lambda message: message

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

llm = LLM(
    model="groq/openai/gpt-oss-20b",
    api_key=GROQ_API_KEY,
    temperature=0.3
)

code_analyzer = Agent(
    role="Programming Lab Code Analyzer",
    goal="Identify the student's underlying programming misconception without directly giving the full solution.",
    backstory="You are a strict programming lab instructor who focuses on conceptual understanding.",
    llm=llm,
    verbose=True
)

adaptive_tutor = Agent(
    role="Adaptive Programming Tutor",
    goal="Generate a targeted hint, practice problem, and viva question based on the student's identified weakness.",
    backstory="You help students fix misconceptions by adapting the next activity to their weakness instead of giving generic exercises.",
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

Identify:
1. The main concept involved.
2. The student's misconception.
3. Why the approach is problematic.
4. One short hint.

Do not provide the complete corrected program.
''',
    expected_output='''
Concept:
Misconception:
Explanation:
Hint:
''',
    agent=code_analyzer
)

tutor_task = Task(
    description='''
Use the Code Analyzer's result.

Do the following:
1. Identify the weakness that needs practice.
2. Give one progressive hint.
3. Generate one NEW Java problem testing the same concept.
4. Ask one short viva question.
5. Do not provide the full solution.
''',
    expected_output='''
Weakness:
Hint:
Practice Problem:
Viva Question:
''',
    agent=adaptive_tutor,
    context=[analysis_task]
)

crew = Crew(
    agents=[
        code_analyzer,
        adaptive_tutor
    ],
    tasks=[
        analysis_task,
        tutor_task
    ],
    process=Process.sequential,
    verbose=True
)

result = crew.kickoff()

print("\n========== LABTWIN FINAL RESULT ==========\n")
print(result)
