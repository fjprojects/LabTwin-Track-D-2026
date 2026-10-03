import json

from django.db.models import Avg, Count
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .models import (
    StudentProfile,
    ConceptProgress,
    TopicProgress,
    Attempt,
)


def _question_fingerprint(value):
    """
    Stable identity for a programming question.

    Whitespace/line-wrap differences from the browser or LLM should
    not create a fake extra attempt.
    """
    return " ".join(
        str(value or "").split()
    ).casefold()


def _unique_attempt_records(queryset):
    """
    Return one newest evidence row per student topic + normalized
    programming question.
    """
    rows = list(
        queryset.order_by(
            "created_at"
        )
    )

    unique = {}

    for attempt in rows:
        key = (
            str(
                attempt.topic or ""
            ).strip().casefold(),
            _question_fingerprint(
                attempt.question
            ),
        )

        if not key[1]:
            continue

        unique[key] = attempt

    return sorted(
        unique.values(),
        key=lambda item:
            item.created_at
    )




def _memory_topic_misconception(value):
    """
    Only V4-classified topic misconceptions count as persistent
    conceptual weakness. Older unclassified records are intentionally
    treated as untrusted legacy evidence.
    """
    prefix = "TOPIC_RELATED::"
    text = str(value or "").strip()

    if text.startswith(prefix):
        return text[len(prefix):].strip()

    return ""


def _topic_memory_summary(student, topic):
    """Return trusted topic-related misconception history for one topic."""
    values = [
        cleaned
        for attempt in _unique_attempt_records(
            Attempt.objects.filter(
                student=student,
                topic=topic,
            )
        )
        for cleaned in [
            _memory_topic_misconception(
                attempt.misconception
            )
        ]
        if cleaned
    ]

    return {
        "count": len(values),
        "last": values[-1] if values else "",
    }


def _weighted_average(values):
    """
    Recent evidence matters more than older evidence.
    Input must already be ordered oldest -> newest.
    """
    clean = [
        float(value)
        for value in values
        if value is not None
    ]

    if not clean:
        return 0.0

    weights = list(range(1, len(clean) + 1))

    return sum(
        value * weight
        for value, weight in zip(clean, weights)
    ) / sum(weights)


def _hint_independence_score(level):
    """
    0 hints -> 100
    1 hint  -> 70
    2 hints -> 40
    3+      -> 10
    """
    try:
        level = max(0, int(level))
    except Exception:
        level = 0

    return max(
        10,
        100 - (30 * level),
    )



