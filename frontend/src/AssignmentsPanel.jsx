import { useEffect, useState } from "react";
import api, { API } from "./api";
import { useLiveSharing } from "./useLiveSharing";
import { useAssessmentEvents } from "./assessmentEvents";
import { SharingControls, TeacherLiveView } from "./LiveSharing";
import { CoachingPanel } from "./learning/PracticeWorkspace";
import { get } from "./learning/api";

const message = error => error.response?.data?.error || "Could not connect. Please retry.";

export default function AssignmentsPanel({ room, teacher, reportsOnly = false, onSource, onViva, onLearningChanged }) {
  const [assignments, setAssignments] = useState([]), [active, setActive] = useState(null);
  const [revision, setRevision] = useState(0), [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState([]);
  useEffect(() => {
    const controller = new AbortController();
    api.get(`${API}/classrooms/${room.id}/assignments/`, { signal: controller.signal })
      .then(({ data }) => setAssignments(data.assignments))
      .catch(err => { if (!controller.signal.aborted) setError(message(err)); });
    return () => controller.abort();
  }, [room.id, revision]);

  async function start(assignment) {
    setBusy(true); setError("");
    try { const { data } = await api.post(`${API}/assignments/${assignment.id}/attempts/`, {}); setActive(data.attempt); }
    catch (err) { setError(message(err)); } finally { setBusy(false); }
  }
  async function loadHistory(assignment) {
    setError("");
    try { const { data } = await api.get(`${API}/assignments/${assignment.id}/submissions/`); setHistory(data.submissions); }
    catch (err) { setError(message(err)); }
  }
  return <section className="classroomBox">
    <h2>{room.name} · Assignments</h2>
    <div hidden={reportsOnly}><button className="secondary" onClick={() => { setError(""); setRevision(value => value + 1); }}>Refresh assignments</button>
    {teacher && <CreateAssignment room={room} onCreated={() => setRevision(value => value + 1)} />}
    {error && <p role="alert">{error}</p>}
    {!assignments.length && <p>No assignments yet.</p>}
    {assignments.map(item => <article key={item.id} className="classroomTile">
      <h3>{item.title} · {item.language}</h3><p style={{ whiteSpace: "pre-wrap" }}>{item.instructions}</p>
      <p>{item.due_at ? `Due: ${new Date(item.due_at).toLocaleString()}` : "No due date"} · Paste {item.allow_paste ? "allowed" : "blocked"} · Screen {item.require_screen ? "required" : "optional"} · Viva camera {item.require_camera ? "required" : "optional"}</p>
      {!teacher && <><button disabled={busy || !!active} onClick={() => start(item)}>Start / resume assignment</button>{" "}<button className="secondary" onClick={() => loadHistory(item)}>My submissions</button></>}
    </article>)}
    </div>
    {active && <StudentAssignment key={active.id} initial={active} onClose={() => setActive(null)} onSource={onSource} onViva={onViva} onLearningChanged={onLearningChanged} />}
    {!teacher && history.map(row => <details key={row.id}><summary>{row.assignment.title} · {row.status} · {row.submitted_at ? new Date(row.submitted_at).toLocaleString() : "In progress"}</summary><pre>{row.code}</pre><p>{row.viva_answer}</p><p>Test score: {row.test_score ?? "Pending"} · Teacher score: {row.teacher_score ?? "Not reviewed"}</p><p>{row.teacher_feedback}</p></details>)}
    {teacher && <TeacherReports room={room} assignments={assignments} />}
  </section>;
}

function CreateAssignment({ room, onCreated }) {
  const [form, setForm] = useState({ title: "", instructions: "", language: "Python", viva_question: "", due: "", allow_paste: true, require_screen: false, require_camera: true, camera_cues_enabled: true, camera_eye_closure: false, topic_id: "", starter_code: "", allow_solution: false });
  const [topics, setTopics] = useState([]);
  useEffect(() => { let active = true; get("courses/").then(data => { if (active) setTopics(data.courses.filter(c => c.classroom_id === room.id).flatMap(c => c.topics.map(t => ({ ...t, course: c.name })))); }).catch(() => {}); return () => { active = false; }; }, [room.id]);
  const [tests, setTests] = useState([{ input: "", expected: "" }]);
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const set = (key, value) => setForm(previous => ({ ...previous, [key]: value }));
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      await api.post(`${API}/classrooms/${room.id}/assignments/`, { ...form, tests, due_at: form.due ? new Date(form.due).toISOString() : null });
      setForm({ title: "", instructions: "", language: "Python", viva_question: "", due: "", allow_paste: true, require_screen: false, require_camera: true, camera_cues_enabled: true, camera_eye_closure: false });
      setTests([{ input: "", expected: "" }]); onCreated();
    } catch (err) { setError(message(err)); } finally { setBusy(false); }
  }
  return <details className="assignmentCreator"><summary>Create an assignment</summary><form onSubmit={submit}>
    <label>Title<input required maxLength={160} value={form.title} onChange={e => set("title", e.target.value)} /></label>
    <label>Instructions<textarea required value={form.instructions} onChange={e => set("instructions", e.target.value)} /></label>
    <label>Language<select value={form.language} onChange={e => set("language", e.target.value)}>{["Python", "C", "Java"].map(item => <option key={item}>{item}</option>)}</select></label>
    <label>Course topic for mastery tracking<select value={form.topic_id || ""} onChange={e => set("topic_id", e.target.value)}><option value="">Existing lab assignment · no course link</option>{topics.map(topic => <option key={topic.id} value={topic.id}>{topic.course} · {topic.name}</option>)}</select></label>
    <label>Starter code (optional)<textarea className="codeEditor" value={form.starter_code || ""} onChange={e => set("starter_code", e.target.value)} /></label>
    <label>Viva question<textarea value={form.viva_question} onChange={e => set("viva_question", e.target.value)} /></label>
    <label>Due date (your local time)<input type="datetime-local" value={form.due} onChange={e => set("due", e.target.value)} /></label>
    <fieldset><legend>Assessment settings</legend>{[["allow_paste", "Allow copy/paste into the answer"], ["require_screen", "Require screen sharing"], ["require_camera", "Require camera and microphone for viva"], ["camera_cues_enabled", "Offer optional on-device camera reminders"], ["camera_eye_closure", "Offer optional eyes-closed explanation during viva"]].map(([key, label]) => <label className="checkLabel" key={key}><input type="checkbox" checked={form[key]} onChange={e => set(key, e.target.checked)} />{label}</label>)}</fieldset>
    <h3>Hidden test cases</h3><p>Students see pass/fail after submitting. Test inputs, expected answers and captured outputs are visible to the teacher.</p>
    {tests.map((test, index) => <div key={index} className="classroomColumns">
      <label>Test {index + 1} input<textarea value={test.input} onChange={e => setTests(previous => previous.map((t, i) => i === index ? { ...t, input: e.target.value } : t))} /></label>
      <label>Expected output<textarea value={test.expected} onChange={e => setTests(previous => previous.map((t, i) => i === index ? { ...t, expected: e.target.value } : t))} /></label>
    </div>)}
    <button type="button" disabled={tests.length >= 20} onClick={() => setTests(previous => [...previous, { input: "", expected: "" }])}>Add test</button>{" "}
    {tests.length > 1 && <button type="button" className="secondary" onClick={() => setTests(previous => previous.slice(0, -1))}>Remove last test</button>}
    {error && <p role="alert">{error}</p>}<div><button disabled={busy}>{busy ? "Saving…" : "Publish assignment to class"}</button></div>
  </form></details>;
}

