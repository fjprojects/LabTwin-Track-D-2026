import json
import hashlib
import re
import time
import os
import subprocess
import sys
import tempfile
import uuid
import shutil
from pathlib import Path

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from dotenv import load_dotenv
from pypdf import PdfReader

from crewai import Agent, Task, Crew, Process, LLM
from .ai_retry import kickoff_with_retry
from .response_history import record_response, record_execution
from .access import current_student_id
from .hidden_results import private_summary

import crewai.llms.cache as _crewai_cache
_crewai_cache.mark_cache_breakpoint = lambda message: message


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
STATE_FILE = PROJECT_ROOT / "syllabus_state.json"

STUDENT_SESSION_DIR = (
    PROJECT_ROOT /
    "student_sessions"
)

SYLLABUS_ANALYSIS_CACHE_FILE = (
    PROJECT_ROOT /
    "syllabus_analysis_cache.json"
)

load_dotenv(PROJECT_ROOT / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

llm = LLM(
    model="groq/openai/gpt-oss-20b",
    api_key=GROQ_API_KEY,
    temperature=0.1
)


syllabus_agent = Agent(
    role="Programming Lab Syllabus Analyzer",
    goal="Detect programming language, topics and existing lab questions from a syllabus.",
    backstory="You are an experienced university programming lab instructor.",
    llm=llm,
    verbose=False
)

question_agent = Agent(
    role="Programming Lab Question Generator",
    goal="Generate programming questions that directly test the exact syllabus topic in the correct programming language.",
    backstory="You never translate language-specific concepts into unrelated concepts from another language.",
    llm=llm,
    verbose=False
)

analyzer_agent = Agent(
    role="Programming Misconception Analyzer",
    goal="Identify the main programming misconception responsible for failed tests.",
    backstory="You diagnose only mistakes relevant to the stated problem.",
    llm=llm,
    verbose=False
)

tutor_agent = Agent(
    role="Adaptive Programming Tutor",
    goal="Help students correct misconceptions through hints, practice and viva.",
    backstory="You provide personalized guidance without immediately revealing full answers.",
    llm=llm,
    verbose=False
)

evaluator_agent = Agent(
    role="Programming Understanding Evaluator",
    goal="Evaluate corrected code and conceptual understanding.",
    backstory="You combine real code execution results with the viva answer.",
    llm=llm,
    verbose=False
)


def clean_json_output(output):
    if output is None:
        raise ValueError("AI returned an empty response.")

    text = str(output).strip()

    if not text:
        raise ValueError("AI returned an empty response.")

    if text.startswith("```json"):
        text = text[7:].strip()
    elif text.startswith("```"):
        text = text[3:].strip()

    if text.endswith("```"):
        text = text[:-3].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    object_start = text.find("{")
    object_end = text.rfind("}")

    if object_start != -1 and object_end > object_start:
        candidate = text[object_start:object_end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    print("INVALID AI JSON RESPONSE:", repr(text[:1000]))
    raise ValueError("AI returned an invalid response. Please try again.")


def _normalize_topic_name(value):
    return "".join(
        char.lower()
        for char in str(value or "")
        if char.isalnum()
    )


def expected_concept_key_for_topic(topic):
    """Best deterministic broad concept for clearly named syllabus topics."""
    name = str(topic or "").strip().lower()

    # Java foundation topics are conceptual/structural, not conditionals/loops.
    java_foundations = (
        "introduction to java",
        "java runtime environment",
        "jre",
        "java development kit",
        "jdk",
        "java virtual machine",
        "jvm",
        "java compiler",
        "java program structure",
        "java tokens",
    )

    if any(item == name for item in java_foundations):
        return "OTHER"

    # Order matters: pointer/file/dynamic-memory topics may also mention
    # arrays, strings, functions or structures.
    if "pointer" in name:
        return "POINTERS"
    if "dynamic memory" in name or "malloc" in name or "calloc" in name or "realloc" in name:
        return "DYNAMIC_MEMORY"
    if "file" in name or any(word in name for word in ("fseek", "ftell", "fread", "fwrite")):
        return "FILES"
    if "struct" in name or "union" in name:
        return "STRUCTURES"
    if "array" in name:
        return "ARRAYS"
    if "string" in name:
        return "STRINGS"
    if any(word in name for word in ("conditional", "if else", "if-else", "switch")):
        return "CONDITIONALS"
    if any(word in name for word in ("loop", "iteration", "while", "for loop")):
        return "LOOPS"
    if any(word in name for word in ("class", "object", "inheritance", "polymorphism", "interface", "encapsulation", "abstraction")):
        return "OOP"
    if any(word in name for word in ("function", "method")):
        return "FUNCTIONS"
    if "operator" in name and "arithmetic" in name:
        return "ARITHMETIC_OPERATORS"

    return None


def validate_generated_question_alignment(generated, allowed_topics, required_topic=None):
    """Return an error string when AI output drifts away from the syllabus topic."""
    if not isinstance(generated, dict):
        return "Generated question is not a JSON object."

    raw_topic = str(generated.get("topic", "")).strip()
    normalized = _normalize_topic_name(raw_topic)

    canonical = None
    for allowed in allowed_topics or []:
        if _normalize_topic_name(allowed) == normalized:
            canonical = str(allowed).strip()
            break

    if not canonical:
        return f'Topic "{raw_topic}" is not one of the uploaded syllabus topics.'

    generated["topic"] = canonical

    if required_topic and _normalize_topic_name(canonical) != _normalize_topic_name(required_topic):
        return f'Expected exact verification topic "{required_topic}", but AI generated "{canonical}".'

    expected_key = expected_concept_key_for_topic(canonical)
    actual_key = str(generated.get("concept_key", "OTHER") or "OTHER").strip().upper()

    if expected_key and actual_key != expected_key:
        return (
            f'Topic/concept mismatch: "{canonical}" should primarily test '
            f'{expected_key}, but generated concept_key was {actual_key}.'
        )

    return ""


def viva_question_matches_topic(topic, viva_question):
    """Fast guard for foundation topics that commonly drift to incidental code logic."""
    topic_name = str(topic or "").strip().lower()
    viva = str(viva_question or "").strip().lower()

    if not viva:
        return False

    if topic_name == "java program structure":
        forbidden = (
            "short-circuit",
            "short circuit",
            "if-else",
            "if else",
            "switch statement",
            "switch case",
            "loop",
        )
        if any(word in viva for word in forbidden):
            return False

        required = (
            "main",
            "class",
            "entry point",
            "program structure",
            "method signature",
            "import",
        )
        return any(word in viva for word in required)

    if topic_name == "java tokens":
        return any(
            word in viva
            for word in (
                "token",
                "keyword",
                "identifier",
                "literal",
                "operator",
                "separator",
            )
        )

    if topic_name in ("java virtual machine", "jvm"):
        return any(word in viva for word in ("jvm", "bytecode", "runtime", "class loader"))

    if topic_name in ("java development kit", "jdk"):
        return any(word in viva for word in ("jdk", "javac", "development", "compiler"))

    if topic_name in ("java runtime environment", "jre"):
        return any(word in viva for word in ("jre", "runtime environment", "jvm"))

    if topic_name == "java compiler":
        return any(word in viva for word in ("compiler", "javac", "bytecode"))

    return True


def default_state():
    return {
        "student_id": None,
        "filename": "",
        "syllabus_text": "",
        "language": "Python",
        "mode": "",
        "topics": [],
        "existing_questions": [],
        "question_index": 0,
        "history": [],
        "current_question": None,
    }


def _student_session_path(
    student_id,
):
    if student_id in (
        None,
        "",
    ):
        return None

    STUDENT_SESSION_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    safe_id = str(
        student_id
    ).strip()

    return (
        STUDENT_SESSION_DIR /
        f"student_{safe_id}.json"
    )


def load_student_snapshot(
    student_id,
):
    path = _student_session_path(
        student_id
    )

    if (
        path is None
        or not path.exists()
    ):
        return None

    try:
        with open(
            path,
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(
                file
            )

        if isinstance(
            data,
            dict,
        ):
            return data

    except Exception as error:
        print(
            "STUDENT SESSION READ ERROR:",
            error,
        )

    return None


def save_student_snapshot(
    state,
):
    if not isinstance(
        state,
        dict,
    ):
        return

    student_id = state.get(
        "student_id"
    )

    path = _student_session_path(
        student_id
    )

    if path is None:
        return

    try:
        with open(
            path,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                state,
                file,
                indent=2,
                ensure_ascii=False,
            )

    except Exception as error:
        print(
            "STUDENT SESSION WRITE ERROR:",
            error,
        )


def load_state():
    student_id = current_student_id.get()
    if student_id is not None:
        state = load_student_snapshot(student_id) or default_state()
        state["student_id"] = str(student_id)
        return state
    if not STATE_FILE.exists():
        return default_state()

    try:
        with open(
            STATE_FILE,
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(
                file
            )

        if isinstance(
            data,
            dict,
        ):
            return data

    except Exception:
        pass

    return default_state()


def save_state(
    state,
):
    student_id = current_student_id.get()
    if student_id is not None:
        if state.get("student_id") and str(state["student_id"]) != str(student_id):
            raise ValueError("Student session mismatch")
        state["student_id"] = str(student_id)
        save_student_snapshot(state)
        return
    with open(
        STATE_FILE,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            state,
            file,
            indent=2,
            ensure_ascii=False,
        )

    # Every active-state save is also copied
    # into that student's own persistent session.
    if state.get(
        "student_id"
    ):
        save_student_snapshot(
            state
        )


def activate_student_session(
    student_id,
    fresh=False,
):
    """
    Activate one student's saved state.

    fresh=True:
        create a completely new learning state.

    fresh=False:
        restore the student's saved syllabus,
        question and history when available.
    """

    if fresh:
        state = default_state()

        state[
            "student_id"
        ] = str(
            student_id
        )

        save_state(
            state
        )

        return state


    state = load_student_snapshot(
        student_id
    )


    # Migration path for sessions created before
    # per-student snapshots were introduced.
    if not state:

        active = load_state()

        if str(
            active.get(
                "student_id"
            )
        ) == str(
            student_id
        ):
            state = active


    if not state:
        state = default_state()

        state[
            "student_id"
        ] = str(
            student_id
        )


    state[
        "student_id"
    ] = str(
        student_id
    )

    save_state(
        state
    )

    return state


def public_student_session(
    state,
):
    """
    Return session information safe for React.

    Hidden tests are intentionally NOT returned.
    """

    if not isinstance(
        state,
        dict,
    ):
        state = default_state()

    question = state.get(
        "current_question"
    )

    public_question = None

    if isinstance(
        question,
        dict,
    ):

        language = question.get(
            "language",
            state.get(
                "language",
                "Python",
            ),
        )

        public_question = {
            "id":
                question.get(
                    "id"
                ),

            "source":
                question.get(
                    "source",
                    "generated",
                ),

            "language":
                language,

            "execution_supported":
                language
                in [
                    "Python",
                    "Java",
                    "C",
                ],

            "topic":
                question.get(
                    "topic",
                    "Programming",
                ),

            "concept_key":
                question.get(
                    "concept_key",
                    "OTHER",
                ),

            "problem":
                question.get(
                    "problem",
                    "",
                ),

            "adaptation_reason":
                question.get(
                    "adaptation_reason",
                    "",
                ),

            "is_verification":
                bool(
                    question.get(
                        "is_verification",
                        False,
                    )
                ),

            "question_number":
                max(
                    1,
                    len(
                        state.get(
                            "history",
                            [],
                        )
                    ),
                ),
        }


    return {
        "student_id":
            state.get(
                "student_id"
            ),

        "has_syllabus":
            bool(
                state.get(
                    "syllabus_text"
                )
            ),

        "filename":
            state.get(
                "filename",
                "",
            ),

        "language":
            state.get(
                "language",
                "Python",
            ),

        "mode":
            state.get(
                "mode",
                "",
            ),

        "topics":
            state.get(
                "topics",
                [],
            ),

        "existing_question_count":
            len(
                state.get(
                    "existing_questions",
                    [],
                )
            ),

        "question_index":
            state.get(
                "question_index",
                0,
            ),

        "has_current_question":
            public_question
            is not None,

        "current_question":
            public_question,
    }


@csrf_exempt
def student_session(
    request,
):
    if request.method != "GET":
        return JsonResponse(
            {
                "error":
                    "GET required"
            },
            status=405,
        )

    student_id = request.GET.get(
        "student_id"
    )

    if not student_id:
        return JsonResponse(
            {
                "error":
                    "student_id is required"
            },
            status=400,
        )

    activate = (
        request.GET.get(
            "activate",
            "1",
        )
        != "0"
    )

    if activate:
        state = activate_student_session(
            student_id,
            fresh=False,
        )
    else:
        state = (
            load_student_snapshot(
                student_id
            )
            or default_state()
        )

    return JsonResponse({
        "success":
            True,

        "session":
            public_student_session(
                state
            ),
    })


def extract_file_text(uploaded_file):
    filename = uploaded_file.name.lower()

    if filename.endswith(".pdf"):
        reader = PdfReader(uploaded_file)
        pages = []

        for page in reader.pages:
            text = page.extract_text()

            if text:
                pages.append(text)

        return "\n".join(pages)

    if filename.endswith(".txt"):
        return uploaded_file.read().decode("utf-8", errors="ignore")

    raise ValueError("Only PDF and TXT files are supported.")


def get_current_question(
    question_id=None,
    student_id=None,
):
    if student_id:
        state = (
            load_student_snapshot(
                student_id
            )
            or {**default_state(), "student_id": str(student_id)}
        )
    else:
        state = load_state()

    question = state.get(
        "current_question"
    )

    if not question:
        return None

    if (
        question_id
        and question.get(
            "id"
        ) != question_id
    ):
        return None

    return question


# ============================================================
# LANGUAGE DETECTION
# ============================================================


# ============================================================
# SYLLABUS AI CACHE + RATE LIMIT PROTECTION
# ============================================================

def _syllabus_cache_key(text):
    """
    Stable fingerprint for syllabus content.

    Same syllabus content = same cache key,
    even when uploaded again.
    """

    normalized = "\n".join(
        line.strip()
        for line in text.splitlines()
        if line.strip()
    )

    return hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()


def _load_syllabus_analysis_cache():

    if not SYLLABUS_ANALYSIS_CACHE_FILE.exists():
        return {}

    try:
        with open(
            SYLLABUS_ANALYSIS_CACHE_FILE,
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        if isinstance(data, dict):
            return data

    except Exception as error:
        print(
            "SYLLABUS CACHE READ ERROR:",
            error,
        )

    return {}


def _save_syllabus_analysis_cache(cache):

    try:

        # Prevent this small local cache from
        # growing forever.
        if len(cache) > 30:
            cache = dict(
                list(
                    cache.items()
                )[-30:]
            )

        with open(
            SYLLABUS_ANALYSIS_CACHE_FILE,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                cache,
                file,
                indent=2,
                ensure_ascii=False,
            )

    except Exception as error:

        print(
            "SYLLABUS CACHE WRITE ERROR:",
            error,
        )


def _compact_syllabus_text(
    text,
    max_chars=11000,
):
    """
    Reduce duplicate PDF/slide text before
    sending it to the LLM.

    Example:
    repeated headings such as "Java Tokens"
    are sent only once.
    """

    cleaned_lines = []

    seen = set()

    for raw_line in text.splitlines():

        line = " ".join(
            raw_line.split()
        ).strip()

        if not line:
            continue

        key = line.casefold()

        if key in seen:
            continue

        seen.add(key)

        cleaned_lines.append(
            line
        )

    compact = "\n".join(
        cleaned_lines
    )

    if len(compact) <= max_chars:
        return compact

    # Keep both beginning and ending instead
    # of blindly deleting the entire end.
    first_size = int(
        max_chars * 0.75
    )

    last_size = (
        max_chars -
        first_size
    )

    return (
        compact[:first_size]
        +
        "\n\n[... syllabus shortened for AI analysis ...]\n\n"
        +
        compact[-last_size:]
    )


def _is_rate_limit_error(error):

    message = str(
        error
    ).lower()

    indicators = (
        "rate limit",
        "ratelimit",
        "rate_limit",
        "too many requests",
        "tokens per minute",
        "tpm",
        "429",
    )

    return any(
        indicator in message
        for indicator in indicators
    )


def _groq_retry_wait_seconds(
    error,
    attempt_number,
):
    """
    Read Groq's own retry duration when
    available and add a safety buffer.
    """

    message = str(
        error
    )

    patterns = (
        r"try again in\s*([0-9.]+)\s*s",
        r"retry after\s*([0-9.]+)\s*s",
        r"retry_after[^0-9]*([0-9.]+)",
    )

    for pattern in patterns:

        match = re.search(
            pattern,
            message,
            re.IGNORECASE,
        )

        if match:

            try:
                requested = float(
                    match.group(1)
                )

                # Add buffer because retrying exactly
                # on Groq's boundary can fail again.
                return max(
                    5.0,
                    min(
                        requested + 5.0,
                        70.0,
                    ),
                )

            except Exception:
                pass

    # Fallback when Groq did not include
    # an exact retry duration.
    return min(
        15.0 +
        (
            attempt_number *
            10.0
        ),
        70.0,
    )


def analyze_syllabus_text(text):

    compact_text = (
        _compact_syllabus_text(
            text
        )
    )

    print(
        "SYLLABUS ORIGINAL CHARS:",
        len(text),
    )

    print(
        "SYLLABUS AI CHARS:",
        len(compact_text),
    )

    last_error = None

    # Four controlled attempts.
    # Rate-limit retries WAIT before trying again.
    for attempt_number in range(
        1,
        5,
    ):

        task = Task(
            description=f"""
Analyze this programming lab syllabus:

{compact_text}

Detect:

1. Main programming language.
2. Programming topics.
3. Whether actual lab questions already exist.

LANGUAGE RULES:

Return one of:

Python
Java
C
Web/FullStack

IMPORTANT EXECUTION CLASSIFICATION:

Choose Web/FullStack when the syllabus mainly contains
React, Django REST Framework, APIs, Axios, Fetch,
CORS, authentication, ViewSets, Postman,
browser storage, frontend/backend integration,
deployment, or similar web application topics.

Do NOT classify an entire React/Django/full-stack
syllabus as Python merely because Django itself
uses Python.

Examples:

Pointers, function pointers, malloc, structures, unions
normally indicate C.

Classes, inheritance, JVM, interfaces, packages
normally indicate Java.

Python syntax, tuples, dictionaries, lists, indentation
normally indicate Python.

IMPORTANT:

Do not translate a language-specific concept into another language.

For example:

"Pointer to Function" is a C concept.
Do NOT convert it into Python built-in functions.

If actual programming questions exist:
mode = "existing_questions"

Otherwise:
mode = "topics"

Return ONLY valid JSON:

{{
    "language": "C",
    "mode": "topics",
    "topics": [
        "Pointers",
        "Pointer to Function"
    ],
    "existing_questions": []
}}
""",
            expected_output=(
                "Valid syllabus JSON"
            ),
            agent=syllabus_agent,
        )

        crew = Crew(
            agents=[
                syllabus_agent
            ],
            tasks=[
                task
            ],
            process=Process.sequential,
            verbose=False,
        )

        try:

            print(
                f"SYLLABUS AI attempt {attempt_number}/4..."
            )

            result = kickoff_with_retry(crew, label="views.py")

            raw = getattr(
                result,
                "raw",
                result,
            )

            print(
                f"SYLLABUS AI RESPONSE attempt {attempt_number}:",
                repr(
                    str(raw)[:500]
                ),
            )

            parsed = clean_json_output(
                raw
            )

            return parsed

        except Exception as error:

            last_error = error

            print(
                f"SYLLABUS ANALYSIS attempt {attempt_number} failed:",
                error,
            )

            if attempt_number >= 4:
                break

            if _is_rate_limit_error(
                error
            ):

                wait_seconds = (
                    _groq_retry_wait_seconds(
                        error,
                        attempt_number,
                    )
                )

                print(
                    "GROQ RATE LIMIT DETECTED."
                )

                print(
                    f"LabTwin will automatically wait {wait_seconds:.1f} seconds."
                )

                print(
                    "Do not upload the syllabus again while waiting."
                )

                time.sleep(
                    wait_seconds
                )

            else:

                # Short retry for malformed JSON or
                # temporary non-rate-limit errors.
                wait_seconds = min(
                    1.5 *
                    attempt_number,
                    5.0,
                )

                time.sleep(
                    wait_seconds
                )

    if (
        last_error is not None
        and
        _is_rate_limit_error(
            last_error
        )
    ):

        raise RuntimeError(
            "Groq's token limit is still full even after "
            "LabTwin automatically waited and retried. "
            "Please wait about one minute and try once."
        )

    raise ValueError(
        "Syllabus AI analysis failed after automatic retries. "
        f"Last error: {last_error}"
    )


# ============================================================
# CODE RUNNERS
# ============================================================

def run_python_code(code, test_input):
    path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
            encoding="utf-8"
        ) as file:
            file.write(code)
            path = file.name

        result = subprocess.run(
            [sys.executable, path],
            input=test_input,
            capture_output=True,
            text=True,
            timeout=5
        )

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip()
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": "Execution timed out."
        }

    except Exception as error:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(error)
        }

    finally:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass


def run_java_code(code, test_input):
    temp_dir = tempfile.mkdtemp()

    try:
        source_path = os.path.join(
            temp_dir,
            "Main.java"
        )

        with open(
            source_path,
            "w",
            encoding="utf-8"
        ) as file:
            file.write(code)

        compile_result = subprocess.run(
            ["javac", source_path],
            capture_output=True,
            text=True,
            timeout=10
        )

        if compile_result.returncode != 0:
            return {
                "success": False,
                "stdout": "",
                "stderr": compile_result.stderr.strip()
            }

        result = subprocess.run(
            [
                "java",
                "-cp",
                temp_dir,
                "Main"
            ],
            input=test_input,
            capture_output=True,
            text=True,
            timeout=5
        )

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip()
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": "Execution timed out."
        }

    except Exception as error:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(error)
        }

    finally:
        shutil.rmtree(
            temp_dir,
            ignore_errors=True
        )



