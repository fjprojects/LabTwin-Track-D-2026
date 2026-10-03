import logging
import re

from django.db import transaction
from django.core.files.base import ContentFile
from django.db.models import Max

from ..models import SourceUnit, SourceChunk
from .access import LearningError
from .ai import structured_completion
from .extraction import extract
from .vectors import index_chunks, remove_vectors, tokens
from .processing import claim_material, progress, finish_material, ProcessingInterrupted

logger = logging.getLogger(__name__)


def split_chunks(text, limit=1000, overlap=140):
    text = re.sub(r"[ \t]+", " ", text).strip()
    pieces = []
    start = 0
    while start < len(text):
        end = min(start + limit, len(text))
        if end < len(text):
            boundary = max(text.rfind("\n", start + limit // 2, end), text.rfind(". ", start + limit // 2, end))
            if boundary > start:
                end = boundary + 1
        pieces.append(text[start:end].strip())
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    return [piece for piece in pieces if piece]


def lecture_intelligence(material, units):
    topics = list(material.course.topics.all())
    names = [t.name for t in topics]
    selected = [name for name in names if set(tokens(name)) & set(tokens(" ".join(u["text"] for u in units)))]
    if not selected:
        selected = list(dict.fromkeys((u.get("title") or u["text"].split("\n")[0])[:100] for u in units if u.get("title") or 3 <= len(u["text"].split("\n")[0]) <= 100))[:12]
    chapters = []
    last_topic = None
    for unit in units:
        leading = unit["text"].split(".")[0].strip()
        caption_heading = leading if material.transcript_origin in ("teacher_captions", "embedded_captions") and len(units) <= 30 and 3 <= len(leading) <= 60 else ""
        name = caption_heading or unit.get("topic_name") or unit.get("title") or material.title
        if name != last_topic or (not chapters) or (unit.get("start_seconds", 0) or 0) - chapters[-1].get("start", 0) >= 180:
            chapters.append({"title": name, "start": unit.get("start_seconds") or 0, "unit_number": unit["number"]})
            last_topic = name
    usable = [unit for unit in units if unit["text"]]
    count = min(12, len(usable))
    # Include the end of a long lecture, rather than summarizing only its opening.
    indices = [round(index * (len(usable) - 1) / max(1, count - 1)) for index in range(count)]
    excerpts = [usable[index]["text"][:500] for index in indices]
    summary = "Source overview: " + "\n".join(excerpt[:220] for excerpt in excerpts)
    result = None if material.course.is_demo else structured_completion("Summarize this teaching material using ONLY these passages sampled throughout it. Return JSON {summary: string}. No new facts.", {"passages": excerpts}, 700)
    if result and isinstance(result.get("summary"), str):
        summary = result["summary"][:4000]
    return summary, chapters[:100], selected


def process_material(material, captions=None, lease_token=None):
    token = lease_token or claim_material(material.id)
    if not token:
        return False
    report = lambda stage, completed=0, total=0, unit="": progress(material.id, token, stage, completed, total, unit)
    try:
        report("extracting")
        # Saved captions make queued processing and retries reproducible.
        if captions is None and material.transcript_origin == "teacher_captions":
            captions = material.transcript
        units, warnings, extra, _ = extract(material, captions, progress=report)
        from .taxonomy import tag_units
        report("topics", total=len(units), unit="sections")
        units = tag_units(material, units)
        report("saving", total=len(units), unit="sections")
        old_ids = list(material.units.filter(archived=False).values_list("chunks__id", flat=True))
        remove_vectors([value for value in old_ids if value])
        with transaction.atomic():
            # Keep previously cited source units and figures across retries.
            material.units.filter(archived=False).update(archived=True)
            offset = material.units.aggregate(value=Max("number"))["value"] or 0
            chunks = []
            for section_number, data in enumerate(units, 1):
                data["number"] += offset
                visual_blob = data.pop("visual_blob", None)
                if material.topic:
                    topic_name = material.topic.name
                else:
                    topic_name = data.get("topic_name", "")
                data["topic_name"] = topic_name
                unit = SourceUnit.objects.create(material=material, **data)
                if visual_blob:
                    unit.visual_file.save("figure.png", ContentFile(visual_blob))
                for position, text in enumerate(split_chunks(unit.text)):
                    metadata = {"course_id": material.course_id, "classroom_id": material.course.classroom_id, "material_id": material.id, "document": material.title, "filename": material.filename, "lecture_name": material.title if material.kind in ("audio", "video") else "", "page": unit.page_number or 0, "slide": unit.slide_number or 0, "start": unit.start_seconds if unit.start_seconds is not None else -1, "end": unit.end_seconds if unit.end_seconds is not None else -1, "topic": topic_name, "subtopic": unit.subtopic, "concepts": ", ".join(unit.concepts), "prerequisites": ", ".join(unit.prerequisite_names), "content_type": unit.content_type, "analysis_method": unit.analysis_method, "unit": unit.id, "origin": unit.layout.get("origin", material.kind)}
                    chunks.append(SourceChunk.objects.create(unit=unit, course=material.course, position=position, text=text, metadata=metadata, embedding_model=""))
                report("saving", section_number, len(units), "sections")
        if not chunks:
            raise LearningError("No usable teaching content was found.")
        report("indexing", total=len(chunks), unit="chunks")
        index_chunks(chunks, material.course, progress=report)
        for key, value in extra.items():
            setattr(material, key, value)
        report("summary")
        material.summary, material.chapters, material.key_topics = lecture_intelligence(material, units)
        material.warnings = warnings
        finish_material(material, token)
        return True
    except ProcessingInterrupted:
        return False
    except Exception as error:
        logger.warning("Course material %s processing failed: %s", material.id, type(error).__name__)
        message = error.message if isinstance(error, LearningError) else "Processing failed. Check the file and retry; the original upload was retained."
        try:
            finish_material(material, token, error=message)
        except ProcessingInterrupted:
            pass
        material.refresh_from_db()
        return False
