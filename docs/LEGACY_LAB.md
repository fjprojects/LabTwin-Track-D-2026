# Existing programming lab and classroom workflows

These preserved workflows remain available alongside course learning. The current setup and learner model are documented in the project README.

## Security

API keys and credentials are not committed. Configure them locally using .env.example.
All student APIs now require sign-in and enforce student ownership. A teacher
can read progress and response history only for students enrolled in their own
classes. Passwords use Django hashing; bearer tokens are stored as hashes on the
server, expire after 24 hours and are revoked by sign-out. The frontend stores
the token and session drafts in browser session storage.

The existing Python/C/Java runner executes submitted programs on the backend
host. Before opening the service to untrusted users, isolate execution in a
restricted container/worker with resource and network limits. Classroom sign-in
does not sandbox submitted code. Keep the Django database and
`student_sessions/` in the LabTwin project directory on persistent storage, and
use HTTPS when hosted.

## Classrooms and assignments

1. Create a teacher account, create a class, and share its join code.
2. Students create their own accounts and join using the code. Joining shares
   their lab progress and response history with that class's teacher.
3. Open the class and publish an assignment with a language, instructions,
   input/output tests, optional deadline and viva question. Paste is allowed by
   default; the teacher can block it and require screen sharing and a viva camera.
4. Students open assignments, start/resume a saved draft, enter code and answer
   the viva. Submission runs the teacher's tests on the server, retains code and
   viva answers even if execution fails, and keeps previous attempts.
5. The teacher can see the roster, lab readiness, response history and assignment
   reports. Reports include code, output/errors, test scores, late status,
   clipboard counts, hidden-page counts and an activity timeline. The teacher
   can give a separate score and feedback and export a CSV summary. Students
   see their own previous submissions and teacher feedback in **My submissions**.

Leaving a class or removing a student revokes the teacher's access to that
student's progress and assessment/live endpoints. Browser live connections close
on the next signaling poll. Submissions remain in the database. A student can
join multiple classes.

New sign-ups create a new owned profile. They cannot claim an old name-only
profile by typing its name or ID. To retain existing demo history, a trusted
administrator must verify the student and link the new account to the old
`StudentProfile` through Django admin (create an admin with
`python manage.py createsuperuser`). Existing history cannot be reconstructed
when earlier versions stored scores without code.

## Live sharing and assessment activity

Students explicitly start screen sharing in the browser picker and grant camera
and microphone permission. Clicking **Answer viva** requests the camera when the
assignment requires it. The student sees who is watching and can stop capture.
Only the class teacher can open **Watch live**. Screen, camera and microphone
streams use WebRTC; the backend handles authenticated signaling and does not
record media. Selecting a single tab shares that tab, so choose the entire screen
when the assessment requires visibility of other apps. Screen capture needs a
supported desktop browser; media access needs HTTPS or localhost.

Configure `WEBRTC_ICE_SERVERS` as a JSON list of STUN/TURN servers in the backend
environment. The default is a public STUN server. Use an authenticated TURN relay
for school networks and connections where a direct peer connection is blocked:

```dotenv
WEBRTC_ICE_SERVERS=[{"urls":"stun:stun.l.google.com:19302"},{"urls":"turn:turn.example.com:3478","username":"YOUR_USER","credential":"YOUR_CREDENTIAL"}]
```

TURN credentials are sent to signed-in participants as part of connection setup;
use a dedicated relay account and rotate credentials or configure short-lived
credentials. Check screen, camera and audio delivery on the actual deployment
and school network before using them for an assessment.

Activity logging is active only while an assignment attempt is open. It records
page visibility/focus changes, copy/cut/paste actions in answer fields, paste
blocks, sharing starts/stops and reminders. Events retry after connection loss
and use IDs to avoid duplicates; pending events must sync before submission.
It stores event metadata and character counts, not clipboard contents, external
URLs, camera images or video recordings. The screen content selected for sharing
is visible to the teacher while sharing is on.

A hidden page can mean a tab switch, minimized window or app switch; a blur event
can come from a permission dialog. Client/browser telemetry can be modified and
does not prove copying or detect another device. Paste blocking is a UI policy,
not a security boundary. A paste or return-to-page event during viva shows an
own-words reminder, including an optional request to briefly close the eyes and
explain the code. This is an event-triggered coaching reminder, not an AI gaze
analysis or an automatic cheating verdict. Camera sharing does not analyze faces
or eye movements. Teachers review the events and explanation before grading.

## Student response history

The **My response history** panel keeps every new initial submission, corrected
submission, viva answer and progressive hint request for the selected student.
It stores the exact submitted code, question snapshot, test output/errors, hint
context and evaluation feedback. Earlier submissions are retained when the same
question is tried again. Existing mastery summaries continue to behave as before.

Responses are saved before execution/evaluation. Test results are saved before
AI feedback is requested, so an AI failure does not erase the student's work.
A response left as `processing` means evaluation did not finish; it is not a pass.
Old code submissions cannot be reconstructed from earlier score-only summaries.

After pulling this change, run `python manage.py migrate` from `backend`, then
rebuild/redeploy the frontend and restart the backend. The Docker startup command
already runs migrations. The history uses the configured Django database: use a
persistent database/disk in hosting so redeploys do not discard SQLite data.

The history API is `GET /api/response-history/?student_id=<id>`; it returns 20
records at a time and a `next_before` cursor for older records. Students can read
their own history. Teachers can read it for students enrolled in their classes.
No submitted student data is stored in GitHub.
