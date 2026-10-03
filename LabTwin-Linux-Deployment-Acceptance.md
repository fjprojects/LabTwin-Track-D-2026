# LabTwin Linux HTTPS Deployment Acceptance

Date: 2026-10-03 UTC. Repository: `fjprojects/LabTwin-Track-D-2026`.
Target branch: `hardening/track-d-demo-20261003`.
Inspected/tested base: `f7bd4209f9e2ce21aadff7a9b780315db18c8840`.
Preserved GitHub checkpoint: `checkpoint/pre-https-f7bd420-20261003`.
Deployment changes are in the commit containing this report.

**No hosted application URL has been provisioned.** Render is available but
not connected to this session. The workspace cannot resolve the Cloudflare
Tunnel endpoints and the Quick Tunnel provisioning endpoint returns HTTP 403.
No attempt was made to bypass those network restrictions. The Linux application
and deployment configuration were tested locally; this is not a hosted HTTPS
or real-browser certification. No application-level defect remains observed
in the executed regression/native HTTP checks. Demo readiness is not certified.

## Requested deployment status

| Item | Result | Evidence / scope |
|---|---|---|
| 1. Deployment URL | BLOCKED BY TEST ENVIRONMENT | Hosting account not connected; no real service URL exists |
| 2. Branch/commit actually deployed | NOT TESTED | Nothing deployed; prepared branch above retains f7bd420 as its parent |
| 3. Backend deployment | BLOCKED BY TEST ENVIRONMENT | Native Linux Gunicorn startup passes; hosted service not created |
| 4. Frontend deployment | BLOCKED BY TEST ENVIRONMENT | Existing Vite build and actual Gunicorn asset serving pass; hosted UI not created |
| 5. Deployment DB/migrations | NOT TESTED | Fresh native SQLite migrations pass; hosted DB not provisioned |
| 6. Deployed worker/material processing | NOT TESTED | Real native background worker reaches Ready; hosted worker not provisioned |
| 7. Reachable HTTPS/certificate | BLOCKED BY TEST ENVIRONMENT | HTTPS proxy settings tested with local simulated headers; actual TLS not tested |
| 8. Real browser citation click/refresh | BLOCKED BY TEST ENVIRONMENT | No reachable hosted URL; metadata/bytes are not a click test |
| 9. Real dashboard rendering vs saved values | BLOCKED BY TEST ENVIRONMENT | Saved records verified through backend; no live UI comparison |
| 10. Real camera OFF/ON/revoked/denied | BLOCKED BY TEST ENVIRONMENT | No live URL or physical browser camera test attempted; policy tests alone do not certify hardware |
| 11. Automated regression | PASS | 128 original backend, 15 deployment, 10 camera-policy, 4 API tests; build/lint; migrations |
| 12. Isolated deployment changes | PASS | Only optional deployment files, Docker context exclusions and README/report; application/frontend/requirements/migrations unchanged |
| 13. Remaining deployment blockers | BLOCKED BY TEST ENVIRONMENT | Hosting connection; service build/capacity/HTTPS verification; then browser acceptance |
| 14. Exact manual instructions | PASS | `deployment/README.md`, grounded in the existing UI/routes, includes four physical-camera cases |

## Executed tests

