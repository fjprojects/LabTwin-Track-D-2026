"""Explicit legacy replay preserves original evidence and every old snapshot."""
from django.core.management.base import BaseCommand
from django.db import transaction
from labtwin.models import LearningEvidence, TopicMastery, MasterySnapshot, CourseTopic, StudentProfile
from labtwin.learning.learner_model import replay, MODEL_VERSION
from labtwin.learning.mastery import state_for


class Command(BaseCommand):
    help = "Replay retained course evidence into BKT. Historical snapshots are preserved."
    def add_arguments(self, parser):
        parser.add_argument("--course", type=int)
    def handle(self, *args, **options):
        evidence = LearningEvidence.objects.all()
        if options["course"]:
            evidence = evidence.filter(topic__course_id=options["course"])
        for student_id, topic_id in evidence.values_list("student_id", "topic_id").distinct():
            with transaction.atomic():
                topic = CourseTopic.objects.get(pk=topic_id)
                rows = list(evidence.filter(student_id=student_id, topic=topic).order_by("created_at", "id"))
                probability, parameters, traces, observations = replay(topic, rows)
                score = round(probability * 100, 1) if observations else 0
                current = TopicMastery.objects.filter(student_id=student_id, topic=topic).first()
                if current and current.model_version == MODEL_VERSION and current.model_parameters == parameters and current.score == score:
                    continue
                old_model = current.model_version if current else "unassessed"
                old_score = current.score if current else None
                mastery, _ = TopicMastery.objects.update_or_create(student_id=student_id, topic=topic, defaults={
                    "score": score, "state": state_for(score, observations), "attempts": observations,
                    "knowledge_probability": probability, "model_version": MODEL_VERSION, "model_parameters": parameters,
                    "average_hint_level": sum(e.hint_level for e in rows) / len(rows) if rows else 0})
                MasterySnapshot.objects.create(student_id=student_id, topic=topic, score=score, state=mastery.state,
                    evidence={"model": MODEL_VERSION, "event": "model_replay", "previous_model": old_model, "previous_score": old_score,
                        "parameters": parameters, "evidence_ids": [e.id for e in rows], "note": "Model transition is not a measured learning gain."})
                self.stdout.write(f"Replayed student {student_id}, topic {topic_id}: {observations} scored observations")
