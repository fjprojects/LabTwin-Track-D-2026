from crewai import Agent, Task, Crew, Process, LLM
import crewai.llms.cache as _crewai_cache
from dotenv import load_dotenv
import os

# Temporary CrewAI + Groq compatibility fix
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
    goal="Analyze student code and identify the underlying conceptual mistake without directly giving the full solution.",
    backstory="You are an experienced programming lab instructor. You focus on understanding the student's misconception instead of encouraging memorization.",
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
1. The programming concept involved.
2. The student's main misconception.
3. Why the approach is problematic.
4. One hint.

Do not provide the complete corrected program.
''',
    expected_output='''
Concept:
Mistake:
Explanation:
Hint:
''',
    agent=code_analyzer
)

crew = Crew(
    agents=[code_analyzer],
    tasks=[analysis_task],
    process=Process.sequential,
    verbose=True
)

result = crew.kickoff()

print("\n========== LABTWIN RESULT ==========\n")
print(result)