| Feature / test | Result | Evidence | Files changed | Remaining limitation |
|---|---|---|---|---|
| Exact initial clone | PASS | HEAD f7bd420, tree 0f98896c65c01ce63d37a90563167fd68e13a63a, 196 tracked files | None | Hosting build separate |
| Fresh Linux dependency installation | PASS | Unchanged requirements installed in separate fresh application/evaluation venvs; dependency compatibility check passes | None | Docker build not executed |
| Native Gunicorn startup | PASS | Actual `deployment/start.py`, migrations, collectstatic, health and compiled UI HTTP responses | `deployment/` | Local HTTP with simulated TLS proxy headers |
| Production settings/gate | PASS | 15 tests: DEBUG off, strong runtime secrets, host validation, HTTPS redirect, CSRF-protected private login, secure separate cookie, expiry/rotation, asset/path protection, normal auth remains required | `deployment/` | Hosted edge configuration still requires verification |
| Fresh migrations/schema | PASS | All ordinary migrations apply; `makemigrations --check --dry-run` reports no changes | None | Hosted DB not provisioned |
| Real PDF HTTP ingestion | PASS | Record(1).pdf Ready, 16 units, 12.25 s observed, through actual Gunicorn/background dispatcher | No extraction changes | Deployment compute differs from this Linux runtime |
| Wider material processing | PASS | Real PDF/PPTX/captioned video/raster PDF reach Ready; corrupted PDF reaches Failed with retained original | None | Captionless STT/vision provider not certified here |
| Scanned PDF/OCR | PASS | Tesseract extracts raster fixture; existing unavailable-OCR regression cases terminate in a recoverable failure | None | Hosted Tesseract installation not yet observed |
| Citation metadata/source bytes | PASS | Actual HTTP source reports page 1, HTTPS origin from proxy headers, original PDF bytes match, authorized source 200; outsider source 404 | No source/viewer changes | No browser render/click/refresh performed |
| Off-material refusal | PASS | Actual HTTP weather query declined without citations; background integration also passes | None | General live AI quality outside this test |
| MCQ/short-answer/numerical | PASS | Verified questions, actual 100 scores and cited feedback saved in disposable integration | None | Browser interaction pending |
| Mistake feedback/weakness/adaptation | PASS | Real failing C work, progressive hints, correct retry, BKT update and follow-up executed | None | UI values not yet compared |
| Teacher Insights / saved results | PASS | Actual student/topic/evidence records retained; example Linked Lists 99.9 mastery, 7 attempts | None | Hosted dashboard rendering pending |
| Actual DeepEval proxy storage | PASS | Completed saved run, 20 benchmark cases and 3 simulated profiles; metrics below | None | Deterministic proxies, not live semantic judge or human study |
| Python execution | PASS | Actual runner: 2/2 tests, score 100 | None | Hosted runtime pending |
| C execution | PASS | Actual GCC runner: 2/2 tests, score 100 | None | Hosted runtime pending |
| Java execution | PASS | Actual full JDK runner: 2/2 tests, score 100 | None | Hosted JDK/container pending |
| Original backend regression | PASS | Final run: 128 tests, 65.411 s, OK; none disabled | None | Does not certify browser behavior |
| Deployment security tests | PASS | 15 tests, OK | `deployment/tests.py` | No live HTTPS edge yet |
| Camera policy tests | PASS | 10/10 | None | No physical-camera certification |
| API tests | PASS | 4/4 | None | SSR module tests, not real browser tests |
| Frontend build/lint | PASS | npm ci; VITE_API_URL=/api Vite build; oxlint | No frontend changes | Actual browser rendering pending |
| Native camera asset serving | PASS | Gunicorn serves bundled face model and local WASM | Deployment static serving only | Loading assets is not camera consent or analysis verification |
| Blueprint parse/context inspection | PASS | Free plan; Docker path; target branch; generated secrets; no real credentials/paid resources in YAML; private data excluded | `render.yaml`, `.dockerignore` | Render API/build not executed |
| Docker image build | NOT TESTED | No Docker engine in this workspace | `deployment/Dockerfile` | Must execute on hosting service or compatible Docker host |
| Hosted Free plan capacity | NOT TESTED | Backend import/check measured 318380 KiB (~311 MiB); child workers add memory; Free has 512 MB | No dependency reduction | Capacity may require an approved larger service; never silently upgrade |
| HTTPS browser citation click | BLOCKED BY TEST ENVIRONMENT | No hosted URL | None | Must click actual page-1 PDF and refresh |
| Student / teacher / evaluation UI | BLOCKED BY TEST ENVIRONMENT | No hosted URL | None | Must compare visible values against saved API/DB records |
| Camera OFF/ON/revoked/denied | BLOCKED BY TEST ENVIRONMENT | No hosted URL; physical browser interaction not attempted | None | User's physical camera may be needed; not an app failure finding |

