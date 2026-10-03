import re

from .ai import structured_completion
from .sources import citation
from .vectors import retrieve, tokens


def normalized(text):
    return " ".join(str(text).split()).casefold()


def grounded_answer(course, question, material_id=None, student=None, source_id=None):
    matches = retrieve([course], question, material_id, source_id=source_id)
    covered = set(tokens(" ".join(item["chunk"].text for item in matches))) & set(tokens(question))
    if not matches or (not any(item.get("location_match") for item in matches) and len(covered) / max(1, len(set(tokens(question)))) < 0.5):
        return {"answer": "I could not find enough information in the uploaded materials to answer this. Ask your teacher to add a relevant resource or choose another course.",
                "claims": [], "citations": [], "grounded": False, "mode": "insufficient_sources"}
    contexts = [{"id": item["chunk"].id, "text": item["chunk"].text[:2200]} for item in matches]
    from .learner_model import tutoring_policy
    policy = tutoring_policy(student, course, question)
    generated = None if course.is_demo else structured_completion(
        "You are a source-grounded tutor. Answer only from the supplied course excerpts. If they do not answer the question, return supported:false. "
        "Return {supported:boolean,claims:[{text:string,source_id:integer,quote:string}]}. Every claim needs an exact short supporting quote from its cited excerpt. "
        "Never use outside knowledge, invented citations, or unsupported interpretations. Keep explanations clear and concise.",
        {"question": question, "sources": contexts, "tutoring_policy": policy},
    )
    indexed = {item["chunk"].id: item["chunk"] for item in matches}
    if generated and generated.get("supported") is False:
        return {"answer": "The available course excerpts do not contain enough information for a supported answer to this question.", "claims": [], "citations": [], "grounded": False, "mode": "insufficient_sources"}
    claims = []
    if generated and generated.get("supported") is True and isinstance(generated.get("claims"), list):
        for item in generated["claims"][:6]:
            if not isinstance(item, dict):
                claims = []; break
            source_id, quote, text = item.get("source_id"), item.get("quote", ""), item.get("text", "")
            if not isinstance(source_id, int) or isinstance(source_id, bool) or source_id not in indexed or not isinstance(text, str) or not isinstance(quote, str) or len(quote.strip()) < 16 or normalized(quote) not in normalized(indexed[source_id].text):
                claims = []; break
            claims.append({"text": text[:1800], "quote": quote[:700], "citation": citation(indexed[source_id])})
    mode = "ai_grounded" if claims else "source_excerpts"
    if not claims:
        # This is explicitly an extractive fallback, not fabricated AI prose.
        for item in matches[:4]:
            chunk = item["chunk"]
            sentences = re.split(r"(?<=[.!?])\s+|\n\n", chunk.text)
            excerpt = " ".join(sentences[:3]).strip()[:800]
            claims.append({"text": excerpt, "quote": excerpt, "citation": citation(chunk)})
    citations = list({item["citation"]["id"]: item["citation"] for item in claims}.values())
    prefix = "Here are the relevant excerpts from your course materials:\n\n" if mode == "source_excerpts" else ""
    steps = ["Read the source labels.", "Follow one relationship at a time.", "Check the prerequisite and try a short practice question."] if policy["style"] == "foundation" else ["Explain the relationship in your own words.", "Apply it to a new example from the course."] if policy["style"] == "guided" else ["Compare the cited concepts.", "Test a boundary case or transfer the reasoning."]
    return {"answer": prefix + "\n\n".join(item["text"] for item in claims), "claims": claims,
            "citations": citations, "grounded": True, "mode": mode, "tutoring_policy": policy, "learning_steps": steps}