def run_c_code(code, test_input):
    temp_dir = tempfile.mkdtemp()

    try:
        source_path = os.path.join(
            temp_dir,
            "main.c"
        )

        executable_path = os.path.join(
            temp_dir,
            "program.exe"
        )

        with open(
            source_path,
            "w",
            encoding="utf-8"
        ) as file:
            file.write(code)

        # -----------------------------
        # COMPILE C CODE
        # -----------------------------

        compile_result = subprocess.run(
            [
                "gcc",
                source_path,
                "-o",
                executable_path,
                "-std=c11"
            ],
            capture_output=True,
            text=True,
            timeout=10
        )

        if compile_result.returncode != 0:
            return {
                "success": False,
                "stdout": "",
                "stderr": compile_result.stderr.strip()
            }

        # -----------------------------
        # EXECUTE COMPILED PROGRAM
        # -----------------------------

        result = subprocess.run(
            [executable_path],
            input=test_input,
            capture_output=True,
            text=True,
            timeout=5
        )

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip()
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": "Execution timed out."
        }

    except Exception as error:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(error)
        }

    finally:
        shutil.rmtree(
            temp_dir,
            ignore_errors=True
        )


def run_tests(student_code, tests, language):

    from .execution import remote_tests
    remote = remote_tests(student_code, tests, language)
    if remote is not None:
        return remote

    results = []
    passed_count = 0

    for index, test in enumerate(
        tests,
        start=1
    ):

        test_input = str(
            test.get("input", "")
        )

        if language == "Java":
            execution = run_java_code(
                student_code,
                test_input
            )

        elif language == "Python":
            execution = run_python_code(
                student_code,
                test_input
            )

        elif language == "C":
            execution = run_c_code(
                student_code,
                test_input
            )

        else:
            raise ValueError(
                f"Unsupported programming language: {language}"
            )

        expected = str(
            test.get("expected", "")
        ).strip()

        actual = execution[
            "stdout"
        ].strip()

        passed = (
            execution["success"]
            and actual == expected
        )

        if passed:
            passed_count += 1

        results.append({
            "test": index,
            "input": test_input,
            "expected": expected,
            "actual": (
                actual
                if execution["success"]
                else execution["stderr"]
            ),
            "passed": passed,
            "stdout": execution["stdout"],
            "stderr": execution["stderr"],
            "success": execution["success"],
        })

    if not tests:
        return 0, []

    score = round(
        passed_count / len(tests) * 100
    )

    return score, results