def _topic_mastery_breakdown(
    student,
    topic,
):
    """
    Return an explainable breakdown using exactly the
    same evidence and weights as topic mastery.

    This does not change the mastery calculation.
    It only exposes its components for the UI.
    """

    attempts = _unique_attempt_records(
        Attempt.objects.filter(
            student=student,
            topic=topic,
        )
    )

    if not attempts:
        return None

    # Mastery already uses the latest five unique
    # completed pieces of topic evidence.
    recent = attempts[-5:]

    initial_average = _weighted_average(
        [
            attempt.initial_score
            for attempt in recent
        ]
    )

    final_average = _weighted_average(
        [
            (
                attempt.final_score
                if attempt.final_score is not None
                else attempt.initial_score
            )
            for attempt in recent
        ]
    )

    viva_values = [
        attempt.viva_score
        for attempt in recent
        if attempt.viva_score is not None
    ]

    viva_average = _weighted_average(
        viva_values
    )

    hint_average = _weighted_average(
        [
            attempt.hint_level
            for attempt in recent
        ]
    )

    independence_average = _weighted_average(
        [
            _hint_independence_score(
                attempt.hint_level
            )
            for attempt in recent
        ]
    )

    verification_passed = any(
        attempt.verification
        and attempt.initial_score >= 80
        and (
            attempt.final_score is None
            or attempt.final_score >= 80
        )
        and attempt.viva_score is not None
        and attempt.viva_score >= 75
        and attempt.hint_level <= 1
        for attempt in attempts
    )

    verification_score = (
        100
        if verification_passed
        else 0
    )

    initial_contribution = (
        0.35 * initial_average
    )

    viva_contribution = (
        0.25 * viva_average
    )

    final_contribution = (
        0.15 * final_average
    )

    verification_contribution = (
        0.15 * verification_score
    )

    independence_contribution = (
        0.10 * independence_average
    )

    raw_mastery = (
        initial_contribution
        + viva_contribution
        + final_contribution
        + verification_contribution
        + independence_contribution
    )

    final_mastery = raw_mastery

    cap_reasons = []

    if not viva_values:
        final_mastery = min(
            final_mastery,
            69.0,
        )

        cap_reasons.append(
            "No viva evidence yet, so mastery cannot exceed 69%."
        )

    if not verification_passed:
        final_mastery = min(
            final_mastery,
            79.0,
        )

        cap_reasons.append(
            "Independent verification has not been passed, so mastery cannot exceed 79%."
        )

    final_mastery = round(
        max(
            0,
            min(
                100,
                final_mastery,
            ),
        ),
        1,
    )

    if not verification_passed:
        main_limiter = (
            "Independent verification has not yet been passed."
        )

    elif not viva_values:
        main_limiter = (
            "More conceptual viva evidence is required."
        )

    else:
        evidence_scores = {
            "First-attempt coding":
                initial_average,
            "Concept understanding":
                viva_average,
            "Final corrected code":
                final_average,
            "Hint independence":
                independence_average,
        }

        weakest_evidence = min(
            evidence_scores,
            key=evidence_scores.get,
        )

        main_limiter = (
            f"The weakest current evidence is {weakest_evidence.lower()}."
        )

    return {
        "evidence_attempts":
            len(recent),

        "scores": {
            "initial":
                round(
                    initial_average,
                    1,
                ),

            "viva":
                round(
                    viva_average,
                    1,
                ),

            "final":
                round(
                    final_average,
                    1,
                ),

            "verification":
                verification_score,

            "hint_independence":
                round(
                    independence_average,
                    1,
                ),

            "average_hint_level":
                round(
                    hint_average,
                    1,
                ),
        },

        "weights": {
            "initial":
                35,

            "viva":
                25,

            "final":
                15,

            "verification":
                15,

            "hint_independence":
                10,
        },

        "contributions": {
            "initial":
                round(
                    initial_contribution,
                    1,
                ),

            "viva":
                round(
                    viva_contribution,
                    1,
                ),

            "final":
                round(
                    final_contribution,
                    1,
                ),

            "verification":
                round(
                    verification_contribution,
                    1,
                ),

            "hint_independence":
                round(
                    independence_contribution,
                    1,
                ),
        },

        "verification_passed":
            verification_passed,

        "raw_mastery":
            round(
                raw_mastery,
                1,
            ),

        "final_mastery":
            final_mastery,

        "cap_reasons":
            cap_reasons,

        "main_limiter":
            main_limiter,
    }


def recalculate_topic_progress(student, topic):
    """
    Rebuild exact-topic mastery from recent unique evidence.
    Newer questions matter more than older questions.
    """
    attempts = _unique_attempt_records(
        Attempt.objects.filter(
            student=student,
            topic=topic,
        )
    )

    if not attempts:
        return None

    recent = attempts[-5:]

    initial_average = _weighted_average(
        [
            attempt.initial_score
            for attempt in recent
        ]
    )

    final_average = _weighted_average(
        [
            (
                attempt.final_score
                if attempt.final_score is not None
                else attempt.initial_score
            )
            for attempt in recent
        ]
    )

    viva_values = [
        attempt.viva_score
        for attempt in recent
        if attempt.viva_score is not None
    ]

    viva_average = _weighted_average(
        viva_values
    )

    hint_average = _weighted_average(
        [
            attempt.hint_level
            for attempt in recent
        ]
    )

    independence_average = _weighted_average(
        [
            _hint_independence_score(
                attempt.hint_level
            )
            for attempt in recent
        ]
    )

    verification_passed = any(
        attempt.verification
        and attempt.initial_score >= 80
        and (
            attempt.final_score is None
            or attempt.final_score >= 80
        )
        and attempt.viva_score is not None
        and attempt.viva_score >= 75
        and attempt.hint_level <= 1
        for attempt in attempts
    )

    verification_score = (
        100
        if verification_passed
        else 0
    )

    # Topic mastery:
    # 35% first-attempt coding
    # 25% conceptual understanding
    # 15% final/corrected coding
    # 15% independent verification
    # 10% hint independence
    mastery = (
        (0.35 * initial_average)
        + (0.25 * viva_average)
        + (0.15 * final_average)
        + (0.15 * verification_score)
        + (0.10 * independence_average)
    )

    if not viva_values:
        mastery = min(
            mastery,
            69.0,
        )

    if not verification_passed:
        mastery = min(
            mastery,
            79.0,
        )

    mastery = round(
        max(
            0,
            min(
                100,
                mastery,
            ),
        ),
        1,
    )

    latest = attempts[-1]

    latest_final = (
        latest.final_score
        if latest.final_score is not None
        else latest.initial_score
    )

    latest_viva = (
        latest.viva_score
        if latest.viva_score is not None
        else 0
    )

    if latest_final < 80:
        status = "Needs Coding Practice"

    elif latest_viva < 50:
        status = "Needs Practice"

    elif latest_viva < 75:
        status = "Needs Verification"

    elif not verification_passed:
        status = "Needs Verification"

    elif mastery >= 80:
        status = "Mastered"

    else:
        status = "Developing"

    misconceptions = [
        cleaned
        for attempt in attempts
        for cleaned in [
            _memory_topic_misconception(
                attempt.misconception
            )
        ]
        if cleaned
    ]

    progress, _ = TopicProgress.objects.get_or_create(
        student=student,
        topic=topic,
        defaults={
            "concept_key":
                latest.concept_key,
        },
    )

    progress.concept_key = latest.concept_key
    progress.attempts = len(attempts)
    progress.mastery_score = mastery
    progress.status = status
    progress.verification_passed = verification_passed
    progress.verification_required = (
        status != "Mastered"
    )
    progress.misconception_count = len(
        misconceptions
    )
    progress.last_misconception = (
        misconceptions[-1]
        if misconceptions
        else ""
    )
    progress.average_hint_level = round(
        hint_average,
        1,
    )
    progress.save()

    Attempt.objects.filter(
        id=latest.id
    ).update(
        mastery_score=mastery
    )

    return progress

