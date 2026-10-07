# Feature check and phone recovery acceptance

Baseline: `eefe5149c17d5fb718863d5d39c51659c14db66d`, branch
`hardening/track-d-demo-20261003`. The complete baseline project is retained;
phone recovery changes are additive. No CrewAI/LanceDB/library/lockfile versions,
learning model, code runners or original feature implementation was changed.

The first validation completed 205 backend tests, 30 deployment/media tests,
18 frontend tests, build/lint and fresh migrations. A long browser-authentication
timeout reset the local workspace before publication. The completed patches were
restored from session evidence for Task 3 validation, not redesigned/reimplemented.

PASS below describes executed local automated checks. It does not substitute for
live browser, carrier delivery, live AI providers or a real human learning study.

| Feature/check | Result | Evidence / boundary |
| --- | --- | --- |
| Student/teacher authentication and classroom isolation | PASS | Existing `test_classrooms`, `test_assessments`, learning authorization tests |
| Classrooms, courses, materials and preserved account roles/identities | PASS | Existing tests plus phone reset/migration snapshot preservation |
| Assignments, hidden tests, drafts, saved submissions/results and viva answers | PASS | Existing history/assessment tests unchanged; private answers stay server-side |
| Teacher grading, feedback, reports, CSV, activity timelines | PASS | Existing assessment/teacher authorization and evidence tests |
| Paste controls and permission-based screen/camera/mic supervision | PASS | Existing consent/signaling/policy tests; events never prove cheating or alter mastery |
| PDF/PPTX text, native figures/tables/diagrams and exact source metadata | PASS | `test_learning`, `test_track_d`, `test_reliability` |
| Scanned PDF OCR, missing/timeout error states | PASS | Real installed OCR plus recoverable failure tests |
| Captioned video, transcript/timestamp preservation | PASS | Actual embedded-caption fixtures; successful provider STT is mocked |
| Live captionless STT, arbitrary raster vision and neural model assets | NOT TESTED | Requires provider/model configuration and real acceptance corpus; fallback/error contracts tested |
| Grounded Ask LabTwin, authorized sources and off-material refusal | PASS | Existing source/RAG/privacy tests; offline excerpts are accurately labelled |
| Citation new-tab authorization | PASS | 13 deployment-media tests including the exact private-gate PDF failure |
| Verified MCQ/short-answer/numerical assessments and safe novelty exhaustion | PASS | `test_track_d`: sources/keys/difficulty, cited feedback, measured repeats |
| Conceptual feedback, progressive hints, corrected retests and adaptive viva | PASS | Existing learning/coaching/assessment tests; uncertain responses need teacher review |
| BKT/diagnostics/history, adaptive tutoring, Learning Path/Mastery APIs | PASS | Existing actual formula/evidence/policy tests; parameters remain prototype, uncalibrated |
| Teacher Insights and stored DeepEval proxy/simulation evidence | PASS | Actual evaluation execution/storage tests, supporting record/denominator tests |
| Semantic LLM evaluation or population/human calibration | NOT TESTED | No simulated/proxy result is claimed as a human study |
| Email recovery links/OTPs | PASS | All 42 existing recovery tests preserved; live SMTP still requires provider configuration |
| Phone recovery security | PASS | 34 phone/provider tests, plus populated migration test; real provider calls mocked |
| Password reset/login and learning-data preservation after reset | PASS | Existing email tests plus SMS single-use/session-revocation/role/data tests |
| Actual SMS/carrier delivery | NOT TESTED | No real Twilio credentials/recipient supplied; no SMS sent |
| Actual Python and C execution | PASS | Existing runners executed two synthetic arithmetic inputs per language |
| Actual Java execution in this current scratch environment | BLOCKED BY TEST ENVIRONMENT | JRE present, `javac` absent; deployment Dockerfile already installs full JDK; runner unchanged |
| Deployed citation rendered-page click, dashboards and physical camera checks | NOT TESTED | Unit/API evidence does not prove current deployed frontend rendering or camera operation |

Validation totals: 205 complete backend tests, 17 deployment tests, 13 private
media tests, 10 camera-policy tests, 4 API tests, 4 auth-parser tests. Frontend
production build uses `/api`; lint passes. Fresh migrations through 0011 and
`makemigrations --check --dry-run` pass. Existing security.W021 remains visible
because this temporary HTTPS hostname is deliberately not HSTS-preloaded.

The original Free Render Docker service was inspected still Live on `e0d59ed`,
auto-deploy off, SQLite/private uploads under ephemeral `/data`. Code migrations
preserve existing records, but hosting redeployment/restart/idle spin-down can
discard that filesystem. A code-level passing migration cannot guarantee hosting
data preservation. A verified backup/restoration or explicit disposable-data
approval is required before replacing it. No paid resource was created.

Real SMS requires the server-only variables/setup in [PHONE_OTP.md](PHONE_OTP.md).
Keep SMS disabled until those credentials and the authorized destination are
configured. Current reports do not claim carrier delivery or final-demo readiness.