# ============================================================
# QUESTION GENERATION
# ============================================================

def generate_tests_for_question(
    problem,
    language
):

    java_rule = ""

    if language == "Java":
        java_rule = """
The submitted Java program must use:

public class Main

so it can be compiled automatically.
"""

    task = Task(
        description=f"""
Programming language:

{language}

EXISTING SYLLABUS QUESTION:

{problem}

Create exactly THREE hidden stdin/stdout tests.

IMPORTANT:

The tests must match the exact question.

Do NOT change the original concept.

{java_rule}

Return ONLY JSON:

{{
    "concept_key": "FUNCTIONS",
    "tests": [
        {{
            "input": "input",
            "expected": "exact output"
        }},
        {{
            "input": "input",
            "expected": "exact output"
        }},
        {{
            "input": "input",
            "expected": "exact output"
        }}
    ]
}}

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
OTHER
""",
        expected_output="Exactly three hidden tests",
        agent=question_agent
    )

    crew = Crew(
        agents=[question_agent],
        tasks=[task],
        process=Process.sequential,
        verbose=False
    )

    return clean_json_output(
        kickoff_with_retry(crew, label="views.py").raw
    )


def generate_question_from_topics(
    topics,
    history,
    language
):

    previous = [
        item.get("problem", "")
        for item in history[-10:]
    ]

    execution_note = ""

    if language == "Java":
        execution_note = """
Require the student to write:

public class Main

with a public static void main(String[] args).
"""

    if language == "C":
        execution_note = """
Generate a genuine C programming problem.

C-specific topics such as pointers,
function pointers, structures and unions
must remain genuine C concepts.
"""

    task = Task(
        description=f"""
Generate ONE programming lab question.

PROGRAMMING LANGUAGE:

{language}

ALLOWED SYLLABUS TOPICS:

{json.dumps(topics, indent=2)}

PREVIOUS QUESTIONS:

{json.dumps(previous, indent=2)}

STRICT RULES:

1. Use ONLY the uploaded syllabus topics.
2. Use the detected programming language: {language}.
3. The question must DIRECTLY test the selected topic.
3A. The selected syllabus topic must be the PRIMARY SKILL needed to solve the problem, not merely a construct that appears incidentally in the code.
3B. Example: if topic = Java Program Structure, test class Main, the main method, imports/entry point/program layout. Do NOT turn it into a conditionals, loops, arrays, or switch problem.
4. Never replace a language-specific concept with a loose equivalent.
5. Do not repeat previous questions.
6. Keep input/output deterministic.
7. Generate exactly THREE hidden tests.
8. No files, GUI, internet or external packages.

{execution_note}

For example:

If topic = Pointer to Function
and language = C,

generate a genuine C function-pointer problem,
NOT a Python function selection problem.

Return ONLY JSON:

{{
    "topic": "Pointer to Function",
    "concept_key": "POINTERS",
    "problem": "Programming question",
    "tests": [
        {{
            "input": "input",
            "expected": "output"
        }},
        {{
            "input": "input",
            "expected": "output"
        }},
        {{
            "input": "input",
            "expected": "output"
        }}
    ]
}}
""",
        expected_output="One language-correct programming question",
        agent=question_agent
    )

    crew = Crew(
        agents=[question_agent],
        tasks=[task],
        process=Process.sequential,
        verbose=False
    )

    return clean_json_output(
        kickoff_with_retry(crew, label="views.py").raw
    )


# ============================================================
# UPLOAD
# ============================================================