def _update_broad_concept_progress(
    student,
    concept_key,
):
    """
    Compatibility summary for the original broad-concept table.
    Uses unique completed question evidence.
    """
    attempts = _unique_attempt_records(
        Attempt.objects.filter(
            student=student,
            concept_key=concept_key,
        )
    )

    progress, _ = ConceptProgress.objects.get_or_create(
        student=student,
        concept_key=concept_key,
    )

    progress.attempts = len(
        attempts
    )

    progress.failures = sum(
        1
        for attempt in attempts
        if attempt.initial_score < 100
    )

    progress.mastered = TopicProgress.objects.filter(
        student=student,
        concept_key=concept_key,
        status="Mastered",
    ).count()

    misconceptions = [
        cleaned
        for attempt in attempts
        for cleaned in [
            _memory_topic_misconception(
                attempt.misconception
            )
        ]
        if cleaned
    ]

    progress.misconception_count = len(
        misconceptions
    )

    progress.last_misconception = (
        misconceptions[-1]
        if misconceptions
        else ""
    )

    scores = [
        (
            attempt.final_score
            if attempt.final_score is not None
            else attempt.initial_score
        )
        for attempt in attempts
    ]

    progress.total_score = sum(
        scores
    )

    progress.save()


def _current_syllabus_topics_for_student(
    student_id,
):
    """
    Return the exact topic list belonging to the
    student's CURRENT syllabus.

    None means:
        no syllabus session could be resolved.

    [] means:
        syllabus exists but contains no topic list.
    """

    try:
        from .views import (
            load_student_snapshot,
            load_state,
        )

        state = (
            load_student_snapshot(
                student_id
            )
            or load_state()
        )

        if not isinstance(
            state,
            dict,
        ):
            return None

        state_student_id = (
            state.get(
                "student_id"
            )
        )

        if (
            state_student_id
            and
            str(
                state_student_id
            )
            != str(
                student_id
            )
        ):
            return None

        has_syllabus = bool(
            state.get(
                "syllabus_text"
            )
            or
            state.get(
                "filename"
            )
        )

        if not has_syllabus:
            return None

        topics = []

        seen = set()

        for raw_topic in state.get(
            "topics",
            [],
        ):

            topic = str(
                raw_topic
            ).strip()

            if not topic:
                continue

            key = topic.casefold()

            if key in seen:
                continue

            seen.add(
                key
            )

            topics.append(
                topic
            )

        return topics

    except Exception as error:

        print(
            "CURRENT SYLLABUS TOPIC LOOKUP ERROR:",
            error,
        )

        return None


