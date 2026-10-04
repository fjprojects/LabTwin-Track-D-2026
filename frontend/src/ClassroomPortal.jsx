import { Suspense, lazy, useEffect, useState } from "react";
import api, { API } from "./api";
import ResponseHistory from "./components/ResponseHistory";
import AssignmentsPanel from "./AssignmentsPanel";
import LearningPortal from "./learning/LearningPortal";
import PasswordReset from "./auth/PasswordReset";
import { initialResetTarget, RESET_STORAGE_KEY } from "./auth/resetLink";
import "./ClassroomPortal.css";

const message = error => error.response?.data?.error || "Could not connect. Please try again.";
const App = lazy(() => import("./App"));

export default function ClassroomPortal() {
  const [account, setAccount] = useState(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [register, setRegister] = useState(false);
  const [form, setForm] = useState({ username: "", password: "", email: "", name: "", role: "student" });
  const [resetTarget, setResetTarget] = useState(initialResetTarget);
  const [recovering, setRecovering] = useState(() => Boolean(initialResetTarget()));

  useEffect(() => {
    // Consume the private-gate handoff and remove credentials from browser
    // history once copied into component memory. Reopen the email after a refresh.
    if (window.location.hash.startsWith("#password-reset="))
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
    try { sessionStorage.removeItem(RESET_STORAGE_KEY); } catch { /* Storage can be disabled. */ }
  }, []);

  function clearSession() {
    window.dispatchEvent(new Event("labtwin-stop-sharing"));
    sessionStorage.removeItem("labtwin_access_token");
    sessionStorage.removeItem("labtwin_student");
    Object.keys(sessionStorage).filter(key => key.startsWith("labtwin_draft_")).forEach(key => sessionStorage.removeItem(key));
    setAccount(null);
  }

  async function prepareAccount(user) {
    sessionStorage.removeItem("labtwin_student");
    if (user.role === "student") {
      const { data } = await api.post(`${API}/start-student/`, {});
      sessionStorage.setItem("labtwin_student", JSON.stringify(data));
    }
    return user;
  }

  useEffect(() => {
    let active = true;
    const expired = () => { clearSession(); setError("Your session ended. Please sign in again."); };
    window.addEventListener("labtwin-signout", expired);
    async function restore() {
      if (!sessionStorage.getItem("labtwin_access_token")) { setBusy(false); return; }
      try {
        const { data } = await api.get(`${API}/auth/me/`);
        const user = await prepareAccount(data.account);
        if (active) setAccount(user);
      } catch (err) {
        if (active) { clearSession(); setError(message(err)); }
      } finally { if (active) setBusy(false); }
    }
    restore();
    return () => { active = false; window.removeEventListener("labtwin-signout", expired); };
  }, []);

  async function submit(event) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const { data } = await api.post(`${API}/auth/${register ? "register" : "login"}/`, form);
      sessionStorage.setItem("labtwin_access_token", data.token);
      setAccount(await prepareAccount(data.account));
      setForm(previous => ({ ...previous, password: "" }));
    } catch (err) { clearSession(); setError(message(err)); }
    finally { setBusy(false); }
  }

  async function signOut() {
    try { await api.post(`${API}/auth/logout/`, {}); }
    catch { setError("Signed out on this device. The server session expires automatically within 24 hours."); }
    finally { clearSession(); }
  }

  if (recovering) return <PasswordReset key={resetTarget ? "confirm" : "request"} target={resetTarget}
    onComplete={() => clearSession()}
    onRequestNew={() => setResetTarget(null)}
    onBack={() => { setRecovering(false); setResetTarget(null); setRegister(false); setError(""); }} />;

  if (!account) return <main className="classroomPortal authCard">
    <p className="eyebrow">LABTWIN · CLASSROOMS</p>
    <h1>Your learning classroom</h1>
    <p>Learn from your course materials, practise programming and build understanding. Teachers follow progress with evidence.</p>
    <form onSubmit={submit}>
      {register && <label>Your name<input required maxLength={100} autoComplete="name" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} /></label>}
      {register && <label>Email (for password recovery)<input type="email" maxLength={254} autoComplete="email" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} /></label>}
      <label>Username<input required maxLength={150} autoComplete="username" value={form.username} onChange={e => setForm({ ...form, username: e.target.value })} /></label>
      <label>Password<input required type="password" autoComplete={register ? "new-password" : "current-password"} value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} /></label>
      {register && <label>I am a<select value={form.role} onChange={e => setForm({ ...form, role: e.target.value })}><option value="student">Student</option><option value="teacher">Teacher</option></select></label>}
      {error && <p role="alert">{error}</p>}
      <button disabled={busy}>{busy ? "Please wait…" : register ? "Create account" : "Sign in"}</button>
      {!register && <button type="button" className="secondary" disabled={busy} onClick={() => { setRecovering(true); setError(""); }}>Forgot password?</button>}
      <button type="button" className="secondary" disabled={busy} onClick={() => { setRegister(!register); setError(""); }}>{register ? "Already have an account? Sign in" : "New here? Create an account"}</button>
    </form>
  </main>;

  return <LearningPortal account={account} onSignOut={signOut}
    onSwitchAccount={async user => { setAccount(await prepareAccount(user)); }}
    renderClassrooms={props => <Classrooms key={account.id} account={account} {...props} />}
    renderLab={() => <Suspense fallback={<p>Opening your programming lab…</p>}><App key={account.id} onLogout={signOut} /></Suspense>} />;
}

