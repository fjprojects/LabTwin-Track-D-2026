from django.core.management.base import BaseCommand
from labtwin.models import CourseMaterial, SourceChunk
from labtwin.learning.vectors import index_chunks, remove_vectors


class Command(BaseCommand):
    help = "Rebuild vectors from retained SQL source chunks into the configured vector directory."

    def handle(self, *args, **options):
        for material in CourseMaterial.objects.filter(status="ready").select_related("course"):
            # Historical units remain available to saved citations, but must not
            # return to current retrieval when rebuilding an existing index.
            remove_vectors(list(SourceChunk.objects.filter(unit__material=material, unit__archived=True).values_list("id", flat=True)))
            chunks = list(SourceChunk.objects.filter(unit__material=material, unit__archived=False))
            index_chunks(chunks, material.course)
            self.stdout.write(f"Indexed material {material.id}")