def classify_syllabus_execution_mode(
    text,
    analysis,
):
    """
    Decide whether LabTwin's current native
    console runner can meaningfully execute
    questions from this syllabus.

    This prevents examples such as:

        React/Django syllabus
              ->
        falsely classified as Python
              ->
        meaningless stdin/base64 question

    Current automatic execution prototype:
        C console programs
        Java console programs
        Python console programs

    Web application labs require a different
    runtime and are therefore detected instead
    of being incorrectly converted.
    """

    analysis = (
        analysis
        if isinstance(
            analysis,
            dict,
        )
        else {}
    )


    language = str(
        analysis.get(
            "language",
            "",
        )
    ).strip()


    topics = [
        str(
            topic
        )

        for topic in analysis.get(
            "topics",
            []
        )
    ]


    combined = (
        str(
            text
        )
        +
        "\n"
        +
        "\n".join(
            topics
        )
    ).casefold()


    strong_web_markers = (
        "react",
        "axios",
        "fetch api",
        "django rest framework",
        "viewset",
        "viewsets",
        "cors",
        "postman",
        "localstorage",
        "context api",
        "global state management",
        "frontend",
        "full-stack",
        "full stack",
        "token-based authentication",
        "session authentication",
        "is_authenticated",
        "isauthenticated",
        "netlify",
        "vercel",
        "heroku",
        "api testing",
    )


    hits = [
        marker

        for marker
        in strong_web_markers

        if marker
        in combined
    ]


    obvious_web_stack = (
        "react"
        in combined

        or

        "django rest framework"
        in combined

        or

        (
            len(
                hits
            )
            >= 3
        )
    )


    if obvious_web_stack:

        return {
            "supported":
                False,

            "mode":
                "web_fullstack",

            "language":
                "Web/FullStack",

            "reason":
                (
                    "This syllabus is mainly a web/full-stack "
                    "lab syllabus. LabTwin's current automatic "
                    "code runner supports C, Java and Python "
                    "console programs. React/Django/API labs "
                    "require a browser/server runtime, so "
                    "LabTwin will not generate a misleading "
                    "console question from this syllabus."
                ),

            "detected_markers":
                hits[:8],
        }


    if language not in [
        "Python",
        "Java",
        "C",
    ]:

        return {
            "supported":
                False,

            "mode":
                "unsupported",

            "language":
                language
                or
                "Unknown",

            "reason":
                (
                    "This syllabus does not map safely to "
                    "LabTwin's current C, Java or Python "
                    "console execution environment."
                ),

            "detected_markers":
                hits[:8],
        }


    return {
        "supported":
            True,

        "mode":
            "console",

        "language":
            language,

        "reason":
            "",

        "detected_markers":
            hits[:8],
    }



@csrf_exempt
def upload_syllabus(request):

    if request.method != "POST":

        return JsonResponse(
            {
                "error":
                    "POST required"
            },
            status=405,
        )

    try:

        syllabus_file = (
            request.FILES.get(
                "syllabus"
            )
        )

        if not syllabus_file:

            return JsonResponse(
                {
                    "error":
                        "Select a syllabus file."
                },
                status=400,
            )

        student_id = (
            request.POST.get(
                "student_id"
            )
        )

        text = extract_file_text(
            syllabus_file
        )

        if not text.strip():

            return JsonResponse(
                {
                    "error":
                        "No readable text was found in the syllabus."
                },
                status=400,
            )


        # ====================================================
        # CHECK CACHE
        # ====================================================

        cache_key = (
            _syllabus_cache_key(
                text
            )
        )

        cache = (
            _load_syllabus_analysis_cache()
        )

        analysis = cache.get(
            cache_key
        )

        analysis_source = None


        if analysis:

            analysis_source = (
                "analysis_cache"
            )

            print(
                "SYLLABUS CACHE HIT:",
                syllabus_file.name,
            )


        # ====================================================
        # REUSE EXISTING syllabus_state.json
        # ====================================================

        if not analysis:

            old_state = load_state()

            old_text = old_state.get(
                "syllabus_text",
                "",
            )

            if old_text:

                old_key = (
                    _syllabus_cache_key(
                        old_text
                    )
                )

                if (
                    old_key ==
                    cache_key
                    and
                    (
                        old_state.get(
                            "topics"
                        )
                        or
                        old_state.get(
                            "existing_questions"
                        )
                    )
                ):

                    analysis = {
                        "language":
                            old_state.get(
                                "language",
                                "Python",
                            ),

                        "mode":
                            old_state.get(
                                "mode",
                                "topics",
                            ),

                        "topics":
                            old_state.get(
                                "topics",
                                [],
                            ),

                        "existing_questions":
                            old_state.get(
                                "existing_questions",
                                [],
                            ),
                    }

                    analysis_source = (
                        "existing_state"
                    )

                    print(
                        "REUSING EXISTING SYLLABUS ANALYSIS:",
                        syllabus_file.name,
                    )


        # ====================================================
        # AI ONLY IF WE HAVE NEVER ANALYZED THIS SYLLABUS
        # ====================================================

        if not analysis:

            print(
                "NEW SYLLABUS - AI ANALYSIS REQUIRED:",
                syllabus_file.name,
            )

            analysis = (
                analyze_syllabus_text(
                    text
                )
            )

            analysis_source = "ai"


        # ====================================================
        # STORE CLEAN ANALYSIS IN CACHE
        # ====================================================

        cache_analysis = {
            "language":
                analysis.get(
                    "language",
                    "Python",
                ),

            "mode":
                analysis.get(
                    "mode",
                    "topics",
                ),

            "topics":
                analysis.get(
                    "topics",
                    [],
                ),

            "existing_questions":
                analysis.get(
                    "existing_questions",
                    [],
                ),
        }

        cache[
            cache_key
        ] = cache_analysis

        _save_syllabus_analysis_cache(
            cache
        )


        # ====================================================
        # CREATE ACTIVE SESSION STATE
        # ====================================================

        # ====================================================
        # RUNTIME-SCOPE-GUARD
        # ====================================================

        runtime_support = (
            classify_syllabus_execution_mode(
                text,
                cache_analysis,
            )
        )


        if not runtime_support[
            "supported"
        ]:

            cache_analysis[
                "language"
            ] = runtime_support[
                "language"
            ]


        state = default_state()

        state[
            "execution_mode"
        ] = runtime_support[
            "mode"
        ]

        state[
            "unsupported_reason"
        ] = runtime_support[
            "reason"
        ]

        state[
            "execution_supported"
        ] = runtime_support[
            "supported"
        ]



        state[
            "student_id"
        ] = student_id

        state[
            "filename"
        ] = syllabus_file.name

        state[
            "syllabus_text"
        ] = text

        state[
            "analysis_cache_key"
        ] = cache_key

        state[
            "language"
        ] = cache_analysis[
            "language"
        ]

        state[
            "mode"
        ] = cache_analysis[
            "mode"
        ]

        state[
            "topics"
        ] = cache_analysis[
            "topics"
        ]

        state[
            "existing_questions"
        ] = cache_analysis[
            "existing_questions"
        ]

        save_state(
            state
        )

        execution_supported = (
            runtime_support[
                "supported"
            ]
        )


        return JsonResponse({
            "success":
                True,

            "filename":
                state[
                    "filename"
                ],

            "language":
                state[
                    "language"
                ],

            "mode":
                state[
                    "mode"
                ],

            "topics":
                state[
                    "topics"
                ],

            "existing_question_count":
                len(
                    state[
                        "existing_questions"
                    ]
                ),

            "execution_supported":
                execution_supported,

            "execution_mode":
                runtime_support[
                    "mode"
                ],

            "unsupported_reason":
                runtime_support[
                    "reason"
                ],

            "cached":
                (
                    analysis_source
                    !=
                    "ai"
                ),

            "analysis_source":
                analysis_source,

            "message":
                (
                    "Existing syllabus analysis reused."
                    if analysis_source != "ai"
                    else
                    "Syllabus analyzed successfully."
                ),
        })


    except Exception as error:

        print(
            "UPLOAD ERROR:",
            error,
        )

        if _is_rate_limit_error(
            error
        ):

            return JsonResponse(
                {
                    "error":
                        "AI token capacity is temporarily full. "
                        "LabTwin already waited and retried automatically. "
                        "Please wait about one minute and try once."
                },
                status=429,
            )

        return JsonResponse(
            {
                "error":
                    str(
                        error
                    )
            },
            status=500,
        )


# ============================================================
# NEXT QUESTION
# ============================================================

@csrf_exempt
def next_question(request):

    if request.method != "POST":
        return JsonResponse(
            {"error": "POST required"},
            status=405
        )

    try:
        state = load_state()

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

        history = state.get(
            "history",
            []
        )

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
                    "message": "All syllabus questions completed."
                })

            problem = questions[index]

            generated = generate_tests_for_question(
                problem,
                language
            )

            question = {
                "id": str(uuid.uuid4()),
                "source": "syllabus",
                "language": language,
                "topic": generated.get(
                    "concept_key",
                    "Programming"
                ),
                "concept_key": generated.get(
                    "concept_key",
                    "OTHER"
                ),
                "problem": problem,
                "tests": generated.get(
                    "tests",
                    []
                )
            }

            state["question_index"] = (
                index + 1
            )

        else:

            generated = generate_question_from_topics(
                state.get("topics", []),
                history,
                language
            )

            question = {
                "id": str(uuid.uuid4()),
                "source": "generated",
                "language": language,
                "topic": generated.get(
                    "topic",
                    "Programming"
                ),
                "concept_key": generated.get(
                    "concept_key",
                    "OTHER"
                ),
                "problem": generated.get(
                    "problem",
                    ""
                ),
                "tests": generated.get(
                    "tests",
                    []
                )
            }

        state["current_question"] = question

        history.append({
            "id": question["id"],
            "source": question["source"],
            "language": language,
            "topic": question["topic"],
            "concept_key": question["concept_key"],
            "problem": question["problem"]
        })

        state["history"] = history

        save_state(state)

        return JsonResponse({
            "finished": False,
            "id": question["id"],
            "source": question["source"],
            "language": language,
            "execution_supported": (
                language in [
                    "Python",
                    "Java",
                    "C"
                ]
            ),
            "topic": question["topic"],
            "concept_key": question["concept_key"],
            "problem": question["problem"],
            "question_number": len(history)
        })

    except Exception as error:
        print(
            "NEXT QUESTION ERROR:",
            error
        )

        return JsonResponse(
            {"error": str(error)},
            status=500
        )



# ============================================================
# REQUIRED TOPIC EVIDENCE
# ============================================================

