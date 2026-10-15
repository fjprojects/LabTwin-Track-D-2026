"""Source-backed assessment candidates; OCR noise is not evidence of a valid question.

The deterministic MCQ checks understanding of a source fact rather than whether
a sentence merely appears on a page. If the extracted text is unreadable, offer
no automatically graded question; a teacher can still review the original PDF.
"""
import hashlib
import re

from .ai import structured_completion


FACT = re.compile(
    r"^([A-Za-z][A-Za-z -]{2,70}?)\s+(is|are|means|refers to|stores|identifies|has)\s+(.+?)[.!?]?$",
    re.I,
)
INDEX_LABEL = re.compile(r"\b(?:sno|s\.\s*no|page\s*no|title\s+of\s+the\s+topic|table\s+of\s+contents)\b", re.I)


def readable_source_sentence(value):
    """Reject visibly garbled text, not silently 'correct' unknown OCR words."""
    if not isinstance(value, str):
        return False
    value = value.strip()
    if not 25 <= len(value) <= 700 or INDEX_LABEL.search(value):
        return False
    if re.search(r"[|_\\{}<>\uFFFD\u007f]|[\x00-\x08\x0b-\x1f]", value):
        return False
    if not re.search(r"[A-Za-z]{3,}", value) or len(value.split()) < 5:
        return False
    words = re.findall(r"[A-Za-z]+", value)
    if sum(len(w) <= 1 for w in words) > 3:
        return False
    return True


def candidates(chunks, topic, difficulty, kind=None):
    # Build distractors from OTHER readable facts, never from invented "not in
    # the passage" claims. We need two separate facts before we can offer an MCQ.
    facts = []
    for chunk in chunks:
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", chunk.text)]
        for excerpt in sentences:
            if not readable_source_sentence(excerpt):
                continue
            match = FACT.fullmatch(excerpt)
            if not match:
                continue
            subject, verb, definition = match.groups()
            if len(definition.strip()) < 8 or INDEX_LABEL.search(subject):
                continue
            if sum(char.isalpha() for char in definition) < 6:
                continue
            facts.append((chunk, excerpt, subject.strip(), verb.lower(), definition.strip().rstrip(".")))

    for chunk in chunks:
        base = {"language": topic.course.language, "source_ids": [chunk.id], "tests": [], "starter_code": "", "solution": "", "rubric": []}
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", chunk.text)]
        for excerpt in sentences:
            if not readable_source_sentence(excerpt):
                continue
            metadata = {"support_quote": excerpt, "subtopic": chunk.unit.subtopic, "concepts": chunk.unit.concepts}
            fact = next((fact for fact in facts if fact[0].id == chunk.id and fact[1] == excerpt), None)
            if kind in (None, "quiz") and fact:
                _, _, subject, _, _ = fact
                distractors = []
                for other in facts:
                    if other[1] == excerpt or subject.casefold() in other[1].casefold() or other[2].casefold() in subject.casefold():
                        continue
                    if other[2].casefold() == subject.casefold() or other[1] in distractors:
                        continue
                    distractors.append(other[1])
                    if len(distractors) >= 3:
                        break
                if distractors:
                    options = distractors.copy()
                    correct_index = int.from_bytes(hashlib.sha256(f"{chunk.id}:{excerpt}".encode()).digest()[:4], "big") % (len(options) + 1)
                    options.insert(correct_index, excerpt)
                    yield {**base, "kind": "quiz", "difficulty": 1,
                           "prompt": f"According to your course material, which statement describes {subject}?",
                           "options": options, "answer": {"correct_index": correct_index},
                           "explanation": excerpt,
                           "metadata": {**metadata, "template": "concept_mcq", "subject": subject}}
            if kind in (None, "short_answer") and fact:
                _, _, subject, verb, definition = fact
                yield {**base, "kind": "short_answer", "difficulty": 1,
                       "prompt": f"Complete the source definition: ____ {verb} {definition}",
                       "options": [], "answer": {"accepted": [subject]},
                       "explanation": excerpt, "metadata": {**metadata, "template": "definition_blank"}}
            if kind in (None, "numerical"):
                expression = re.search(r"([\d.()\s+*/×÷^\-]{3,50})\s*=\s*(-?\d+(?:\.\d+)?)", excerpt)
                if expression:
                    yield {**base, "kind": "numerical", "difficulty": 2,
                           "prompt": f"Evaluate the worked expression {expression[1].strip()} from your course material.",
                           "options": [], "answer": {"value": expression[2], "tolerance": 0},
                           "explanation": excerpt, "metadata": {**metadata, "template": "worked_arithmetic", "expression": expression[1].strip().replace("^", "**")}}
        if kind in (None, "numerical") and chunk.unit.content_type == "visual":
            graph = chunk.unit.layout.get("analysis", {}).get("graph", {})
            if graph.get("nodes"):
                yield {**base, "kind": "numerical", "difficulty": 2,
                       "prompt": f"How many connected labelled elements are shown in the diagram at {chunk.unit.material.title}, page/slide {chunk.unit.page_number or chunk.unit.slide_number}? Include pointer and NULL labels, when present.",
                       "options": [], "answer": {"value": len(graph["nodes"]), "tolerance": 0},
                       "explanation": chunk.unit.visual_description,
                       "metadata": {"support_quote": chunk.text, "template": "diagram_count", "graph_unit_id": chunk.unit_id, "subtopic": chunk.unit.subtopic}}
    if chunks and not topic.course.is_demo and any(readable_source_sentence(c.text[:700]) for c in chunks):
        source = next(c for c in chunks if readable_source_sentence(c.text[:700]))
        generated = structured_completion(
            "Generate one assessment grounded exclusively in this source. Return JSON {kind:quiz|short_answer|numerical,prompt,options,answer:{correct_index OR accepted:[strings] OR value,tolerance},explanation,metadata:{support_quote}}. The quote must be verbatim. No code or hidden tests. Difficulty 1 recall, 2 application, 3 transfer. Generation alone will not verify your answer.",
            {"topic": topic.name, "kind": kind or "quiz", "difficulty": difficulty, "source": source.text[:3500]}, 1600)
        if generated and isinstance(generated.get("prompt"), str) and generated.get("kind") in ("quiz", "short_answer", "numerical"):
            generated["metadata"] = {"support_quote": generated.get("metadata", {}).get("support_quote", "")} if isinstance(generated.get("metadata"), dict) else {}
            generated.update(language=topic.course.language, difficulty=difficulty, source_ids=[source.id], tests=[], starter_code="", solution="", rubric=[])
            yield generated
