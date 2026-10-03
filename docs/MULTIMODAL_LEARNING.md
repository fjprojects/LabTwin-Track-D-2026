# Multimodal learning architecture and operations

This additive Django/React module is exposed under `/api/learning/`. Existing auth/classrooms, execution, assignments, history and consent-based sharing remain in use. Installation and dependency isolation are documented in [README](../README.md).

## Data and migration

`learning_models.py` is explicitly imported by `models.py`. Migration `0006` introduced the course module; `0007_final_track_d` adds visual/concept metadata, archived source versions, BKT fields, assessment sessions, verification/novelty fields, graded feedback and evaluation runs. It does not delete source/student data or mislabel old weighted scores as BKT. Both migration paths have preservation tests.

Source units are bounded by a PDF page, slide, transcript segment or text section. Chunks never cross these boundaries. Text/visual units share exact classroom/course/material identity and location metadata. Native diagram relationships and optional pixel-based vision descriptions are searchable text representations of visual content, accompanied by the original/private figure image and analysis method.

Reprocessing archives existing units, removes their vectors and indexes a new version. Saved historical citations continue to address retained chunk IDs. Current retrieval and `reindex_materials` exclude archived units. Deleted materials revoke citations; reprocessing does not silently retarget them.

## Services

| Module | Responsibility |
|---|---|
| `access.py` | Endpoints, enrolled course queries, teacher/student ownership |
| `ingestion.py` | Validated uploads, worker jobs, extraction orchestration, bounded chunking/indexing |
| `processing.py`, `workers.py` | Durable processing leases, real stage/count progress, bounded local child workers, deadlines and interrupted-job recovery |
| `extraction.py`, `transcription.py` | PDF/PPTX/text and timestamped embedded subtitles/speech/video frame OCR |
| `visuals.py` | Native PDF/PPTX graph extraction, real-image provider input, private PNGs |
| `taxonomy.py` | Source-heading/definition/explicit-prerequisite mapping and supporting quotes |
| `vectors.py` | Chroma persistent embeddings, filtered lexical/semantic reranking and index rebuild |
| `rag.py`, `sources.py`, `media.py` | Unsupported-query detection, support/citation gate, exact source viewer and token-bound media |
| `question_generation.py`, `question_verification.py`, `novelty.py` | Grounded templates/AI candidates, independent correctness gate, duplicate prevention |
| `practice.py`, `assessments.py` | Delivery, server grading, scope selection, reports and review |
| `learner_model.py`, `mastery.py` | Auditable BKT, cold start, replay, learning path and history |
| `coaching.py`, `viva.py`, `insights.py` | Progressive hints, adaptive viva, evidence-backed observations |
| `evaluation.py`, `evaluation_views.py` | Authorized queued framework runs and measured result storage |

## Source grounding and privacy

The frontend never queries Chroma directly. Authorized course IDs filter vector queries, then SQL checks enrollment, ready material status and active units again. Source-specific questions use an authorized chunk/location. Empty or insufficient coverage yields a clear unsupported result; outside knowledge is not silently generated.

AI answer citations must reference retrieved chunks and include an exact supporting quotation. Invalid references/quotes fall back to source excerpts. This validates source existence and quote presence, not full semantic entailment of every paraphrase. Actual offline evaluation is deliberately labelled accordingly.

PDF citations open `#page=N` in a private frame, slide citations open the reconstructed source slide/figure, and lecture citations set the original media time. Media is not served by a public uploads URL. Signed tickets expire after five minutes and bind material/visual unit to the current active bearer token. Each byte/range request rechecks expiry, ownership and enrollment. Source opening records engagement without asserting learning.

## Learner evidence

BKT replays all scored topic evidence in time order. Saved snapshots retain parameters, evidence IDs, likelihood reliability and the posterior/update. Assistance and provisional estimates are documented reliability extensions; resource views/Ask exchanges remain unscored. Conversation comprehension questions contribute scored conversation evidence.

Existing topic-linked programming submissions, hidden-test results, hint use, retries, misconceptions and viva use the same evidence service. Unlinked legacy lab progress remains intact. Strong/Developing/Needs Practice/Not Started describe model evidence, not a psychological diagnosis. Model-transition snapshots are excluded from measured improvement.

