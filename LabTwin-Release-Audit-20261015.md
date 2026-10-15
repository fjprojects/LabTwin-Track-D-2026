# LabTwin release audit — 2026-10-15

**NOT READY FOR FINAL DEMO.** The development build passes the local core gates and browser suites. The existing live Render service still returns a reproduced 502, and its SQLite/media backup cannot be verified. This audit does not authorize production deployment or storage cutover.

Repository: [fjprojects/LabTwin-Track-D-2026](https://github.com/fjprojects/LabTwin-Track-D-2026)

Review: [Draft pull request #3](https://github.com/fjprojects/LabTwin-Track-D-2026/pull/3), targeting `hardening/track-d-demo-20261003`.

Validated release checkpoint: `3dd464b79a6dc54eae4dcd2a469467ff846b64d6` on `audit/release-20261015`. Subsequent documentation/screenshots do not change application behavior. [Linux CI run](https://github.com/fjprojects/LabTwin-Track-D-2026/actions/runs/38641300790).

## Safety and scope

- Preserved hardened base `cbe72c9631259af301afea78befa2ea65bb859f8` and the unfinished UI/camera branch. Integrated the useful existing UI and assessment-quality siblings in merge commits, retaining their ancestry.
- No production deploy, restart, environment update, storage migration, plan change, account edit or deletion was performed. No paid resources or public development execution endpoints were created.
- Authentication, account/student models, database migrations, password/email/phone recovery services, production settings, tested CrewAI/LanceDB dependency requirements and frontend dependency lockfile are unchanged from the hardened base.
- All development writes use disposable local/CI databases and synthetic accounts/materials. No real student records, passwords, OTPs, reset links, tokens or provider credentials are included in this report or screenshots.
- The storage candidate was inspected/tested in a separate checkout. It was not merged into this release or applied to production.

## Results

The labels below refer to the stated scope; a local result is not a live Render result.

| Feature / test | Result | Evidence | Remaining limitation |
|---|---|---|---|
| Integrated backend baseline | PASS — tested successfully | 230 tests before the new fixes | Historical counts are not substituted for current tests |
| Complete backend regression | PASS — tested successfully | 235 tests, no failures/skips, `manage.py test labtwin --settings=backend.test_settings` | External providers are mocked/disabled in controlled tests |
| Private deployment/media regression | PASS — tested successfully | 30 tests via `scripts/check_deployment.py` | Live Render acceptance blocked |
| Frontend utility/policy/API/auth/topic tests | PASS — tested successfully | 40 distinct Node tests; includes 10 unchanged cue-policy tests plus 3 setup/recovery tests | No configured TypeScript checker; this project uses JSX/JS |
| Frontend build and lint | PASS — tested successfully | Production Vite build and oxlint; existing chunk warning remains visible | Main bundle exceeds the 500 kB warning threshold; not concealed |
| Fresh GitHub checkout and Linux install | PASS — tested successfully | Linux CI checkout, unchanged requirements install and frontend install/build succeeded | Live Render is a separate unverified deployment |
| Fresh migrations | PASS — tested successfully | 11 LabTwin migrations applied to an empty temporary SQLite DB; no migration drift; `PRAGMA integrity_check` OK | Production migrations not run |
| Registration/login/logout and role/account isolation | PASS — tested successfully | Full backend auth suites and actual browser student/teacher registration, login and sign-out | Live login blocked by Render 502 |
| Email/phone password recovery preservation | PARTIAL — limitations remain | Existing reset/token/OTP/verified-phone/security regressions pass; services unchanged | Actual email/SMS delivery not tested; safe configured provider credentials required |
| Classrooms, courses, topics and prerequisites | PASS — tested successfully | Browser creation/join; topic blank/duplicate/foreign validation, real HTTP 400 recovery and rapid-submit guard | Existing production record inventory inaccessible |
| PDF processing and corrupt-file termination | PASS — tested successfully | Actual child-worker/API check: original PDF Ready, corrupt PDF Failed | Uploaded `Record(1).pdf` was not reused in this synthetic-data audit |
| Scanned PDF/OCR | PASS — tested successfully | Real installed Tesseract extraction and actual background raster-PDF upload reached Ready; unavailable/timeout cases have defined errors | OCR availability in production not revalidated |
| PPTX, figures and source metadata | PASS — tested successfully | Actual PPTX processing; preserved rendered figures/native connector relationships; real browser figure loads | Complex visual interpretation with a live vision model not tested |
| Vision unavailable/provider failure | PASS — tested successfully | Failure-injection regressions preserve readable text/pixels/provenance and redact provider details | Not a live vision-quality evaluation |
| Captioned video and timestamp citation | PASS — tested successfully | Actual caption extraction; STT not called; browser seeks to 0:10 and lecture search to 0:30 | Fixture contains captions, not spoken narration |
| Captionless speech transcription | PARTIAL — limitations remain | Missing-provider and timeout/error retention tests pass | Successful live STT not executed; provider needed |
| Supported tutoring and unsupported refusal | PASS — tested successfully | Browser/source retrieval, grounded excerpts, source links and off-material refusal; normal-architecture background check | Live model generation/semantic judge not executed; excerpts clearly labelled |
| PDF citation/modal/keyboard behavior | PASS — tested successfully | Browser clicks open cited source; page-6 fragment/location verified; Close remains visible at 1366/390/320 widths; Escape restores citation focus; refresh preserves sources | This does not prove native PDF pixels in every browser |
| Live protected original-PDF new-tab/page-1 click | BLOCKED — external access or prerequisite missing | Existing exact private-media authorization regression passes; live site returns 502 | Must test original link, actual page 1 and refresh on the live site after hosting repair |
| Student/teacher dashboard rendering | PASS — tested successfully | Visible student state/attempt totals and teacher topic/mastery/support totals compared directly to saved API results; backend tests verify retained DB evidence | Live dashboards not accessible |
| Live dashboard rendering | BLOCKED — external access or prerequisite missing | Public Render 502 reproduced after wake-up and one retry | Requires reachable backend and protected test access |
| MCQ, short-answer and numerical | PASS — tested successfully | All three verified formats scored with cited feedback in actual background/API workflow; MCQ/short-answer browser report tests pass | Uncertain open answers retain teacher review; no unconfirmed mastery credit |
| Wrong answers, hints, retest and mastery adaptation | PASS — tested successfully | Actual C failure → conceptual feedback → progressive hints → correct retry → BKT evidence → adaptive follow-up; browser and background checks | BKT parameters are prototype parameters, not population-calibrated |
| Assessment question quality and repetition | PARTIAL — limitations remain | Quality/verification/duplicate regressions pass; actual measured repetitions A 0/8, B 0/2, C 0/8 | B exhausts the verified foundation pool after session 1; no invented replacement questions |
| Viva, saved reasoning, review and exports | PASS — tested successfully | Actual browser saved answers/follow-up/provisional review, teacher reports and CSV | Provisional feedback is not confirmed mastery evidence |
| Python and C execution | PASS — tested successfully | Fixed trusted programs each execute two real cases; additional real C workflow and Python classroom submission | Tests use trusted fixtures, not arbitrary public code execution |
| Java execution | PASS — tested successfully | Linux CI native-runner gate compiles and runs two fixed Java cases with JDK 17 | Local scratch lacked javac; its package download failed. No dependency downgrade was used |
| Camera consent OFF | PASS — tested successfully | Browser test records no camera tracks before opt-in | Synthetic device; physical device not tested |
| Camera permission DENIED | PASS — tested successfully | Explicit denied-permission fixture yields clear error, no tracks, usable assessment and Retry | Physical browser permission dialog remains a human check |
| Camera consent ON/model/cues | PASS — tested successfully | Actual browser stream and MediaPipe worker/WASM/model; real face and blank-frame outputs, neutral cue, optional own-words response | Synthetic public test image/feed, not a physical webcam study |
| Camera consent REVOKED/access removed | PASS — tested successfully | Uncheck consent stops owned tracks/worker; sample count stops; pending permission stream is stopped when it arrives; enrollment removal stops capture | Stopping local reminders does not revoke separately consented classroom sharing |
| Camera model/inference failure recovery | PASS — tested successfully | Injected real component stalls terminate at bounded deadlines, stop capture and retain answer editing | Device/browser variability requires physical tests |
| Physical camera and live HTTPS consent | NOT TESTED | No physical camera or working authenticated live site in this audit | Human allow/deny/revoke check required |
| Normal clipboard editing | PASS — tested successfully | Actual browser clipboard and Ctrl+V/Ctrl+C with multiline short answer; normal learning text selection preserved | OS/mobile clipboard behavior requires a human check |
| Restricted assignment paste | PASS — tested successfully | Existing assignment setting/disclosure and field-scoped blocked-paste event verified; visible accommodation guidance added; teacher timeline validated | Application cannot prevent switching tabs or all external copying |
| Tab/focus counts, refresh, retry and teacher timeline | PASS — tested successfully | Controlled overlapping browser visibility/blur events count one departure; real lost-response retry uses same ID; refresh/teacher summary/time stamps verified | Headless visibility transitions are controlled fixtures; physical tab switching remains a human check |
| Security/privacy and hidden answer protection | PASS — tested successfully | Account/classroom/source isolation, revoked sessions, hidden keys/tests, private ticket authorization, event allowlists, no camera/clipboard content, no activity scoring | This is regression evidence, not a complete penetration test |
| Executed RAG/personalization evaluation | PASS — tested successfully | DeepEval 4.2.7 actually executes 20 cases and three four-session simulations; dashboard values matched exported saved results | Deterministic proxies, small synthetic dataset; B has pool exhaustion, no real human study |
| Supabase adapter offline tests | PASS — tested successfully | 8 tests on candidate `44d2623`: TLS config/private storage/cache rehydration/path protection | Separate branch only; fake in-memory S3, not live storage |
| Live Supabase persistence | BLOCKED — external access or prerequisite missing | Historical read-only run 38382705879: DB connection OK, required LabTwin tables absent, bucket HTTP 403 | No current live upload/download/restart or migration verified |
| Existing Render hosting | FAIL — reproducible defect | Real browser wake-up page → 502, then one retry → 502; public screenshot saved | Precise cause not established by available logs/metrics |
| Verified production backup/restoration | BLOCKED — external access or prerequisite missing | No authorized full SQLite/media export access obtained | Existing record/file counts and preservation cannot be confirmed |
| Public staging/production redeploy | BLOCKED — external access or prerequisite missing | No hosting changes made; public repository and draft PR available | No deployment success or preview URL claimed |

## Bugs fixed and retained work

| Problem / root cause | Change | Files | Evidence |
|---|---|---|---|
| Ordinary assessments prevented every paste in answer fields | Allow ordinary editor paste; log allowed metadata independently of consent/camera | `useAssessmentActivity.js`, `AssessmentWorkspace.jsx`, `camera.py`, `camera_views.py` | Native clipboard browser assertions; activity backend tests |
| Late history responses and lost replies could create unreliable counters | Gate initial synchronization; reconcile IDs; separate committed/pending counts; bounded queue and safe retry | `activityQueue.js`, `activityQueue.test.js`, `useAssessmentActivity.js` | Initialization race, lost response, refresh and no-receipt tests |
| Overlapping browser events could be ambiguous/double-counted | Count hidden transitions only; keep blur/focus separate; deduplicate each transition; disclose rules | `assessmentEvents.js`, activity hook/queue, teacher review UI | Controlled overlapping events + persisted teacher counts |
| Retry failed at the event cap even for an existing ID | Apply capacity limit only when creating a new event | `camera.py`, `test_assessment_activity.py` | Idempotent replay succeeds at 2,000 events; new event rejected |
| Offline pre-submission activity could not finish syncing | Allow only browser metadata observed before completion to drain within 15 minutes | `camera.py`, `camera_views.py` | New/late/out-of-window events rejected; grading/camera rules unchanged |
| Camera consent checkbox was locked while active | Permit revocation and immediately shut down owned capture/analysis | `AssessmentCamera.jsx` | Actual model browser revocation test; tracks and samples stop |
| Permission, preview and frame waits could stall indefinitely | Bound permission 30s, preview 10s, consent sync 15s, model 45s and frame analysis 10s; stop late streams | `camera/setup.js`, `AssessmentCamera.jsx` | Setup unit tests and browser model/inference stall injection |
| Camera failures lacked useful recovery steps | Setup checklist, live preview/model/calibration status, Retry/Recalibrate/Stop, safe device/permission errors | Camera component/CSS/setup tests | Actual model/denial/revocation browser suite |
| Small navigation widths split words awkwardly; lab entry was indirect | Preserve whole navigation words and expose the existing programming lab | `LearningPortal.jsx`, `PortalIcon.jsx`, `WorkspaceLayouts.css` | All roles/pages, 6 viewports, no page horizontal overflow |
| Deployment test confused the test DB with the configured production path | Snapshot configured path before Django substitutes its in-memory database | `deployment/tests.py` | Full combined 30-test suite passes without weakening checks |
| Old personalization prose claimed more questions/gain than current measured run | Report actual delivered counts, exhausted pool and negative/unchanged B mastery | `evaluation/README.md`, measured result JSON | Saved run includes zero deliveries in B sessions 2–4 |

Retained sibling work includes full-screen workspace layouts, source modal, truthful source-excerpt labels, progressive answer rendering, topics/prerequisite feedback, assessment quality verification and activity endpoints. The earlier Add topic fix remains unchanged and was re-tested.

The first Linux CI run passed backend/deployment/migrations/Java/frontend/UI gates, then failed the new activity fixture because it read table cells before the asynchronous row loaded. The fixture now waits for that row without relaxing count assertions. The corrected local browser test and the complete subsequent Linux run 38641300790 passed. The separate UI regression workflow 38641308036 also passed. Exact outcomes are retained in [the validation record](docs/release-audit/validation.json).

## Actual evaluation evidence

[Saved measured run](evaluation/results/release-audit-20261015.json), from an executed disposable browser/evaluation workflow; no production learners. Twenty cases: fourteen source-backed, six off-material.

| Measurement | Actual value | Meaning |
|---|---:|---|
| Faithfulness | 1.0000 | Supporting-quote proxy, not semantic entailment |
| Answer relevancy | 1.0000 | Required-concept coverage proxy |
| Context precision | 0.955952 | Gold source-location ranking |
| Context recall | 0.976190 | Required source-location recall |
| Unsupported refusal | 6 / 6 | Small known negative set |
| A delivered repetition | 0 / 8 | Lexical semantic proxy |
| B delivered repetition | 0 / 2 | Limited pool exhausted; not sufficient question coverage |
| C delivered repetition | 0 / 8 | Lexical semantic proxy |

A/C estimates improve under fixed synthetic responses; B's fundamentals estimate decreases after wrong answers and its linked-list estimate stays unchanged. These are model estimates and simulations, not causal human learning gains. Current BKT parameters are prototype parameters and have not been population-calibrated.

## Render and persistence diagnosis

Live Render service: `srv-db0lecvavr4c7388hd90`, Free, Docker. The provider reports live commit `86898558574f8655edb35a4dfc6589bf0797de0d` from October 10; the audited development branch has not been deployed. Auto-deploy was off.

Actual browser observations: Render's wake-up interstitial was followed by Bad Gateway. One normal reload reproduced the wake-up → 502 sequence. This is a real HTTP failure, not inferred from backend metadata or a bot-detection assumption.

Read-only evidence: Gunicorn had listened on port 10000; logs at 20:31:08 UTC on October 14 showed SIGTERM/worker exit. Queried events carried no failure reason. Recent sampled memory was about 331 MB versus a 537 MB limit, and available HTTP-count metrics were empty. No OOM, worker-boot failure, traceback or worker-timeout was returned for the queried window. These samples do not rule out transient startup/resource problems. No startup rewrite, dependency downgrade or port change was justified by this evidence.

[Render Free documentation](https://render.com/docs/free) states that local filesystem contents can be lost on deploy/restart/spin-down and that Free services do not provide SSH/dashboard shell/persistent disks. A backup export/restoration was not obtained. **Do not infer that existing production records remain present or that a repo clone contains user data.**

The separate Supabase candidate's most recent available executed read-only connection check (October 13, run 38382705879) connected to PostgreSQL, but found no LabTwin `auth_user`, account or practice-attempt tables. The private S3 bucket check returned HTTP 403. This is historical evidence; no current credentials were exposed or production migrations attempted.

Required before production change:

1. Authorized complete SQLite snapshot, uploaded media and legacy state export, stored securely outside the ephemeral service. Verify integrity, per-file hashes/counts and restore into an isolated environment. The backup must cover accounts/roles, classroom membership, courses/topics/source units, assignments/submissions, mastery/history, and original/extracted media. Current counts cannot be confirmed here.
2. Resolve safe database/storage access and validate the candidate in isolation: `LABTWIN_DATABASE_URL`, `LABTWIN_S3_ENDPOINT`, `LABTWIN_S3_REGION`, `LABTWIN_S3_BUCKET`, `LABTWIN_S3_ACCESS_KEY_ID`, `LABTWIN_S3_SECRET_ACCESS_KEY`. Keep the bucket private and values server-side. Verify required tables/migration history and real private upload/download/rehydration.
3. Diagnose the 502 with instance/health failure information or authorized running-instance access. Preserve the private gate, DEBUG off and authorization; do not publish unsafe execution endpoints.
4. After backup/restoration and rollback are verified, obtain the user's final deployment permission. No such permission is assumed here.

Email/SMS deliveries also remain untested. Preserve the existing fail-closed settings. For email, a real SMTP sender/TLS configuration and enabled recovery setting are required. For SMS, use `LABTWIN_PASSWORD_RESET_SMS_ENABLED`, `TWILIO_ACCOUNT_SID`, `TWILIO_VERIFY_SERVICE_SID`, and either an authorized `TWILIO_API_KEY_SID`/`TWILIO_API_KEY_SECRET` pair or `TWILIO_AUTH_TOKEN`. Do not post credentials, OTPs or reset links in chat, logs, public files or reports.

## Changed commits

| Commit | Scope |
|---|---|
| `b2ef84b780ab0d566752b5c5ebd3336928ce6156` | Integrate existing UI sibling and preserve unfinished navigation ancestry |
| `9c7740a06abb0f09f0b807b603ed7b306b433419` | Integrate existing assessment-quality/activity sibling |
| `f66269f14af4e9f540b8824a125d5a3d3baf1f6b` | Clipboard editing, neutral activity synchronization/counts/teacher evidence |
| `c9f713f74fd71ac0aea77837435c7dbd1aba54ac` | Camera revocation, bounded waits and recoverable setup |
| `8c4ed8d87369056944ec0616ab8d1c16e191dff2` | Existing programming lab navigation/readable labels |
| `dab12171b2c94d0f4c369997a08a9db2da6d1e50` | Reproducible gates and dashboard comparisons |
| `3dd464b79a6dc54eae4dcd2a469467ff846b64d6` | Wait for the asynchronous teacher activity row; exact assertions retained |

Published trees were checked against the locally tested Git tree/blob hashes. All original repository files are retained; this is not a partial copy. Audit documents and screenshots are an additional documentation commit.

## Reproduce safely

Use the existing application dependency requirements and a separate `requirements-evaluation.txt` virtual environment. Do not install DeepEval into the CrewAI/Chroma environment. Set `LABTWIN_TEST_EVALUATOR_PYTHON` to the evaluator interpreter without exposing provider secrets.

```bash
python backend/manage.py test labtwin --settings=backend.test_settings --noinput
python scripts/check_deployment.py
python scripts/check_fresh_migrations.py
python scripts/check_programming_runners.py --require-all
python scripts/check_background_uploads.py --results /tmp/labtwin-background-results.json
cd frontend
npm ci
node --test src/camera/*.test.js src/api.test.js src/auth/*.test.js src/learning/*.test.js
npm run lint
npm run build
```

For browser checks, install Playwright outside production dependencies and its Chromium runtime, install the test-only Matplotlib sample dependency (or provide a public fixture with `--image`), then from the repository root:

```bash
python scripts/create_camera_fixture.py /tmp/labtwin-camera-test.y4m
export LABTWIN_CAMERA_TEST_VIDEO=/tmp/labtwin-camera-test.y4m
node scripts/run_browser_checks.cjs scripts/e2e_topics.cjs scripts/e2e_ui.cjs scripts/e2e_activity.cjs scripts/e2e_assessment_camera.cjs scripts/e2e_learning.cjs
```

The runner starts and deletes only its disposable DB/vector/media fixture. Browser tests bind localhost only. `e2e_server.py` stubs legacy remote AI handlers; authentication, new learning services and trusted code runners are real. `check_background_uploads.py` additionally exercises the actual normal architecture and real child processing/evaluation jobs. Headless clipboard checks use real browser shortcuts; hidden/focus transitions and network loss are controlled fault fixtures. The separate classroom suite passed sharing consent/signaling and report/CSV/clipboard/removal checks with `LABTWIN_E2E_SIGNALING_ONLY=1`; actual remote WebRTC media transport was not verified in this restricted network.

## Screenshots

All learning/account screenshots use synthetic fixtures. Desktop comparisons use 1366×768 at 100% CSS zoom; mobile comparisons use 390×844. The earlier base is `cbe72c9`; the after screenshots use this audit's final frontend. [Screenshot hashes](docs/release-audit/screenshot-manifest.json).

| View | Before | After |
|---|---|---|
| Teacher course materials, desktop | [Before](docs/release-audit/screenshots/before-teacher-1366.png) | [After](docs/release-audit/screenshots/after-teacher-1366.png) |
| Student assessment, desktop | [Before](docs/release-audit/screenshots/before-student-1366.png) | [After](docs/release-audit/screenshots/after-student-1366.png) |
| Teacher course materials, mobile | [Before](docs/release-audit/screenshots/before-teacher-390.png) | [After](docs/release-audit/screenshots/after-teacher-390.png) |
| Student assessment, mobile | [Before](docs/release-audit/screenshots/before-student-390.png) | [After](docs/release-audit/screenshots/after-student-390.png) |

[Actual MediaPipe synthetic-camera check](docs/release-audit/screenshots/camera-synthetic.png) · [Teacher activity timeline](docs/release-audit/screenshots/teacher-activity-timeline.png) · [Actual live Render 502](docs/release-audit/screenshots/render-502.jpg) · [Background processing evidence](docs/release-audit/background-processing.json)

## Remaining limitations and human acceptance

| Priority | Remaining item |
|---|---|
| BLOCKER | Live Render 502; authenticated live citation/dashboard/camera acceptance cannot run |
| BLOCKER | No verified restorable production SQLite/media backup; production deployment/storage changes on hold |
| IMPORTANT | Supabase target tables and private bucket permissions not verified for cutover; historical tables absent/S3 403 |
| IMPORTANT | Physical camera consent/permission behavior, native PDF page-1/new-tab display, real tab switching and remote WebRTC transport not yet verified |
| IMPORTANT | Small verified question pools can be exhausted; weak-profile B has only two deliveries in this run |
| IMPORTANT | Actual email/SMS delivery and live STT/vision/semantic LLM judge not tested |
| OPTIONAL | Reduce the existing main-bundle size after mandatory live checks; no warning threshold was increased |
| FUTURE / RESEARCH LIMITATION | Population-calibrated BKT parameters, large human learning study and robust camera generalization; activity does not prove misconduct |

After hosting and backup are safe, prioritize:

1. Sign in through the private gate. Upload `Record(1).pdf`, wait for Ready, ask a page-1 question, click citation, then **Open original material**. Confirm actual page 1, correct file and refresh behavior; test a foreign classroom is inaccessible.
2. Complete controlled correct/incorrect assessments; compare Student Dashboard, Teacher Insights and Evaluation values with the saved evidence. Confirm proxy/simulated labels and teacher-review states.
3. Use a physical camera on HTTPS: consent off, allow permission/on, revoke while active, deny permission and retry. Check preview/model/calibration status and that answers remain usable. No camera/activity event may change grades or mastery.
4. Actually switch tabs and open/close a browser permission dialog. Confirm one hidden departure and a separate focus count; reconnect/refresh and compare the teacher timeline.
5. Test native desktop/mobile copy/cut/paste and text selection in normal learning and in a specifically disclosed restricted assignment. Confirm accommodation guidance and no page-wide restriction.
6. Verify real email/phone OTP delivery, invalid/expired/reused challenges and login after reset through secure provider configuration; never expose the challenge values.

Stop product development once the blocker-level live checks and regression gates pass. Do not record or claim a final public demo as ready before that point.
