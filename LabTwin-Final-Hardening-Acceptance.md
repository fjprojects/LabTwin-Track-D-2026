# LabTwin Final Hardening Acceptance

**Decision: NOT READY FOR FINAL DEMO**

Date: 2026-10-03. Repository: `fjprojects/LabTwin-Track-D-2026` (public).
Baseline: `98ac69e3e67acbd1b0b95a4b5e4d4ae93ce47e02`, 193 tracked files.
Pre-edit checkpoint: `checkpoint/track-d-hardening-start-20261003` and a Git bundle.
Hardening branch: `hardening/track-d-demo-20261003`.

The working architecture, database schema, BKT equations, runner selection and camera policy were preserved. No migrations or dependency replacements were required. No existing tests were removed or disabled. No final demo was recorded.

## Browser blocker

The real cloud-browser navigation to `http://127.0.0.1:5173/` was rejected with **`net::ERR_BLOCKED_BY_CLIENT`**. The Django and Vite processes separately passed actual local HTTP startup checks (protected API: 401 as expected; frontend: 200). That does not demonstrate browser rendering.

No citation was actually clicked in this hardening run. No rendered dashboard or camera permission/stream lifecycle was observed. API, SSR and policy tests below are not substitutes for those checks. The previously bundled demo is not a new acceptance recording.

## Acceptance table

Statuses describe only the evidence actually executed: **PASS / FAIL / PARTIAL / NOT TESTED**.