def check_required_topic_evidence(
    topic,
    language,
    code,
):
    """
    Hidden tests prove OUTPUT correctness.

    This function checks whether the student's code
    actually demonstrates certain explicit syllabus
    techniques when the question requires them.

    Example:
        Topic = Pointer to Function

    A solution that directly calls add(), sub(), etc.
    may produce perfect output but does NOT demonstrate
    a function pointer.
    """

    topic_text = str(
        topic or ""
    ).strip()

    topic_key = (
        topic_text.casefold()
    )

    language_key = str(
        language or ""
    ).strip().casefold()


    # Remove C comments so commented-out syntax
    # cannot satisfy the evidence checker.

    source = re.sub(
        r"/\*[\s\S]*?\*/",
        " ",
        str(
            code or ""
        ),
    )

    source = re.sub(
        r"//[^\n]*",
        " ",
        source,
    )


    result = {
        "required":
            False,

        "met":
            True,

        "topic":
            topic_text,

        "evidence":
            "",

        "missing":
            "",
    }


    # Only deterministic C rules are enabled here.
    # Unknown/ambiguous topics are NOT penalized.

    if language_key != "c":

        return result


    # ========================================================
    # POINTER TO FUNCTION / FUNCTION POINTER
    # ========================================================

    if (
        "pointer to function"
        in topic_key
        or
        "function pointer"
        in topic_key
    ):

        result[
            "required"
        ] = True


        # ----------------------------------------------------
        # 1. Find typedef function-pointer aliases.
        #
        # Example:
        #
        # typedef int (*Operation)(int, int);
        # ----------------------------------------------------

        typedef_aliases = set(
            re.findall(
                r"\btypedef\b"
                r"[^;]*?"
                r"\(\s*\*\s*"
                r"([A-Za-z_]\w*)"
                r"\s*\)"
                r"\s*\([^;]*\)"
                r"\s*;",
                source,
            )
        )


        pointer_variables = set()


        # ----------------------------------------------------
        # 2. Direct function-pointer declarations.
        #
        # Example:
        #
        # int (*operation)(int, int);
        # ----------------------------------------------------

        direct_declarations = re.findall(
            r"\(\s*\*\s*"
            r"([A-Za-z_]\w*)"
            r"\s*\)"
            r"\s*\([^;{}]*\)",
            source,
        )


        for name in direct_declarations:

            # A typedef declaration gives us a TYPE name,
            # not an actual pointer variable.
            if name not in typedef_aliases:

                pointer_variables.add(
                    name
                )


        # ----------------------------------------------------
        # 3. Variables declared using typedef aliases.
        #
        # Example:
        #
        # Operation operation = NULL;
        # ----------------------------------------------------

        for alias in typedef_aliases:

            alias_pattern = (
                rf"\b{re.escape(alias)}"
                rf"\s+"
                rf"([A-Za-z_]\w*)"
                rf"\b"
            )


            for match in re.finditer(
                alias_pattern,
                source,
            ):

                variable = (
                    match.group(1)
                )

                pointer_variables.add(
                    variable
                )


        # ----------------------------------------------------
        # 4. Verify that an actual function-pointer variable
        #    is assigned a function AND invoked.
        # ----------------------------------------------------

        for name in pointer_variables:

            assignment = re.search(
                rf"\b{re.escape(name)}"
                rf"\s*=\s*"
                rf"(?:&\s*)?"
                rf"(?!NULL\b)"
                rf"(?!0\b)"
                rf"([A-Za-z_]\w*)",
                source,
            )


            direct_call = re.search(
                rf"\b{re.escape(name)}"
                rf"\s*\(",
                source,
            )


            dereferenced_call = re.search(
                rf"\(\s*\*\s*"
                rf"{re.escape(name)}"
                rf"\s*\)"
                rf"\s*\(",
                source,
            )


            if (
                assignment
                and
                (
                    direct_call
                    or
                    dereferenced_call
                )
            ):

                result[
                    "met"
                ] = True

                result[
                    "evidence"
                ] = (
                    "A function-pointer variable is "
                    "declared directly or through typedef, "
                    "assigned to a function, and invoked."
                )

                return result


        result[
            "met"
        ] = False

        result[
            "missing"
        ] = (
            "The output is correct, but the program "
            "does not demonstrate a function pointer "
            "being declared, assigned to an operation, "
            "and used to call that operation."
        )

        return result


    # ========================================================
    # POINTER TO POINTER
    # ========================================================

    if (
        "pointer to pointer"
        in topic_key
    ):

        result[
            "required"
        ] = True

        found = bool(
            re.search(
                r"\*\s*\*\s*[A-Za-z_]\w*",
                source,
            )
        )

        result[
            "met"
        ] = found

        if found:

            result[
                "evidence"
            ] = (
                "Pointer-to-pointer syntax is present."
            )

        else:

            result[
                "missing"
            ] = (
                "The required pointer-to-pointer "
                "technique is not demonstrated."
            )

        return result


    # ========================================================
    # ARRAY OF POINTERS
    # ========================================================

    if (
        "array of pointers"
        in topic_key
    ):

        result[
            "required"
        ] = True

        found = bool(
            re.search(
                r"\*\s*[A-Za-z_]\w*"
                r"\s*\[[^\]]*\]",
                source,
            )
        )

        result[
            "met"
        ] = found

        if not found:

            result[
                "missing"
            ] = (
                "The code does not demonstrate "
                "an array of pointers."
            )

        return result


    # ========================================================
    # POINTER TO STRUCTURE
    # ========================================================

    if (
        "pointer to structure"
        in topic_key
    ):

        result[
            "required"
        ] = True

        pointer_decl = bool(
            re.search(
                r"\bstruct\s+[A-Za-z_]\w*"
                r"\s*\*\s*[A-Za-z_]\w*",
                source,
            )
        )

        arrow_usage = (
            "->"
            in source
        )


        result[
            "met"
        ] = (
            pointer_decl
            and
            arrow_usage
        )


        if not result[
            "met"
        ]:

            result[
                "missing"
            ] = (
                "The code does not clearly demonstrate "
                "a structure pointer being used with ->."
            )

        return result


    # ========================================================
    # DYNAMIC MEMORY
    # ========================================================

    if (
        "dynamic memory"
        in topic_key
    ):

        result[
            "required"
        ] = True

        found = bool(
            re.search(
                r"\b(?:malloc|calloc|realloc)\s*\(",
                source,
            )
        )

        result[
            "met"
        ] = found

        if not found:

            result[
                "missing"
            ] = (
                "The code produces output without "
                "demonstrating dynamic memory allocation."
            )

        return result


    # ========================================================
    # PASSING POINTERS TO FUNCTIONS
    # ========================================================

    if (
        "passing pointers to functions"
        in topic_key
    ):

        result[
            "required"
        ] = True

        found = bool(
            re.search(
                r"[A-Za-z_]\w*\s+"
                r"[A-Za-z_]\w*\s*"
                r"\([^)]*\*\s*[A-Za-z_]\w*[^)]*\)",
                source,
            )
        )

        result[
            "met"
        ] = found

        if not found:

            result[
                "missing"
            ] = (
                "The code does not show a pointer "
                "being passed as a function parameter."
            )

        return result


    # ========================================================
    # POINTER ARRAY ACCESS
    # ========================================================

    if (
        "accessing array elements using pointers"
        in topic_key
    ):

        result[
            "required"
        ] = True

        found = bool(
            re.search(
                r"\*\s*\(\s*[A-Za-z_]\w*"
                r"\s*\+\s*[^)]+\)",
                source,
            )
        )

        result[
            "met"
        ] = found

        if not found:

            result[
                "missing"
            ] = (
                "The code does not demonstrate "
                "array access through pointer "
                "dereferencing."
            )

        return result


    # ========================================================
    # OPEN / CLOSE FILE
    # ========================================================

    if (
        "opening & closing a file"
        in topic_key
        or
        "opening and closing a file"
        in topic_key
    ):

        result[
            "required"
        ] = True

        found = (
            bool(
                re.search(
                    r"\bfopen\s*\(",
                    source,
                )
            )
            and
            bool(
                re.search(
                    r"\bfclose\s*\(",
                    source,
                )
            )
        )

        result[
            "met"
        ] = found

        if not found:

            result[
                "missing"
            ] = (
                "The code does not demonstrate both "
                "opening and closing a file."
            )

        return result


    # ========================================================
    # FILE READ / WRITE
    # ========================================================

    if (
        "writing to and reading from a file"
        in topic_key
    ):

        result[
            "required"
        ] = True

        found = bool(
            re.search(
                r"\b(?:fread|fwrite|fscanf|fprintf|"
                r"fgets|fputs)\s*\(",
                source,
            )
        )

        result[
            "met"
        ] = found

        if not found:

            result[
                "missing"
            ] = (
                "No file read/write operation "
                "is demonstrated."
            )

        return result


    # ========================================================
    # SPECIFIC FILE LIBRARY FUNCTIONS
    # ========================================================

    if (
        "fseek"
        in topic_key
        or
        "ftell"
        in topic_key
        or
        "fread"
        in topic_key
        or
        "fwrite"
        in topic_key
    ):

        result[
            "required"
        ] = True

        found = bool(
            re.search(
                r"\b(?:fseek|ftell|fread|fwrite)\s*\(",
                source,
            )
        )

        result[
            "met"
        ] = found

        if not found:

            result[
                "missing"
            ] = (
                "The required C file-library "
                "operation is not demonstrated."
            )

        return result


    # Unknown / broad topics remain output-tested only.
    # This avoids false negatives.

    return result



# ============================================================
# ANALYZE
# ============================================================

