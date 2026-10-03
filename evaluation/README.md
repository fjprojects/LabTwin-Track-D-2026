# Executed evaluation and personalization benchmark

LabTwin executes **DeepEval 4.2.7** against its actual ingestion, retrieval and answer pipeline. The saved [baseline](results/baseline.json) contains measurements from an executed run, not fixed dashboard values. Production students/materials are excluded: every run creates and destroys a separate SQLite database, private upload directory and Chroma index.

## Dataset

`benchmark.json` is an original team-built 20-case gold dataset (`labtwin-team-gold-v1`). Fourteen supported questions cover simple facts, multiple concepts, a native diagram, textbook pages, slides and video timestamps. Six intentionally off-material questions must produce insufficient-material responses with no invented citations. Each supported case includes the known reference answer, required concepts and exact required source locations.

The three original materials are in `backend/labtwin/demo_assets/`: `Data-Structures-Notes.pdf`, `Linked-Lists.pptx` and `Lecture-4.webm`. They are ingested automatically for each run. The lecture contains embedded captions; extraction does not depend on manual preprocessing or an external speech call. A separate original fundamentals text is added only for the learner experiment after RAG cases have run.

Source hashes, dataset hash, execution timestamp, framework version, embedding backend and pipeline version are retained. Benchmark questions are not inserted into production learner history.

## Two evaluation modes

| Mode | What actually executes | Interpretation |
|---|---|---|
| `deterministic` | DeepEval `evaluate` with four custom `BaseMetric` implementations; hash retrieval and source excerpts | Reproducible offline **proxies**, not semantic LLM judgments |
| `llm` | DeepEval standard `FaithfulnessMetric`, `AnswerRelevancyMetric`, `ContextualPrecisionMetric`, `ContextualRecallMetric` using a configured Groq `DeepEvalBaseLLM` | Semantic judge scores for a live tutor/model run; requires key and current supported models |

The release baseline uses deterministic mode. LLM mode is integrated but was not executed with live credentials here. Do not relabel offline results as RAGAS/semantic entailment, or combine metric types without labelling. Framework/provider failure produces a failed run with no invented substitute scores.

## Metric definitions

| Dashboard field | Offline measurement | Limit |
|---|---|---|
| Faithfulness | Fraction of claimed support quotes found in retrieved contexts | Checks quote presence; an unrelated or contradictory paraphrase could still pass |
| Answer Relevancy | Coverage of team-labelled required concepts in the actual answer | Lexical concept coverage, not a semantic relevance judgment |
| Context Precision | Average precision of gold source locations in ranked retrieved units | Gold locations are hand-labelled; additional valid context may be penalized |
| Context Recall | Fraction of required gold locations retrieved | Measures location recall, not exhaustive semantic recall |
| Unsupported-query handling | Off-material cases with `grounded=false` and no citations / all off-material cases | Small six-case negative set |
| Question repetition rate | Delivered items semantically/lexically matching an earlier item / delivered items | Offline lexical proxy; ONNX vectors enable a neural comparison in configured use |

Four RAG averages are computed on the fourteen supported cases. Negative-query handling is reported separately. Each case stores metric scores/reasons, actual output, reference answer, retrieved contexts/locations and citations. Empty measurements are absent/null, not displayed as perfect scores.

## Actual saved baseline

Run: `2026-10-01T01:43:11.338323+00:00`; DeepEval `4.2.7`; hash backend; deterministic proxy mode. Values below come from the saved JSON and are rounded for readability.

| Measured field | Result |
|---|---:|
| Supporting-quote faithfulness proxy | 1.0000 |
| Reference-concept relevancy proxy | 1.0000 |
| Gold-location context precision | 0.9560 |
| Gold-location context recall | 0.9762 |
| Off-material queries correctly declined | 6 / 6 |

Perfect quote/concept proxy values on this small excerpt-based corpus do not establish perfect semantic tutoring or generalize to arbitrary courses. Check per-case contexts and reasons, not only averages.

