# Private Linux browser acceptance deployment

This optional deployment packages the **existing** Django and React/Vite
application from the hardening branch. The original Dockerfile, requirements,
migrations, classroom authorization, learning model and frontend are retained.
It does not require Python or LabTwin dependencies on the browser computer.

## Render setup

1. Add/connect the Render integration to let the assistant create and inspect
   the service, or sign in at <https://dashboard.render.com/> in your browser.
2. Create a **Blueprint** from `fjprojects/LabTwin-Track-D-2026`. Choose branch
   `hardening/track-d-demo-20261003` and the root `render.yaml` file. The
   [deployment setup link](https://render.com/deploy?repo=https%3A%2F%2Fgithub.com%2Ffjprojects%2FLabTwin-Track-D-2026%2Ftree%2Fhardening%2Ftrack-d-demo-20261003)
   selects this branch; it is not a live application URL. Confirm the
   configured plan is **Free**; the file requests no paid disk or worker.
3. Render builds `deployment/Dockerfile`. It builds the unchanged Vite UI with
   `VITE_API_URL=/api`, installs the unchanged application/evaluation requirements
   in separate environments, and installs Tesseract, FFmpeg, GCC and a full JDK.
4. Startup runs ordinary migrations, collects Django static files, performs
   deployment checks, then starts Gunicorn with one worker/two threads. The
   existing local bounded dispatcher handles extraction and evaluations with
   child-process deadlines, against the same database and private storage.
5. Wait until the service is **Live**. Use the **actual URL shown by Render**;
   do not infer a domain from the service name. Confirm HTTPS and inspect
   `/deployment/health/`, which returns only `{"status":"ok"}`.
6. In the service's Environment page, privately copy the generated
   `LABTWIN_DEPLOYMENT_PASSWORD`. Enter it in the private-access form at the
   actual service URL. Do not share it in a public demo, repository or report.
   Then create/sign in to normal LabTwin teacher/student test accounts.

The generated `DJANGO_SECRET_KEY` stays server-side. Render generates a
256-bit secret; short base64 representations are deterministically expanded to
64 hex characters for Django's length check. Existing secrets of 50+ characters
are used unchanged. No secret is baked into the image or Vite build.

The original application auth still runs after the additional private gate.
The gate uses a signed, Secure/HttpOnly/SameSite=Strict cookie with a 12-hour
expiry, leaving bearer Authorization headers intact. Private uploads and source
URLs still go through the original classroom checks and signed media routes.
Rotating the deployment password invalidates gate cookies; rotating the Django
key invalidates signed gate/media tickets. Reopen a citation to refresh its
five-minute source URL.

## Temporary hosting limitations

- Free Render services have 512 MB memory, ephemeral filesystems and can restart
  or spin down. **Capacity and the actual Docker build must be tested on the
  hosting service.** Do not count local checks as a hosted deployment pass.
- `/data` contains the SQLite database, private originals/figures, vector index
  and legacy session state. On the Free plan these survive only while that
  instance's filesystem remains intact. Use disposable test data and download
  reports/evaluation evidence before stopping/redeploying. Do not import the
  existing production database or real student records.
- No paid resource is automatically requested. A sustained deployment needs
  sufficient compute and an approved persistent disk mounted at `/data`.
  Obtain approval before selecting paid resources. Do not reduce dependencies
  or disable tests to fit a smaller plan.
- The private gate limits this deployment to trusted browser acceptance tests.
  **Do not share its access password with untrusted users.** Before a public
  student rollout, configure the existing separate isolated Docker execution
  worker from `executor/README.md`; the compatibility runner executes on the
  application host. Do not expose the Docker socket to the Django container.
- The template explicitly selects existing `hash` embeddings for repeatable
  offline tests. They are lexical feature hashing, not neural embeddings.
  Without `GROQ_API_KEY`, grounded tutoring uses clearly labelled source
  excerpts; arbitrary vision/STT and legacy provider-backed AI need their
  existing provider configuration. The deterministic DeepEval mode is a
  measured proxy, not a semantic LLM judge or a human learning study.
- HSTS is enabled for an hour. The temporary hostname is deliberately not
  preloaded; Django's `security.W021` warning remains visible, unsuppressed.
  No debug page, key, private rubric, answer key or hidden test is served.

## Manual real-browser acceptance

Use Chrome/Edge or another supported desktop browser at the actual HTTPS URL.
The old Intel Mac needs only that browser. Keep developer tools available to
compare saved API values with UI values; never copy bearer tokens into reports.

### Citation

1. Sign in as a teacher. Create a classroom/course or prepare the existing
   guided Demo Mode. In **Course Materials**, upload `Record(1).pdf`.
2. Observe queued/processing becoming **Ready**. An error is not a Ready result;
   retain the displayed error and logs if it fails.
3. Join the same classroom as a student, or enter the isolated demo learner.
   Select that course/material and ask **How is a palindrome checked with charAt?**
4. Click the answer's `Record(1).pdf — Page 1` citation. Inspect the **rendered
   PDF**, including the viewer's page indicator and page-1 contents. A label or
   iframe URL alone does not prove the rendered page is correct.
5. Close/reopen the source, refresh the browser and reopen its citation. Confirm
   the correct document/page again. A different classroom student must not be
   able to open the source through the authenticated source API.
6. Ask an off-material question, such as tomorrow's Tokyo weather. Confirm a
   refusal without invented source citations.

### Dashboards

1. Complete actual student practice/assessments. Include an incorrect answer,
   its cited feedback, and a successful reassessment. The guided demo also
   supports a real failed C submission, hints, corrected code and follow-up.
2. Open **Dashboard**, **Mastery Map** and **Progress**. Compare displayed values
   with the selected course's `/path/`, `/report/` and `/assessments/` responses
   under `/api/learning/courses/<id>/`, plus `/api/learning/topics/<id>/`.
3. Return to the teacher and open **AI Insights**. Inspect the actual student,
   topic, mastery, weaknesses and retained evidence. Compare with the course's
   `/insights/` response and expand the supporting record IDs.
4. In **Evaluation**, run **deterministic** evaluation. Wait for Completed;
   inspect saved `/api/learning/evaluations/<id>/` results. Match all visible
   values and the proxy/simulated labels to those saved results. Download the
   evidence. Never substitute example values for a failed/missing run.

### Camera (physical browser)

1. Start a student assessment with camera consent **off**. No camera indicator,
   preview or analysis should start; no `camera_started` observation is valid.
2. Enable the displayed camera consent/start control, then **Allow** the browser
   permission prompt. Confirm the camera preview/status and permitted analysis.
   If the teacher disabled cues, enable them through existing course settings.
3. Revoke consent/use **Stop camera**. The stream and analysis must stop. Confirm
   the hardware indicator turns off and no further cues are recorded. Keep the
   browser open briefly and inspect the camera evidence timeline.
4. Reset/block camera permission for that origin, start again, and **Deny** the
   prompt. Confirm a clear error with a usable assessment, without a spinner or
   crash. Restore permission afterwards in browser site settings.
5. Camera events themselves must not change grades/mastery or declare cheating.
   Compare values before/after a cue **without submitting an answer**. Frames
   remain on the device; only the existing allowed observations are retained.

A cloud browser without a physical camera is **BLOCKED BY TEST ENVIRONMENT** for
the physical consent/stream checks, not evidence of an application failure.

## Other compatible Linux hosting

Build from the repository root:

```bash
docker build -f deployment/Dockerfile -t labtwin-private-demo .
```

Set these runtime variables privately in the hosting dashboard/secret store:

| Variable | Value/purpose |
|---|---|
| `DJANGO_SECRET_KEY` | Strong random signing secret, 43+ characters; prefer 50+ |
| `LABTWIN_DEPLOYMENT_PASSWORD` | Strong random private-access password, 24+ characters |
| `LABTWIN_PUBLIC_URL` | Exact HTTPS origin; Render can infer its assigned hostname |
| `LABTWIN_DATA_DIR` | `/data`; mount approved persistent storage here if needed |
| `LABTWIN_EMBEDDING_BACKEND` | `hash` for explicitly offline tests, or existing `onnx` with a warmed model cache |
| `LABTWIN_DEMO_ENABLED` | `true` for the existing guided demo |
| `GROQ_API_KEY` | Optional existing provider credential; never a frontend build argument |
| `LABTWIN_VISION_MODEL` | Existing supported vision model, if configured |
| `LABTWIN_RUNNER_URL`, `LABTWIN_RUNNER_SECRET` | Existing private isolated worker for untrusted submissions |
| `PORT` | Host-provided HTTP port, default 10000 |

Use a trusted HTTPS reverse proxy that overwrites `X-Forwarded-Proto`. Never
expose Gunicorn's HTTP port directly to public traffic. No localhost API URL is
embedded in the deployed frontend.

## Verification commands

Run the original tests unchanged, using separate application/evaluation
environments as documented in the main README. With the deployment runtime
variables present, `PYTHONPATH=<repo>:<repo>/backend`, and
`DJANGO_SETTINGS_MODULE=deployment.settings`, additionally run:

```bash
python backend/manage.py test deployment.tests --noinput
python backend/manage.py check --deploy
python backend/manage.py migrate --noinput
python backend/manage.py makemigrations --check --dry-run
```

These checks cover the private access gate, secret requirements, HTTPS/host
configuration, preserved application auth, compiled assets, path traversal and
camera permission policy. They do not certify a real browser click or camera.

Hosting references: [Docker](https://render.com/docs/docker),
[Blueprint schema](https://render.com/docs/blueprint-spec),
[generated secrets](https://render.com/docs/configure-environment-variables),
[health checks](https://render.com/docs/health-checks),
[Free plan limitations](https://render.com/docs/free).
