# Track D compliance audit

Audit date: **1 October 2026**. Baseline: the supplied official three-page **Track D: Personalized Tutoring & Adaptive Learning** specification and submission guidelines, followed by the user's expanded 33-section request. This is an implementation/evidence audit, not a predicted judging score or official certification.

**Implemented** means the stated behavior has an executed local code/test/demo path. **Partially Implemented** means a material portion works but coverage or live validation is incomplete. **Not Implemented** means no completed working deliverable is present. An optional feature is not silently made mandatory. External publication is distinct from local implementation.

Route abbreviations below use `/api/learning/` unless a full prefix is shown. File paths are relative to the project; learning services are under `backend/labtwin/learning/`. UI components are under `frontend/src/learning/`. Test shorthand: **L** = `backend/labtwin/test_learning.py`; **D** = `test_track_d.py`; **M** = `test_learning_migrations.py`; **E2E** = `scripts/e2e_learning.cjs`. Existing classroom/assessment/history tests remain enabled.

## Every official mandatory requirement

| ID / requirement | Status | Working files/modules | Route and UI | Executed coverage | Remaining limits |
|---|---|---|---|---|---|
| 1a. Videos, textbooks and slides without manual preprocessing | Partially Implemented | `ingestion`, `extraction`, `transcription`, `visuals` | `courses/:id/materials/`; Course Materials/My Courses | L/D real PDF/PPTX/video embedded subtitles; E2E uploads | Whisper uncaptained speech contract mocked, not live; legacy PPT converter not available locally |
| 1b. Topics, concepts, prerequisites with exact original sources | Partially Implemented | `taxonomy`, source/unit/chunk models | `topics/:id/`, source viewer, mastery map | D source-backed prerequisites/concepts; metadata/citation tests | Explicit headings/definitions/prerequisite text and native diagrams work; general semantic taxonomy limited |
| 1c. Major topics, subtopics and key concept tagging | Partially Implemented | `taxonomy`, `ingestion`, `CourseTopic`, `SourceUnit` | `courses/:id/topics/`; Course Materials/Mastery Map | D automatic subtopic/concept/source evidence | No broad learned classifier; unknown text is left untagged |
| 1d. Extract and use textbook/slide images, diagrams and figures | Partially Implemented | `visuals`, `extraction`, `vectors`, private PNG media | `sources/:id/`, visual-media route; SourceViewer/Ask | D actual native diagram edges, retrieved visual units, authorized image bytes; VLM real-pixel input mocked; E2E | Native PDF/PPTX directed figures work; arbitrary raster/chart semantics require live vision validation; OCR is explicitly limited |
| 2a. Cited grounded answers and functional exact source navigation | Implemented | `vectors`, `rag`, `sources`, `media` | `courses/:id/ask/`, `sources/:id/`; Ask/SourceViewer | L/D isolation/invalid citations; E2E PDF/slide/video seek | Slides reconstructed; support quotes do not mechanically prove every model paraphrase |
| 2b. Unsupported queries clearly rejected/outside knowledge flagged | Implemented | `rag`, benchmark negatives | Ask LabTwin / Demo | L/D and six actual negative benchmark cases | Outside-knowledge generation remains disabled, so no uncited outside answer is silently presented |
| 3a. Scope-based MCQ, short-answer and numerical assessments with topic/source/difficulty | Implemented | `assessments`, `practice`, `question_generation` | `courses/:id/assessments/`, `questions/:id/attempts/`; Assessments/Practice | D three formats, scopes, reports and private keys; E2E | Numericals bounded by supported worked expressions/native diagram counts or teacher bank; limited generated recall pool |
| 3b. Question correctness and nonrepetition verification | Partially Implemented | `question_verification`, `novelty` | Question delivery/teacher bank; verification labels | D bad key/citation/difficulty rejected, safe arithmetic, repeat pool exhausted | Templates deterministic and teacher banks distinct; independent live verifier not executed; semantic novelty approximate offline |
| 3c. Cited feedback, weak-topic/misconception report | Implemented | `practice`, `assessments`, learner evidence | Assessment report, Practice feedback, teacher review | D objective/pending-review grading, sources/mastery impact, ownership; E2E | General open responses need teacher review; likely misconceptions are not definitive diagnoses |
| 4a. Formal topic mastery from quizzes/conversations and other evidence | Implemented | `learner_model`, `mastery`, `coaching`, `viva` | `path/`, topic detail, exchange check; Mastery/Ask | D BKT formula/reliability, scored conversation check, replay; L coding/hints/viva bridges | BKT is uncalibrated; fractional/reliability extensions documented; unscored engagement earns no mastery |
| 4b. New-student diagnostic/initial state | Implemented | `assessments`, `mastery`; AssessmentSession | diagnostic scope; Dashboard/Assessments | D unknown cold start, different diagnostic outcomes; E2E | Formal prior is shared until diagnostic evidence arrives; no unsupported assumed initial skill |
| 5a. Established evaluation framework | Implemented | `scripts/evaluate_metrics.py`, separate requirements | evaluation routes; teacher Evaluation | D and CLI actually execute DeepEval 4.2.7 | Separate runtime required; no fake scores after failure |
| 5b. Four RAG metrics, team gold dataset, off-material cases | Partially Implemented | `evaluation/benchmark.json`, benchmark/metric workers | Evaluation dashboard/export; saved baseline JSON | Actual 20-case run, four measured proxies, six negative cases | Standard semantic DeepEval metrics integrated but not live-executed; offline faithfulness/relevancy are explicitly proxies |
| 5c. Simulated profiles, multiple sessions, mastery/novelty measurements | Implemented | `scripts/run_benchmarks.py`, BKT/selection/grading | Evaluation profile/session evidence | Actual three profiles × four sessions; Brier/static baseline, recommendations, difficulty and repetition | Synthetic outcomes demonstrate model adaptation, not causal improvement for human learners |

