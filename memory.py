import json
from pathlib import Path

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

if __name__ == "__main__":

    save_weakness(
        "Java String Comparison",
        "Uses == instead of equals() for comparing String contents"
    )

    memory = load_memory()

    print("\n========== STUDENT MEMORY ==========\n")
    print(json.dumps(memory, indent=4))
