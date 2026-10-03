import json
import uuid
import re
import time
import threading

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from crewai import Agent, Task, Crew, Process
from .ai_retry import kickoff_with_retry

from .models import StudentProfile, ConceptProgress, TopicProgress, Attempt

from .views import (
    load_state,
    load_student_snapshot,
    save_state,
    llm,
    clean_json_output,
    generate_tests_for_question,
    validate_generated_question_alignment,
)


adaptive_agent = Agent(
    role="Adaptive Lab Question Planner",
    goal=(
        "Select and generate the best next programming lab question "
        "based on the uploaded syllabus, programming language, and "
        "student weaknesses."
    ),
    backstory=(
        "You are a university programming lab instructor. "
        "You never convert language-specific concepts into another language. "
        "C concepts remain C, Java concepts remain Java, and Python concepts remain Python."
    ),
    llm=llm,
    verbose=False
)


# Prevent two Django requests from entering the adaptive
# CrewAI generator at exactly the same time.
_ADAPTIVE_AI_LOCK = threading.Lock()


def _trusted_topic_memory(student_id, topic):
    """
    Return only V4-classified topic-related misconceptions.
    Legacy unclassified mistakes are not trusted as conceptual evidence.
    """
    prefix = "TOPIC_RELATED::"

    values = []

    for attempt in Attempt.objects.filter(
        student_id=student_id,
        topic=topic,
    ).order_by("created_at"):
        text = str(
            attempt.misconception or ""
        ).strip()

        if text.startswith(prefix):
            cleaned = text[len(prefix):].strip()

            if cleaned:
                values.append(cleaned)

    return {
        "count": len(values),
        "last": values[-1] if values else "",
    }