## Official expected deliverables and submission conditions

| Deliverable | Status | Evidence | Remaining work |
|---|---|---|---|
| Runnable prototype combining lectures, textbooks and slides | Implemented | Django/React app, migrations, workers, native fixtures, full workflow/browser checks | Live-provider deployment validation still needed for broad media coverage |
| Technical documentation and setup | Implemented | README, architecture/API guide, BKT/assessment/evaluation definitions, `.env.example` | Keep model choices and target deployment configuration current |
| Measured evaluation results and reproducibility | Implemented | `evaluation/results/baseline.json`, gold data, CLI, dashboard, profiles | Broader corpus, semantic live run and real-student study remain weaknesses |
| 3–10 minute demonstration with English audio/subtitles | Implemented | `docs/demo/labtwin-track-d-demo.mp4`, original WebM and English SRT | Local recording; publish to YouTube as required |
| Public GitHub repository with upgraded code and README | Partially Implemented | `fjprojects/LabTwin-Track-D-2026`; full source archive | Publication is in progress; see the current checkpoint for verified completion |
| Required YouTube demo link | Not Implemented | Local video ready | Upload as public/unlisted, not private; no YouTube publication performed |
| Devpost submission, complete team names/memberships | Not Implemented | Existing team labels retained in README | Verified full names, all team accounts and final submission not provided/performed |

## Expanded user checklist: all 33 sections

