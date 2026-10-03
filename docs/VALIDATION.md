# Release validation

Executed locally on **1 October 2026**. This record distinguishes completed automation from unverified external deployment/provider behavior.

| Check | Executed result |
|---|---|
| Existing + new Django regression suites | **83 tests passed**, 42.200 seconds; response history, classrooms, assessments, learning, Track D and migration suites all enabled |
| Archived source reindex regression after final command fix | **1 targeted test passed**, including real Chroma check that a retained historical chunk is not reindexed |
| Django normal settings | `manage.py check`: no issues |
| Migration drift | `makemigrations --check --dry-run`: no changes detected |
| Frontend production build | `npm run build`: passed, Vite 8.2.1 |
| Frontend lint | `npm run lint`: passed without source warnings |
| Full learning browser workflow | Passed all 17 demo completion conditions, actual multimodal upload/diagram/source viewer, page/slide/video citation seek, unsupported query, diagnostic/short/report, real C failure/hints/retry, BKT/map/path, follow-up, viva/progress, teacher evidence/CSV, executed DeepEval/download and responsive layouts |
| Preserved classroom browser workflow | Passed sign-in/classes/assignments, clipboard/paste blocking, activity report, teacher review, saved student history, sharing/navigation, CSV/mobile and removal-triggered capture/watch revocation |
| Live media scope | Consent, WebRTC offer/answer/track setup and access/revocation checked with explicit signaling-only mode; decoded real frames/audio not asserted in this restricted network |
| Real evaluation framework | DeepEval 4.2.7 completed 20-case benchmark and three four-session learner simulations; results retained in baseline JSON |
| Independent evaluation CLI | New reproduction command executed; four RAG metrics, source/dataset hashes and full personalization result exactly matched the dashboard-run baseline |
| Demo recording | Successful real browser run with 18 English caption segments and a 3–10 minute video; converted to MP4 and inspected at key frames |

## Reproduction

Use the exact setup and commands in [README](../README.md), [evaluation guide](../evaluation/README.md) and [demo guide](DEMO_GUIDE.md). `test_real_deepeval_benchmark_and_simulations_are_executed` requires the separate evaluator environment; it is not skipped when that environment is missing. Tests use disposable data and mock remote provider contracts only where stated.

The initial combined suite exposed a fixture that restored the entire Python module cache and removed imported vector/native dependencies. The fixture now restores only mocked handler entries; all 83 tests subsequently passed, including malformed generated-question payload rejection. No failing tests were disabled. Existing valid corrupt-upload/provider-outage tests log processing failures by design.

The preserved classroom browser run exposed colliding React keys between a selected submission report and a live session with the same numeric ID. Distinct `report-` and `live-` keys plus guarded late track events resolve stale panels; removal/revocation was rerun and passed.

## Not verified here

Live Groq speech/vision/tutor/independent-verifier/semantic-judge quality; ONNX model-cache downloads; legacy PPT conversion with LibreOffice; Docker image build; isolated runner deployment; real-school WebRTC/TURN transport; broad-course evaluation; population parameter/difficulty calibration; causal human learning benefit; YouTube publication and Devpost submission. GitHub publication status is recorded in the current [checkpoint](FUNCTIONAL_CHECKPOINT.md).

LiteLLM's unavailable remote price-map fetch fell back to its bundled local map during normal settings checks. This did not prevent the application check or migrations. No source/student credentials, production database or uploads are included in the source release.

## Assessment camera extension — 1 October 2026

The following checks were actually executed for the optional assessment camera extension. Camera observations remain separate from grading and learner evidence.