def _adaptive_current_syllabus_topics(
    student_id,
):
    """
    Current allowed syllabus topics for adaptive
    question generation.

    This prevents learning memory from another
    syllabus from controlling the next question.
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

            key = (
                topic.casefold()
            )

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
            "ADAPTIVE SYLLABUS LOOKUP ERROR:",
            error,
        )

        return None


def get_weakest_concept(student_id):

    if not student_id:
        return None

    try:
        rows = TopicProgress.objects.filter(
            student_id=student_id
        )

        # SYLLABUS-SCOPED-WEAKNESS
        allowed_topics = (
            _adaptive_current_syllabus_topics(
                student_id
            )
        )

        if allowed_topics is not None:

            if not allowed_topics:
                return None

            rows = rows.filter(
                topic__in=allowed_topics
            )

        # 1. Highest priority:
        # exact topics that explicitly require verification.
        verification_rows = rows.filter(
            verification_required=True,
            verification_passed=False
        ).order_by(
            "mastery_score",
            "-updated_at"
        )

        row = verification_rows.first()

        if row:
            return {
                "concept_key":
                    row.concept_key,
                "exact_topic":
                    row.topic,
                "mastery_score":
                    row.mastery_score,
                "status":
                    row.status,
                "last_misconception":
                    _trusted_topic_memory(
                        student_id,
                        row.topic
                    )["last"],
                "misconception_count":
                    _trusted_topic_memory(
                        student_id,
                        row.topic
                    )["count"],
                "average_hint_level":
                    row.average_hint_level,
                "reason":
                    "verification"
            }

        # 2. Then target the weakest exact topic that is not mastered.
        weak_row = (
            rows.exclude(
                status="Mastered"
            )
            .order_by(
                "mastery_score",
                "-updated_at"
            )
            .first()
        )

        if weak_row:
            return {
                "concept_key":
                    weak_row.concept_key,
                "exact_topic":
                    weak_row.topic,
                "mastery_score":
                    weak_row.mastery_score,
                "status":
                    weak_row.status,
                "last_misconception":
                    _trusted_topic_memory(
                        student_id,
                        weak_row.topic
                    )["last"],
                "misconception_count":
                    _trusted_topic_memory(
                        student_id,
                        weak_row.topic
                    )["count"],
                "average_hint_level":
                    weak_row.average_hint_level,
                "reason":
                    "weakness"
            }

        return None

    except Exception as error:

        print(
            "Adaptive memory lookup error:",
            error
        )

        return None



# ============================================================
# LOCAL RATE-LIMIT FALLBACK QUESTION ENGINE
# ============================================================

def build_local_fallback_question(
    topics,
    history,
    language,
    weak_concept=None,
):
    """
    Deterministic emergency question generator.

    Used only when the external AI provider
    cannot accept the request.

    It keeps the student moving instead of
    stopping the entire learning session.
    """

    required_topic = ""

    if weak_concept:
        required_topic = str(
            weak_concept.get(
                "exact_topic",
                "",
            )
            or ""
        ).strip()


    # FALLBACK-SYLLABUS-GUARD
    #
    # Example prevented:
    # required_topic = "Java Program Structure"
    # language       = "C"
    # current topics = ["Pointers", ...]
    #
    # That old Java topic must be discarded.

    allowed_topic_map = {
        str(
            topic
        ).strip().casefold():
            str(
                topic
            ).strip()

        for topic in topics

        if str(
            topic
        ).strip()
    }


    if required_topic:

        required_key = (
            required_topic
            .casefold()
        )

        if (
            required_key
            not in allowed_topic_map
        ):

            print(
                "DISCARDING OUT-OF-SYLLABUS WEAK TOPIC:",
                required_topic,
            )

            required_topic = ""


    if not required_topic:

        used_topics = {
            str(
                item.get(
                    "topic",
                    "",
                )
            ).strip().casefold()
            for item in history
            if isinstance(
                item,
                dict,
            )
        }

        for candidate in topics:

            candidate_text = str(
                candidate
            ).strip()

            if (
                candidate_text
                and
                candidate_text.casefold()
                not in used_topics
            ):
                required_topic = (
                    candidate_text
                )

                break


    if (
        not required_topic
        and topics
    ):
        required_topic = str(
            topics[0]
        ).strip()


    if not required_topic:
        required_topic = (
            "Programming Fundamentals"
        )


    topic_lower = (
        required_topic
        .casefold()
    )

    language_lower = (
        str(
            language
        )
        .casefold()
    )


    # ========================================================
    # JAVA
    # ========================================================

    if language_lower == "java":

        if (
            "program structure"
            in topic_lower
            or
            "introduction to java"
            in topic_lower
            or
            "main method"
            in topic_lower
        ):

            return {
                "topic":
                    required_topic,

                "concept_key":
                    "OOP",

                "adaptation_reason":
                    (
                        "AI capacity was temporarily busy, "
                        "so LabTwin selected a built-in "
                        "syllabus-aligned Java verification task."
                    ),

                "problem":
                    (
                        "Write a Java program using "
                        "public class Main and "
                        "public static void main(String[] args). "
                        "Read one line of text and print exactly: "
                        "Hello, <input>!"
                    ),

                "tests": [
                    {
                        "input":
                            "Francis\n",

                        "expected":
                            "Hello, Francis!",
                    },

                    {
                        "input":
                            "Java\n",

                        "expected":
                            "Hello, Java!",
                    },

                    {
                        "input":
                            "LabTwin\n",

                        "expected":
                            "Hello, LabTwin!",
                    },
                ],
            }


        if "token" in topic_lower:

            return {
                "topic":
                    required_topic,

                "concept_key":
                    "ARITHMETIC_OPERATORS",

                "adaptation_reason":
                    (
                        "Built-in Java syllabus task "
                        "used while AI capacity is busy."
                    ),

                "problem":
                    (
                        "Write a Java program using "
                        "public class Main. Read two integers "
                        "a and b and print their sum. "
                        "Use valid Java identifiers, literals, "
                        "operators and statements."
                    ),

                "tests": [
                    {
                        "input":
                            "5 7\n",

                        "expected":
                            "12",
                    },

                    {
                        "input":
                            "-3 8\n",

                        "expected":
                            "5",
                    },

                    {
                        "input":
                            "100 25\n",

                        "expected":
                            "125",
                    },
                ],
            }


        return {
            "topic":
                required_topic,

            "concept_key":
                "OTHER",

            "adaptation_reason":
                (
                    "Built-in Java fallback question "
                    "used because the AI provider "
                    "temporarily reached its token limit."
                ),

            "problem":
                (
                    "Write a Java program using "
                    "public class Main that reads "
                    "one integer and prints its square."
                ),

            "tests": [
                {
                    "input":
                        "5\n",

                    "expected":
                        "25",
                },

                {
                    "input":
                        "-4\n",

                    "expected":
                        "16",
                },

                {
                    "input":
                        "12\n",

                    "expected":
                        "144",
                },
            ],
        }


    # ========================================================
    # C - FUNCTION POINTER
    # ========================================================

    if (
        language_lower == "c"
        and
        (
            "pointer to function"
            in topic_lower
            or
            "function pointer"
            in topic_lower
        )
    ):

        return {
            "topic":
                required_topic,

            "concept_key":
                "POINTERS",

            "adaptation_reason":
                (
                    "Built-in C function-pointer "
                    "verification task used while "
                    "AI capacity is unavailable."
                ),

            "problem":
                (
                    "Write a C program that defines "
                    "two functions add(int,int) and "
                    "subtract(int,int). "
                    "Read three integers: a, b and choice. "
                    "Use a function pointer. "
                    "If choice is 1 call add through "
                    "the function pointer; otherwise "
                    "call subtract through the pointer. "
                    "Print only the result."
                ),

            "tests": [
                {
                    "input":
                        "8 3 1\n",

                    "expected":
                        "11",
                },

                {
                    "input":
                        "8 3 2\n",

                    "expected":
                        "5",
                },

                {
                    "input":
                        "-2 5 1\n",

                    "expected":
                        "3",
                },
            ],
        }


    # ========================================================
    # C - POINTER TO POINTER
    # ========================================================

    if (
        language_lower == "c"
        and
        "pointer to pointer"
        in topic_lower
    ):

        return {
            "topic":
                required_topic,

            "concept_key":
                "POINTERS",

            "adaptation_reason":
                (
                    "Built-in pointer-to-pointer "
                    "verification task used because "
                    "the AI service is temporarily busy."
                ),

            "problem":
                (
                    "Write a C program that reads "
                    "one integer x. Create an int pointer "
                    "pointing to x and an int double pointer "
                    "pointing to that pointer. "
                    "Using the double pointer, add 5 to x "
                    "and print the final value."
                ),

            "tests": [
                {
                    "input":
                        "10\n",

                    "expected":
                        "15",
                },

                {
                    "input":
                        "-5\n",

                    "expected":
                        "0",
                },

                {
                    "input":
                        "100\n",

                    "expected":
                        "105",
                },
            ],
        }


    # ========================================================
    # C - POINTER TO STRUCTURE
    # ========================================================

    if (
        language_lower == "c"
        and
        (
            "pointer to structure"
            in topic_lower
            or
            "structure pointer"
            in topic_lower
        )
    ):

        return {
            "topic":
                required_topic,

            "concept_key":
                "STRUCTURES",

            "adaptation_reason":
                (
                    "Built-in structure-pointer task "
                    "used while Groq capacity is busy."
                ),

            "problem":
                (
                    "Define a struct Student containing "
                    "integer id and integer mark. "
                    "Read id and mark. "
                    "Create a pointer to the structure "
                    "and print the values using the -> operator "
                    "in the format: id mark"
                ),

            "tests": [
                {
                    "input":
                        "1 90\n",

                    "expected":
                        "1 90",
                },

                {
                    "input":
                        "25 76\n",

                    "expected":
                        "25 76",
                },

                {
                    "input":
                        "100 100\n",

                    "expected":
                        "100 100",
                },
            ],
        }


    # ========================================================
    # C - DYNAMIC MEMORY
    # ========================================================

    if (
        language_lower == "c"
        and
        (
            "dynamic memory"
            in topic_lower
            or
            "malloc"
            in topic_lower
            or
            "calloc"
            in topic_lower
        )
    ):

        return {
            "topic":
                required_topic,

            "concept_key":
                "DYNAMIC_MEMORY",

            "adaptation_reason":
                (
                    "Built-in dynamic-memory task "
                    "used because external AI capacity "
                    "is temporarily unavailable."
                ),

            "problem":
                (
                    "Write a C program that reads n, "
                    "dynamically allocates memory for n integers "
                    "using malloc or calloc, reads the integers, "
                    "prints their sum, and frees the memory."
                ),

            "tests": [
                {
                    "input":
                        "4\n1 2 3 4\n",

                    "expected":
                        "10",
                },

                {
                    "input":
                        "3\n-2 5 7\n",

                    "expected":
                        "10",
                },

                {
                    "input":
                        "1\n99\n",

                    "expected":
                        "99",
                },
            ],
        }


    # ========================================================
    # C - FILE HANDLING
    # ========================================================

    if (
        language_lower == "c"
        and
        (
            "file"
            in topic_lower
            or
            "fopen"
            in topic_lower
            or
            "fclose"
            in topic_lower
            or
            "fread"
            in topic_lower
            or
            "fwrite"
            in topic_lower
        )
    ):

        return {
            "topic":
                required_topic,

            "concept_key":
                "FILES",

            "adaptation_reason":
                (
                    "Built-in file-handling task "
                    "used while AI capacity is busy."
                ),

            "problem":
                (
                    "Write a C program that reads one word "
                    "from standard input. Open a file named "
                    "labtwin_temp.txt for writing, write the word, "
                    "close the file, reopen it for reading, "
                    "read the word back, print it, "
                    "and close the file."
                ),

            "tests": [
                {
                    "input":
                        "hello\n",

                    "expected":
                        "hello",
                },

                {
                    "input":
                        "LabTwin\n",

                    "expected":
                        "LabTwin",
                },

                {
                    "input":
                        "pointer\n",

                    "expected":
                        "pointer",
                },
            ],
        }


    # ========================================================
    # C - STRING USING POINTERS
    # ========================================================

    if (
        language_lower == "c"
        and
        (
            "string"
            in topic_lower
            and
            "pointer"
            in topic_lower
        )
    ):

        return {
            "topic":
                required_topic,

            "concept_key":
                "POINTERS",

            "adaptation_reason":
                (
                    "Built-in string-pointer task "
                    "used during temporary AI capacity limits."
                ),

            "problem":
                (
                    "Write a C program that reads one word. "
                    "Using a char pointer, count the number "
                    "of characters without calling strlen. "
                    "Print only the length."
                ),

            "tests": [
                {
                    "input":
                        "hello\n",

                    "expected":
                        "5",
                },

                {
                    "input":
                        "pointer\n",

                    "expected":
                        "7",
                },

                {
                    "input":
                        "LabTwin\n",

                    "expected":
                        "7",
                },
            ],
        }


    # ========================================================
    # C - GENERAL POINTER / ARRAY POINTER
    # ========================================================

    if (
        language_lower == "c"
    ):

        return {
            "topic":
                required_topic,

            "concept_key":
                "POINTERS",

            "adaptation_reason":
                (
                    "Built-in C pointer question "
                    "used because Groq reached its "
                    "temporary token-per-minute limit."
                ),

            "problem":
                (
                    "Write a C program that reads n "
                    "followed by n integers. "
                    "Use a pointer to access the array elements "
                    "and calculate their sum. "
                    "Print only the sum."
                ),

            "tests": [
                {
                    "input":
                        "4\n1 2 3 4\n",

                    "expected":
                        "10",
                },

                {
                    "input":
                        "3\n10 -5 2\n",

                    "expected":
                        "7",
                },

                {
                    "input":
                        "5\n1 1 1 1 1\n",

                    "expected":
                        "5",
                },
            ],
        }


    # ========================================================
    # PYTHON
    # ========================================================

    return {
        "topic":
            required_topic,

        "concept_key":
            "OTHER",

        "adaptation_reason":
            (
                "Built-in syllabus question used "
                "because external AI capacity "
                "is temporarily unavailable."
            ),

        "problem":
            (
                "Write a Python program that reads "
                "one integer and prints its square."
            ),

        "tests": [
            {
                "input":
                    "5\n",

                "expected":
                    "25",
            },

            {
                "input":
                    "-3\n",

                "expected":
                    "9",
            },

            {
                "input":
                    "12\n",

                "expected":
                    "144",
            },
        ],
    }


def _generate_adaptive_question_unchecked(
    topics,
    history,
    language,
    weak_concept=None
):

    previous_questions = [

        item.get("problem", "")

        for item in history[-4:]

    ]


    weakness_instruction = ""

    if weak_concept:

        exact_topic = weak_concept.get(
            "exact_topic"
        )

        concept_key = weak_concept.get(
            "concept_key",
            "OTHER"
        )

        reason = weak_concept.get(
            "reason",
            "weakness"
        )

        misconception = weak_concept.get(
            "last_misconception",
            ""
        )

        misconception_count = weak_concept.get(
            "misconception_count",
            0
        )

        mastery_score = weak_concept.get(
            "mastery_score",
            0
        )

        if (
            exact_topic
            and reason == "verification"
        ):

            weakness_instruction = f"""