| FEATURE / TEST | RESULT | EVIDENCE | FILES CHANGED | REMAINING LIMITATION |
|---|---|---|---|---|
| 1. Fresh install / migrations | PASS | Clean public GitHub clone of baseline; new application and evaluator environments; `npm ci`; migrations through 0009. Integration also migrates a new disposable SQLite database. Django check and migration-drift check pass. | No schema/dependency changes; acceptance script | Final remote hardening branch should receive its own deployment smoke check. |
| 2. Real PDF | PASS | `Record(1).pdf`: queued/background processing to Ready, 16 units, no warnings, without manual DB repair. Ready/source verification observed within 23.13s in a concurrent upload batch. | extraction.py; acceptance script | This time includes batch polling and source verification; it is not a standalone speed benchmark. Actual browser upload is NOT TESTED. |
| 3. Scanned PDF / OCR | PASS | Real installed Tesseract reads raster notes. Native text works without OCR. Missing required OCR and forced OCR timeout terminate with a clear failed state and retained original. Sparse headers no longer masquerade as sufficient teaching content. | extraction.py; test_reliability.py | OCR installation and readable scan quality remain deployment requirements. |
| 4. Diagram / vision | PARTIAL | Actual PDF/PPTX native node relationships retrieve successfully; native slide tables remain searchable. Images, captions and locations survive optional OCR failure. Vision timeout retains actual native provenance and submits image pixels in the adapter test. | extraction.py; visuals.py; SourceViewer.jsx; reliability tests | Arbitrary raster semantics were not validated against a live vision provider. UI warning rendering remains unverified. |
| 5. Captioned video | PASS | Real `Lecture-4.webm` reaches Ready. Embedded timestamped captions are extracted before speech transcription; the test asserts the speech provider is not called. Timestamp metadata and multimodal lecture citations remain intact. | No transcription algorithm changes; reliability tests; acceptance script | Browser timestamp jump is NOT TESTED. Frame OCR is sampled and labelled as such. |
| 6. Captionless video / STT | PARTIAL | A real video with caption tracks removed terminates Failed when speech service is unavailable, retaining its file. Injected speech-provider timeout gives a redacted recoverable error; 120s timeout and one SDK retry are verified. | reliability tests | Successful live captionless transcription was not executed; configure the existing speech provider to demonstrate it. |
| 7. AI provider failure | PASS | Injected tutoring/vision/speech timeouts preserve grounded fallbacks or retained uploads. Legacy provider timeout added, implicit retries disabled, and private exception response/log leakage reproduced then fixed. | views.py; adaptive_views.py; hint_views.py; ai_retry.py; settings.py; frontend API; reliability tests | Live provider availability/quality is not certified. No additional provider or silent provider switch was introduced. |
| 8. Citation metadata / authorized source | PASS | Real PDF answer cites `Record(1).pdf — Page 1`; authorized source request returns 200 and byte-for-byte original PDF. Other-class source access returns 404. PDF page, slide and lecture timestamp metadata tested. | acceptance script; extraction provenance | These are API checks, not visible viewer/page-offset checks. |
| 9. REAL BROWSER citation click / refresh | NOT TESTED | Browser navigation rejected with `ERR_BLOCKED_BY_CLIENT`. | SourceViewer error/warning display only; citation routing preserved | Must click the page-1 citation, inspect the actual page, then refresh/reopen it in a reachable browser. |
| 10. Student dashboard | PARTIAL | Saved mastery and student-report API agree: Linked Lists 99.9, Strong, 7 scored attempts; history shows 51.1 → 99.9. Recommendations and report data returned. | acceptance script | Actual dashboard rendering and visible weakness/history/recommendation values are NOT TESTED. |
| 11. Teacher Insights | PARTIAL | Saved topic mastery and teacher API agree at 99.9 for the controlled learner. Three assessment answers average 100.0, with evidence IDs. Coding misconception and improvement evidence retained. | acceptance script | Actual teacher page and evidence drill-down rendering are NOT TESTED. |
| 12. Evaluation dashboard | PARTIAL | New completed EvaluationRun contains actual DeepEval results for 20 cases and three simulated profiles. Results explicitly say deterministic proxy metrics. No replacement scores on failure. | acceptance script | Actual displayed values/labels are NOT TESTED; semantic LLM-judge metrics were not executed. |
| 13. MCQ | PASS | Actual API creates a verified question; scored 100 with cited feedback. Student payload excludes answer keys, hidden tests and support quotes. | acceptance script; existing verification tests | Small-source question pools are finite. |
| 14. Short answer | PASS | Actual API creates/verifies/scorers a supported short answer at 100 with citation. Existing uncertain-answer teacher-review and no-confirmed-mastery-before-review checks remain passing. | acceptance script; existing grading tests | Objective short answers were executed; live open-ended semantic grading is not certified. |
| 15. Numerical | PASS | Actual API creates a source-supported, verified numerical question; scored 100 with cited feedback. Deterministic arithmetic rejection tests remain passing. | acceptance script | Numericals require actual numeric/diagram evidence. |
| 16. Duplicate questions / repetition | PASS | Existing duplicate-bank exhaustion returns a controlled unavailable response. Real simulated profiles each deliver eight questions across four sessions with 0/8 repeated under the documented lexical proxy. Injected duplicates are counted by regression tests. | No novelty algorithm changes; acceptance script | Hash-mode novelty is an approximate lexical proxy, not a validated semantic paraphrase detector. |
| 17. Cited feedback / mistake detection | PASS | Actual C assignment fails hidden tests, receives three progressive hints, and succeeds on retry. Follow-up and three assessment-format feedback responses have source resources. | No coaching algorithm changes; acceptance script | Hidden test details remain private. Live AI misconception accuracy was not measured. |
| 18. BKT mastery update | PASS | Saved evidence/snapshots and probability `0.9987702925528864` agree with displayed API score 99.9. Diagnostic/replay/reliability/regression tests pass. | Documentation only; no learner-model changes | Prototype parameters are not population-calibrated. Model gains are not proof of human learning. |
| 19. Adaptive follow-up | PASS | Actual programming follow-up has source resources and selection reason. Three profiles show different weakness targeting and difficulty progression across four sessions. | acceptance script; unchanged personalization services | Controlled simulation, not a real human study. |
| 20. Python execution | PASS | Real original runner: two controlled stdin/output cases, 2/2 passed, score 100. | No runner changes; acceptance script | Host compatibility runner is for trusted development; use existing isolated worker for public untrusted code. |
| 21. C execution | PASS | Real GCC runner: 2/2 controlled cases passed plus failing/corrected classroom assignment and adaptive code question. | No runner changes; acceptance script | Same deployment isolation limitation. |
| 22. Java execution | PASS | Full official checksum-verified Temurin JDK 17; original runner compiles/runs two cases, 2/2 passed. | No runner changes; acceptance script | Full JDK must be available on deployment PATH. |
| 23. Camera consent OFF in browser | NOT TESTED | Existing server consent regressions and 10 client policy tests pass; no actual browser assessment started. | No camera changes | Must observe no stream, analysis or camera observations with consent off. |
| 24. Camera consent ON in browser | NOT TESTED | Local model assets build successfully; real permission grant/stream was not observed. | No camera changes | Requires reachable browser, permitted camera and applicable HTTPS/localhost permission context. |
| 25. Camera consent REVOKED in browser | NOT TESTED | Policy/server lifecycle regressions pass, but no real stream was started and revoked. | No camera changes | Must observe tracks and analysis stop, and no further observations. |
| 26. Authorization / security | PASS | Classroom/student/teacher isolation, protected uploads/source/media, logout/revoked enrollment, private tests/keys/reviews and camera consent regressions all remain passing. New legacy exception-redaction regression passes. | Safe legacy errors; reliability tests | This is regression evidence, not a complete penetration test. |
| 27. Backend test count | PASS | **128 tests**, 73.196s, OK; baseline **110 tests**, 70.120s, OK. All 18 new tests included in normal discovery. | test_reliability.py | None of the existing tests was disabled. |
| 28. Camera-policy test count | PASS | **10 tests**, 10 passed, 0 failed/skipped/cancelled. | No camera-policy changes | These do not certify hardware/permission behaviour. |
| 29. Frontend build / lint | PASS | Production Vite build and configured Oxlint pass; four new actual-module API regressions pass. | API deadline/errors; source failure/warning display; test script | No standalone type-check command is configured; browser rendering is NOT TESTED. |
| Browser permission DENIED | NOT TESTED | No real browser permission prompt reached. | No camera changes | Confirm explanation, finite error state and usable assessment under optional-camera policy. |