def _dashboard_payload(student):

    # CURRENT-SYLLABUS-SCOPED-DASHBOARD
    #
    # Old Java progress must not influence a C syllabus,
    # and C progress must not influence another syllabus.

    allowed_topics = (
        _current_syllabus_topics_for_student(
            student.id
        )
    )


    if allowed_topics is not None:

        if allowed_topics:

            attempts = (
                Attempt.objects.filter(
                    student=student,
                    topic__in=allowed_topics,
                )
            )

            topic_rows = (
                TopicProgress.objects.filter(
                    student=student,
                    topic__in=allowed_topics,
                )
                .order_by(
                    "mastery_score",
                    "-updated_at",
                )
            )

        else:

            attempts = (
                Attempt.objects.none()
            )

            topic_rows = (
                TopicProgress.objects.none()
            )


    else:

        # Legacy fallback only when no syllabus session exists.
        attempts = (
            Attempt.objects.filter(
                student=student
            )
        )

        topic_rows = (
            TopicProgress.objects.filter(
                student=student
            )
            .order_by(
                "mastery_score",
                "-updated_at",
            )
        )


    unique_attempts = _unique_attempt_records(
        attempts
    )

    # Count only attempts that belong to an exact TopicProgress row.
    # This excludes legacy pre-V2 rows such as topic="General" that can
    # otherwise inflate the dashboard counter.
    tracked_topics = {
        str(row.topic or "").strip().casefold()
        for row in topic_rows
    }

    completed_attempts = [
        attempt
        for attempt in unique_attempts
        if (
            str(
                attempt.topic or ""
            ).strip().casefold()
            in tracked_topics
        )
        and (
            attempt.final_score is not None
            or attempt.viva_score is not None
            or attempt.status not in [
                "",
                "Attempted",
            ]
        )
    ]

    questions_attempted = len(
        completed_attempts
    )

    mastered_count = topic_rows.filter(
        status="Mastered"
    ).count()

    average_initial = (
        sum(
            attempt.initial_score
            for attempt in completed_attempts
        )
        / len(completed_attempts)
        if completed_attempts
        else 0
    )

    # Use THIS student's own uploaded syllabus
    # to calculate coverage.
    try:
        from .views import (
            load_student_snapshot,
            load_state,
        )

        state = (
            load_student_snapshot(
                student.id
            )
            or load_state()
        )

        if str(
            state.get(
                "student_id"
            )
        ) != str(
            student.id
        ):
            state = {}

        syllabus_topics = [
            str(
                topic
            ).strip()
            for topic in state.get(
                "topics",
                []
            )
            if str(
                topic
            ).strip()
        ]

    except Exception:
        syllabus_topics = []

    unique_syllabus_topics = list(
        dict.fromkeys(
            syllabus_topics
        )
    )

    tested_topic_names = {
        row.topic
        for row in topic_rows
    }

    if unique_syllabus_topics:
        covered = sum(
            1
            for topic in unique_syllabus_topics
            if topic in tested_topic_names
        )

        coverage = (
            covered
            / len(unique_syllabus_topics)
            * 100
        )

    else:
        # If the source had explicit questions rather than a clean
        # topic list, use tested-topic count as available evidence.
        coverage = (
            100
            if questions_attempted > 0
            else 0
        )

    tested_mastery = (
        topic_rows.aggregate(
            average=Avg("mastery_score")
        )["average"]
        or 0
    )

    # Overall readiness separates "how well tested topics are known"
    # from "how much of the syllabus has actually been covered".
    readiness = round(
        (0.60 * tested_mastery)
        + (0.40 * coverage),
        1,
    )

    weakest_topic = None

    for row in topic_rows:
        if row.status != "Mastered":
            weakest_topic = {
                "topic": row.topic,
                "concept_key":
                    row.concept_key,
                "mastery_score":
                    round(
                        row.mastery_score,
                        1,
                    ),
                "status":
                    row.status,
                "attempts":
                    row.attempts,
                "verification_required":
                    row.verification_required,
                "verification_passed":
                    row.verification_passed,
                "misconception_count":
                    _topic_memory_summary(
                        student,
                        row.topic
                    )["count"],
                "last_misconception":
                    _topic_memory_summary(
                        student,
                        row.topic
                    )["last"],
                "average_hint_level":
                    row.average_hint_level,
            "mastery_breakdown":
                    _topic_mastery_breakdown(
                        student,
                        row.topic,
                    ),
                }
            break

    topics = [
        {
            "topic":
                row.topic,
            "concept_key":
                row.concept_key,
            "attempts":
                row.attempts,
            "mastery_score":
                round(
                    row.mastery_score,
                    1,
                ),
            "status":
                row.status,
            "verification_required":
                row.verification_required,
            "verification_passed":
                row.verification_passed,
            "misconception_count":
                _topic_memory_summary(
                    student,
                    row.topic
                )["count"],
            "last_misconception":
                _topic_memory_summary(
                    student,
                    row.topic
                )["last"],
            "average_hint_level":
                row.average_hint_level,
        "mastery_breakdown":
                    _topic_mastery_breakdown(
                        student,
                        row.topic,
                    ),
                }
        for row in topic_rows
    ]

    recent_attempts = [
        {
            "question":
                attempt.question,
            "topic":
                attempt.topic,
            "concept_key":
                attempt.concept_key,
            "initial_score":
                attempt.initial_score,
            "final_score":
                attempt.final_score,
            "viva_score":
                attempt.viva_score,
            "hint_level":
                attempt.hint_level,
            "verification":
                attempt.verification,
            "status":
                attempt.status,
            "misconception":
                _memory_topic_misconception(
                    attempt.misconception
                ),
            "mastery_score":
                attempt.mastery_score,
        }
        for attempt in list(
            reversed(
                completed_attempts
            )
        )[:5]
    ]

    # Compatibility object for any old UI still expecting
    # weakest_concept.
    weakest_concept = None

    if weakest_topic:
        weakest_concept = {
            "concept_key":
                weakest_topic[
                    "concept_key"
                ],
            "average_score":
                weakest_topic[
                    "mastery_score"
                ],
            "last_misconception":
                weakest_topic[
                    "last_misconception"
                ],
        }

    return {
        "student": {
            "id":
                student.id,
            "name":
                student.name,
        },
        "questions_attempted":
            questions_attempted,
        "mastered":
            mastered_count,
        "average_initial_score":
            round(
                average_initial,
                1,
            ),
        "topic_mastery_average":
            round(
                tested_mastery,
                1,
            ),
        "syllabus_coverage":
            round(
                coverage,
                1,
            ),
        "lab_readiness":
            readiness,
        "weakest_topic":
            weakest_topic,
        "weakest_concept":
            weakest_concept,
        "topics":
            topics,
        "recent_attempts":
            recent_attempts,
    }