function StudentAssignment({ initial, onClose, onSource, onViva, onLearningChanged }) {
  const [attempt, setAttempt] = useState(initial), [stage, setStage] = useState("coding");
  const [code, setCode] = useState(initial.code), [viva, setViva] = useState(initial.viva_answer);
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [saved, setSaved] = useState("");
  const events = useAssessmentEvents(attempt, stage);
  const sharing = useLiveSharing(initial.id, events.log);
  const assignment = attempt.assignment, submitted = attempt.status !== "in_progress";
  useEffect(() => {
    if (submitted) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      api.patch(`${API}/attempts/${attempt.id}/`, { code, viva_answer: viva })
        .then(() => { if (!cancelled) setSaved("Draft saved"); })
        .catch(() => { if (!cancelled) setSaved("Draft not saved. Check your connection."); });
    }, 800);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [attempt.id, code, viva, submitted]);

  async function submit(event) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      if (!await events.flush()) throw new Error("Activity log must sync before submitting. Please retry shortly.");
      if (sharing.screen || sharing.camera) await sharing.announce();
      const { data } = await api.post(`${API}/attempts/${attempt.id}/`, { code, viva_answer: viva });
      setAttempt(data.attempt); await sharing.stopAll();
      onLearningChanged?.();
    } catch (err) { setError(err.response ? message(err) : err.message); } finally { setBusy(false); }
  }
  async function pasteCode() {
    try {
      if (!assignment.allow_paste) { events.log("paste_blocked", { field: "code" }); return; }
      const text = await navigator.clipboard.readText();
      setCode(previous => previous + text); events.log("paste", { field: "code", characters: text.length });
    } catch { setError("Clipboard access was denied. Use your browser's normal paste shortcut if paste is allowed."); }
  }
  async function copyCode() {
    try { await navigator.clipboard.writeText(code); events.log("copy", { field: "code", characters: code.length }); }
    catch { setError("Clipboard access was denied. Select the text and use your browser's copy shortcut."); }
  }
  async function close() {
    if (!submitted) {
      try { await api.patch(`${API}/attempts/${attempt.id}/`, { code, viva_answer: viva }); await events.flush(); }
      catch { setError("Could not save your draft. Please retry before leaving."); return; }
    }
    await sharing.stopAll(); onClose();
  }
  return <section className="classroomBox activeAssignment" aria-label="Active assignment">
    <h2>{assignment.title} · Your attempt</h2><button className="secondary" disabled={busy} onClick={close}>Save and close</button>
    <p>During this assignment, LabTwin logs copy/paste actions, hidden-page events and focus changes for teacher review. These events do not prove copying.</p>
    {!submitted && <SharingControls sharing={sharing} assignment={assignment} stage={stage} onCameraEvent={events.log} />}
    {!submitted && <div><button onClick={() => setStage("coding")}>Code</button>{" "}<button onClick={() => {
      setStage("viva"); events.log("viva_started");
      if (assignment.require_camera && !sharing.camera) sharing.startCamera();
    }}>Answer viva</button></div>}
    {events.reminder && !submitted && <aside className="vivaReminder" role="status"><p>{events.reminder}</p><button onClick={() => { events.log("coach_reminder", { message: "Own-words reminder acknowledged" }); events.setReminder(""); }}>I will explain in my own words</button></aside>}
    <form onSubmit={submit}>
      {stage === "coding" && <><label>Your {assignment.language} code<textarea aria-label={`Your ${assignment.language} code`} data-assessment-field="code" className="codeEditor" value={code} readOnly={submitted} onChange={e => setCode(e.target.value)} spellCheck={false} /></label>
        {!submitted && <><button type="button" onClick={copyCode}>Copy code</button>{" "}<button type="button" disabled={!assignment.allow_paste} onClick={pasteCode}>Paste code</button><p>{assignment.allow_paste ? "Paste is allowed and recorded." : "Your teacher has blocked paste for this assignment."}</p></>}
      </>}
      {stage === "viva" && <><p><strong>Viva question:</strong> {assignment.viva_question || "Explain how your program works and why you chose this approach."}</p><label>Your viva answer<textarea aria-label="Your viva answer" data-assessment-field="viva_answer" value={viva} readOnly={submitted} onChange={e => setViva(e.target.value)} /></label><p>You can explain aloud to a teacher who is watching, and save your written explanation here.</p></>}
      {error && <p role="alert">{error}</p>}{events.logError && !submitted && <p role="alert">{events.logError}</p>}
      {!submitted && <><p>{saved}</p><button disabled={busy || !code.trim() || (assignment.require_camera && !sharing.camera) || (assignment.require_screen && !sharing.screen)}>{busy ? "Submitting…" : "Submit code and viva"}</button></>}
    </form>
    {submitted && <><h3>Submitted response</h3><p>Test score: {attempt.test_score ?? "Pending"}{attempt.test_score != null ? "%" : ""}</p>{attempt.error && <p role="alert">{attempt.error}</p>}
      {attempt.test_results.map((test, index) => <div key={index}><p>Test {test.test}: {test.passed ? "Passed" : "Failed"}</p></div>)}
      <p>Teacher score: {attempt.teacher_score ?? "Not reviewed yet"}</p><p>{attempt.teacher_feedback}</p>
    </>}
    {assignment.topic_id && <><CoachingPanel assignmentAttemptId={attempt.id} onSource={onSource} />{onViva && <button className="secondary" onClick={() => onViva({ assignment_attempt_id: attempt.id, topic_id: assignment.topic_id, course_id: assignment.course_id })}>Adaptive viva for this work</button>}</>}
  </section>;
}

