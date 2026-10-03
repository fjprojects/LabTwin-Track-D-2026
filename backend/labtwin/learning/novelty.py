"""Per-student semantic novelty with an explicit, measurable fallback method."""
import hashlib
import json
from difflib import SequenceMatcher

from .vectors import embed, embedding_backend, tokens


def signature(values):
    answer = values.get("answer", {})
    if values.get("kind") == "quiz":
        options = values.get("options", [])
        index = answer.get("correct_index")
        answer = options[index] if type(index) is int and 0 <= index < len(options) else ""
    key = [values.get("kind"), sorted(tokens(values.get("prompt", ""))), answer]
    return hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()


def vector(values, course):
    try:
        return embed([values["prompt"]], embedding_backend(course))[0]
    except Exception:
        return []


def equivalent(values, previous, candidate_vector=None, backend="hash"):
    if signature(values) == (previous.fingerprint or signature(previous.__dict__)):
        return True
    if previous.kind != values["kind"]:
        return False
    left, right = set(tokens(values["prompt"])), set(tokens(previous.prompt))
    overlap = len(left & right) / max(1, len(left | right))
    similarity = SequenceMatcher(None, " ".join(sorted(left)), " ".join(sorted(right))).ratio()
    # Hash vectors are lexical, so do not describe them as neural semantics.
    semantic = 0
    if backend == "onnx" and candidate_vector and previous.semantic_vector:
        semantic = sum(a * b for a, b in zip(candidate_vector, previous.semantic_vector))
    return overlap >= .82 or similarity >= .93 or semantic >= .92


def repetition_rate(questions, backend="hash"):
    prior, repeated = [], 0
    for question in questions:
        if any(equivalent(question.__dict__, other, question.semantic_vector, backend) for other in prior):
            repeated += 1
        prior.append(question)
    return {"rate": repeated / len(prior) if prior else None, "repeated": repeated,
            "delivered": len(prior), "method": "neural+lexical" if backend == "onnx" else "lexical_semantic_proxy"}
