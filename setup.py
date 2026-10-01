from crewai import Agent, Task, Crew, Process, LLM
from dotenv import load_dotenv
import os

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

print("Groq API key loaded:", bool(GROQ_API_KEY))

MODEL = "groq/openai/gpt-oss-20b"

llm = LLM(
    model=MODEL,
    api_key=GROQ_API_KEY,
    temperature=0.3
)

print("Groq LLM connected")