## API map

All paths below are relative to `/api/learning/` and require authentication except signed media, which validates its token-bound ticket.

| Route | Purpose / access |
|---|---|
| `courses/`, `courses/:id/topics/` | Authorized course listing; owner-teacher creation/settings/topics |
| `courses/:id/materials/`, `materials/:id/`, `materials/:id/retry/` | Owner uploads, authorized exploration/search, retained-file retry |
| `sources/:chunk/` | Authorized citation/location, source unit and temporary media/visual URLs |
| `materials/:id/media/`, `materials/:id/visuals/:unit/media/` | Revocable private byte-range media |
| `courses/:id/ask/`, `courses/:id/ask/history/` | Student/teacher grounded questions and owned history |
| `exchanges/:id/check/` | Student-owned source-backed comprehension check |
| `courses/:id/assessments/`, `assessments/:id/` | Student quiz/mock/diagnostic and owned history/report |
| `courses/:id/assessment-review/`, `practice-attempts/:id/review/` | Owner-teacher pending short-answer review |
| `courses/:id/practice/`, `questions/:id/attempts/` | Personalized questions, private grading and feedback |
| `topics/:id/bank/`, `questions/:id/solution/`, `hint/` | Teacher banks, teacher-permitted solutions and progressive hints |
| `courses/:id/path/`, `topics/:id/` | Student/mastery path, graph metadata, evidence/history/resources |
| `courses/:id/vivas/`, `vivas/:id/answer/` | Adaptive viva and follow-up; provisional feedback |
| `courses/:id/viva-review/`, `viva-turns/:id/review/` | Authorized teacher viva review |
| `courses/:id/insights/`, `evidence/:id/`, `courses/:id/report/` | Traceable class observations and student reports/CSV |
| `courses/:id/evaluations/`, `evaluations/:id/?download=json` | Owner-teacher real benchmark runs/history/export |
| `demo/`, `demo/:id/student/` | Enabled teacher-only demo preparation and isolated learner preview |

## Workers and recovery

Local development uses `LABTWIN_PROCESS_MODE=local` with `LABTWIN_PROCESS_INLINE=false`: uploads/evaluations dispatch automatically after database commit to a bounded scheduler. Material processing is supervised in a child with a default 600-second deadline. The SQL queue survives restarts; authorized teacher polling resumes queued jobs. Every job has a private lease token, stage, real completed/total counts and heartbeat; tokens are never returned to clients. For hosting, set `LABTWIN_PROCESS_MODE=external` and run web, `process_materials --watch` and `process_evaluations --watch` using the same application environment/database and private storage. The evaluator starts its metric subprocess using the separately configured evaluator interpreter. Inline mode remains available for small trusted fixtures/tests.

Interrupted material jobs automatically become failed/retryable after their deadline plus a 30-second grace period; the worker command and authorized material page recover them. `process_materials --recover-stale` is retained. Failed uploads keep originals, old citations and useful errors/warnings. Retry cannot replace a live lease; old workers cannot publish over a new retry. Evaluation child failure retains failed status and never substitutes metrics; authorized evaluation polling expires interrupted runs after 990 seconds, allowing a fresh run. The local scheduler bounds queued in-process work and uses one child at a time. Scanned PDF rendering uses PyMuPDF with local Tesseract OCR, without requiring Poppler.

To rebuild vectors after an index-format change, preserve the old index, configure a new `LABTWIN_VECTOR_ROOT`, then run `python manage.py reindex_materials`. It indexes active SQL chunks only. `rebuild_mastery --course ID` explicitly replays retained evidence into BKT without deleting historical snapshots.

## Executed path and limits

Native labelled PDF/PPTX diagrams, private image access/revocation, embedded video subtitles/timestamps, lexical hash vectors, verified assessment templates, BKT, insights and DeepEval proxy evaluation are exercised by automated and browser tests. Vision/Whisper/independent-verifier contracts are tested with mocks; live credentials, model compatibility, legacy PPT conversion, ONNX cache access, Docker deployment and WebRTC frame delivery still need target-environment validation. Video frame OCR is not general scene understanding. Generic semantic topic inference is deliberately conservative.