## Personalization experiment

Three simulated profiles complete a two-topic diagnostic and four sessions of two delivered questions each:

- A: strong programming fundamentals, weak linked lists.
- B: weak fundamentals and linked lists.
- C: strong overall.

The simulation fixes response outcomes so the experiment is reproducible. LabTwin actually selects questions, prevents duplicates, grades answers, updates BKT and generates explanations/recommendations. A human-authored, source-linked question pool includes recall/application/transfer items and is labelled `teacher_reviewed`, not model-generated.

Before each response, the learner model predicts correctness as `p_known × (1-slip) + (1-p_known) × guess`. **Brier loss** is `(prediction - observed_binary_response)^2`; lower is better. An unchanged-prior model supplies the baseline. Each session records evidence count, mean selected difficulty, Brier loss, binary model entropy, mastery, recommendations and tutor style.

| Profile | Mean Brier | Static-prior Brier | Session 1 → 4 Brier | Linked-list mastery change | Repeated / delivered |
|---|---:|---:|---|---:|---:|
| A | 0.1285 | 0.1646 | 0.2641 → 0.0435 | +69.4 points | 0 / 8 |
| B | 0.2159 | 0.2346 | 0.3105 → 0.1615 | +34.0 points | 0 / 8 |
| C | 0.0449 | 0.1296 | 0.0823 → 0.0195 | +41.4 points | 0 / 8 |

Profile C progresses from mean difficulty 2 to 3. B remains at foundation difficulty 1. A moves from 1 to 2. B's loss increases slightly between sessions 3 and 4, and its uncertainty rises as accumulated successful responses move its estimate toward 0.5. Improvement is not claimed to be monotonic in every metric/session.

This demonstrates different selection/policy behavior and prediction improvement in a controlled synthetic sequence. Improving simulated outcomes do **not** establish that LabTwin caused human learning gains. Parameters and difficulty labels are not fitted/calibrated. A real student study with independent pre/post assessments and a comparison group remains necessary for causal effectiveness claims.

## Reproduce

Install the application and separate evaluator environments exactly as in the README. From the project root with the application environment activated:

```bash
python scripts/run_benchmarks.py --mode deterministic --evaluator-python "$PWD/.venv-evaluation/bin/python" --output evaluation/results/local-run.json
```

For a live semantic run, configure `.env` with `GROQ_API_KEY`, `LABTWIN_EVALUATION_JUDGE_MODEL`, current tutor/verifier/vision models and an ONNX cache if selecting neural retrieval:

```bash
python scripts/run_benchmarks.py --mode llm --embedding-backend onnx --evaluator-python "$PWD/.venv-evaluation/bin/python" --output evaluation/results/live-run.json
```

The command saves only measurements from a completed framework run. It propagates failures. Do not install `requirements-evaluation.txt` into the main application environment: DeepEval and the preserved Chroma/CrewAI runtime require conflicting PostHog versions.

The teacher **Evaluation** page and **Demo Mode → Run evaluation** queue the same pipeline. Run `python manage.py process_evaluations --watch` in the application environment. `EvaluationRun` stores owner/course/status/dataset/results/timestamps, and authorized JSON export includes the supporting cases. A worker killed mid-run can leave a running row that currently requires administrator recovery.

## Tests and references

`test_track_d.test_real_deepeval_benchmark_and_simulations_are_executed` executes the real framework. It checks 20 cases, four-session profiles, bounded metrics, retained dataset version and production-data isolation. Missing evaluator configuration, cross-teacher/student access, unsupported queries and novelty have separate regressions.

Primary framework documentation: https://deepeval.com/docs/metrics-custom and https://deepeval.com/docs/metrics-introduction . BKT baseline: Corbett and Anderson (1994), *Knowledge Tracing: Modeling the Acquisition of Procedural Knowledge*, https://doi.org/10.1007/BF01099821 . LabTwin's partial-grade/reliability extension is specified in `learner_model.py` and the README, not attributed to a fitted original BKT implementation.
