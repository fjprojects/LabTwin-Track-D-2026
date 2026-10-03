# Track D demo: source → assessment → evidence

The recorded release demonstration is a little over three minutes and includes English captions: [MP4](demo/labtwin-track-d-demo.mp4), [original WebM](demo/labtwin-track-d-demo.webm), [English SRT](demo/labtwin-track-d-demo.srt). It shows actual application actions and measured outputs. YouTube upload is still required by the supplied submission guidelines; public or unlisted is allowed, private is not.

## Prepare the normal application

Install/migrate/build as in the README, including the separate evaluation virtual environment and ffmpeg/Poppler/Tesseract. For a small trusted demo, set `.env`:

```dotenv
LABTWIN_DEMO_ENABLED=true
LABTWIN_PROCESS_INLINE=true
LABTWIN_EMBEDDING_BACKEND=hash
```

Set `LABTWIN_EVALUATOR_PYTHON` to the absolute evaluation interpreter. Start the Django backend and React frontend. With inline processing disabled, run both material and evaluation workers.

Create/sign into a teacher account. Open **Demo Mode → Prepare guided demo**. This creates a teacher-owned demo classroom/course and processes three original files through the real ingestion pipeline. It also creates a separate enrolled demo learner, assignment and source-linked question pool. Real students, courses and existing databases are not reset.

Fixtures are `Data-Structures-Notes.pdf`, `Linked-Lists.pptx` and `Lecture-4.webm`. The PDF and slides contain native labelled boxes/arrows; the video embeds timestamped captions. These are extracted automatically. The fixture video has no spoken narration; do not describe its embedded-caption extraction as a live speech-transcription test. Generic raster vision and speech require configured live providers.

## The 17-step workflow

Allow roughly 3–8 minutes. The checklist displays actual completed conditions and does not mark a step complete just because its button was clicked.

| Step | Action | Evidence shown |
|---|---|---|
| 1 | Create/open teacher classroom (Demo Mode can prepare one) | Existing teacher auth, private class and course |
| 2 | Upload/process PDF + slide deck + lecture video | Three ready materials in the same knowledge base |
| 3 | Explore materials and diagram source | Text, native visual relationships, topics/concepts, source pages/slides/timestamps |
| 4 | Enter isolated student preview and click **Ask demo question** | A real source retrieval and course-backed answer |
| 5 | Click page, slide and lecture citations | Exact private PDF page, reconstructed slide/figure, lecture seek near 0:10 |
| 6 | Click **Ask off-material question** | Insufficient-material response without invented course citations |
| 7 | Click **Start demo assessment** | Verified source-supported diagnostic MCQ |
| 8 | Inspect question metadata | Topic, source, difficulty and verification label |
| 9 | Answer and submit | Actual score, explanation, citation and BKT change |
| 10 | Click **Start demo assignment → Run hidden checks** | Real C execution fails; private test cases remain hidden |
| 11 | Click **Hint 1**, **Hint 2**, optionally **Hint 3** | Conceptual → specific → pseudocode help, with relevant resources |
| 12 | Retry with the teacher-allowed example and run checks | Real successful retest, retained first submission and mastery update |
| 13 | Click **Generate adaptive follow-up** | Question selected from updated weaknesses/mastery |
| 14 | Expand **Why am I getting this question?** | Recorded conceptual evidence and source recommendation |
| 15 | Complete the follow-up | Saved response, retest and model history |
| 16 | **Return to teacher**, click improvement insight | Supporting student records, mastery history, attempts/hints/viva and CSV export |
| 17 | Click **Run evaluation** | Newly executed DeepEval results, cases, three profile sessions and JSON export |

The demo teacher explicitly allows full examples. That permission does not change other course settings. In normal practice, complete solutions stay unavailable unless the teacher permits them. Activity events can prompt a fresh conceptual viva question; they never label cheating.

Use **Assessments** to demonstrate topic/weak-topic/module scopes and short/numerical formats. **Mastery Map** exposes the graph, history, mistakes and resources. **My Courses** offers lecture search, chapters and **Ask this lecture**. **Progress** summarizes supported strengths/weaknesses and resources opened.

## Browser regression and recording

The automated demo uses `scripts/e2e_server.py`, a **test-only** local server. It uses disposable SQLite/private storage, MD5 test hashing and stubs only the old remote CrewAI handlers. Authentication/classroom logic, new offline source tutoring, extraction/Chroma, programming runners, assessments, BKT and DeepEval are real. Never expose it publicly or use a production database.

With application/evaluator environments installed and the frontend already built, install optional Playwright outside the project repository:

```bash
npm install --prefix /tmp/labtwin-playwright playwright
NODE_PATH=/tmp/labtwin-playwright/node_modules /tmp/labtwin-playwright/node_modules/.bin/playwright install chromium
```

From the project root with the application environment activated:

```bash
export NODE_PATH=/tmp/labtwin-playwright/node_modules
export LABTWIN_TEST_EVALUATOR_PYTHON="$PWD/.venv-evaluation/bin/python"
export LABTWIN_E2E_DATABASE=/tmp/labtwin-demo-check.sqlite3
python scripts/e2e_server.py
```

In another terminal with the same variables/environment, from the project root:

```bash
node scripts/e2e_learning.cjs
node scripts/e2e_classrooms.cjs
```

The normal classroom check asserts decoded media frames/audio. A restricted network can explicitly run `LABTWIN_E2E_SIGNALING_ONLY=1 node scripts/e2e_classrooms.cjs`; that checks consent, offers/answers, tracks, access and revocation but does not claim media transport was verified. The default full check remains enabled for deployment.

To record the actual learning workflow with English overlays and SRT, set an absolute staging directory (the script deliberately pauses at checkpoints):

```bash
LABTWIN_E2E_RECORD_DIR=/tmp/labtwin-demo-recording node scripts/e2e_learning.cjs
ffmpeg -i /tmp/labtwin-demo-recording/labtwin-track-d-demo.webm -c:v libx264 -crf 26 -pix_fmt yuv420p -movflags +faststart /tmp/labtwin-demo-recording/labtwin-track-d-demo.mp4
```

Publish only a recording whose browser check exits successfully. Inspect key frames/captions and use ffprobe to confirm 3–10 minute duration. Copy the completed video and SRT to `docs/demo/` when preparing a release. No provider result or metric is painted into the application; overlays provide narration only.

## Submission checks

Use the audit and judging report for remaining gaps. Supply the upgraded public GitHub commit/README, upload the English-captioned video to YouTube as public/unlisted, verify all team members/full names and complete Devpost. No remote publication or team identity was invented by this implementation.