@csrf_exempt
def start_student(request):

    if request.method != "POST":
        return JsonResponse(
            {
                "error":
                    "POST required"
            },
            status=405,
        )

    try:
        data = json.loads(
            request.body or "{}"
        )

        name = data.get(
            "name",
            "",
        ).strip()

        mode = data.get(
            "mode",
            "new",
        )

        if not name:
            return JsonResponse(
                {
                    "error":
                        "Student name is required"
                },
                status=400,
            )


        # Import inside the request handler to avoid
        # module circular-import problems.
        from .views import (
            activate_student_session,
            public_student_session,
        )


        if mode == "new":

            student = (
                StudentProfile.objects.create(
                    name=name
                )
            )

            state = (
                activate_student_session(
                    student.id,
                    fresh=True,
                )
            )

            return JsonResponse({
                "student_id":
                    student.id,

                "name":
                    student.name,

                "mode":
                    "new",

                "message":
                    "New learning session created.",

                "session":
                    public_student_session(
                        state
                    ),
            })


        existing = (
            StudentProfile.objects.filter(
                name__iexact=name
            )
            .annotate(
                attempt_count=Count(
                    "attempts"
                )
            )
            .order_by(
                "-attempt_count",
                "-created_at",
            )
            .first()
        )


        if not existing:
            return JsonResponse(
                {
                    "error":
                        "No previous student profile found with this name."
                },
                status=404,
            )


        state = (
            activate_student_session(
                existing.id,
                fresh=False,
            )
        )


        return JsonResponse({
            "student_id":
                existing.id,

            "name":
                existing.name,

            "mode":
                "continue",

            "message":
                "Previous progress and learning session restored.",

            "session":
                public_student_session(
                    state
                ),
        })


    except Exception as error:
        return JsonResponse(
            {
                "error":
                    str(
                        error
                    )
            },
            status=500,
        )


