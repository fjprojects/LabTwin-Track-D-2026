# Optional assessment camera and reasoning reminders

Students can use a camera during diagnostic assessments, quizzes and mock exams. The existing classroom assignment camera/microphone and teacher WebRTC sharing are preserved; the same local cue component can analyze that stream during coding or viva.

## Student workflow

1. Open **Assessments**, choose the scope/format and start an assessment.
2. Read the camera disclosure and tick the consent checkbox. Nothing captures automatically.
3. Select **Turn on assessment camera** and grant browser camera permission. This private preview requests video only, not microphone access.
4. Look at the screen for a few seconds for neutral-posture calibration. Recalibrate after moving the device or changing your seating position.
5. A sustained head-position change or inability to clearly locate a face can produce a neutral reminder. Brief movements are ignored.
6. An optional source-linked own-words check asks the student to explain their reasoning. They can save a written explanation or dismiss the check without a penalty.
7. If the teacher enables eyes-closed prompts **and** the student opts in, the reminder offers: “If comfortable, pause writing, briefly close your eyes and explain aloud in your own words.” Keeping eyes open is equally acceptable. The app never checks eye closure or grades it. A button pauses cues for the explanation.
8. **Stop assessment camera**, navigation away, sign-out, page exit, completion or loss of classroom access stops private capture. A pending permission request that resolves after Stop also releases its tracks.

For classroom assignments, turn on the existing camera/microphone, then explicitly consent and select **Start camera reminders**. **Stop camera reminders** stops analysis only; the existing camera/microphone controls stop live teacher sharing. The activity timeline distinguishes `camera_analysis_started` / `camera_analysis_stopped` from actual camera capture events. Eyes-closed prompts are limited to the viva stage and require both teacher permission and the student's explicit opt-in, including reminders triggered by returning to the page or pasting. The existing **Stop all sharing** control also stops cue analysis.

## Teacher controls and evidence

Under **Assessments → Assessment camera & reasoning checks**, a teacher can enable/disable local cues and optional eyes-closed prompts. Disabling cues does not prevent assessment answers. Active private cameras check authorization and cue settings every five seconds; loss of access stops capture. Assignment creation has equivalent cue/eyes-closed settings.

The review table shows camera-cue counts and voluntary reasoning responses. **Review assessment** opens the timestamped event timeline, question context, source links and saved explanation. Only the current classroom teacher and the owning enrolled student can access the timeline. Removing a student revokes access. Existing assignment events appear in the existing teacher activity timeline.

## Detection and privacy

- Google MediaPipe Face Landmarker runs in a classic Web Worker with a CPU delegate. The official model is bundled; the pinned npm package supplies self-hosted WASM assets. No API key or external inference service is needed.
- The worker discards frames and landmarks after inference. Only transient local head-position ratios reach the UI. No frames, recordings, landmark arrays, device IDs, clipboard text or visited URLs are accepted by the camera-event API.
- Head position is a conservative geometric approximation using nose/face landmarks relative to the student's calibrated posture. It is not eye-gaze tracking. There is no identity matching, emotion estimation, comprehension estimation, phone detection or copying classifier.
- A cue requires at least eight continuous seconds. Missing sample intervals reset continuity; reminders are limited to one per minute. Camera cues pause for hidden pages, source dialogs and voluntary reasoning checks. Returning after an away interval or pasting can offer a separate neutral own-words prompt while the consented camera is active.
- Poor lighting, glasses, disabilities, device position, reading, background interruptions and tracking failures can affect observations. Students can recalibrate, keep eyes open, stop analysis or use written explanations.
- Browser observations are client-reported and can be modified. **They are evidence for review only.** They never establish intent, cheating or knowledge, never automatically penalize students and never update grades or BKT mastery. Understanding is assessed by the existing answer/code/viva assessment pipelines.
- Private assessment preview is not streamed to teachers. Existing assignment camera/microphone sharing remains a separately disclosed live WebRTC operation with its own stop controls.

## Installation and APIs

Run the existing backend setup and `python manage.py migrate` for additive migration **0008_assessment_camera**. No existing records are replaced. From `frontend`, run `npm ci` followed by `npm run dev` or `npm run build`. The predev/prebuild script copies the pinned MediaPipe WASM runtime into `public/camera/wasm`. Serve these generated files and the bundled `.task` model with the frontend. Production camera permission requires HTTPS; localhost is supported for development. The runtime requires Worker, ImageBitmap/OffscreenCanvas and a recent camera-capable browser.

| API | Authorization / purpose |
|---|---|
| `GET/POST /api/learning/assessments/:id/camera-events/` | Owning enrolled student can write; own student/class teacher can read; minimal event whitelist |
| `POST /api/learning/assessment-camera/events/:id/response/` | Owning enrolled student saves/dismisses a voluntary, ungraded reasoning check |
| `GET /api/learning/courses/:id/assessment-activity/` | Classroom teacher lists enrolled students' assessment activity |
| `PATCH /api/learning/courses/:id/` | Classroom teacher sets `camera_cues_enabled`, `camera_eye_closure`; existing `activity_verification` controls fresh checks |
| Existing assignment activity API | Accepts camera cues in the existing private teacher timeline; no media payloads |

Permission denial, absent camera, unsupported browser, missing/corrupt model, inference failure and event-sync errors produce visible messages. The assessment remains usable. Camera metadata has a bounded per-assessment limit; callers cannot upload recordings through these endpoints.

## Tests

```bash
# Application environment, from backend
python manage.py test labtwin.test_assessment_camera labtwin.test_learning_migrations --settings=backend.test_settings
# From frontend
npm run test:camera
npm run lint
npm run build
```

`scripts/e2e_assessment_camera.cjs` tests the real model, explicit consent, face/blank observations, automatic prompt, optional eye closure, saved teacher evidence, metadata privacy, stopped tracks and enrollment revocation. It uses disposable test accounts and a fake camera video; no person's webcam is accessed. Set `LABTWIN_CAMERA_TEST_VIDEO` to a Y4M containing a centered face for at least five seconds followed by at least eleven seconds of blank frames. `LABTWIN_E2E_CHROMIUM` optionally selects a local Chromium executable.

Use `scripts/e2e_server.py` only with a disposable database, as described in the demo guide. In environments that isolate loopback networks per execution command, start the server and browser test from the same process/command and terminate the server after the test. Existing learning and classroom browser scripts also accept `LABTWIN_E2E_CHROMIUM`. For a restricted runtime that requires Chromium's single-process mode, set `LABTWIN_E2E_SINGLE_PROCESS=1`; the shared browser helper launches a separate browser for each isolated context. Ordinary CI uses standard Playwright contexts.

The controlled real-model smoke test is not a field study. No copying-detection accuracy or comprehension-detection accuracy is claimed. Real classroom/device testing is still needed to characterize false prompts.