THIS IS A REQUIRED INDEPENDENT VERIFICATION QUESTION.

EXACT REQUIRED TOPIC:
{exact_topic}

BROAD CONCEPT:
{concept_key}

CURRENT TOPIC MASTERY:
{mastery_score}%

PREVIOUS MISCONCEPTION:
{misconception}

MISCONCEPTION OCCURRENCES:
{misconception_count}

NON-NEGOTIABLE RULES:

1. The generated question MUST directly test "{exact_topic}".
2. Do NOT switch to another syllabus topic.
3. Do NOT merely reword the previous problem.
4. Use a different task/context/input pattern so this is independent evidence.
5. Do not include a hint or solution inside the problem statement.
"""

        elif exact_topic:

            weakness_instruction = f"""
TARGET THE STUDENT'S EXACT WEAK TOPIC:

{exact_topic}

BROAD CONCEPT:
{concept_key}

CURRENT TOPIC MASTERY:
{mastery_score}%

PREVIOUS MISCONCEPTION:
{misconception}

Generate a new problem that directly reinforces "{exact_topic}".
Do not switch to a sibling topic and do not repeat a previous problem.
"""

        else:

            weakness_instruction = f"""
TARGET THIS WEAK CONCEPT:

{concept_key}

PREVIOUS MISCONCEPTION:
{misconception}

Generate a new question inside the uploaded syllabus that directly
reinforces this weakness without repeating a previous question.
"""


    if language == "C":

        language_rules = """
THIS IS A C PROGRAMMING SYLLABUS.

Generate a genuine C programming problem.

Important examples:

- Pointer to Function means actual C function pointers,
  such as int (*ptr)(int, int).

- Pointer to Pointer means actual ** pointer usage.

- Pointer to Structure means struct pointers and -> operator.

- Dynamic Memory Allocation means malloc, calloc,
  realloc or free where appropriate.

- File Handling means actual C FILE pointers and
  fopen/fclose/fread/fwrite/etc.

NEVER convert these concepts into Python dictionaries,
Python functions, Java objects, or another language.

The student must write C code.
"""

    elif language == "Java":

        language_rules = """
THIS IS A JAVA PROGRAMMING SYLLABUS.

Generate genuine Java questions.

The submitted program should use:

public class Main

and:

public static void main(String[] args)

Do not translate Java-specific concepts into Python or C.
"""

    else:

        language_rules = """
THIS IS A PYTHON PROGRAMMING SYLLABUS.

Generate genuine Python questions using standard Python.
"""


    task = Task(
        description=f"""
Generate ONE NEW adaptive programming lab question.

PROGRAMMING LANGUAGE:

{language}

EXACT SELECTED SYLLABUS TOPIC:

{topics[0] if topics else ""}

THIS IS THE ONLY ALLOWED TOPIC FOR THIS QUESTION.

The programming problem must primarily test this exact topic.
Do not use another syllabus topic as the main skill.

SELECTED-TOPIC NECESSITY RULE:
The selected topic must be REQUIRED to solve the problem, not optional.

For example:
- Arrays: explicitly require the student to STORE values in an array
  and process them using array indexing. Do not generate a problem
  that can be solved simply by reading one value at a time.
- Strings: explicitly require string/character-array processing.
- Functions: explicitly require defining and calling a function.
- Pointers: explicitly require pointer usage.
- Bitwise Operators: explicitly require bitwise operators.

For Arrays, prefer direct introductory lab operations such as:
sum using stored array elements, maximum/minimum, reverse,
search, counting, or indexed traversal.

IMPORTANT SYLLABUS-SCOPE RULE:
Do NOT introduce an algorithm, technique, data structure, or advanced concept
that is not explicitly present in the uploaded syllabus.

For broad introductory topics, generate a direct college-lab exercise.

Examples:
- Arrays: sum, minimum/maximum, reverse, count, search, direct traversal.
  Do NOT require Kadane's algorithm, advanced sorting, dynamic programming,
  sliding window, prefix sums, or another unstated algorithm.
- Strings: direct character/string processing.
- Functions: require defining and calling functions.
- Pointers: require genuine pointer access or pointer arithmetic.

PREVIOUS QUESTIONS:

{json.dumps(previous_questions, indent=2)}

{weakness_instruction}

{language_rules}

STRICT RULES:

1. Stay strictly inside the uploaded syllabus.
2. Use exactly the detected programming language: {language}.
3. The question must DIRECTLY test "{topics[0] if topics else ""}".
3A. "{topics[0] if topics else ""}" must be the PRIMARY SKILL required to solve the problem, not merely something that appears incidentally in the code.
3B. The returned "topic" field MUST exactly equal "{topics[0] if topics else ""}".
3B. Example: Java Program Structure must test class Main, main method/entry point/imports/program layout. Do NOT label a conditionals, switch, loops, arrays, or short-circuiting problem as Java Program Structure.
4. Never create a "{language} adaptation" of a concept from
   another programming language.
5. Never replace a language-specific concept with a loosely
   related concept.
6. Do not repeat previous questions.
7. Keep the question appropriate for a college programming lab.
8. Generate exactly THREE deterministic hidden test cases.
9. Hidden tests must match the exact stated question.
10. Avoid file-based questions for automatic execution unless
    deterministic stdin/stdout testing is possible.

concept_key must be one of:

ARITHMETIC_OPERATORS
STRINGS
CONDITIONALS
LOOPS
ARRAYS
FUNCTIONS
OOP
POINTERS
STRUCTURES
FILES
DYNAMIC_MEMORY
OTHER

Return ONLY valid JSON:

{{
    "topic": "Exact syllabus topic",
    "concept_key": "POINTERS",
    "adaptation_reason": "Why this question was selected",
    "problem": "Programming problem in the detected language",
    "tests": [
        {{
            "input": "stdin input",
            "expected": "exact stdout"
        }},
        {{
            "input": "stdin input",
            "expected": "exact stdout"
        }},
        {{
            "input": "stdin input",
            "expected": "exact stdout"
        }}
    ]
}}
""",
        expected_output=(
            "One language-correct adaptive programming question"
        ),
        agent=adaptive_agent
    )
    # IMPORTANT:
    # Do not create one Crew and reuse it across retries.
    # Every attempt below gets a fresh Agent, Task and Crew.

    # AI providers occasionally return malformed JSON or rate-limit errors.
    # Retry safely, but WAIT when the provider tells us to slow down.
    last_error = None

    for attempt_number in range(1, 4):

        try:
            # ------------------------------------------------
            # FRESH CREW PER RETRY
            # ------------------------------------------------

            lock_acquired = (
                _ADAPTIVE_AI_LOCK.acquire(
                    timeout=120
                )
            )

            if not lock_acquired:
                raise RuntimeError(
                    "AI question generator is busy. "
                    "Please try again in a few seconds."
                )

            try:

                # Never reuse the old Agent executor.
                fresh_agent = Agent(
                    role=(
                        "Adaptive Lab Question Planner"
                    ),

                    goal=(
                        "Select and generate the best next "
                        "programming lab question based on "
                        "the uploaded syllabus, programming "
                        "language, and student weaknesses."
                    ),

                    backstory=(
                        "You are a university programming lab "
                        "instructor. You never convert "
                        "language-specific concepts into "
                        "another language. C concepts remain C, "
                        "Java concepts remain Java, and Python "
                        "concepts remain Python."
                    ),

                    llm=llm,
                    verbose=False,
                )


                # Fresh Task.
                # Reuse only the prompt TEXT from the template task,
                # not the previous execution object.
                fresh_task = Task(
                    description=
                        task.description,

                    expected_output=(
                        "One language-correct adaptive "
                        "programming question"
                    ),

                    agent=
                        fresh_agent,
                )


                # Fresh Crew / executor.
                fresh_crew = Crew(
                    agents=[
                        fresh_agent
                    ],

                    tasks=[
                        fresh_task
                    ],

                    process=
                        Process.sequential,

                    verbose=False,
                )


                print(
                    "ADAPTIVE AI: fresh CrewAI executor "
                    f"created for attempt {attempt_number}"
                )


                result = (
                    kickoff_with_retry(fresh_crew, label="adaptive_views.py")
                )


            finally:

                _ADAPTIVE_AI_LOCK.release()

            generated = clean_json_output(
                result.raw
            )

            if not isinstance(generated, dict):
                raise ValueError(
                    "Generated question was not a JSON object."
                )

            topic = str(generated.get("topic", "")).strip()
            problem = str(generated.get("problem", "")).strip()
            tests = generated.get("tests", [])

            if not topic:
                raise ValueError(
                    "Generated question has no topic."
                )

            if not problem:
                raise ValueError(
                    "Generated question has no problem statement."
                )

            if not isinstance(tests, list) or len(tests) != 3:
                raise ValueError(
                    "Exactly 3 hidden tests were not generated."
                )

            for index, test in enumerate(tests, start=1):
                if not isinstance(test, dict):
                    raise ValueError(
                        f"Hidden test {index} is invalid."
                    )

                if "input" not in test or "expected" not in test:
                    raise ValueError(
                        f"Hidden test {index} is incomplete."
                    )

            required_topic = None
            if weak_concept:
                required_topic = weak_concept.get(
                    "exact_topic"
                )

            alignment_error = validate_generated_question_alignment(
                generated,
                topics,
                required_topic=required_topic,
            )

            if alignment_error:
                raise ValueError(
                    "TOPIC ALIGNMENT REJECTED: " + alignment_error
                )

            if attempt_number > 1:
                print(
                    "ADAPTIVE QUESTION RECOVERED ON ATTEMPT",
                    attempt_number
                )

            return generated

        except Exception as error:
            last_error = error
            message = str(error)
            lowered = message.lower()

            print(
                f"ADAPTIVE QUESTION AI ATTEMPT {attempt_number} FAILED:",
                error
            )

            if attempt_number >= 3:
                break

            is_executor_busy = (
                "executor is already running"
                in lowered
                or
                "cannot invoke the same executor"
                in lowered
            )

            if is_executor_busy:

                print(
                    "CREWAI EXECUTOR BUSY: "
                    "discarding this executor and "
                    "creating a fresh one."
                )

                if attempt_number < 3:
                    time.sleep(2.0)
                    continue


            is_rate_limit = (
                "rate limit" in lowered
                or "rate_limit" in lowered
                or "rate_limit_exceeded" in lowered
                or "tokens per minute" in lowered
            )

            if is_rate_limit:

                print(
                    "GROQ TPM LIMIT REACHED."
                )

                print(
                    "LABTWIN HYBRID MODE: "
                    "switching immediately to "
                    "local syllabus question."
                )

                return (
                    build_local_fallback_question(
                        topics,
                        history,
                        language,
                        weak_concept,
                    )
                )

            else:
                time.sleep(1.0)

    print(
        "AI question generation unavailable after retries:",
        last_error,
    )

    print(
        "LABTWIN FALLBACK: continuing with local question."
    )

    return build_local_fallback_question(
        topics,
        history,
        language,
        weak_concept,
    )



def _sanitize_state_for_current_syllabus(
    state,
):
    """
    Remove questions/history that do not belong
    to the currently active syllabus.

    This is the final protection against cases like:

        language = C
        syllabus = Pointers
        old topic = Java Program Structure
    """

    if not isinstance(
        state,
        dict,
    ):
        return state

    if state.get(
        "mode"
    ) == "existing_questions":
        return state


    topics = [
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


    allowed = {
        topic.casefold():
            topic

        for topic in topics
    }


    if not allowed:

        state[
            "history"
        ] = []

        state[
            "current_question"
        ] = None

        return state


    # --------------------------------------------------------
    # CLEAN HISTORY
    # --------------------------------------------------------

    clean_history = []

    for item in state.get(
        "history",
        []
    ):

        if not isinstance(
            item,
            dict,
        ):
            continue

        topic = str(
            item.get(
                "topic",
                ""
            )
        ).strip()

        key = (
            topic.casefold()
        )

        if key not in allowed:

            print(
                "REMOVING CROSS-SYLLABUS HISTORY:",
                topic,
            )

            continue


        # Canonical syllabus spelling.
        item[
            "topic"
        ] = allowed[
            key
        ]

        clean_history.append(
            item
        )


    state[
        "history"
    ] = clean_history


    # --------------------------------------------------------
    # CLEAN CURRENT QUESTION
    # --------------------------------------------------------

    question = state.get(
        "current_question"
    )


    if isinstance(
        question,
        dict,
    ):

        question_topic = str(
            question.get(
                "topic",
                ""
            )
        ).strip()

        question_language = str(
            question.get(
                "language",
                ""
            )
        ).strip()

        state_language = str(
            state.get(
                "language",
                ""
            )
        ).strip()


        topic_valid = (
            question_topic.casefold()
            in allowed
        )


        language_valid = (
            not question_language
            or
            not state_language
            or
            question_language.casefold()
            ==
            state_language.casefold()
        )


        if not (
            topic_valid
            and
            language_valid
        ):

            print(
                "REMOVING INVALID CURRENT QUESTION:",
                question_topic,
                "/",
                question_language,
            )

            state[
                "current_question"
            ] = None

        else:

            question[
                "topic"
            ] = allowed[
                question_topic.casefold()
            ]


    return state




# LABTWIN_SEMANTIC_TOPIC_RECONCILIATION_V1
# ============================================================
# EXACT SYLLABUS TOPIC SEMANTIC RECONCILIATION
# ============================================================

def _normalize_topic_name(value):

    return " ".join(
        str(value or "")
        .strip()
        .lower()
        .replace("-", " ")
        .split()
    )


def _find_exact_syllabus_topic(
    syllabus_topics,
    *candidate_names
):

    wanted = {
        _normalize_topic_name(name)
        for name in candidate_names
    }

    for topic in syllabus_topics:

        if (
            _normalize_topic_name(topic)
            in wanted
        ):
            return topic

    return None


def _find_topic_containing(
    syllabus_topics,
    *parts
):

    required = [
        _normalize_topic_name(part)
        for part in parts
    ]

    for topic in syllabus_topics:

        normalized = (
            _normalize_topic_name(topic)
        )

        if all(
            part in normalized
            for part in required
        ):
            return topic

    return None


def _infer_semantic_topic(
    problem,
    syllabus_topics,
    selected_topic,
    language
):

    if str(language).strip().lower() != "c":
        return None

    text = str(
        problem or ""
    ).lower()

    topics = list(
        syllabus_topics or []
    )

    # --------------------------------------------------------
    # MOST SPECIFIC POINTER TOPICS FIRST
    # --------------------------------------------------------

    if (
        "function pointer" in text
        or "pointer to function" in text
    ):

        match = (
            _find_exact_syllabus_topic(
                topics,
                "Pointer to Function",
                "Function Pointers",
                "Function Pointer"
            )
            or
            _find_topic_containing(
                topics,
                "function",
                "pointer"
            )
        )

        if match:
            return match


    if (
        "pointer to pointer" in text
        or "double pointer" in text
        or "**" in text
    ):

        match = (
            _find_exact_syllabus_topic(
                topics,
                "Pointer to Pointer"
            )
            or
            _find_topic_containing(
                topics,
                "pointer to pointer"
            )
        )

        if match:
            return match


    if "array of pointers" in text:

        match = (
            _find_exact_syllabus_topic(
                topics,
                "Array of Pointers"
            )
            or
            _find_topic_containing(
                topics,
                "array",
                "pointers"
            )
        )

        if match:
            return match


    if (
        "pointer to structure" in text
        or "structure pointer" in text
        or "->" in text
    ):

        match = (
            _find_exact_syllabus_topic(
                topics,
                "Pointer to Structure"
            )
            or
            _find_topic_containing(
                topics,
                "pointer",
                "structure"
            )
        )

        if match:
            return match


    # --------------------------------------------------------
    # DYNAMIC MEMORY
    # --------------------------------------------------------

    if any(
        token in text
        for token in (
            "malloc",
            "calloc",
            "realloc",
            "free("
        )
    ):

        match = (
            _find_exact_syllabus_topic(
                topics,
                "Dynamic Memory Allocation",
                "Memory Management (malloc, free)",
                "Memory Management"
            )
            or
            _find_topic_containing(
                topics,
                "memory"
            )
        )

        if match:
            return match


    # --------------------------------------------------------
    # FILE SUBTOPICS
    # --------------------------------------------------------

    if any(
        token in text
        for token in (
            "fseek",
            "ftell",
            "fread",
            "fwrite"
        )
    ):

        match = _find_topic_containing(
            topics,
            "library functions"
        )

        if match:
            return match


    if (
        ("fopen" in text or "open a file" in text)
        and
        ("fclose" in text or "close the file" in text)
        and
        not any(
            token in text
            for token in (
                "fprintf",
                "fscanf",
                "fgets",
                "fputs",
                "fread",
                "fwrite"
            )
        )
    ):

        match = (
            _find_topic_containing(
                topics,
                "opening",
                "closing"
            )
        )

        if match:
            return match


    if any(
        token in text
        for token in (
            "fprintf",
            "fscanf",
            "fgets",
            "fputs"
        )
    ):

        match = (
            _find_topic_containing(
                topics,
                "writing",
                "reading"
            )
        )

        if match:
            return match


    # --------------------------------------------------------
    # POINTER + STRING
    # --------------------------------------------------------

    if (
        "pointer" in text
        and
        (
            "string" in text
            or "character array" in text
        )
    ):

        match = (
            _find_exact_syllabus_topic(
                topics,
                "Processing Strings Using Pointers"
            )
            or
            _find_topic_containing(
                topics,
                "strings",
                "pointers"
            )
        )

        if match:
            return match


    # --------------------------------------------------------
    # PASSING POINTERS TO FUNCTIONS
    # --------------------------------------------------------

    if (
        "pointer" in text
        and
        "function" in text
        and
        any(
            phrase in text
            for phrase in (
                "pass",
                "parameter",
                "argument",
                "swap"
            )
        )
    ):

        match = (
            _find_exact_syllabus_topic(
                topics,
                "Passing Pointers to Functions"
            )
            or
            _find_topic_containing(
                topics,
                "passing",
                "pointers",
                "functions"
            )
        )

        if match:
            return match


    # --------------------------------------------------------
    # POINTER ARITHMETIC
    #
    # This catches the exact bug:
    #
    # label = Pointers
    # problem = "use only pointer arithmetic"
    # --------------------------------------------------------

    if any(
        phrase in text
        for phrase in (
            "pointer arithmetic",
            "array indexing is not allowed",
            "array indexing is disallowed",
            "without array indexing",
            "increment the pointer",
            "decrement the pointer",
            "pointer increment",
            "pointer decrement"
        )
    ):

        match = (
            _find_exact_syllabus_topic(
                topics,
                "Pointer Arithmetic"
            )
            or
            _find_topic_containing(
                topics,
                "pointer arithmetic"
            )
        )

        if match:
            return match


    # --------------------------------------------------------
    # ACCESSING ARRAY ELEMENTS USING POINTERS
    # --------------------------------------------------------

    if (
        "array" in text
        and
        "pointer" in text
        and
        any(
            word in text
            for word in (
                "access",
                "traverse",
                "iterate",
                "element"
            )
        )
    ):

        match = (
            _find_exact_syllabus_topic(
                topics,
                "Accessing Array Elements Using Pointers"
            )
            or
            _find_topic_containing(
                topics,
                "array",
                "pointers"
            )
        )

        if match:
            return match


    return None


def _concept_key_for_topic(
    topic
):

    normalized = _normalize_topic_name(
        topic
    )

    if "dynamic memory" in normalized:
        return "DYNAMIC_MEMORY"

    if "memory management" in normalized:
        return "DYNAMIC_MEMORY"

    if "pointer" in normalized:
        return "POINTERS"

    if "array" == normalized:
        return "ARRAYS"

    if "string" in normalized:
        return "STRINGS"

    if "function" in normalized:
        return "FUNCTIONS"

    if "structure" in normalized:
        return "STRUCTURES"

    if "file" in normalized:
        return "FILES"

    return "OTHER"


def _build_exact_topic_fallback(
    selected_topic,
    language
):

    if str(language).strip().lower() != "c":
        return None

    topic = _normalize_topic_name(
        selected_topic
    )


    if topic == "arrays":

        return {
            "topic": selected_topic,
            "concept_key": "ARRAYS",
            "adaptation_reason":
                "Deterministic exact-topic fallback.",
            "problem":
                (
                    "Write a C program that reads N followed by "
                    "N integers, stores them in an array, and "
                    "prints the array in reverse order. You must "
                    "use array indexing to access the stored "
                    "elements."
                ),
            "tests": [
                {
                    "input":
                        "5\n1 2 3 4 5\n",
                    "expected":
                        "5 4 3 2 1"
                },
                {
                    "input":
                        "1\n7\n",
                    "expected":
                        "7"
                },
                {
                    "input":
                        "4\n-1 0 7 2\n",
                    "expected":
                        "2 7 0 -1"
                }
            ]
        }


    if topic == "pointers":

        return {
            "topic": selected_topic,
            "concept_key": "POINTERS",
            "adaptation_reason":
                "Deterministic exact-topic fallback.",
            "problem":
                (
                    "Write a C program that reads one integer. "
                    "Store it in an int variable, create an int "
                    "pointer containing that variable's address, "
                    "increase the value by 1 using dereferencing "
                    "through the pointer, and print the updated "
                    "value. Do not use pointer arithmetic."
                ),
            "tests": [
                {
                    "input": "5\n",
                    "expected": "6"
                },
                {
                    "input": "-2\n",
                    "expected": "-1"
                },
                {
                    "input": "0\n",
                    "expected": "1"
                }
            ]
        }


    if topic == "pointer arithmetic":

        return {
            "topic": selected_topic,
            "concept_key": "POINTERS",
            "adaptation_reason":
                "Deterministic exact-topic fallback.",
            "problem":
                (
                    "Write a C program that reads N followed by "
                    "N integers and stores them in an array. "
                    "Using a pointer and pointer arithmetic only, "
                    "visit every array element and print their "
                    "sum. Do not use arr[i] while computing the "
                    "sum."
                ),
            "tests": [
                {
                    "input":
                        "5\n1 2 3 4 5\n",
                    "expected":
                        "15"
                },
                {
                    "input":
                        "3\n-1 -2 -3\n",
                    "expected":
                        "-6"
                },
                {
                    "input":
                        "1\n10\n",
                    "expected":
                        "10"
                }
            ]
        }


    if "passing pointers to functions" in topic:

        return {
            "topic": selected_topic,
            "concept_key": "POINTERS",
            "adaptation_reason":
                "Deterministic exact-topic fallback.",
            "problem":
                (
                    "Write a C program that reads two integers. "
                    "Create a function swap(int *a, int *b) and "
                    "pass the addresses of the two integers to "
                    "that function. Print the values after "
                    "swapping."
                ),
            "tests": [
                {
                    "input": "2 5\n",
                    "expected": "5 2"
                },
                {
                    "input": "-1 7\n",
                    "expected": "7 -1"
                },
                {
                    "input": "0 0\n",
                    "expected": "0 0"
                }
            ]
        }


    if "accessing array elements using pointers" in topic:

        return {
            "topic": selected_topic,
            "concept_key": "POINTERS",
            "adaptation_reason":
                "Deterministic exact-topic fallback.",
            "problem":
                (
                    "Write a C program that reads N followed by "
                    "N integers into an array. Create a pointer "
                    "to the first element and access the stored "
                    "elements through that pointer to find and "
                    "print the maximum value."
                ),
            "tests": [
                {
                    "input":
                        "5\n1 8 3 2 5\n",
                    "expected":
                        "8"
                },
                {
                    "input":
                        "3\n-5 -2 -9\n",
                    "expected":
                        "-2"
                },
                {
                    "input":
                        "1\n4\n",
                    "expected":
                        "4"
                }
            ]
        }


    if "processing strings using pointers" in topic:

        return {
            "topic": selected_topic,
            "concept_key": "POINTERS",
            "adaptation_reason":
                "Deterministic exact-topic fallback.",
            "problem":
                (
                    "Write a C program that reads one word into "
                    "a character array. Use a char pointer to "
                    "traverse the string and print its length. "
                    "Do not use strlen."
                ),
            "tests": [
                {
                    "input": "hello\n",
                    "expected": "5"
                },
                {
                    "input": "C\n",
                    "expected": "1"
                },
                {
                    "input": "pointer\n",
                    "expected": "7"
                }
            ]
        }


    if "pointer to pointer" in topic:

        return {
            "topic": selected_topic,
            "concept_key": "POINTERS",
            "adaptation_reason":
                "Deterministic exact-topic fallback.",
            "problem":
                (
                    "Write a C program that reads an integer x. "
                    "Create an int pointer p to x and an int "
                    "double-pointer pp to p. Add 5 to x using "
                    "**pp and print the updated value."
                ),
            "tests": [
                {
                    "input": "5\n",
                    "expected": "10"
                },
                {
                    "input": "-5\n",
                    "expected": "0"
                },
                {
                    "input": "0\n",
                    "expected": "5"
                }
            ]
        }


    if "array of pointers" in topic:

        return {
            "topic": selected_topic,
            "concept_key": "POINTERS",
            "adaptation_reason":
                "Deterministic exact-topic fallback.",
            "problem":
                (
                    "Write a C program that reads three integers "
                    "a, b and c. Create an array containing "
                    "pointers to these three variables. "
                    "Dereference the pointers in the array and "
                    "print the sum of the three values."
                ),
            "tests": [
                {
                    "input": "1 2 3\n",
                    "expected": "6"
                },
                {
                    "input": "-1 4 2\n",
                    "expected": "5"
                },
                {
                    "input": "0 0 0\n",
                    "expected": "0"
                }
            ]
        }


    if (
        "pointer to function" in topic
        or
        "function pointers" in topic
        or
        "function pointer" == topic
    ):

        return {
            "topic": selected_topic,
            "concept_key": "POINTERS",
            "adaptation_reason":
                "Deterministic exact-topic fallback.",
            "problem":
                (
                    "Write a C program with add and multiply "
                    "functions. Read integers a, b and op. "
                    "Create a function pointer of type "
                    "int (*fp)(int, int). If op is 1 assign add "
                    "to fp; otherwise assign multiply. Call the "
                    "selected function only through fp and print "
                    "the result."
                ),
            "tests": [
                {
                    "input": "2 3 1\n",
                    "expected": "5"
                },
                {
                    "input": "4 5 2\n",
                    "expected": "20"
                },
                {
                    "input": "-2 7 1\n",
                    "expected": "5"
                }
            ]
        }


    if "pointer to structure" in topic:

        return {
            "topic": selected_topic,
            "concept_key": "STRUCTURES",
            "adaptation_reason":
                "Deterministic exact-topic fallback.",
            "problem":
                (
                    "Define a C structure Pair containing two "
                    "integers a and b. Read both values, create "
                    "a pointer to the structure, access both "
                    "members using the -> operator, and print "
                    "their sum."
                ),
            "tests": [
                {
                    "input": "2 3\n",
                    "expected": "5"
                },
                {
                    "input": "-5 2\n",
                    "expected": "-3"
                },
                {
                    "input": "0 0\n",
                    "expected": "0"
                }
            ]
        }


    if (
        "dynamic memory allocation" in topic
        or
        "memory management" in topic
    ):

        return {
            "topic": selected_topic,
            "concept_key": "DYNAMIC_MEMORY",
            "adaptation_reason":
                "Deterministic exact-topic fallback.",
            "problem":
                (
                    "Write a C program that reads N followed by "
                    "N integers. Allocate memory dynamically for "
                    "the N integers using malloc or calloc, "
                    "store the values, print their sum, and free "
                    "the allocated memory before the program "
                    "ends."
                ),
            "tests": [
                {
                    "input":
                        "4\n1 2 3 4\n",
                    "expected":
                        "10"
                },
                {
                    "input":
                        "3\n-1 -2 5\n",
                    "expected":
                        "2"
                },
                {
                    "input":
                        "1\n9\n",
                    "expected":
                        "9"
                }
            ]
        }


    return None


def generate_adaptive_question(
    topics,
    history,
    language,
    weak_concept=None
):

    selected_topic = str(
        topics[0]
        if topics
        else ""
    ).strip()

    state = load_state()

    all_syllabus_topics = (
        state.get(
            "topics",
            []
        )
        or
        topics
        or
        []
    )

    # If we are asking the same topic again because of
    # weakness/verification, DO NOT allow semantic relabelling
    # to a sibling topic.
    strict_target = bool(
        weak_concept
    )

    if history and selected_topic:

        previous_topic = str(
            history[-1].get(
                "topic",
                ""
            )
            or ""
        ).strip()

        if (
            _normalize_topic_name(
                previous_topic
            )
            ==
            _normalize_topic_name(
                selected_topic
            )
        ):
            strict_target = True


    last_error = None

    for attempt in range(2):

        try:

            generated = (
                _generate_adaptive_question_unchecked(
                    topics,
                    history,
                    language,
                    weak_concept
                )
            )

            if not isinstance(
                generated,
                dict
            ):
                raise ValueError(
                    "Question generator did not return JSON."
                )

            problem = str(
                generated.get(
                    "problem",
                    ""
                )
                or ""
            ).strip()

            if not problem:
                raise ValueError(
                    "Generated programming problem is empty."
                )


            semantic_topic = (
                _infer_semantic_topic(
                    problem,
                    all_syllabus_topics,
                    selected_topic,
                    language
                )
            )


            # =================================================
            # SEMANTIC SIBLING DETECTED
            # =================================================

            if (
                semantic_topic
                and
                selected_topic
                and
                _normalize_topic_name(
                    semantic_topic
                )
                !=
                _normalize_topic_name(
                    selected_topic
                )
            ):

                if strict_target:

                    last_error = ValueError(
                        "Generated problem drifted from exact "
                        f'topic "{selected_topic}" to sibling '
                        f'topic "{semantic_topic}".'
                    )

                    continue


                # Normal first-time question:
                # If the AI actually produced a more specific
                # exact syllabus topic, correct the label to
                # match the semantics.
                generated[
                    "topic"
                ] = semantic_topic

                generated[
                    "concept_key"
                ] = _concept_key_for_topic(
                    semantic_topic
                )

                generated[
                    "adaptation_reason"
                ] = (
                    "Question semantics matched the more "
                    "specific uploaded syllabus topic: "
                    + semantic_topic
                    + "."
                )

                return generated


            # No sibling conflict.
            # Keep the exact selected syllabus topic.
            if selected_topic:

                generated[
                    "topic"
                ] = selected_topic

                generated[
                    "concept_key"
                ] = _concept_key_for_topic(
                    selected_topic
                )


            return generated


        except Exception as error:

            last_error = error

            print(
                "SEMANTIC QUESTION ATTEMPT",
                attempt + 1,
                "FAILED:",
                error
            )


    # =========================================================
    # RELIABLE EXACT-TOPIC FALLBACK
    # =========================================================

    fallback = _build_exact_topic_fallback(
        selected_topic,
        language
    )

    if fallback:

        print(
            "USING EXACT-TOPIC FALLBACK:",
            selected_topic
        )

        return fallback


    raise ValueError(
        "Could not generate a semantically aligned question "
        f'for exact syllabus topic "{selected_topic}". '
        f"Last error: {last_error}"
    )



@csrf_exempt
def adaptive_next_question(request):

    if request.method != "POST":

        return JsonResponse(
            {"error": "POST required"},
            status=405
        )


    try:

        data = json.loads(
            request.body or "{}"
        )

        student_id = data.get(
            "student_id"
        )

        # Exact topic requested by the completed learning cycle.
        # Used when the previous topic still needs independent verification.
        required_topic = str(
            data.get(
                "required_topic",
                ""
            ) or ""
        ).strip()


        state = (
            load_student_snapshot(
                student_id
            )
            or load_state()
        )


        # Final syllabus/session safety guard.
        state = (
            _sanitize_state_for_current_syllabus(
                state
            )
        )

        # Save the cleaned version immediately.
        save_state(
            state
        )


        state_student_id = state.get(
            "student_id"
        )

        if (
            state_student_id
            and str(state_student_id)
            != str(student_id)
        ):
            return JsonResponse(
                {
                    "error":
                        "Upload a syllabus for this student session first."
                },
                status=400
            )


        if not state.get(
            "syllabus_text"
        ):

            return JsonResponse(
                {"error": "Upload syllabus first."},
                status=400
            )


        language = state.get(
            "language",
            "Python"
        )


        # UNSUPPORTED-RUNTIME-GUARD
        if language not in [
            "Python",
            "Java",
            "C",
        ]:

            return JsonResponse(
                {
                    "error":
                        state.get(
                            "unsupported_reason"
                        )
                        or
                        (
                            "This syllabus requires a runtime "
                            "that is not supported by the "
                            "current automatic code runner."
                        ),

                    "unsupported_runtime":
                        True,

                    "language":
                        language,
                },
                status=422,
            )


        history = state.get(
            "history",
            []
        )


        weak_concept = get_weakest_concept(
            student_id
        )


        # FINAL-WEAK-TOPIC-GUARD
        allowed_topic_map = {
            str(
                topic
            ).strip().casefold():
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
        }


        if weak_concept:

            weak_topic = str(
                weak_concept.get(
                    "exact_topic",
                    ""
                )
            ).strip()

            weak_key = (
                weak_topic.casefold()
            )


            if (
                weak_topic
                and
                weak_key
                not in allowed_topic_map
            ):

                print(
                    "IGNORING OLD WEAK TOPIC:",
                    weak_topic,
                )

                weak_concept = None


            elif (
                weak_topic
                and
                weak_key
                in allowed_topic_map
            ):

                weak_concept[
                    "exact_topic"
                ] = (
                    allowed_topic_map[
                        weak_key
                    ]
                )


        is_verification = bool(
            weak_concept
            and weak_concept.get(
                "reason"
            ) == "verification"
        )


        # ==================================================
        # EXISTING QUESTIONS IN SYLLABUS
        # ==================================================

        if state.get(
            "mode"
        ) == "existing_questions":

            questions = state.get(
                "existing_questions",
                []
            )

            index = state.get(
                "question_index",
                0
            )


            if index >= len(questions):

                return JsonResponse({

                    "finished": True,

                    "message":
                        "All syllabus questions have been completed."

                })


            problem = questions[
                index
            ]


            generated = generate_tests_for_question(
                problem,
                language
            )


            question = {

                "id":
                    str(uuid.uuid4()),

                "source":
                    "syllabus",

                "language":
                    language,

                "topic":
                    generated.get(
                        "concept_key",
                        "Programming"
                    ),

                "concept_key":
                    generated.get(
                        "concept_key",
                        "OTHER"
                    ),

                "adaptation_reason":
                    "This is an original question from the uploaded syllabus.",

                "is_verification":
                    False,

                "problem":
                    problem,

                "tests":
                    generated.get(
                        "tests",
                        []
                    )
            }


            state[
                "question_index"
            ] = index + 1


        # ==================================================
        # TOPICS ONLY
        # ==================================================

        else:

            # ==================================================
            # EXACT INDEPENDENT VERIFICATION TOPIC
            # ==================================================

            generation_topics = state.get(
                "topics",
                []
            )

            canonical_required_topic = ""

            if required_topic:

                for syllabus_topic in generation_topics:

                    if (
                        str(syllabus_topic).strip().casefold()
                        == required_topic.casefold()
                    ):

                        canonical_required_topic = str(
                            syllabus_topic
                        ).strip()

                        break


                if not canonical_required_topic:

                    raise ValueError(
                        f'Required verification topic "{required_topic}" '
                        "does not belong to the active syllabus."
                    )


                # A report requesting verification MUST generate
                # another question on this exact same topic.
                generation_topics = [
                    canonical_required_topic
                ]

                is_verification = True


            # ==================================================
            # ONE-TOPIC GENERATION GUARD
            # ==================================================
            # For ordinary questions, choose ONE syllabus topic
            # before asking the AI to create the problem.
            #
            # This prevents cases such as:
            # Topic = Character Set
            # Problem = pointer/array problem

            if not canonical_required_topic:

                all_topics = [
                    str(topic).strip()
                    for topic in generation_topics
                    if str(topic).strip()
                ]

                if not all_topics:

                    raise ValueError(
                        "No valid syllabus topics are available."
                    )


                used_topics = {
                    str(
                        item.get(
                            "topic",
                            ""
                        )
                    ).strip().casefold()

                    for item in history

                    if isinstance(
                        item,
                        dict
                    )
                    and str(
                        item.get(
                            "topic",
                            ""
                        )
                    ).strip()
                }


                # Prefer topics that produce strong,
                # executable programming-lab demonstrations.
                preferred_topics = [
                    "Arrays",
                    "Functions",
                    "Pointers",
                    "Strings",
                    "Bitwise Operators",
                    "Function Pointers",
                    "File Handling",
                ]


                target_topic = None


                # First try preferred practical topics.
                for preferred in preferred_topics:

                    for syllabus_topic in all_topics:

                        if (
                            syllabus_topic.casefold()
                            == preferred.casefold()
                            and syllabus_topic.casefold()
                            not in used_topics
                        ):

                            target_topic = (
                                syllabus_topic
                            )

                            break

                    if target_topic:
                        break


                # Then use the next untested syllabus topic.
                if not target_topic:

                    for syllabus_topic in all_topics:

                        if (
                            syllabus_topic.casefold()
                            not in used_topics
                        ):

                            target_topic = (
                                syllabus_topic
                            )

                            break


                # If every topic has evidence, safely reuse
                # one syllabus topic instead of leaving scope open.
                if not target_topic:

                    target_topic = (
                        all_topics[0]
                    )


                # CRITICAL:
                # The LLM sees ONLY this topic.
                generation_topics = [
                    target_topic
                ]


            generated = generate_adaptive_question(

                generation_topics,

                history,

                language,

                weak_concept
            )


            # FINAL-GENERATED-TOPIC-GUARD
            allowed_topic_map = {
                str(
                    topic
                ).strip().casefold():
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
            }


            generated_topic = str(
                generated.get(
                    "topic",
                    ""
                )
            ).strip()


            generated_key = (
                generated_topic.casefold()
            )


            # During independent verification, merely belonging to
            # the syllabus is not enough. It must be the SAME topic.
            if (
                canonical_required_topic
                and generated_key
                != canonical_required_topic.casefold()
            ):

                print(
                    "REJECTED WRONG VERIFICATION TOPIC:",
                    generated_topic,
                    "EXPECTED:",
                    canonical_required_topic,
                )

                generated = (
                    build_local_fallback_question(
                        [
                            canonical_required_topic
                        ],
                        history,
                        language,
                        weak_concept,
                    )
                )

                generated_topic = str(
                    generated.get(
                        "topic",
                        canonical_required_topic
                    )
                ).strip()

                generated_key = (
                    generated_topic.casefold()
                )


                if (
                    generated_key
                    != canonical_required_topic.casefold()
                ):

                    raise ValueError(
                        "Independent verification question "
                        "could not be generated on the exact required topic."
                    )


                generated[
                    "topic"
                ] = canonical_required_topic


            if (
                generated_key
                not in allowed_topic_map
            ):

                print(
                    "REJECTED CROSS-SYLLABUS QUESTION:",
                    generated_topic,
                )

                print(
                    "Generating safe local fallback "
                    "from CURRENT syllabus only."
                )


                generated = (
                    build_local_fallback_question(
                        state.get(
                            "topics",
                            []
                        ),
                        history,
                        language,
                        None,
                    )
                )


                generated_topic = str(
                    generated.get(
                        "topic",
                        ""
                    )
                ).strip()

                generated_key = (
                    generated_topic.casefold()
                )


            if (
                generated_key
                not in allowed_topic_map
            ):

                raise ValueError(
                    "Question rejected because its topic "
                    "does not belong to the active syllabus."
                )


            # Always use exact syllabus spelling.
            generated[
                "topic"
            ] = (
                allowed_topic_map[
                    generated_key
                ]
            )


            question = {

                "id":
                    str(uuid.uuid4()),

                "source":
                    (
                        "adaptive"
                        if weak_concept
                        else "generated"
                    ),

                "language":
                    language,

                "topic":
                    generated.get(
                        "topic",
                        "Programming"
                    ),

                "concept_key":
                    generated.get(
                        "concept_key",
                        "OTHER"
                    ),

                "adaptation_reason":
                    generated.get(
                        "adaptation_reason",
                        "Selected from the uploaded syllabus."
                    ),

                "is_verification":
                    is_verification,

                "problem":
                    generated.get(
                        "problem",
                        ""
                    ),

                "tests":
                    generated.get(
                        "tests",
                        []
                    )
            }


        if len(
            question["tests"]
        ) != 3:

            raise ValueError(
                "Exactly 3 hidden tests were not generated."
            )


        state[
            "current_question"
        ] = question


        history.append({

            "id":
                question["id"],

            "source":
                question["source"],

            "language":
                question["language"],

            "topic":
                question["topic"],

            "concept_key":
                question["concept_key"],

            "is_verification":
                question.get(
                    "is_verification",
                    False
                ),

            "problem":
                question["problem"]
        })


        state[
            "history"
        ] = history


        save_state(
            state
        )


        execution_supported = (
            language
            in ["Python", "Java", "C"]
        )


        return JsonResponse({

            "finished":
                False,

            "id":
                question["id"],

            "source":
                question["source"],

            "language":
                language,

            "execution_supported":
                execution_supported,

            "topic":
                question["topic"],

            "concept_key":
                question["concept_key"],

            "problem":
                question["problem"],

            "question_number":
                len(history),

            "weak_concept":
                weak_concept,

            "is_verification":
                question.get(
                    "is_verification",
                    False
                ),

            "adaptation_reason":
                question["adaptation_reason"]
        })


    except Exception as error:

        print(
            "ADAPTIVE NEXT ERROR:",
            error
        )

        return JsonResponse(
            {"error": str(error)},
            status=500
        )