function TeacherReports({ room, assignments }) {
  const [reports, setReports] = useState([]), [students, setStudents] = useState([]);
  const [filter, setFilter] = useState(""), [revision, setRevision] = useState(0), [selected, setSelected] = useState(null);
  const [sessions, setSessions] = useState([]), [watching, setWatching] = useState(null), [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    api.get(`${API}/classrooms/${room.id}/reports/`, { params: { assignment_id: filter || undefined }, signal: controller.signal })
      .then(({ data }) => { setReports(data.reports); setStudents(data.students); })
      .catch(err => { if (!controller.signal.aborted) setError(message(err)); });
    return () => controller.abort();
  }, [room.id, filter, revision]);
  useEffect(() => {
    let cancelled = false, running = false;
    async function poll() { if (running) return; running = true;
      try { const { data } = await api.get(`${API}/classrooms/${room.id}/live/`); if (!cancelled) {
        setSessions(data.sessions);
        setWatching(current => current && data.sessions.some(session => session.id === current.id) ? current : null);
      } }
      catch (err) { if (!cancelled) setError(message(err)); } finally { running = false; }
    }
    poll(); const timer = setInterval(poll, 3000); return () => { cancelled = true; clearInterval(timer); };
  }, [room.id]);
  async function download() {
    try {
      const { data } = await api.get(`${API}/classrooms/${room.id}/reports/`, { params: { format: "csv", assignment_id: filter || undefined }, responseType: "blob" });
      const url = URL.createObjectURL(data), link = document.createElement("a"); link.href = url; link.download = "classroom-reports.csv"; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) { setError(message(err)); }
  }
  const missing = students.filter(student => !reports.some(row => row.student_id === student.id && row.status === "submitted"));
  return <section className="classroomBox"><h2>Assignment reports and live monitoring</h2>
    <p>Page-hidden counts include tab changes, minimizing and some app switches. Focus changes can also come from browser permission dialogs. Review the timeline before drawing conclusions.</p>
    <label>Assignment<select value={filter} onChange={e => { setFilter(e.target.value); setSelected(null); }}><option value="">All assignments</option>{assignments.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>
    <button onClick={() => { setError(""); setRevision(value => value + 1); }}>Refresh reports</button>{" "}<button onClick={download}>Download CSV report</button>
    {error && <p role="alert">{error}</p>}
    {!!missing.length && <p>No completed submission{filter ? " for this assignment" : " yet"}: {missing.map(student => student.name).join(", ")}</p>}
    <div className="rosterScroll"><table><thead><tr><th>Student / assignment</th><th>Status</th><th>Test / teacher score</th><th>Tab/hidden-page events</th><th>Paste / blocked</th><th>Review</th></tr></thead><tbody>
      {reports.map(row => <tr key={row.id}><td>{row.student_name}<small>{row.assignment.title}</small></td><td>{row.status}{row.late && " · late"}</td><td>{row.test_score ?? "—"} / {row.teacher_score ?? "—"}</td><td>{row.event_counts.page_hidden || 0}</td><td>{row.event_counts.paste || 0} / {row.event_counts.paste_blocked || 0}</td><td><button onClick={() => setSelected(row)}>View full report</button></td></tr>)}
    </tbody></table></div>
    {!reports.length && <p>No attempts yet.</p>}
    <h3>Students sharing now</h3>{!sessions.length && <p>No active screen or camera shares.</p>}
    {sessions.map(session => <div key={session.id}><p>{session.student_name} · {session.assignment_title} · Screen {session.screen_active ? "on" : "off"} · Camera {session.camera_active ? "on" : "off"}</p><button onClick={() => setWatching(session)}>Watch live</button></div>)}
    {watching && <TeacherLiveView key={`live-${watching.id}`} session={watching} onClose={() => setWatching(null)} />}
    {selected && <SubmissionReview key={`report-${selected.id}`} report={selected} onSaved={() => setRevision(value => value + 1)} onClose={() => setSelected(null)} />}
  </section>;
}

