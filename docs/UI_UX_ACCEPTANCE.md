# LabTwin UI/UX acceptance — 14 October 2026

Base: `hardening/track-d-demo-20261003` at `cbe72c9631259af301afea78befa2ea65bb859f8`.
Working branch: `fix/ui-ux-20261014`.

## Causes and changes

| Reported issue | Cause in the inspected base | Change |
| --- | --- | --- |
| Account controls below laptop viewport | Sticky `100vh` sidebar with a navigation list that cannot shrink/scroll; account footer follows all buttons. Mobile footer is absolutely positioned. | Navigation owns a constrained vertical scroll area. Branding and account footer remain in the viewport on desktop. Mobile account controls stay in normal document flow beneath horizontally scrolling navigation. |
| Empty margins and small controls | Shell also inherits the generic `classroomPortal` outer margins; legacy lab styles use viewport-based widths inside a smaller main column. Several controls use 10–12px labels. | Explicit full-width shell with zero outer margins, responsive padding, contained legacy widths, larger controls, wrapping forms and contained table scrolling. |
| Teacher gets student-only action error | `AskLabTwin` renders conversation checks for every grounded exchange without knowing the account role. | Portal passes the role; only students see the controls. Account-specific component keys clear conversation state when switching users. Teachers get an Ask LabTwin navigation entry. Backend authorization is unchanged. |
| Topic paragraph with arrows | All topic names are joined with arrows irrespective of actual prerequisite IDs. | Responsive topic list displays stored prerequisites and parent topic names. Selected course cards have an explicit selected state. No topic names or records change. |
| Topic feedback is unclear | Existing validation/ref lock is present, but there is no typing-time duplicate warning or save-success state; topic saves share upload busy state. | Inline errors/warnings, separate pending state, a synchronous repeated-submit guard, save success, immediate use of the API's returned course, and course refresh. Duplicate validation still matches the API's exact-name rule. |
| Copied text looks like an AI answer | Source excerpts, supported AI explanations and insufficient-source results share a large paragraph layout. | Distinct response labels; collapsed source passages with unchanged citation links; readable Markdown for AI explanations; optional supporting quotes; explicit unsupported-material guidance. Historical fallback answers retain their full source text in an expandable panel. |
| PDF viewer hard to use | Dialog body and header scroll together; maximum width is 1000px; page fragment can receive a missing value. | Wider responsive dialog with a separately scrolling body and persistent Close source control. Positive page numbers come directly from the source API. Embedded and original PDF links open the cited page. Source text, slides, figures, audio/video and signed media authorization remain available. |

## What is deliberately unchanged

No database reset, data deletion, schema migration, API removal, role-policy relaxation, production Supabase operation, Render deployment or Supabase draft-PR merge is part of this branch. All backend application files are unchanged; the added backend file contains tests only. No authentication credentials are stored in the branch.

## Exact files changed

- `frontend/src/learning/LearningPortal.jsx`
- `frontend/src/learning/LearningPortal.css`
- `frontend/src/learning/CourseMaterials.jsx`
- `frontend/src/learning/AskLabTwin.jsx`
- `frontend/src/learning/SourceViewer.jsx`
- `frontend/src/learning/topicForm.js`
- `frontend/src/learning/topicForm.test.js`
- `frontend/src/learning/answerState.js`
- `frontend/src/learning/answerState.test.js`
- `frontend/package.json`
- `backend/labtwin/test_ui_permissions.py`
- `scripts/e2e_ui.cjs`
- `.github/workflows/ui-ux.yml`
- `docs/UI_UX_ACCEPTANCE.md`

## Automated validation

The branch's GitHub Actions workflow `LabTwin UI and learning regression checks` runs:

- Frontend lint, existing API/auth/camera tests, learning/topic tests and Vite production build.
- Existing backend topic and learning tests, additional teacher/student authorization and answer-mode tests, and selected Track D conversation, short-answer review, diagnostic and verified-format regressions.
- Existing topic browser tests for stale duplicate rejection and rapid submission.
- New browser checks using the real UI/API at 1920×1080, 1366×768, 1280×720, 900×480, 390×844 and 320×568 CSS pixels, with no browser zoom changes.
- Teacher editor layouts for MCQ, short answer, numerical and code formats; contained dashboard table scrolling; teacher and student sign-out; topic prerequisites/success/warnings; teacher understanding-check denial, student check grading, persisted mastery, MCQ and short-answer assessment reports, unsupported questions, and a generated six-page PDF cited at page 6.

The workflow uses `backend.test_settings` and a disposable local test server. The database, uploaded test materials, vectors and artificial accounts live only in the runner's temporary filesystem. Remote AI is disabled. No production environment variables or deployment secrets are used.

