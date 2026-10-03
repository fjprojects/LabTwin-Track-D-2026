# LabTwin functionality checkpoint — 3 October 2026

This file is updated as checks complete. Pending checks are not claimed as passes.

## Current work

Reported issue: PDF course uploads remain at Processing instead of becoming searchable.

Confirmed defects repaired and verified:

- Default non-inline uploads required an independently started extraction worker. Local mode now dispatches after database commit and resumes queued uploads from the authorized material page.
- Unbounded extraction/model operations could retain Processing after interruption. Extraction runs in a supervised child with a configurable deadline, retained original files, safe retry and invalidated old worker leases.
- Material cards displayed no real progress. The API and UI now show the current stage and actual page/slide/chunk counts.
- Scanned PDF OCR required Poppler as well as Tesseract. Rendering now uses the project's PyMuPDF dependency; Tesseract remains required for local OCR.
- An unreadable image-only PDF could index empty figure-label placeholders. It now produces a clear OCR/vision error.
- Topic prerequisite inference walked every topic pair before finding source support. It now examines explicit prerequisite statements first.
- Evaluation runs also relied on a separately started worker. Local dispatch and interrupted-run recovery use the same scheduler; no fabricated metrics are substituted.

## Completed checks

- **110 Django tests passed** (83.026 seconds), including all existing suites, 13 new queue/OCR regressions and additive migration preservation. No tests disabled.
- **17 final targeted processing/migration tests passed**; normal application check passed; no migration drift.
- Frontend production build, lint and **10 camera-policy tests passed**.
- `scripts/check_background_uploads.py` passed using normal API routes and a persistent disposable database, with non-inline automatic workers. Real native PDF, raster PDF OCR, PPTX and embedded-caption video became searchable; corrupted PDF failed with its original file retained.
- Cited tutoring, classroom/source isolation, insufficient-material refusal, real C hidden-test failure, hints 1–3, corrected-code success, BKT updates, adaptive follow-up/reason/resources, viva answers, path/report, teacher improvement evidence and CSV passed through actual API routes.
- A real background DeepEval evaluation completed successfully; no substitute scores were generated.
- Backend camera consent, privacy, cue, optional eye-closure and ownership/revocation checks passed in the regression suite. The actual-model browser camera evidence and responsive classroom/demo browser runs remain the separately documented **1 October** checks.

## Still pending / deployment checks

- Complete publication to `fjprojects/LabTwin-Track-D-2026` and verify every source/blob hash. The earlier upload committed only 28 files; publication is now continuing and completion will be recorded after verification.
- Live speech/vision/tutor/verifier/semantic-judge quality, ONNX model download/cache and legacy PPT conversion need configured provider/native tools. Current reproducible checks explicitly use offline embeddings and captioned video.
- Java compilation was not validated here because `javac` is unavailable. Install a full JDK on the target machine. Existing Java functionality is retained.
- Camera field accuracy, real-school WebRTC transport, Docker/isolated-runner deployment and human-learning effectiveness remain unverified.
- YouTube/Devpost hackathon submission remains external work.

## Applying the repair to an existing installation

Back up the database/uploads/index; install updated requirements, run `python manage.py migrate`, and restart the backend. Use `LABTWIN_PROCESS_MODE=local` for automatic local processing. Hosted deployments can use `external` with the documented material/evaluation worker commands. Open Course Materials, then Retry processing or Resume retained uploads. Scanned notes require Tesseract on PATH. See the README for exact commands and timeout settings.

The actual problem PDF and the user's server logs were not attached. Fixture testing can establish the confirmed fixes, but does not establish that every page of that specific file extracts correctly.