## Actual stored evaluation values

These came from the executed disposable benchmark, not constants in the UI.

| Measured deterministic DeepEval proxy | Value |
|---|---:|
| Faithfulness (support-quote occurrence proxy) | 1.000000 |
| Answer relevancy (labelled-concept coverage proxy) | 1.000000 |
| Context precision (gold-location average precision) | 0.955952 |
| Context recall (gold-location coverage) | 0.976190 |

The benchmark is separate from student data. Simulated profiles are explicitly
simulated, not a real human study. These values must **not** be copied into an
empty hosted dashboard; that service must execute/save its own evaluation run.

## Baseline investigation, without hiding failures

The first run using a restored evaluation venv found 128 tests, with one
DeepEval evaluation failure. The actual evaluator exited with SIGBUS (-7) while
importing its restored native gRPC binary. A **fresh Linux** evaluation venv from
unchanged requirements imports gRPC/DeepEval correctly. Baseline then passed
128/128, and the final fresh-application regression passed 128/128 again.
CrewAI remains 1.15.14, LanceDB 0.30.0 (within its required range), Chroma 1.1.1,
LiteLLM 1.96.0 and Pydantic 2.12.5. No Intel Mac package workaround was attempted.
The first baseline failure and diagnostic logs remain in the evidence archive.

The first native HTTP smoke finished all functional checks but its optional
/proc memory probe failed because the environment's PID view does not expose
the subprocess PID. Removing that harness-only probe allowed the complete
smoke to finish. No application change was made for that instrumentation issue.

## Changes and security scope

- `deployment/Dockerfile`: multi-stage unchanged Vite build plus Linux backend,
  original requirements, isolated evaluation venv, native tools and non-root user.
- `deployment/settings.py`: optional settings overlay, DEBUG off, canonical
  HTTPS host/origin, runtime secrets, private `/data` SQLite/media/vectors,
  existing bounded local workers; no schema/BKT changes.
- `deployment/access.py`: additional private deployment password gate and safe
  health route; normal LabTwin role/classroom auth remains mandatory.
- `deployment/frontend.py`, `urls.py`: compiled assets only; no private upload,
  source code, directory listing, answer-key or hidden-test serving.
- `deployment/start.py`: ordinary migrations/static checks/Gunicorn; writable
  original legacy state on the same private data directory.
- `deployment/tests.py`, `README.md`: isolated checks and exact setup/browser steps.
- Root `render.yaml`, `.dockerignore`, `README.md`, this report: deployment only.
- Main branch preserved; original source remains in the checkpoint branch/history.

The gate is for **trusted** test accounts. It does not sandbox submitted code.
Before accepting untrusted public submissions, use the existing separate
isolated runner. No public DEBUG, API keys, environment values, database,
private student records or raw camera frames are included in this commit.
HSTS is enabled, but a temporary provider hostname is deliberately not preloaded;
Django W021 remains visible and unsuppressed. Free hosting is ephemeral: use
new test data, export evidence, and do not import production records.

## Required next actions

1. Add/connect Render so the prepared service can actually be created, or use
   the browser-only deployment setup procedure in `deployment/README.md`.
2. Observe the real Docker build and service health. Verify adequate capacity,
   actual HTTPS, host/proxy behavior, private source access and a Ready upload.
   Do not downgrade packages or choose paid resources without approval.
3. Execute actual citation clicks/refresh and dashboard comparisons. Run/save
   the service's own evaluation rather than importing example dashboard metrics.
4. Execute camera consent OFF, ON with Allow, revoked, and Deny from a physical
   supported browser if the cloud browser lacks camera hardware.
5. Only after those real-browser checks and regression pass, certify demo
   readiness and create a stable demo tag. No final video or demo-ready tag was
   created in this environment.

Evidence archive: `LabTwin-Linux-Deployment-Evidence.zip` (provided separately).
Manual steps and deployment settings: [deployment/README.md](deployment/README.md).