@csrf_exempt
def save_attempt(request):

    if request.method != "POST":
        return JsonResponse(
            {"error": "POST required"},
            status=405,
        )

    try:
        data = json.loads(
            request.body or "{}"
        )

        student = StudentProfile.objects.get(
            id=data.get(
                "student_id"
            )
        )

        topic = (
            data.get(
                "topic",
                "",
            ).strip()
            or "General"
        )

        concept_key = (
            data.get(
                "concept_key",
                "OTHER",
            )
            or "OTHER"
        )

        initial_score = float(
            data.get(
                "initial_score",
                0,
            )
            or 0
        )

        final_score = data.get(
            "final_score"
        )

        viva_score = data.get(
            "viva_score"
        )

        misconception = (
            data.get(
                "misconception",
                "",
            )
            or ""
        ).strip()

        topic_related = bool(
            data.get(
                "topic_related",
                False
            )
        )

        topic_misconception = str(
            data.get(
                "topic_misconception",
                ""
            )
            or ""
        ).strip()

        if topic_related and topic_misconception:
            misconception = (
                "TOPIC_RELATED::"
                + topic_misconception
            )
        else:
            # Keep unrelated coding errors out of persistent topic memory.
            misconception = ""

        status = (
            data.get(
                "status",
                "Attempted",
            )
            or "Attempted"
        )

        question = (
            data.get(
                "question",
                "",
            )
            or ""
        )

        hint_level = int(
            data.get(
                "hint_level",
                0,
            )
            or 0
        )

        hint_level = max(
            0,
            min(
                3,
                hint_level,
            ),
        )

        verification = bool(
            data.get(
                "verification",
                False,
            )
        )

        final_score_value = (
            float(final_score)
            if final_score is not None
            else None
        )

        viva_score_value = (
            float(viva_score)
            if viva_score is not None
            else None
        )

        independent = (
            initial_score >= 80
            and hint_level == 0
        )

        # Idempotent memory save using a normalized question
        # fingerprint. Browser line wrapping or whitespace changes
        # cannot create a fake extra attempt.
        question_key = _question_fingerprint(
            question
        )

        matching = [
            item
            for item in Attempt.objects.filter(
                student=student,
                topic=topic,
            ).order_by(
                "created_at"
            )
            if _question_fingerprint(
                item.question
            ) == question_key
        ]

        attempt = (
            matching[-1]
            if matching
            else None
        )

        if attempt:
            duplicate_ids = [
                item.id
                for item in matching[:-1]
            ]

            if duplicate_ids:
                Attempt.objects.filter(
                    id__in=duplicate_ids
                ).delete()

            attempt.question = question
            attempt.concept_key = concept_key
            attempt.initial_score = initial_score
            attempt.final_score = final_score_value
            attempt.viva_score = viva_score_value
            attempt.misconception = misconception
            attempt.status = status
            attempt.hint_level = hint_level
            attempt.verification = verification
            attempt.independent = independent
            attempt.save()

        else:
            attempt = Attempt.objects.create(
                student=student,
                question=question,
                topic=topic,
                concept_key=concept_key,
                initial_score=initial_score,
                final_score=final_score_value,
                viva_score=viva_score_value,
                misconception=misconception,
                status=status,
                hint_level=hint_level,
                verification=verification,
                independent=independent,
            )

        topic_progress = (
            recalculate_topic_progress(
                student,
                topic,
            )
        )

        _update_broad_concept_progress(
            student,
            concept_key,
        )

        dashboard = _dashboard_payload(
            student
        )

        return JsonResponse({
            "success":
                True,
            "attempt_id":
                attempt.id,
            "topic_progress": {
                "topic":
                    topic_progress.topic,
                "mastery_score":
                    topic_progress.mastery_score,
                "status":
                    topic_progress.status,
                "verification_required":
                    topic_progress.verification_required,
                "verification_passed":
                    topic_progress.verification_passed,
                "misconception_count":
                    topic_progress.misconception_count,
                "average_hint_level":
                    topic_progress.average_hint_level,
            },
            "dashboard":
                dashboard,
        })

    except StudentProfile.DoesNotExist:
        return JsonResponse(
            {"error": "Student not found"},
            status=404,
        )

    except Exception as error:
        return JsonResponse(
            {"error": str(error)},
            status=500,
        )


def progress_dashboard(request):

    student_id = request.GET.get(
        "student_id"
    )

    if not student_id:
        return JsonResponse(
            {
                "error":
                    "student_id required"
            },
            status=400,
        )

    try:
        student = StudentProfile.objects.get(
            id=student_id
        )

        return JsonResponse(
            _dashboard_payload(
                student
            )
        )

    except StudentProfile.DoesNotExist:
        return JsonResponse(
            {"error": "Student not found"},
            status=404,
        )