@csrf_exempt
@record_response("analysis")
def analyze_code(request):

    if request.method != "POST":
        return JsonResponse(
            {"error": "POST required"},
            status=405
        )

    try:
        data = json.loads(
            request.body
        )

        code = data.get(
            "code",
            ""
        ).strip()

        question = get_current_question(
            data.get(
                "question_id"
            ),
            student_id=data.get(
                "student_id"
            ),
        )

        if not question:
            return JsonResponse(
                {"error": "Question not found."},
                status=400
            )

        language = question.get(
            "language",
            "Python"
        )

        score, results = run_tests(
            code,
            question["tests"],
            language
        )
        record_execution(request, results)

        # ==================================================
        # CONCEPT-EVIDENCE-GUARD
        # ==================================================

        topic_evidence = (
            check_required_topic_evidence(
                question.get(
                    "topic",
                    "",
                ),
                language,
                code,
            )
        )


        if (
            score == 100
            and
            topic_evidence[
                "required"
            ]
            and
            not topic_evidence[
                "met"
            ]
        ):

            missing_message = (
                topic_evidence.get(
                    "missing"
                )
                or
                (
                    "The required syllabus technique "
                    "was not demonstrated."
                )
            )


            return JsonResponse({
                "test_score":
                    100,

                "functional_test_score":
                    100,

                "concept_requirement_met":
                    False,

                "topic_evidence":
                    topic_evidence,

                "test_results":
                    results,

                "diagnosis": {

                    "has_misconception":
                        True,

                    "concept_key":
                        question[
                            "concept_key"
                        ],

                    "misconception":
                        missing_message,

                    "error_category":
                        "topic_concept",

                    "topic_related":
                        True,

                    "topic_misconception":
                        missing_message,

                    "explanation":
                        (
                            "All hidden output tests passed, "
                            "but output correctness alone does "
                            "not prove the required syllabus "
                            "concept was used. "
                            +
                            missing_message
                        ),

                    "hint":
                        (
                            "Keep your working logic, but modify "
                            "the solution so it explicitly uses "
                            "the required technique for the topic: "
                            +
                            str(
                                question.get(
                                    "topic",
                                    "current topic",
                                )
                            )
                            +
                            "."
                        ),
                },
            })


        if score == 100:

            return JsonResponse({
                "test_score":
                    100,

                "functional_test_score":
                    100,

                "concept_requirement_met":
                    True,

                "topic_evidence":
                    topic_evidence,

                "test_results":
                    results,

                "diagnosis": {

                    "has_misconception":
                        False,

                    "concept_key":
                        question[
                            "concept_key"
                        ],

                    "misconception":
                        None,

                    "error_category":
                        "none",

                    "topic_related":
                        False,

                    "topic_misconception":
                        "",

                    "explanation":
                        (
                            "The solution correctly solves the "
                            "problem, passes all hidden tests, "
                            "and satisfies the required topic "
                            "evidence when a deterministic check "
                            "is available."
                        ),

                    "hint":
                        "No correction is needed.",
                },
            })


        task = Task(
            description=f"""
LANGUAGE:
{language}

QUESTION:
{question["problem"]}

CONCEPT:
{question["concept_key"]}

STUDENT CODE:
{code}

REAL TEST RESULTS:
{json.dumps(private_summary(results), indent=2)}

Identify the SINGLE MAIN reason the program failed.

IMPORTANT CLASSIFICATION RULE:
The programming QUESTION TOPIC is:
{question.get("topic", "Programming")}

A coding error is NOT automatically a misconception about the question topic.
For example, a wrong loop index inside a Pointer-to-Pointer problem is an
algorithm/indexing error unless the student's use of pointer-to-pointer is
itself wrong. Markdown backticks inside C source are formatting/syntax errors,
not pointer misconceptions.

Classify the failure into ONE error_category:
- topic_concept
- algorithm_logic
- syntax_formatting
- runtime_memory
- input_output
- other

Set topic_related=true ONLY when the failure demonstrates misunderstanding of
the exact syllabus topic. If topic_related=false, topic_misconception MUST be
an empty string.

Return ONLY JSON:

{{
    "has_misconception": true,
    "concept_key": "{question["concept_key"]}",
    "misconception": "Main coding mistake",
    "error_category": "algorithm_logic",
    "topic_related": false,
    "topic_misconception": "",
    "explanation": "Why the program failed",
    "hint": "Helpful clue"
}}
""",
            expected_output="Valid JSON",
            agent=analyzer_agent
        )

        crew = Crew(
            agents=[analyzer_agent],
            tasks=[task],
            process=Process.sequential,
            verbose=False
        )

        diagnosis = clean_json_output(
            kickoff_with_retry(crew, label="views.py").raw
        )

        diagnosis[
            "has_misconception"
        ] = True

        allowed_categories = {
            "topic_concept",
            "algorithm_logic",
            "syntax_formatting",
            "runtime_memory",
            "input_output",
            "other",
        }

        category = str(
            diagnosis.get(
                "error_category",
                "other"
            )
            or "other"
        ).strip().lower()

        if category not in allowed_categories:
            category = "other"

        diagnosis[
            "error_category"
        ] = category

        topic_related = bool(
            diagnosis.get(
                "topic_related",
                False
            )
        )

        # ==================================================
        # DETERMINISTIC TOPIC-RELATION RECONCILIATION
        #
        # An algorithmic mistake can still be evidence about
        # the selected syllabus topic.
        #
        # Example:
        # Topic = Arrays
        # Mistake = wrong array index during traversal/reversal
        #
        # Keep error_category = algorithm_logic, but mark the
        # misconception as topic-related.
        # ==================================================

        topic_name = str(
            question.get(
                "topic",
                ""
            )
            or ""
        ).strip().lower()

        diagnosis_text = " ".join([
            str(
                diagnosis.get(
                    "misconception",
                    ""
                )
                or ""
            ),
            str(
                diagnosis.get(
                    "explanation",
                    ""
                )
                or ""
            ),
        ]).lower()

        if (
            topic_name == "arrays"
            and
            category == "algorithm_logic"
            and
            any(
                signal in diagnosis_text
                for signal in (
                    "array index",
                    "array indices",
                    "index 0",
                    "index 1",
                    "n-1",
                    "n - 1",
                    "n-2",
                    "n - 2",
                    "last element",
                    "first element",
                    "array element",
                    "travers",
                    "reverse"
                )
            )
        ):
            topic_related = True

        # LABTWIN_TOPIC_RELATION_RECONCILIATION_V2
        # ==================================================
        # ERROR TYPE != TOPIC RELATION
        #
        # algorithm_logic can still be evidence about the
        # selected syllabus topic.
        #
        # Examples:
        # Arrays + wrong traversal index -> related
        # Pointer Arithmetic + wrong pointer increment -> related
        # Pointer-to-Pointer + unrelated loop typo -> unrelated
        # ==================================================

        topic_name = " ".join(
            str(
                question.get(
                    "topic",
                    ""
                )
                or ""
            )
            .strip()
            .lower()
            .replace("-", " ")
            .split()
        )

        diagnosis_text = " ".join([
            str(
                diagnosis.get(
                    "misconception",
                    ""
                )
                or ""
            ),
            str(
                diagnosis.get(
                    "explanation",
                    ""
                )
                or ""
            ),
            str(
                diagnosis.get(
                    "hint",
                    ""
                )
                or ""
            ),
        ]).lower()


        topic_signal_map = {

            "arrays": (
                "array index",
                "array indices",
                "array element",
                "first element",
                "last element",
                "index 0",
                "index 1",
                "n - 1",
                "n-1",
                "n - 2",
                "n-2",
                "array traversal",
                "reverse loop",
            ),

            "pointers": (
                "dereference",
                "dereferencing",
                "address operator",
                "pointer variable",
                "pointer value",
                "address of",
            ),

            "pointer arithmetic": (
                "pointer arithmetic",
                "pointer increment",
                "pointer decrement",
                "pointer offset",
                "increment the pointer",
                "decrement the pointer",
            ),

            "passing pointers to functions": (
                "pointer parameter",
                "pointer argument",
                "pass the address",
                "passing pointer",
                "passing the pointer",
            ),

            "accessing array elements using pointers": (
                "array element",
                "pointer traversal",
                "dereference",
                "pointer access",
            ),

            "processing strings using pointers": (
                "string pointer",
                "character pointer",
                "char pointer",
                "string traversal",
                "null terminator",
            ),

            "pointer to pointer": (
                "pointer to pointer",
                "double pointer",
                "dereference twice",
                "**",
            ),

            "array of pointers": (
                "array of pointers",
                "pointer array",
                "array containing pointers",
            ),

            "pointer to function": (
                "function pointer",
                "pointer to function",
                "assign the function",
            ),

            "function pointers": (
                "function pointer",
                "pointer to function",
                "assign the function",
            ),

            "pointer to structure": (
                "structure pointer",
                "pointer to structure",
                "->",
                "arrow operator",
            ),

            "dynamic memory allocation": (
                "malloc",
                "calloc",
                "realloc",
                "free",
                "allocated memory",
                "dynamic memory",
            ),
        }


        signals = topic_signal_map.get(
            topic_name,
            ()
        )

        if (
            category
            in {
                "algorithm_logic",
                "topic_concept",
                "runtime_memory",
            }
            and
            signals
            and
            any(
                signal in diagnosis_text
                for signal in signals
            )
        ):
            topic_related = True


        # --------------------------------------------------
        # POINTER ARITHMETIC EVIDENCE RECONCILIATION
        #
        # Examples:
        #   a + n - 2 instead of a + n - 1
        #   wrong left/right pointer movement
        #   incorrect pointer increment/decrement
        # --------------------------------------------------

        if (
            topic_name == "pointer arithmetic"
            and
            category in {
                "algorithm_logic",
                "topic_concept",
                "runtime_memory",
            }
            and
            "pointer" in diagnosis_text
            and
            any(
                signal in diagnosis_text
                for signal in (
                    "right pointer",
                    "left pointer",
                    "pointer starts",
                    "pointer start",
                    "pointer position",
                    "last element",
                    "first element",
                    "a +",
                    "a+",
                    "n - 1",
                    "n-1",
                    "n - 2",
                    "n-2",
                    "increment",
                    "decrement",
                    "offset",
                )
            )
        ):
            topic_related = True

        # LABTWIN_POINTER_ARITHMETIC_EVIDENCE_FINAL
        # ==================================================
        # POINTER ARITHMETIC TOPIC EVIDENCE
        #
        # Example:
        #   wrong:  a + n - 2
        #   right:  a + n - 1
        #
        # This is algorithm_logic AND topic-related because
        # the incorrect pointer offset is the reason the
        # algorithm accesses the wrong array position.
        # ==================================================

        if (
            topic_name == "pointer arithmetic"
            and
            category in {
                "algorithm_logic",
                "topic_concept",
                "runtime_memory",
            }
            and
            any(
                signal in diagnosis_text
                for signal in (
                    "right pointer",
                    "left pointer",
                    "pointer initialization",
                    "pointer position",
                    "pointer starts",
                    "pointer start",
                    "pointer offset",
                    "second-to-last",
                    "second to last",
                    "last element",
                    "first element",
                    "a + n - 2",
                    "a+n-2",
                    "n - 2",
                    "n-2",
                    "a + n - 1",
                    "a+n-1",
                    "n - 1",
                    "n-1",
                    "pointer increment",
                    "pointer decrement",
                    "increment the pointer",
                    "decrement the pointer",
                )
            )
        ):
            topic_related = True

            if not str(
                diagnosis.get(
                    "topic_misconception",
                    ""
                )
                or ""
            ).strip():

                diagnosis[
                    "topic_misconception"
                ] = str(
                    diagnosis.get(
                        "misconception",
                        ""
                    )
                    or
                    "Incorrect pointer arithmetic or pointer offset."
                ).strip()


        diagnosis[
            "topic_related"
        ] = topic_related

        if topic_related:
            topic_misconception = str(
                diagnosis.get(
                    "topic_misconception",
                    ""
                )
                or diagnosis.get(
                    "misconception",
                    ""
                )
                or ""
            ).strip()
        else:
            topic_misconception = ""

        diagnosis[
            "topic_misconception"
        ] = topic_misconception

        return JsonResponse({
            "test_score": score,
            "test_results": results,
            "diagnosis": diagnosis
        })

    except Exception as error:
        print(
            "ANALYZE ERROR:",
            error
        )

        return JsonResponse(
            {"error": str(error)},
            status=500
        )


