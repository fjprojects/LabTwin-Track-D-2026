"""Rehydrate disposable Chroma search from embeddings persisted in Postgres."""
from django.core.management.base import BaseCommand

from labtwin.models import SourceChunk
from labtwin.learning.vectors import vector_collection, signature


class Command(BaseCommand):
    help = "Restore the local vector index from existing source chunks after a restart."
    requires_system_checks = []

    def handle(self, *args, **options):
        count = 0
        for backend in ("hash", "onnx"):
            rows = SourceChunk.objects.filter(
                unit__archived=False,
                unit__material__status="ready",
                embedding_model=signature(backend),
            ).order_by("id").iterator(chunk_size=64)
            batch = []

            def flush():
                nonlocal count
                if not batch:
                    return
                vector_collection(backend).upsert(
                    ids=[f"c-{row.id}" for row in batch],
                    embeddings=[row.embedding for row in batch],
                    documents=[row.text for row in batch],
                    metadatas=[row.metadata for row in batch],
                )
                count += len(batch)
                batch.clear()

            for row in rows:
                if not row.embedding:
                    continue
                batch.append(row)
                if len(batch) >= 64:
                    flush()
            flush()
        self.stdout.write(f"Restored {count} source vectors from the database.")