export function SubmissionReview({ report, onSaved, onClose }) {
  const [events, setEvents] = useState([]), [score, setScore] = useState(report.teacher_score ?? ""), [feedback, setFeedback] = useState(report.teacher_feedback);
  const [error, setError] = useState(""), [busy, setBusy] = useState(false), [saved, setSaved] = useState(false);
  useEffect(() => {
    const controller = new AbortController(); api.get(`${API}/attempts/${report.id}/events/`, { signal: controller.signal }).then(({ data }) => setEvents(data.events))
      .catch(err => { if (!controller.signal.aborted) setError(message(err)); }); return () => controller.abort();
  }, [report.id]);
  async function grade(event) {
    event.preventDefault(); setBusy(true); setError("");
    try { await api.post(`${API}/attempts/${report.id}/grade/`, { score, feedback }); setSaved(true); onSaved(); }
    catch (err) { setError(message(err)); } finally { setBusy(false); }
  }
  return <section className="classroomBox"><h3>{report.student_name} · {report.assignment.title}</h3><button className="secondary" onClick={onClose}>Close report</button>
    <p>Started: {new Date(report.started_at).toLocaleString()} · Submitted: {report.submitted_at ? new Date(report.submitted_at).toLocaleString() : "Not yet"}</p>
    <h4>Submitted code</h4><pre>{report.code || "No code saved yet"}</pre><h4>Viva answer</h4><p style={{ whiteSpace: "pre-wrap" }}>{report.viva_answer || "No answer saved yet"}</p>
    {report.test_results.map((test, i) => <details key={i}><summary>Test {test.test}: {test.passed ? "Passed" : "Failed"}</summary><p>Input</p><pre>{test.input}</pre><p>Expected</p><pre>{test.expected}</pre><p>Student output</p><pre>{test.stdout}</pre>{test.stderr && <pre>{test.stderr}</pre>}</details>)}
    <h4>Activity timeline</h4><p>{report.review_note}</p><ul>{events.map((event, i) => <li key={i}>{new Date(event.detail.observed_at || event.created_at).toLocaleTimeString()} · {event.stage} · {event.kind.replaceAll("_", " ")}{event.detail.duration_ms ? ` · ${Math.round(event.detail.duration_ms / 1000)} seconds away` : ""}{event.detail.field ? ` · ${event.detail.field}` : ""}</li>)}</ul>
    {["submitted", "failed"].includes(report.status) && <form onSubmit={grade}><label>Teacher score (0–100)<input type="number" min={0} max={100} step="0.1" value={score} onChange={e => { setScore(e.target.value); setSaved(false); }} /></label><label>Teacher feedback<textarea value={feedback} onChange={e => { setFeedback(e.target.value); setSaved(false); }} /></label><button disabled={busy}>{busy ? "Saving…" : "Save teacher review"}</button>{saved && <p role="status">Review saved.</p>}</form>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