# ============================================================
# TUTOR
# ============================================================

@csrf_exempt
def tutor_help(request):

    if request.method != "POST":
        return JsonResponse(
            {"error": "POST required"},
            status=405
        )

    try:
        data = json.loads(
            request.body or "{}"
        )

        concept = str(
            data.get(
                "concept_key",
                "OTHER"
            )
            or "OTHER"
        ).strip()

        misconception = str(
            data.get(
                "misconception",
                ""
            )
            or ""
        ).strip()

        question = get_current_question(
            data.get("question_id")
        )

        question = question or {}

        language = str(
            question.get("language")
            or data.get("language")
            or "Python"
        ).strip()

        topic = str(
            question.get("topic")
            or data.get("topic")
            or concept
            or "General"
        ).strip()

        problem = str(
            question.get("problem")
            or data.get("problem")
            or ""
        ).strip()


        # ----------------------------------------------------
        # FALLBACKS
        # ----------------------------------------------------

        if misconception:

            fallback_hint = (
                "Focus on the identified mistake: "
                + misconception
                + " Correct that part of your "
                + language
                + " logic without changing the required topic."
            )

            fallback_viva = (
                "In "
                + language
                + ", explain what was wrong in your original "
                + topic
                + " approach and why your correction fixes it."
            )

        else:

            fallback_hint = (
                "Review how "
                + topic
                + " is used in this "
                + language
                + " program."
            )

            fallback_viva = (
                "In "
                + language
                + ", explain how "
                + topic
                + " is used in this program and why it is "
                + "appropriate here."
            )

        fallback_practice = (
            "Write another short "
            + language
            + " program that directly practices "
            + topic
            + " using standard input and output."
        )

        fallback_expected = [
            "Correct understanding of " + topic,
            "Connection between the explanation and the code",
            "Why the corrected approach works"
        ]


        # ----------------------------------------------------
        # AI TUTOR
        # ----------------------------------------------------

        task = Task(
            description=f"""
You are tutoring a student on ONE programming lab question.

CURRENT PROGRAMMING LANGUAGE:
{language}

EXACT SYLLABUS TOPIC:
{topic}

CURRENT PROGRAMMING PROBLEM:
{problem}

DETECTED CONCEPT:
{concept}

DETECTED MISCONCEPTION:
{misconception}

LANGUAGE LOCK -- NON-NEGOTIABLE:

1. Every hint, practice problem and viva question MUST use
   exactly {language}.
2. NEVER mention Java when the current language is C.
3. NEVER mention Python when the current language is C.
4. NEVER switch programming languages.
5. The viva must be directly related to THIS problem,
   THIS topic and the identified mistake.
6. Do not ask a generic viva from another language.
7. Do not reveal the complete corrected program.
8. Keep the hint short and useful.

Generate:
- one progressive hint
- one short related practice problem
- one clear viva question
- exactly three concise expected concepts for that viva

Return ONLY valid JSON:

{{
    "hint": "Short language-correct hint",
    "practice_problem": "Short language-correct practice problem",
    "viva_question": "One language-correct viva question",
    "expected_concepts": [
        "Concept 1",
        "Concept 2",
        "Concept 3"
    ]
}}
""",
            expected_output="Valid JSON",
            agent=tutor_agent
        )

        try:

            crew = Crew(
                agents=[tutor_agent],
                tasks=[task],
                process=Process.sequential,
                verbose=False
            )

            result = clean_json_output(
                kickoff_with_retry(crew, label="views.py").raw
            )

            if not isinstance(result, dict):
                result = {}

        except Exception as ai_error:

            print(
                "TUTOR AI ERROR - USING SAFE FALLBACK:",
                ai_error
            )

            result = {}


        hint = str(
            result.get("hint")
            or fallback_hint
        ).strip()

        practice_problem = str(
            result.get("practice_problem")
            or fallback_practice
        ).strip()

        viva_question = str(
            result.get("viva_question")
            or fallback_viva
        ).strip()

        expected_concepts = result.get(
            "expected_concepts",
            fallback_expected
        )

        if not isinstance(
            expected_concepts,
            list
        ):

            expected_concepts = (
                fallback_expected
            )

        expected_concepts = [
            str(item).strip()
            for item in expected_concepts
            if str(item).strip()
        ][:3]

        while len(expected_concepts) < 3:

            expected_concepts.append(
                fallback_expected[
                    len(expected_concepts)
                ]
            )


        # ----------------------------------------------------
        # HARD LANGUAGE SAFETY CHECK
        # ----------------------------------------------------

        language_lower = (
            language.lower()
        )

        if language_lower == "c":

            forbidden = [
                "java",
                "python",
                "javascript",
                "c++"
            ]

        elif language_lower == "java":

            forbidden = [
                "python",
                "gcc",
                "c language",
                "c program"
            ]

        elif language_lower == "python":

            forbidden = [
                "java",
                "gcc",
                "c language",
                "c program"
            ]

        else:

            forbidden = []


        def wrong_language(value):

            text = str(
                value
            ).lower()

            return any(
                word in text
                for word in forbidden
            )


        if wrong_language(hint):
            hint = fallback_hint

        if wrong_language(
            practice_problem
        ):
            practice_problem = (
                fallback_practice
            )

        if wrong_language(
            viva_question
        ):
            viva_question = (
                fallback_viva
            )

        if any(
            wrong_language(item)
            for item in expected_concepts
        ):
            expected_concepts = (
                fallback_expected
            )


        # ----------------------------------------------------
        # FINAL DIAGNOSIS GROUNDING
        #
        # The viva must verify the mistake actually diagnosed
        # from the student's code. It must not invent another
        # weakness such as overflow, initialization, etc.
        # ----------------------------------------------------

        if misconception and not locals().get("passed_code", False):

            viva_question = (
                "In "
                + language
                + ", explain why this diagnosed "
                + topic
                + " mistake causes incorrect output and how "
                + "you would correct the relevant logic: "
                + misconception
            )


        return JsonResponse({
            "hint":
                hint,

            "practice_problem":
                practice_problem,

            "viva_question":
                viva_question,

            "expected_concepts":
                expected_concepts,

            "language":
                language,

            "topic":
                topic
        })


    except Exception as error:

        print(
            "TUTOR ERROR:",
            error
        )

        return JsonResponse(
            {"error": str(error)},
            status=500
        )