function Classrooms({ account, mode, classroomId, onSource, onViva, onChanged }) {
  const teacher = account.role === "teacher";
  const [rooms, setRooms] = useState([]);
  const [selected, setSelected] = useState(null);
  const [roster, setRoster] = useState([]);
  const [student, setStudent] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadingRoster, setLoadingRoster] = useState(false);
  const [form, setForm] = useState({ name: "", subject: "", code: "" });
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    api.get(`${API}/classrooms/`, { signal: controller.signal }).then(({ data }) => setRooms(data.classrooms))
      .catch(err => { if (!controller.signal.aborted) setError(message(err)); });
    return () => controller.abort();
  }, [revision]);

  useEffect(() => {
    if (classroomId && rooms.some(room => room.id === classroomId)) setSelected(rooms.find(room => room.id === classroomId));
    else if (["Assignments", "Students", "Reports"].includes(mode) && rooms.length) setSelected(previous => previous || rooms[0]);
  }, [classroomId, mode, rooms]);

  useEffect(() => {
    setRoster([]); setStudent(null);
    if (!selected || !teacher) return;
    const controller = new AbortController();
    setLoadingRoster(true); setError("");
    api.get(`${API}/classrooms/${selected.id}/students/`, { signal: controller.signal })
      .then(({ data }) => setRoster(data.students))
      .catch(err => { if (!controller.signal.aborted) setError(message(err)); })
      .finally(() => { if (!controller.signal.aborted) setLoadingRoster(false); });
    return () => controller.abort();
  }, [selected, teacher, revision]);

  async function createOrJoin(event) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const { data } = await api.post(`${API}/classrooms/${teacher ? "" : "join/"}`, form);
      setForm({ name: "", subject: "", code: "" });
      if (teacher) setSelected(data.classroom);
      setRevision(value => value + 1);
      onChanged?.();
    } catch (err) { setError(message(err)); }
    finally { setBusy(false); }
  }

  async function remove(roomId, studentId) {
    if (!window.confirm(teacher ? "Remove this student from the classroom? Their saved work will remain." : "Leave this classroom? Your saved work will remain.")) return;
    setBusy(true); setError("");
    try {
      await api.delete(`${API}/classrooms/${roomId}/students/${studentId}/`);
      setStudent(null); setRevision(value => value + 1);
    } catch (err) { setError(message(err)); }
    finally { setBusy(false); }
  }

  return <>
    <div className="classroomColumns">
      <section className="classroomBox" hidden={!["Classes", "My Courses"].includes(mode)}><h2>{teacher ? "Create a classroom" : "Join a classroom"}</h2>
        <form onSubmit={createOrJoin}>
          {teacher ? <>
            <label>Class name<input required maxLength={120} value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="CSE · Semester 3" /></label>
            <label>Subject<input maxLength={120} value={form.subject} onChange={e => setForm({ ...form, subject: e.target.value })} placeholder="Data Structures Lab" /></label>
          </> : <>
            <label>Class code<input required maxLength={16} value={form.code} onChange={e => setForm({ ...form, code: e.target.value })} placeholder="Code from your teacher" /></label>
            <p>Joining lets this teacher view all your LabTwin progress and saved responses. Leaving removes their access unless you share another class.</p>
          </>}
          <button disabled={busy}>{teacher ? "Create class" : "Join class"}</button>
        </form>
      </section>
      <section className="classroomBox"><h2>My classrooms</h2>
        <button className="secondary" disabled={busy} onClick={() => { setError(""); setRevision(value => value + 1); }}>Refresh</button>
        {!rooms.length && <p>No classrooms yet.</p>}
        {rooms.map(room => <article className="classroomTile" key={room.id}>
          <h3>{room.name}</h3><p>{room.subject} · {room.teacher}</p>
          {teacher ? <><p>Join code: <strong className="joinCode">{room.join_code}</strong></p><p>{room.student_count} students</p><button onClick={() => setSelected(room)}>Open class</button></> : <><button onClick={() => setSelected(room)}>Open assignments</button>{" "}<button disabled={busy} className="secondary" onClick={() => remove(room.id, account.student_id)}>Leave class</button></>}
        </article>)}
      </section>
    </div>
    {error && <p role="alert" className="classroomBox">{error}</p>}
    {selected && teacher && ["Classes", "Students"].includes(mode) && <section className="classroomBox">
      <h2>{selected.name} · Students</h2>
      <p>Review progress across each student's LabTwin topics and saved responses.</p>
      {loadingRoster ? <p role="status">Loading students…</p> : !roster.length ? <p>No students have joined yet. Share the class code with your students.</p> : <div className="rosterScroll"><table>
        <thead><tr><th>Student</th><th>Topics tested</th><th>Topics mastered</th><th>Saved responses</th><th>Actions</th></tr></thead>
        <tbody>{roster.map(item => <tr key={item.student_id}><td>{item.name}<small>@{item.username}</small></td><td>{item.topics_tested}</td><td>{item.topics_mastered}</td><td>{item.response_count}</td><td><button onClick={() => setStudent(item)}>Review</button> <button disabled={busy} className="secondary" onClick={() => remove(selected.id, item.student_id)}>Remove</button></td></tr>)}</tbody>
      </table></div>}
    </section>}
    <div hidden={!selected || !["Classes", "My Courses", "Assignments", "Reports"].includes(mode)}>{selected && <AssignmentsPanel key={selected.id} room={selected} teacher={teacher} reportsOnly={mode === "Reports"} onSource={onSource} onViva={onViva} onLearningChanged={onChanged} />}</div>
    {student && <StudentReview key={`${selected.id}:${student.student_id}`} student={student} onClose={() => setStudent(null)} />}
  </>;
}

