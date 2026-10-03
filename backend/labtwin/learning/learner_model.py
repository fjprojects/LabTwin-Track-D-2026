"""Bayesian Knowledge Tracing with an explicit, auditable evidence extension.

The baseline has latent known/unknown states and prior, learning, guess and
slip parameters (Corbett & Anderson, 1994). Fractional grades and reliability
weighted likelihoods extend that baseline; they are not a fitted population
model or proof of human learning.
"""
import math

DEFAULT_PARAMETERS = {"prior": 0.35, "learn": 0.08, "guess": 0.15, "slip": 0.10}
MODEL_VERSION = "bkt-reliability-v1"


def parameters_for(topic):
    result = {**DEFAULT_PARAMETERS, **topic.learner_parameters}
    for key in DEFAULT_PARAMETERS:
        value = result[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value < 1:
            raise ValueError("BKT parameters must be finite probabilities between zero and one.")
    if result["guess"] + result["slip"] >= 1:
        raise ValueError("Guess plus slip must be less than one.")
    return result


def update_probability(prior, fraction_correct, params, reliability=1, guess=None):
    fraction = min(1, max(0, fraction_correct))
    guessing = guess if guess is not None else params["guess"]
    guessing = min(0.75, max(0.01, guessing))
    known_likelihood = ((1 - params["slip"]) ** fraction * params["slip"] ** (1 - fraction)) ** reliability
    unknown_likelihood = (guessing ** fraction * (1 - guessing) ** (1 - fraction)) ** reliability
    posterior = prior * known_likelihood / (prior * known_likelihood + (1 - prior) * unknown_likelihood)
    after = posterior + (1 - posterior) * params["learn"] * reliability
    return min(0.999, max(0.001, after)), posterior


def replay(topic, evidence):
    params = parameters_for(topic)
    probability, traces, observations = params["prior"], [], 0
    for item in evidence:
        before = probability
        if item.score is None:
            traces.append({"evidence_id": item.id, "before": before, "after": before, "reason": "Engagement is not evidence of correctness."})
            continue
        reliability = [1.0, .85, .65, .45][min(3, item.hint_level)]
        reliability *= max(.35, .90 ** (item.attempt_number - 1))
        reliability *= 1 if item.verified else .40
        choices = item.detail.get("option_count")
        guess = 1 / choices if isinstance(choices, int) and 2 <= choices <= 8 else None
        probability, posterior = update_probability(probability, item.score / 100, params, reliability, guess)
        observations += 1
        traces.append({"evidence_id": item.id, "kind": item.kind, "before": round(before, 6),
                       "posterior": round(posterior, 6), "after": round(probability, 6),
                       "fraction_correct": item.score / 100, "reliability": round(reliability, 4),
                       "guess": guess if guess is not None else params["guess"], "verified": item.verified})
    return probability, params, traces, observations


def tutoring_policy(student, course, question):
    from ..models import CourseTopic, TopicMastery
    from .vectors import tokens
    candidates = list(CourseTopic.objects.filter(course=course))
    terms = set(tokens(question))
    topic = max(candidates, key=lambda item: len(terms & set(tokens(item.name))), default=None)
    if topic and not terms & set(tokens(topic.name)):
        topic = None
    mastery = TopicMastery.objects.filter(student=student, topic=topic).first() if student and topic else None
    state = mastery.state if mastery else "Not Started"
    style = "advanced" if state == "Strong" else "guided" if state == "Developing" else "foundation"
    return {"style": style, "topic_id": topic.id if topic else None, "topic": topic.name if topic else "",
            "state": state, "mastery_probability": mastery.knowledge_probability if mastery else None,
            "reason": f"Guidance uses your {topic.name} evidence: {state}." if topic else "Start with source concepts; no matching topic has been assessed.",
            "instructions": {"foundation": "Use short sentences, explain labels, split reasoning into small steps and invite prerequisite review.",
                             "guided": "Give a concise explanation, then one source-based application check.",
                             "advanced": "Use less scaffolding, discuss relationships and ask a deeper source-based transfer question."}[style]}