| # / requested capability | Status | Files/modules | Route / UI | Tests/evidence | Known limitations |
|---|---|---|---|---|---|
| 1. Multimodal knowledge base and taxonomy | Partially Implemented | extraction/visuals/transcription/taxonomy/ingestion/models | materials/topics; Course Materials | L/D/E2E actual native sources | Broad raster, speech and semantic tagging need live validation |
| 2. Source-grounded Ask LabTwin | Implemented | vectors/rag/sources/media | ask/sources; Ask LabTwin | L/D/E2E cited locations/isolation | Semantic entailment beyond quote validation not guaranteed |
| 3. Unsupported-query detection | Implemented | rag/benchmark | ask; More material needed | L/D + 6/6 benchmark negatives | Small negative set; outside knowledge disabled |
| 4. Visual understanding | Partially Implemented | visuals/extraction/vectors | sources/visual media; figure viewer | D native edges and pixels contract | Arbitrary raster diagrams/charts/figures require VLM; not all visuals captured |
| 5. MCQ/short/numerical adaptive scope | Implemented | assessments/practice/generation | assessments; Assessments/Practice | D formats/scopes; E2E | Source-supported deterministic templates plus teacher banks; broad problem synthesis limited |
| 6. Question correctness verification | Partially Implemented | question_verification | delivery/status; verified/teacher-reviewed labels | D keys/cites/difficulty/arithmetic | Independent semantic model path not live-tested; ambiguity coverage limited |
| 7. Semantic duplicates/history/repetition rate | Partially Implemented | novelty/practice/models | practice/assessment reports/Evaluation | D repeats blocked and measured; simulations | Offline lexical proxy cannot catch every paraphrase; ONNX mode unvalidated locally |
| 8. Cited assessment feedback/report | Implemented | practice/assessments/review | attempts/report/review; report cards | D correct/unknown/review/sources/mastery; E2E | Some open answers await teacher review |
| 9. Formal documented learner model | Implemented | learner_model/mastery/rebuild_mastery | path/topic; Mastery Map/Progress | D BKT/reliability/history/replay; M | Parameters not learned/calibrated; model percentage not psychometric certification |
| 10. New-student cold start | Implemented | assessments/mastery/dashboard | diagnostic; Dashboard/Assessments | D differing outcomes and unknown initial states | No optional free-form intake conversation |
| 11. Observable personalized tutoring | Implemented | learner_model/rag/practice | ask; foundation/guided/advanced steps | D policy/output changes with evidence; profiles | Offline answers remain source excerpts; advanced pool can be exhausted |
| 12. Why this question and resources | Implemented | practice/mastery/coaching | question metadata; expandable reason | L/D/E2E real weakness/prerequisite evidence | Uses retained evidence; no hidden cases disclosed |
| 13. Explain my mistake/progressive hints | Implemented | coaching/practice/existing runners | hint/attempts; Hint 1–3 | L hidden-test privacy; E2E actual C failure/retry | Concept attribution is likely, not certain; full code only when teacher allows |
| 14. Personalized learning path | Implemented | mastery/learner_model | courses/:id/path/; Learning Path | L/D updates/prereqs/resources | Recommended tasks, not an exam-calendar scheduler |
| 15. Visual topic/prerequisite/mastery map | Implemented | topic models/mastery/LearningViews.jsx | topics/:id/; interactive course SVG/map | L/D history + E2E click/mobile | Conservative taxonomy; layout is compact/scrollable for larger graphs |
| 16. Optional generated revision material | Partially Implemented | grounded Ask and source recommendations | Ask/Path/Practice | Cited explanations and mini assessments | No dedicated saved flashcards, revision-note generator or audio briefs |
| 17. Optional exam-date study schedule | Not Implemented | — | — | — | Daily weakness tasks exist, but no time/exam-date/forgetting scheduler |
| 18. Optional multilingual/audio tutoring | Not Implemented | — | — | — | Lecture audio ingestion is supported; tutor translation/speech is not a completed feature |
| 19. Adaptive viva and conceptual verification | Implemented | viva/coaching/mastery | vivas/answer/review; Viva | L/D/E2E previous answer/code/source/weakness follow-ups | Provisional score needs review; signals never prove misconduct |
| 20. Teacher AI insights | Implemented | insights/report views/TeacherInsights.jsx | insights/evidence; AI Insights/Reports | L/D ownership/drill-down/CSV; E2E | Source engagement association is not proof a resource caused improvement |
| 21. Established executed evaluation | Implemented | evaluation/workers/DeepEval | evaluations; Evaluation | D actual framework + CLI | Isolated evaluator dependency environment required |
| 22. Separate gold benchmark | Implemented | evaluation/benchmark.json/assets | benchmark worker | 20 known-answer/location cases | Small original linked-list corpus, not broad academic coverage |
| 23. Four measured RAG metrics | Partially Implemented | evaluate_metrics.py/run_benchmarks.py | saved runs/Evaluation | Actual per-case scores/aggregates | Offline semantic proxies disclosed; LLM semantic run pending |
| 24. Actual-results evaluation dashboard | Implemented | EvaluationRun/evaluation_views/EvaluationDashboard | evaluations and JSON download | D missing-env failure/no scores; E2E real results | Teacher-owned internal page, not separately configured global admin role |
| 25. Simulated student benchmark | Implemented | run_benchmarks.py/learner services | Evaluation profile cards | Three profiles/four sessions actual model calls | Controlled outcomes and team-authored difficulty labels |
| 26. Measurable personalization over sessions | Implemented | profile histories/Brier baseline/entropy | Evaluation sessions/export | Evidence count, loss reduction, different progression | Some intermediate metrics worsen; no causal human-learning claim |
| 27. Modular architecture | Implemented | learning modules + existing architecture | modular route modules/UI | Existing + new regression coverage | Legacy CrewAI views remain large to preserve behavior; new functionality separated |
| 28. Security/privacy | Implemented | access/media/private keys/auth/live | all classroom-scoped routes | Existing auth/assessment + L/D revocation/isolation | Public untrusted execution needs isolated runner; client activity can be modified |
| 29. Reliable 17-step 3–10 minute demo | Implemented | demo/assets/DemoPanel/E2E recording | demo/student; Demo Mode | Actual captioned browser workflow, real code/metrics | Provider-free native/caption fixtures; not live ASR/VLM proof |
| 30. Judging-priority mapping | Implemented | docs/JUDGING_EVIDENCE.md | documentation | Six weighted categories/evidence/weaknesses | No predicted score or claim of judge approval |
| 31. README/setup/configuration/docs | Implemented | README/.env.example/docs/evaluation guide | documentation | Commands validated locally; links checked | Docker instructions present but image not built locally |
| 32. Critical tests/existing regressions | Implemented | test_track_d/L/M/assessment_camera/material_processing/existing suites/E2E | automation | 110 backend tests; 10 camera policy tests; frontend build/lint; actual background upload/learning/evaluation API checks; prior browser workflows | Live media transport, external provider models and deployment unverified |
| 33. Final compliance and judging audit | Implemented | this audit + judging report | documentation | Every official mandatory item and all 33 sections listed | Partial/not-implemented items intentionally retained |

