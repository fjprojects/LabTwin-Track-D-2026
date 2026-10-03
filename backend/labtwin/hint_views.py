import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from crewai import Agent, Task, Crew, Process
from .ai_retry import kickoff_with_retry, AI_UNAVAILABLE_MESSAGE
from .response_history import record_response

from .views import (
    llm,
    clean_json_output,
    get_current_question,
)


progressive_hint_agent = Agent(
    role="Progressive Programming Hint Tutor",
    goal=(
        "Give the next useful hint without revealing "
        "the complete solution."
    ),
    backstory=(
        "You teach programming step by step and stay "
        "strictly in the current programming language."
    ),
    llm=llm,
    verbose=False,
)


def _detect_language(
    explicit_language,
    problem,
):

    explicit = str(
        explicit_language or ""
    ).strip()

    if explicit:
        return explicit

    text = str(
        problem or ""
    ).lower()

    if (
        "c program" in text
        or "gcc" in text
        or "#include" in text
    ):
        return "C"

    if (
        "java" in text
        or "public class main" in text
    ):
        return "Java"

    if "python" in text:
        return "Python"

    return "Python"


@csrf_exempt
@record_response("hint")
def progressive_hint(request):

    if request.method != "POST":

        return JsonResponse(
            {"error": "POST required"},
            status=405
        )

    try:

        data = json.loads(
            request.body or "{}"
        )

        question = None

        question_id = data.get(
            "question_id"
        )

        if question_id:

            try:
                question = (
                    get_current_question(
                        question_id,
                        student_id=data.get("student_id"),
                    )
                )
            except Exception:
                question = None

        question = question or {}

        problem = str(
            question.get("problem")
            or data.get("problem")
            or ""
        ).strip()

        topic = str(
            question.get("topic")
            or data.get("topic")
            or data.get("concept_key")
            or "current topic"
        ).strip()

        language = _detect_language(
            question.get("language")
            or data.get("language"),
            problem,
        )

        misconception = str(
            data.get("misconception")
            or ""
        ).strip()

        previous_hint = str(
            data.get("current_hint")
            or data.get("previous_hint")
            or data.get("hint")
            or ""
        ).strip()


        raw_level = (
            data.get("next_level")
            or data.get("hint_level")
            or data.get("level")
            or 2
        )

        try:
            level = int(
                raw_level
            )
        except Exception:
            level = 2

        level = max(
            2,
            min(
                3,
                level
            )
        )


        if level == 2:

            fallback = (
                "Focus on the exact failing case described by "
                "the diagnosis: "
                + (
                    misconception
                    or "trace the failing test case carefully"
                )
                + ". Compare that case with your current "
                + language
                + " initialization and update logic."
            )

        else:

            fallback = (
                "Trace the smallest input that reproduces the "
                "mistake, identify the exact initialization or "
                "condition responsible, and change only that "
                "part of your "
                + language
                + " solution."
            )


        task = Task(
            description=f"""
Generate progressive hint level {level} of 3.

PROGRAMMING LANGUAGE:
{language}

EXACT TOPIC:
{topic}

PROBLEM:
{problem}

MISCONCEPTION:
{misconception}

PREVIOUS HINT:
{previous_hint}

STRICT RULES:

1. Stay ONLY in {language}.
2. Never mention or switch to another programming language.
3. Hint {level} must be more specific than the previous hint.
4. Do NOT reveal the full corrected program.
5. Directly address the current problem and misconception.
6. Keep the hint concise.

Return ONLY valid JSON:

{{
    "hint": "Next progressive hint"
}}
""",
            expected_output="Valid JSON",
            agent=progressive_hint_agent
        )


        try:

            crew = Crew(
                agents=[
                    progressive_hint_agent
                ],
                tasks=[task],
                process=Process.sequential,
                verbose=False,
            )

            result = clean_json_output(
                kickoff_with_retry(crew, label="hint_views.py").raw
            )

            hint = str(
                result.get(
                    "hint",
                    ""
                )
            ).strip()

        except Exception as ai_error:

            print(
                "PROGRESSIVE HINT AI ERROR - FALLBACK:",
                ai_error
            )

            hint = ""


        if not hint:
            hint = fallback


        # ----------------------------------------------------
        # DIAGNOSIS-LOCKED PROGRESSIVE HINTS
        #
        # Prevent the next hint from inventing a different bug.
        # Each level becomes more actionable while remaining
        # focused on the exact misconception already detected.
        # ----------------------------------------------------

        if misconception:

            if level == 2:

                hint = (
                    "Focus only on the diagnosed mistake: "
                    + misconception
                    + " Trace the exact statement or loop "
                    + "responsible and compare it with what "
                    + "the problem requires."
                )

            else:

                hint = (
                    "Correct only the logic identified in "
                    + "this diagnosis: "
                    + misconception
                    + " Then dry-run the smallest failing "
                    + "input and confirm that every required "
                    + "value or condition is handled."
                )


        # Prevent cross-language leakage.

        if language.lower() == "c":

            bad_words = [
                "java",
                "python",
                "javascript",
                "c++"
            ]

            if any(
                word in hint.lower()
                for word in bad_words
            ):
                hint = fallback


        return JsonResponse({
            "success": True,
            "hint": hint,
            "level": level,
            "hint_level": level,
        })


    except Exception as error:

        print(
            "PROGRESSIVE HINT ERROR:",
            type(error).__name__
        )

        return JsonResponse(
            {
                "error":
                    AI_UNAVAILABLE_MESSAGE
            },
            status=500
        )