@csrf_exempt
@record_response("retest")
def evaluate_code(request):

    if request.method != "POST":
        return JsonResponse(
            {"error": "POST required"},
            status=405
        )

    try:
        data = json.loads(
            request.body or "{}"
        )

        question = get_current_question(
            data.get(
                "question_id"
            ),
            student_id=data.get(
                "student_id"
            ),
        )

        if not question:
            return JsonResponse(
                {"error": "Question not found."},
                status=400
            )

        language = question.get(
            "language",
            "Python"
        )

        corrected_code = data.get(
            "code",
            ""
        ).strip()

        viva_answer = data.get(
            "viva_answer",
            ""
        ).strip()

        viva_question = data.get(
            "viva_question",
            ""
        ).strip()

        misconception = data.get(
            "misconception",
            ""
        )

        initial_score = float(
            data.get(
                "initial_score",
                0
            )
            or 0
        )

        hint_level = int(
            data.get(
                "hint_level",
                0
            )
            or 0
        )

        hint_level = max(
            0,
            min(
                3,
                hint_level
            )
        )

        # LABTWIN_PASSED_CODE_EVALUATION_NORMALIZATION
        # A correct first attempt has no diagnosed coding mistake.
        # The viva must evaluate the requested concept only.
        if initial_score >= 100:
            misconception = ""

        verification = bool(
            data.get(
                "verification",
                False
            )
        )

        expected_concepts = data.get(
            "expected_concepts",
            []
        )

        if not isinstance(
            expected_concepts,
            list
        ):
            expected_concepts = []

        expected_concepts = [
            str(item).strip()
            for item in expected_concepts
            if str(item).strip()
        ][:4]

        retest_score, retest_results = run_tests(
            corrected_code,
            question["tests"],
            language
        )
        record_execution(request, retest_results)

        # ==================================================
        # RETEST-CONCEPT-EVIDENCE-GUARD
        # ==================================================

        functional_retest_score = (
            retest_score
        )

        retest_topic_evidence = (
            check_required_topic_evidence(
                question.get(
                    "topic",
                    "",
                ),
                language,
                corrected_code,
            )
        )


        if (
            retest_topic_evidence[
                "required"
            ]
            and
            not retest_topic_evidence[
                "met"
            ]
        ):

            # Functional outputs may all be correct,
            # but the required technique is still absent.
            #
            # Keep the functional score separately while
            # preventing concept-free code from becoming
            # mastered.

            retest_score = min(
                retest_score,
                67,
            )


        task = Task(
            description=f"""
You are a fair university programming-lab viva examiner.

Evaluate MEANING, not exact wording.

PROGRAMMING LANGUAGE:
{language}

EXACT TOPIC:
{question.get("topic", "")}

PROGRAMMING QUESTION:
{question["problem"]}

VIVA QUESTION:
{viva_question}

PREVIOUS MISCONCEPTION:
{misconception}

STUDENT ANSWER:
{viva_answer}

SUGGESTED CONCEPTS FROM THE TUTOR:
{json.dumps(expected_concepts, indent=2)}

The suggested concepts are guidance only. They are NOT a rigid
keyword checklist. Ignore any suggested item that is ambiguous,
duplicated, factually wrong, or not reasonably requested by the
viva question.

Rate these FOUR dimensions from 0 to 4:

1. core_correctness
   Does the student correctly understand what the concept IS?

2. mechanism
   Does the student explain how the concept works or is used?

3. application
   Does the student connect it to the program, an example,
   purpose, advantage, or realistic use?

4. question_coverage
   How completely did the answer address what the viva question
   actually asked?

RATING SCALE:
4 = strong and clearly correct
3 = correct with a minor omission
2 = meaningful partial understanding
1 = small fragment of correct understanding
0 = absent or fundamentally wrong

CALIBRATION RULES:
- A correct paraphrase counts fully.
- A correct applied example counts as conceptual evidence.
- Missing one detail must NOT erase correct understanding elsewhere.
- Missing exact declaration syntax affects question_coverage only,
  unless the viva question explicitly asks for syntax.
- If the answer correctly states what the concept is, how it is
  used, and gives a correct application, the first three dimensions
  should normally be at least 3.
- Missing information is NOT a contradiction.
- A contradiction exists only when the student explicitly states
  something that conflicts with a central fact.
- Do not compare "pointer to a function" with "function pointer
  variable"; those expressions refer to the same basic concept.
- Do NOT return a percentage or mastery status. Django calculates it.

Return ONLY valid JSON:

{{
    "dimensions": {{
        "core_correctness": {{
            "rating": 4,
            "reason": "Short evidence-based reason"
        }},
        "mechanism": {{
            "rating": 4,
            "reason": "Short evidence-based reason"
        }},
        "application": {{
            "rating": 4,
            "reason": "Short evidence-based reason"
        }},
        "question_coverage": {{
            "rating": 3,
            "reason": "Short evidence-based reason"
        }}
    }},
    "central_contradiction": false,
    "contradictions": [],
    "missing_concepts": [],
    "reason": "One concise, fair overall feedback sentence"
}}
""",
            expected_output="Four-dimension semantic viva assessment",
            agent=evaluator_agent
        )

        crew = Crew(
            agents=[evaluator_agent],
            tasks=[task],
            process=Process.sequential,
            verbose=False
        )

        rubric = clean_json_output(
            kickoff_with_retry(crew, label="views.py").raw
        )

        dimensions = rubric.get(
            "dimensions",
            {}
        )

        if not isinstance(
            dimensions,
            dict
        ):
            dimensions = {}

        dimension_weights = {
            "core_correctness": 0.35,
            "mechanism": 0.30,
            "application": 0.20,
            "question_coverage": 0.15
        }

        normalized_dimensions = {}

        for name, weight in dimension_weights.items():
            item = dimensions.get(
                name,
                {}
            )

            if not isinstance(
                item,
                dict
            ):
                item = {}

            try:
                rating = int(
                    item.get(
                        "rating",
                        0
                    )
                )
            except Exception:
                rating = 0

            rating = max(
                0,
                min(
                    4,
                    rating
                )
            )

            normalized_dimensions[
                name
            ] = {
                "rating": rating,
                "reason": str(
                    item.get(
                        "reason",
                        ""
                    )
                ).strip(),
                "weight": weight
            }

        understanding = round(
            sum(
                (
                    item["rating"]
                    / 4
                    * item["weight"]
                    * 100
                )
                for item in normalized_dimensions.values()
            )
        )

        # Calibration floors prevent one omitted detail from
        # destroying otherwise clear conceptual understanding.
        core_rating = normalized_dimensions[
            "core_correctness"
        ]["rating"]

        mechanism_rating = normalized_dimensions[
            "mechanism"
        ]["rating"]

        application_rating = normalized_dimensions[
            "application"
        ]["rating"]

        if (
            core_rating >= 3
            and mechanism_rating >= 3
        ):
            understanding = max(
                understanding,
                70
            )

        if (
            core_rating == 4
            and mechanism_rating >= 3
            and application_rating >= 2
        ):
            understanding = max(
                understanding,
                80
            )

        contradictions = rubric.get(
            "contradictions",
            []
        )

        if not isinstance(
            contradictions,
            list
        ):
            contradictions = []

        contradictions = [
            str(item).strip()
            for item in contradictions
            if str(item).strip()
        ]

        central_contradiction = bool(
            rubric.get(
                "central_contradiction",
                False
            )
        )

        if (
            central_contradiction
            and contradictions
        ):
            understanding = min(
                understanding,
                35
            )

        understanding = max(
            0,
            min(
                100,
                understanding
            )
        )

        missing = rubric.get(
            "missing_concepts",
            []
        )

        if not isinstance(
            missing,
            list
        ):
            missing = []

        missing = [
            str(item).strip()
            for item in missing
            if str(item).strip()
        ][:4]

        partial = [
            name.replace(
                "_",
                " "
            ).title()
            for name, item
            in normalized_dimensions.items()
            if item["rating"] == 2
        ]

        covered = [
            name.replace(
                "_",
                " "
            ).title()
            for name, item
            in normalized_dimensions.items()
            if item["rating"] >= 3
        ]

        # CONCEPT-EVIDENCE-FEEDBACK

        if (
            retest_topic_evidence[
                "required"
            ]
            and
            not retest_topic_evidence[
                "met"
            ]
        ):

            rubric[
                "reason"
            ] = (
                "Functional output may be correct, but "
                "the corrected code still does not "
                "demonstrate the required technique for "
                f'{question.get("topic", "this topic")}. '
                +
                (
                    retest_topic_evidence.get(
                        "missing"
                    )
                    or
                    ""
                )
            )


        if retest_score < 80:
            status = "Needs Coding Practice"

        elif understanding < 50:
            status = "Needs Practice"

        elif understanding < 75:
            status = "Needs Verification"

        elif verification:
            status = "Mastered"

        else:
            status = "Needs Verification"

        independence_score = max(
            10,
            100 - (
                30 * hint_level
            )
        )

        verification_score = (
            100
            if (
                verification
                and retest_score >= 80
                and understanding >= 75
                and hint_level <= 1
            )
            else 0
        )

        topic_evidence_score = round(
            (0.35 * initial_score)
            + (0.25 * understanding)
            + (0.15 * retest_score)
            + (0.15 * verification_score)
            + (0.10 * independence_score),
            1
        )

        if not verification:
            topic_evidence_score = min(
                topic_evidence_score,
                79.0
            )

        evaluation = {
            "status": status,
            "score": understanding,
            "reason": str(
                rubric.get(
                    "reason",
                    ""
                )
            ).strip(),
            "covered_concepts": covered,
            "partial_concepts": partial,
            "missing_concepts": missing,
            "contradictions": contradictions,
            "central_contradiction": central_contradiction,
            "dimensions": normalized_dimensions
        }

        return JsonResponse({
            "retest_score": retest_score,

            "functional_retest_score":
                functional_retest_score,

            "concept_requirement_met":
                retest_topic_evidence[
                    "met"
                ],

            "topic_evidence":
                retest_topic_evidence,
            "retest_results": retest_results,
            "evaluation": evaluation,
            "initial_score": initial_score,
            "hint_level": hint_level,
            "verification": verification,
            "topic_evidence_score": topic_evidence_score,
            "lab_readiness": topic_evidence_score
        })

    except Exception as error:
        print(
            "EVALUATE ERROR:",
            error
        )

        return JsonResponse(
            {"error": str(error)},
            status=500
        )