| Check | Executed result |
|---|---|
| Complete Django regression suites | **96 tests passed**, 67.752 seconds; all previous suites plus 12 camera tests and the additive migration-preservation test |
| Final assignment/camera regression after distinguishing capture from analysis | **24 tests passed**, 23.755 seconds |
| Local cue-policy tests | **10 tests passed**; sustained turns/absence, calibration, brief movements, sample gaps, cooldowns and pauses |
| Normal application checks | Django system check passed; no migration drift |
| Final frontend lint and production build | Passed; includes a bundled classic worker and self-hosted MediaPipe runtime/model |
| Real-model camera browser workflow | Passed with the actual bundled Face Landmarker: visible face followed by face absence, explicit consent, automatic own-words reminder, dual opt-in eyes-closed prompt, saved explanation and teacher evidence |
| Permission and lifecycle browser cases | Denied permission leaves assessment usable; late permission after cancellation releases tracks; Stop releases capture; enrollment removal stops active capture and revokes timeline access |
| Metadata privacy | Browser/API checks confirm camera events contain no frames, recordings or landmark arrays; backend allowlist and authorization tests passed |
| Preserved learning browser workflow | All 17 existing demo conditions passed after camera integration, including source viewing, real C execution/retry, mastery, teacher evidence and actual evaluation |
| Preserved classroom browser workflow | Assignment, paste controls, teacher reports, CSV, mobile layout and sharing/access-revocation checks passed; media transport remains explicitly signaling-only here |

The camera browser test used a controlled Y4M fixture with a public test portrait and blank frames, not a person's webcam. The detector was not mocked. Geometric head-turn thresholds were exercised separately in policy tests. The classroom regression initially expected an unconditional eyes-closed instruction; it now asserts the own-words reminder remains present and the eyes-closed instruction is absent without dual opt-in. No human copying-detection accuracy, understanding-detection accuracy or field false-prompt rate is claimed. Production device testing and the external checks listed above remain outstanding. No failing tests were disabled.

## PDF Processing repair and regression — 3 October 2026

The reported indefinite Processing state was traced to local uploads requiring a separately started worker, missing interrupted-job recovery, no hard parser/model deadline and no useful progress display. The repair adds bounded automatic local dispatch, durable SQL leases, stale recovery, retained uploads and real stage/count reporting. The additive `0009` migration preserves existing files, hashes, job status and attempts. Local scanned PDF OCR now renders through PyMuPDF and requires Tesseract rather than also requiring Poppler. Empty OCR/figure placeholders fail clearly instead of appearing as searchable notes. Source-evidence prerequisite inference avoids all-pairs graph walks.

| Check executed on 3 October | Actual result |
|---|---|
| Queue, OCR, timeout, retry and authorization regressions | 13 new material-processing tests passed; actual raster-only PDF OCR executed |
| Final processing + migration suite | 17 tests passed in 20.621 seconds, including preservation of original file paths, hashes, attempts and job status through `0009` |
| Full final regression | All **110 tests passed in 83.026 seconds**, including the additional uploaded-file migration test; no tests disabled |
| Normal background upload integration | `scripts/check_background_uploads.py` passed using normal application routes, persistent disposable SQLite, `PROCESS_INLINE=false` and automatic local child workers; no worker was started manually |
| Real uploaded formats | Native PDF, raster-only scanned PDF, PPTX and embedded-caption WebM became ready/searchable. A corrupted PDF failed clearly with its original upload retained |
| Actual API learning loop | Private source/media links and isolation, grounded multimodal tutoring, off-material refusal, real C hidden-test failure, progressive hints, successful retry, BKT, explained adaptive reassessment, viva, path, report, teacher improvement evidence and CSV passed |
| Real automatic evaluation | The normal background dispatcher completed the isolated DeepEval benchmark; results came from framework execution rather than substitute metrics |
| Frontend and camera checks | Production build, lint and all 10 camera-policy tests passed |
| Normal system/migration checks | Django check passed; no migration drift |

The integration check initially expected HTTP 200 for created practice/viva sessions, while the actual API correctly returns 201. Its assertions were corrected and the entire check rerun successfully. The first combined regression attempt ended before completion; the subsequent complete run passed. No test was silenced or disabled.

The user's actual failing PDF/server logs were not provided, so fixture success is not a claim about every page of that file. The integration check uses an explicit offline hash index and disables remote AI, while exercising actual extraction, queues, retrieval, graders and evaluators. Groq quality, uncaptained speech, arbitrary raster interpretation, neural embedding downloads and semantic judge evaluation still need live configuration. Java execution was not validated in this environment because `javac` is unavailable; Python/C paths are covered. The real-model camera/browser evidence above is from 1 October and was not rerun on 3 October; the backend camera and policy regressions were rerun.