function StudentReview({ student, onClose }) {
  const [progress, setProgress] = useState(null);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setError(""); setProgress(null);
    api.get(`${API}/progress/`, { params: { student_id: student.student_id }, signal: controller.signal })
      .then(({ data }) => setProgress(data))
      .catch(err => { if (!controller.signal.aborted) setError(message(err)); });
    return () => controller.abort();
  }, [student.student_id, version]);
  return <section className="classroomBox">
    <h2>{student.name} · Progress</h2><button onClick={() => setVersion(value => value + 1)}>Refresh progress</button> <button className="secondary" onClick={onClose}>Close review</button>
    {error && <p role="alert">{error}</p>}
    {!progress && !error && <p role="status">Loading progress…</p>}
    {progress && <><p className="readiness">Lab readiness: {Number(progress.lab_readiness || 0).toFixed(1)}%</p>
      <div className="rosterScroll"><table><thead><tr><th>Topic</th><th>Status</th><th>Mastery</th><th>Hint level</th><th>Misconception</th></tr></thead><tbody>
        {(progress.topics || []).map((topic, i) => <tr key={i}><td>{topic.topic}</td><td>{topic.status}</td><td>{Number(topic.mastery_score || 0).toFixed(1)}%</td><td>{Number(topic.average_hint_level || 0).toFixed(1)}</td><td>{topic.last_misconception || "—"}</td></tr>)}
      </tbody></table></div>
      {!progress.topics?.length && <p>No topic progress recorded yet.</p>}
      <ResponseHistory title="Student response history" api={API} studentId={student.student_id} version={version} />
    </>}
  </section>;
}