Verified result: [GitHub Actions run 38601023291](https://github.com/fjprojects/LabTwin-Track-D-2026/actions/runs/38601023291) completed successfully against code commit `2ac736682448199c0d0e8d06624637a5b0a456c7`.

- Lint: 0 errors and 0 warnings.
- Frontend API, auth, camera and learning test commands: all passed.
- Vite production build: passed.
- Backend: 50 tests passed, using an in-memory database.
- Existing topic browser suite: passed, including real backend 400 recovery and rapid repeated submissions.
- New UI browser suite: passed, including the six viewport sizes and page-6/source/student assessment checks above.
- Fixture screenshots and disposable server logs are attached to that run as `ui-acceptance-fixtures` (seven-day retention).

The initial CI setup needed job-environment paths corrected and ffmpeg/ffprobe installed for the existing video demo test. Neither change touched application/backend behavior. This final result includes the existing demo regression; no failing test was removed or skipped to achieve it.

The follow-up documentation commit only records this result and the file inventory; the tested application, test scripts and workflow remain identical to the successful code commit.

## Manual browser acceptance checklist

Use Chrome at **100% zoom** (Ctrl+0), with your normal laptop display scaling.

1. **Teacher sidebar:** At normal window height, account name, Recovery phone and Sign out are visible. Scroll navigation to Demo Mode; scroll the main page. Account controls remain reachable.
2. **Student sidebar:** Repeat as a student. On a 390px/320px mobile viewport, account controls do not overlap branding or navigation and navigation can scroll horizontally.
3. **Topics:** Select the intended course. Names appear individually; prerequisites match existing records. Add a genuinely new test topic once. Saving disables the form, success appears, and the new topic/prerequisite option appears. Enter that exact name again: a warning appears and submission sends no duplicate POST. Do not delete real topics to test this.
4. **Role separation:** Teacher Ask LabTwin answers/citations remain available and show no Check my understanding control. As a student, ask a supported question, take the check, submit an answer and verify feedback plus the mastery evidence after reload.
5. **Sources:** In your existing Java OOP notes, open the Dynamic Method Dispatch Page 6 citation. Confirm the viewer and original PDF open page 6. Scroll source text and verify Close source stays accessible. Check PDF readability, source text, a slide, and a lecture timestamp.
6. **Assessments:** Submit an MCQ and an exact accepted short answer. Confirm feedback, citations and saved mastery after reload. Open-ended responses requiring teacher review must retain that status.
7. **Other layouts:** Open teacher question editors, dashboard tables, assignments and student Practice → Programming lab. Content fits the main column; wide tables scroll within their container. Test desktop, laptop and mobile widths.
8. **Answer states:** Compare an AI explanation, a source-excerpt fallback and an off-material question. Labels match the actual backend mode. Citations remain unchanged and clickable.
9. **Sign out:** Use the button in both roles and confirm the login page appears.

## Windows PowerShell: frontend only

Keep the existing local backend running at `http://127.0.0.1:8000`. These commands do not reset or migrate your database.

If `git status --short` shows local changes, preserve them before switching branches; do not run reset/clean commands.

```powershell
Set-Location "C:\Users\francis\LabTwin-Track-D-2026"
git status --short
git fetch origin
git switch fix/ui-ux-20261014
git pull --ff-only

Set-Location .\frontend
node --version
npm.cmd ci
npm.cmd run lint
npm.cmd run test:api
npm.cmd run test:auth
npm.cmd run test:camera
npm.cmd run test:learning
npm.cmd run build
npm.cmd run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open `http://localhost:5173` and press **Ctrl+0**. If port 5173 is already running, stop the old Vite terminal with Ctrl+C before starting the updated one. Node 24 is used in CI; Vite 8 requires a compatible modern Node version.

To run backend regressions locally from a terminal with your existing virtual environment activated:

```powershell
Set-Location "C:\Users\francis\LabTwin-Track-D-2026\backend"
python manage.py test labtwin.test_topic_creation labtwin.test_ui_permissions labtwin.test_learning --settings=backend.test_settings -v 2
```

The existing video/demo regression requires ffmpeg and ffprobe on PATH, along with the project dependencies. This command selects an in-memory test database. Do not substitute production/deployment settings. Use CI for the disposable browser scripts unless you have deliberately set up a separate local test environment.

## Limits and separate AI investigation

The unavailable execution environment in this ChatGPT session means checks must run in GitHub CI or on your laptop; this document does not claim direct access to your Windows browser.

A source-excerpt fallback can result from demo mode, absent AI configuration, provider unavailability (including rate limits), or a generated response failing source-ID/exact-quote checks. Retrieval can also return insufficient coverage for a particular wording or material scope. These are separate mechanisms observed in the code. Their occurrence on a particular production Java question cannot be inferred from CSS or from the fallback label alone.

The new tests cover deterministic modes and preserve citation validation. They do not prove live Groq consistency, faithfulness beyond the existing verification, or correctness of every uploaded file. Diagnose a live inconsistency by comparing the same question, course/material scope, response mode and authorized source IDs, and reviewing sanitized provider diagnostics. Never copy keys, session tokens or private student content into reports.

Headless browser tests verify page fragments, authorized source text and layout. Manually check the actual PDF pixels and your Windows display scaling before merging. Live AI and your existing private uploaded Java document are not exercised by disposable CI fixtures.