## Actual evaluation evidence

Saved run: completed, `mode=deterministic`, DeepEval 4.2.7, team gold dataset, 20 cases. Benchmark data is isolated from production student data. These values are **deterministic proxy metrics**, not semantic entailment measurements:

| Metric | Measured value |
|---|---:|
| Faithfulness proxy | 1.000000 |
| Answer relevancy proxy | 1.000000 |
| Context precision proxy | 0.955952 |
| Context recall proxy | 0.976190 |
| Unsupported queries handled correctly | 6/6 |

**SIMULATED LEARNER EVALUATION** — four sessions per profile; eight delivered questions per profile:

| Profile | Difficulty by session | Repeated questions | Mean next-answer Brier loss | Static-prior baseline |
|---|---|---:|---:|---:|
| A: strong fundamentals, weak linked lists | 1, 1, 2, 2 | 0/8 | 0.128496 | 0.164600 |
| B: weak fundamentals | 1, 1, 1, 1 | 0/8 | 0.215906 | 0.234600 |
| C: strong overall | 2, 2, 3, 3 | 0/8 | 0.044920 | 0.129600 |

**REAL HUMAN STUDY: NOT TESTED.** Current BKT parameters are prototype parameters and have not been population-calibrated. No student population or causal learning improvement is claimed.

## Remaining limitations

| Classification | Limitation / next acceptance action |
|---|---|
| BLOCKER | Actual citation click, correct visible PDF page, refresh/reopen and authorization in a reachable real browser. |
| BLOCKER | Actual student, Teacher Insights and Evaluation page rendering compared with controlled saved values. |
| BLOCKER | Actual camera consent OFF/ON/revoked and permission-denied lifecycle; stream/analysis/events must stop correctly without affecting grades/mastery. |
| IMPORTANT | Live configured arbitrary-diagram vision, captionless speech transcription, neural retrieval/cache and semantic judge/provider quality still require deployment validation. Use the working native diagrams, OCR and captioned fixtures for the reproducible offline path. |
| IMPORTANT | Tesseract, ffmpeg, GCC/JDK, persistent private storage and worker configuration must be verified on the eventual deployment. |
| IMPORTANT | Verified pools remain finite and duplicate detection is approximate. Exhaustion must continue to return a controlled unavailable response, not unsupported questions. |
| OPTIONAL | More teacher-reviewed/source-supported bank questions or additional benchmark cases. No new product features are required to resolve the browser blockers. |
| FUTURE / RESEARCH LIMITATION | Real-user study and BKT parameter/difficulty calibration; existing per-topic parameters support future calibration. |
| FUTURE / RESEARCH LIMITATION | Broader raster semantics/lecture sampling accuracy and richer semantic novelty measurement. |
| FUTURE / RESEARCH LIMITATION | Optional runner registry/additional languages. Current Python/C/Java selection was preserved; no risky runner refactor was justified. |
| FUTURE / RESEARCH LIMITATION | Camera/activity signals cannot prove cheating. They remain evidence/context for optional conceptual verification or teacher review; no automatic verdict or grade/mastery penalty. |

## Reproduction and evidence

`backend/labtwin/test_reliability.py` reproduces OCR absence/timeout, actual raster extraction, slide image retention/table extraction, caption preference, speech failure, actual-image vision adapter, provider timeout and error redaction. Complete test discovery uses `manage.py test labtwin --settings=backend.test_settings`.

`scripts/check_background_uploads.py --record-pdf '/path/to/Record(1).pdf' --all-languages --results /path/to/results.json` reproduces actual child-process ingestion, protected source bytes, three assessment formats, controlled student/teacher evidence, original language runners and a saved DeepEval run when `LABTWIN_TEST_EVALUATOR_PYTHON` is set.

Evidence files: baseline/final backend, camera, API, build, lint and migration logs; initial failing reliability/security tests; corrected integration log and `measured-acceptance.json`; local server HTTP smoke result; browser navigation error record. The first expanded integration harness used the wrong response key (`session` instead of the existing `assessment`); it was corrected without changing the working API. That failed attempt is retained alongside the passing rerun.

After the three browser blocker groups pass against the tested commit, stop development, create the final demo tag, and only then record the final 3–10 minute demo. This checkpoint is not a demo-ready certification.
