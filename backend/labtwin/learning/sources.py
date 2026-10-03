from ..models import SourceChunk


def timestamp(seconds):
    value = max(0, int(seconds or 0))
    return f"{value // 60}:{value % 60:02d}"


def citation(chunk):
    unit, material = chunk.unit, chunk.unit.material
    location = f"Page {unit.page_number}" if unit.page_number else f"Slide {unit.slide_number}" if unit.slide_number else timestamp(unit.start_seconds) if unit.start_seconds is not None else f"Section {unit.number}"
    return {"id": chunk.id, "unit_id": unit.id, "course_id": chunk.course_id, "classroom_id": chunk.course.classroom_id,
            "material_id": material.id, "title": material.title, "filename": material.filename, "kind": material.kind,
            "page_number": unit.page_number, "slide_number": unit.slide_number,
            "start_seconds": unit.start_seconds, "end_seconds": unit.end_seconds,
            "topic": unit.topic_name, "subtopic": unit.subtopic, "concepts": unit.concepts,
            "content_type": unit.content_type, "analysis_method": unit.analysis_method,
            "label": f"{material.title} — {location}", "href": f"#source={chunk.id}"}


def citations_for(course, ids):
    rows = SourceChunk.objects.filter(course=course, id__in=ids, unit__material__status="ready").select_related("unit__material", "course__classroom")
    indexed = {row.id: row for row in rows}
    return [citation(indexed[value]) for value in ids if value in indexed]
