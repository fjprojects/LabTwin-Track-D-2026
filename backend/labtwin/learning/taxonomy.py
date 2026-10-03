"""Conservative automatic tags and prerequisite edges supported by source text."""
import re

from ..models import CourseTopic
from .vectors import tokens


def clean_heading(text):
    value = " ".join(str(text).strip("# \t").split())
    if 3 <= len(value) <= 120 and len(value.split()) <= 14 and not value.endswith((".", "?")):
        return value
    return ""


def would_cycle(topic, prerequisite):
    pending, seen = [prerequisite], set()
    while pending:
        row = pending.pop()
        if row.id == topic.id:
            return True
        if row.id not in seen:
            seen.add(row.id)
            pending.extend(row.prerequisites.all())
    return False


def tag_units(material, units):
    topics = list(material.course.topics.all())
    for unit in units:
        text = unit["text"]
        heading = clean_heading(unit.get("title") or text.split("\n")[0])
        matches = sorted(topics, key=lambda topic: len(set(tokens(topic.name)) & set(tokens(text))), reverse=True)
        matched = matches[0] if matches and set(tokens(matches[0].name)) & set(tokens(text)) else None
        parent = material.topic or matched
        if not parent and heading:
            parent, _ = CourseTopic.objects.get_or_create(
                course=material.course, name=heading,
                defaults={"position": len(topics), "taxonomy_evidence": {"method": "source_heading", "material_id": material.id, "quote": heading}})
            if parent not in topics:
                topics.append(parent)
        # Unknown content stays untagged rather than borrowing an unrelated
        # topic merely because it was created first.
        subtopic = heading if heading and (not parent or heading.casefold() != parent.name.casefold()) else ""
        if parent and subtopic and subtopic.casefold() not in {material.title.casefold(), material.course.name.casefold()}:
            child, _ = CourseTopic.objects.get_or_create(course=material.course, name=subtopic,
                defaults={"parent": parent, "position": len(topics), "taxonomy_evidence": {"method": "source_heading", "material_id": material.id, "quote": heading}})
            if child not in topics:
                topics.append(child)
        definitions = re.findall(r"(?:^|[.\n]\s*)([A-Za-z][A-Za-z -]{2,55}?)\s+(?:is|are|means|refers to)\s+", text)
        labels = [node["label"] for node in unit.get("layout", {}).get("analysis", {}).get("graph", {}).get("nodes", []) if len(node["label"]) <= 60]
        concepts = list(dict.fromkeys([name.strip() for name in definitions] + labels + ([subtopic] if subtopic else [])))[:20]
        if parent:
            unit["topic_name"] = parent.name
            unit["prerequisite_names"] = list(parent.prerequisites.values_list("name", flat=True))
            parent.concepts = list(dict.fromkeys(parent.concepts + concepts))[:100]
            parent.save(update_fields=["concepts"])
        unit["subtopic"], unit["concepts"] = subtopic, concepts
    # Create an edge only when both named topics and an explicit prerequisite
    # relation appear in the material. Never invent a prerequisite taxonomy.
    sentences = re.split(r"(?<=[.!?])\s+|\n", "\n".join(unit["text"] for unit in units))
    # Most notes contain no prerequisite statements. Avoid T^2 database graph
    # walks and T^2 * sentence-count scans merely to discover that fact.
    relation = re.compile(r"\brequires?\b|\bprerequisite\b|\bbefore\b", re.I)
    lowered_names = [(topic, topic.name.casefold()) for topic in topics]
    for sentence in sentences:
        if not relation.search(sentence):
            continue
        lowered = sentence.casefold()
        mentioned = [(topic, name) for topic, name in lowered_names if name in lowered]
        for topic, topic_name in mentioned:
            for prerequisite, prerequisite_name in mentioned:
                if topic.id == prerequisite.id:
                    continue
                explicit = (re.search(re.escape(topic_name) + r".{0,70}\brequires?\b.{0,70}" + re.escape(prerequisite_name), lowered)
                    or re.search(re.escape(prerequisite_name) + r".{0,70}\bprerequisite\b.{0,70}" + re.escape(topic_name), lowered)
                    or re.search(re.escape(prerequisite_name) + r".{0,60}\bbefore\b.{0,60}" + re.escape(topic_name), lowered))
                if not explicit or would_cycle(topic, prerequisite):
                    continue
                topic.prerequisites.add(prerequisite)
                evidence = dict(topic.taxonomy_evidence)
                evidence.setdefault("prerequisites", {})[str(prerequisite.id)] = {"quote": sentence[:1000], "material_id": material.id}
                topic.taxonomy_evidence = evidence
                topic.save(update_fields=["taxonomy_evidence"])
    for unit in units:
        topic = next((item for item in topics if item.name == unit.get("topic_name")), None)
        if topic:
            unit["prerequisite_names"] = list(topic.prerequisites.values_list("name", flat=True))
    return units