## Preservation and security evidence

- Migrations `0005→0006`, `0006→0007`, `0007→0008` and `0008→0009` retain existing profiles/classes/responses, source references, embeddings, private answer keys, legacy model labels and uploaded-file/job state.
- The final 110-test backend suite includes existing response-history, auth/classroom and assignment/live/grade/event tests, plus assessment camera, processing recovery, actual scanned PDF OCR and migration-preservation checks. No tests were disabled. A fixture was corrected to restore only mocked handler modules, preserving real dependencies between suites.
- Student question payloads exclude keys/hidden tests. Unauthorized source, assessment, review, evidence, evaluation and media access are rejected; logout/removal revokes media tickets.
- Historical citations survive material retry. Current retrieval and index rebuild exclude archived units.
- Resource views, tab changes, blur/copy/paste and sharing signals do not automatically grade, imply cheating or update mastery.
- The source archive excludes databases, real uploads, tokens, credentials, caches, installed dependencies and generated production data.

## Remaining work ordered by judging weight

1. Validate broad raster diagrams/figures, scanned documents, uncaptained lectures and legacy PPTs with configured real providers/converters; evaluate on a more varied academic corpus.
2. Execute the integrated semantic DeepEval judge mode; inspect faithfulness failures and strengthen claim entailment beyond quote presence.
3. Calibrate learner/difficulty parameters with independent human assessment evidence and compare interventions against a baseline; simulations alone do not establish causal effectiveness.
4. Broaden verified question pools and neural novelty validation beyond source-recognition templates and the small benchmark.
5. Validate target deployment Docker, isolated execution and real WebRTC frame/audio delivery; then publish code, YouTube demo and complete Devpost/team details.

Optional translation, flashcards/audio briefs and calendar schedules were not prioritized over mandatory grounding/assessment/evaluation work.

## Assessment-camera extension

Optional camera reminders now work in diagnostic/quiz/mock sessions and reuse the existing assignment/viva stream. Migration `0008_assessment_camera`, `learning/camera.py`, `camera_views.py`, `frontend/src/camera/`, `AssessmentCameraReview.jsx` and [camera documentation](ASSESSMENT_CAMERA.md) provide student consent, local face/head geometry, sustained cues, voluntary source-linked explanations, teacher timelines and settings. Eye closure requires teacher and student choice, is never checked or graded, and has an eyes-open/written alternative. No camera inference is used as evidence of comprehension or misconduct; no camera event updates BKT or scores. This extension does not resolve the previously documented live-provider, semantic evaluation, broader-corpus or publication limitations.
