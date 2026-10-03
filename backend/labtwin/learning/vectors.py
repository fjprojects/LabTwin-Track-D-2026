"""Persistent Chroma vectors plus an authorization-filtered lexical reranker."""
import hashlib
import math
import re
from collections import Counter
from functools import lru_cache

from django.conf import settings
from django.db.models import Q

from ..models import SourceChunk
from .access import LearningError

STOPWORDS = set("a an the and or is are was were to of in on for with as at by this that it be can do does how what why where when explain tell me my teacher taught about according please lecture notes material source".split())


def tokens(text):
    words = re.findall(r"[\w]+", str(text).casefold(), flags=re.UNICODE)
    return [word[:-1] if len(word) > 4 and word.endswith("s") and not word.endswith("ss") else word
            for word in words if word not in STOPWORDS]


def embedding_backend(course):
    return "hash" if course.is_demo else getattr(settings, "LABTWIN_EMBEDDING_BACKEND", "onnx")


def signature(backend):
    return "hash-384-v1" if backend == "hash" else "onnx-all-MiniLM-L6-v2"


def hash_embedding(text):
    words = tokens(text)
    features = words + [f"{a}_{b}" for a, b in zip(words, words[1:])]
    vector = [0.0] * 384
    for term, count in Counter(features).items():
        digest = hashlib.sha256(term.encode()).digest()
        index = int.from_bytes(digest[:4], "big") % len(vector)
        vector[index] += (1 + math.log(count)) * (1 if digest[4] % 2 else -1)
    norm = math.sqrt(sum(v * v for v in vector)) or 1
    return [v / norm for v in vector]


@lru_cache(maxsize=2)
def _onnx_embedder():
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
    return DefaultEmbeddingFunction()


def embed(texts, backend):
    if backend == "hash":
        return [hash_embedding(text) for text in texts]
    if backend != "onnx":
        raise LearningError("Unknown embedding backend. Use onnx or hash.", 503)
    try:
        return [list(map(float, vector)) for vector in _onnx_embedder()(texts)]
    except Exception as error:
        raise LearningError("The embedding model could not load. Check model-cache/network access, then retry this material.", 503) from error


@lru_cache(maxsize=8)
def collection(path, backend):
    import chromadb
    from chromadb.config import Settings
    try:
        client = chromadb.PersistentClient(path=path, settings=Settings(anonymized_telemetry=False))
    except BaseException as error:
        # Chroma's Rust bindings raise PanicException outside Exception when an
        # incompatible index is opened. Keep this a recoverable upload failure.
        if type(error).__name__ != "PanicException":
            raise
        raise LearningError("The vector index is incompatible. Back it up, select a fresh LABTWIN_VECTOR_ROOT and run reindex_materials.", 503) from error
    return client.get_or_create_collection(f"labtwin-{backend}-v1", metadata={"hnsw:space": "cosine"}, embedding_function=None)


def vector_collection(backend):
    path = str(getattr(settings, "LABTWIN_VECTOR_ROOT", settings.BASE_DIR / "learning_vectors"))
    return collection(path, backend)


def index_chunks(chunks, course, progress=None):
    backend = embedding_backend(course)
    store = vector_collection(backend)
    for offset in range(0, len(chunks), 64):
        batch = chunks[offset:offset + 64]
        vectors = embed([chunk.text for chunk in batch], backend)
        store.upsert(ids=[f"c-{chunk.id}" for chunk in batch], embeddings=vectors,
                     documents=[chunk.text for chunk in batch], metadatas=[chunk.metadata for chunk in batch])
        for chunk, vector in zip(batch, vectors):
            chunk.embedding, chunk.embedding_model = vector, signature(backend)
        SourceChunk.objects.bulk_update(batch, ["embedding", "embedding_model"])
        if progress:
            progress("indexing", min(offset + len(batch), len(chunks)), len(chunks), "chunks")


def remove_vectors(ids):
    if not ids:
        return
    for backend in ("hash", "onnx"):
        try:
            vector_collection(backend).delete(ids=[f"c-{value}" for value in ids])
        except Exception:
            # SQL authorization/status remains authoritative even if an index is offline.
            pass


def retrieve(courses, question, material_id=None, limit=6, source_id=None):
    courses = list(courses)
    if not courses or not tokens(question):
        return []
    course_ids = [course.id for course in courses]
    allowed = SourceChunk.objects.filter(course_id__in=course_ids, unit__material__status="ready", unit__archived=False).select_related("unit__material", "course__classroom")
    if material_id:
        allowed = allowed.filter(unit__material_id=material_id)
    location = re.search(r"\b(page|slide)\s+(\d+)\b", question, re.I)
    if location:
        field = "unit__page_number" if location[1].lower() == "page" else "unit__slide_number"
        allowed = allowed.filter(**{field: int(location[2])})
    if source_id:
        exact = allowed.filter(pk=source_id).first()
        if not exact:
            return []
        allowed = allowed.filter(unit_id=exact.unit_id)
    if (location or source_id) and re.search(r"\b(diagram|figure|image|chart|flowchart|illustration)\b", question, re.I):
        figures = list(allowed.filter(unit__content_type="visual").order_by("position")[:limit])
        if figures:
            return [{"score": 1.0, "chunk": chunk, "location_match": True} for chunk in figures]
    semantic = {}
    for backend in {embedding_backend(course) for course in courses}:
        ids = [course.id for course in courses if embedding_backend(course) == backend]
        try:
            store = vector_collection(backend)
            if not store.count():
                continue
            where = {"course_id": {"$in": ids}}
            if material_id:
                where = {"$and": [where, {"material_id": material_id}]}
            result = store.query(query_embeddings=embed([question], backend), n_results=min(store.count(), 24), where=where, include=["distances"])
            for chunk_id, distance in zip(result["ids"][0], result["distances"][0]):
                semantic[int(chunk_id[2:])] = max(0, 1 - distance)
        except Exception:
            # Retain source-grounded lexical search during vector-service outages.
            pass
    terms = set(tokens(question))
    word_filter = Q(pk__in=list(semantic))
    for term in terms:
        word_filter |= Q(text__icontains=term)
    candidates = list(allowed.filter(word_filter)[:1000])
    scored = []
    for chunk in candidates:
        chunk_terms = set(tokens(chunk.text + " " + chunk.unit.topic_name))
        coverage = len(terms & chunk_terms) / max(1, len(terms))
        score = 0.60 * semantic.get(chunk.id, 0) + 0.40 * coverage
        # Unsupported topics should not be answered from weak semantic coincidence.
        if coverage == 0 or score < 0.08:
            continue
        scored.append((score, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    diverse, seen_units, seen_materials = [], set(), set()
    # Give page/slide/lecture evidence a chance to appear together rather than
    # filling the entire context with overlapping chunks of a single PDF.
    for score, chunk in scored:
        material = chunk.unit.material_id
        if material not in seen_materials:
            diverse.append((score, chunk)); seen_units.add(chunk.unit_id); seen_materials.add(material)
            if len(diverse) >= limit:
                break
    for item in scored:
        if len(diverse) >= limit:
            break
        if item[1].unit_id not in seen_units:
            diverse.append(item); seen_units.add(item[1].unit_id)
    return [{"score": round(score, 3), "chunk": chunk} for score, chunk in diverse]
