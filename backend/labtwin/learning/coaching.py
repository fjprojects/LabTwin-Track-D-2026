import re

from ..models import CoachingInteraction, SourceChunk
from .ai import structured_completion
from .mastery import resources


def conceptual_mistake(topic, code, score):
    if score is not None and score >= 100:
        return "The submitted program passed the hidden checks. Explain why the key steps preserve the topic's invariant."
    name = topic.name.casefold()
    if "linked" in name and re.search(r"(?:->|\.)next\s*=\s*(?:NULL|None|0)\s*;?", code):
        return "Likely pointer-linking weakness: the new node may not be connected to the previous head before the head is updated. Check this against your code."
    if "recurs" in name:
        return "Check the base case and whether each recursive call moves toward it; a failure can indicate a missing stopping condition."
    return f"The checks suggest a gap in {topic.name}. Trace the invariant, boundary cases and order of updates; this is a likely explanation, not a definitive diagnosis."


def make_hint(student, topic, code, score, level, question=None, assignment_attempt=None):
    misconception = conceptual_mistake(topic, code, score)
    sources = resources(topic)
    clues = [f"{misconception} What must remain true before and after each update?", f"Focus on the order of updates in {topic.name}. Write down the old state and the connections that must survive before replacing it.", "Pseudocode: preserve the old state → connect the new state to it → update the entry/reference → verify empty and non-empty cases."]
    message = clues[level - 1]
    passages = list(SourceChunk.objects.filter(course=topic.course, id__in=[s["id"] for s in sources], unit__material__status="ready").values("id", "text"))
    result = None if topic.course.is_demo else structured_completion("Give progressive tutoring, not a full solution. Level 1 conceptual clue; 2 specific direction; 3 pseudocode. Use supplied topic, code and source excerpts only. Never include executable code, hidden test inputs, outputs or a complete solution. Return JSON {message:string}.", {"topic": topic.name, "code": code[:16000], "likely_concept": misconception, "level": level, "sources": passages}, 600)
    if result and isinstance(result.get("message"), str) and not re.search(r"```|\bdef\s+\w+\(|#include|public\s+class|\bmain\s*\(|\w+\s*->\s*\w+\s*=|\bimport\s+\w+", result["message"]):
        message = result["message"][:2500]
    item = CoachingInteraction.objects.create(student=student, topic=topic, question=question, assignment_attempt=assignment_attempt, level=level, message=message, misconception=misconception, source_ids=[s["id"] for s in sources])
    return {"id": item.id, "level": level, "message": message, "mistake": misconception, "resources": sources}
