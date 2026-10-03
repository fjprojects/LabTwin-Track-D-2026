"""Grounded candidate generation; verification and novelty run separately."""
import re

from .ai import structured_completion


def candidates(chunks, topic, difficulty, kind=None):
    for chunk in chunks:
        base = {"language": topic.course.language, "source_ids": [chunk.id], "tests": [], "starter_code": "", "solution": "", "rubric": []}
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", chunk.text) if 25 <= len(s.strip()) <= 700]
        for excerpt in sentences:
            metadata = {"support_quote": excerpt, "subtopic": chunk.unit.subtopic, "concepts": chunk.unit.concepts}
            if kind in (None, "quiz"):
                yield {**base, "kind": "quiz", "difficulty": 1,
                       "prompt": f"Which statement appears in the uploaded source about {topic.name}: {excerpt[:55].rstrip('.')}…?",
                       "options": [excerpt, "This statement is absent from the supplied source passage."], "answer": {"correct_index": 0},
                       "explanation": excerpt, "metadata": {**metadata, "template": "verbatim_mcq"}}
            if kind in (None, "short_answer"):
                match = re.match(r"(.{2,70}?)\s+(is|are|means|refers to|stores|identifies|has)\s+(.+)", excerpt, re.I)
                if match:
                    subject, verb, definition = match.groups()
                    yield {**base, "kind": "short_answer", "difficulty": 1, "prompt": f"Complete the source definition: ____ {verb} {definition}",
                           "options": [], "answer": {"accepted": [subject.strip()]}, "explanation": excerpt,
                           "metadata": {**metadata, "template": "definition_blank"}}
            if kind in (None, "numerical"):
                expression = re.search(r"([\d.()\s+*/×÷^\-]{3,50})\s*=\s*(-?\d+(?:\.\d+)?)", excerpt)
                if expression:
                    yield {**base, "kind": "numerical", "difficulty": 2, "prompt": f"Evaluate the worked expression {expression[1].strip()} from your course material.",
                           "options": [], "answer": {"value": expression[2], "tolerance": 0}, "explanation": excerpt,
                           "metadata": {**metadata, "template": "worked_arithmetic", "expression": expression[1].strip().replace("^", "**")}}
        if kind in (None, "numerical") and chunk.unit.content_type == "visual":
            graph = chunk.unit.layout.get("analysis", {}).get("graph", {})
            if graph.get("nodes"):
                yield {**base, "kind": "numerical", "difficulty": 2, "prompt": f"How many connected labelled elements are shown in the diagram at {chunk.unit.material.title}, page/slide {chunk.unit.page_number or chunk.unit.slide_number}? Include pointer and NULL labels, when present.",
                       "options": [], "answer": {"value": len(graph["nodes"]), "tolerance": 0}, "explanation": chunk.unit.visual_description,
                       "metadata": {"support_quote": chunk.text, "template": "diagram_count", "graph_unit_id": chunk.unit_id, "subtopic": chunk.unit.subtopic}}
    if chunks and not topic.course.is_demo:
        source = chunks[0]
        generated = structured_completion(
            "Generate one assessment grounded exclusively in this source. Return JSON {kind:quiz|short_answer|numerical,prompt,options,answer:{correct_index OR accepted:[strings] OR value,tolerance},explanation,metadata:{support_quote}}. The quote must be verbatim. No code or hidden tests. Difficulty 1 recall, 2 application, 3 transfer. Generation alone will not verify your answer.",
            {"topic": topic.name, "kind": kind or "quiz", "difficulty": difficulty, "source": source.text[:3500]}, 1600)
        if generated and isinstance(generated.get("prompt"), str) and generated.get("kind") in ("quiz", "short_answer", "numerical"):
            # A generating model cannot grant itself deterministic verification.
            generated["metadata"] = {"support_quote": generated.get("metadata", {}).get("support_quote", "")} if isinstance(generated.get("metadata"), dict) else {}
            generated.update(language=topic.course.language, difficulty=difficulty, source_ids=[source.id], tests=[], starter_code="", solution="", rubric=[])
            yield generated
