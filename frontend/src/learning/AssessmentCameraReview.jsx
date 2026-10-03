import { useEffect, useState } from "react";
import api from "../api";
import { base, get, errorText } from "./api";
import SourceLinks from "./SourceLinks";
import "../camera/AssessmentCamera.css";

export default function AssessmentCameraReview({ course, onSource }) {
  const [rows, setRows] = useState([]), [policy, setPolicy] = useState(course.camera_policy), [selected, setSelected] = useState(null);
  const [events, setEvents] = useState([]), [error, setError] = useState(""), [busy, setBusy] = useState(false), [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    get(`courses/${course.id}/assessment-activity/`).then(data => { if (active) { setRows(data.assessments); setPolicy(data.policy); } }).catch(err => { if (active) setError(errorText(err)); });
    return () => { active = false; };
  }, [course.id, revision]);
  useEffect(() => {
    let active = true; setEvents([]);
    if (selected) get(`assessments/${selected.id}/camera-events/`).then(data => { if (active) setEvents(data.events); }).catch(err => { if (active) setError(errorText(err)); });
    return () => { active = false; };
  }, [selected, revision]);
  async function setting(field, value) {
    const before = policy;
    const policyField = field === "camera_cues_enabled" ? "enabled" : "offer_eye_closure";
    setPolicy(previous => ({ ...previous, [policyField]: value }));
    setBusy(true); setError("");
    try { const { data } = await api.patch(`${base}/courses/${course.id}/`, { [field]: value }); setPolicy(data.course.camera_policy); setRevision(v => v + 1); }
    catch (err) { setPolicy(before); setError(errorText(err)); }
    finally { setBusy(false); }
  }
  return <section className="classroomBox" aria-label="Assessment camera review"><h2>Assessment camera & reasoning checks</h2>
    <p>Students explicitly opt in before camera analysis starts. Frames remain on their device. You see event metadata and optional explanations, not a recording.</p>
    <p className="methodNote">{policy?.interpretation || "Camera cues are fallible observations, not proof of copying or understanding. They never change grades or mastery."}</p>
    <label className="checkLabel"><input type="checkbox" disabled={busy} checked={!!policy?.enabled} onChange={e => setting("camera_cues_enabled", e.target.checked)} />Offer automatic on-device camera reminders</label>
    <label className="checkLabel"><input type="checkbox" disabled={busy} checked={!!policy?.offer_eye_closure} onChange={e => setting("camera_eye_closure", e.target.checked)} />Allow optional eyes-closed, own-words prompts</label>
    <p>Students can keep their eyes open, stop camera analysis, or answer the reasoning check in writing. Eye closure is never required or graded.</p>
    <button className="secondary" onClick={() => setRevision(v => v + 1)}>Refresh assessment activity</button>{error && <p role="alert">{error}</p>}
    <div className="rosterScroll"><table><thead><tr><th>Student</th><th>Assessment</th><th>Camera cues</th><th>Reasoning responses</th><th>Evidence</th></tr></thead><tbody>{rows.map(row => <tr key={row.id}><td>{row.student}</td><td>{row.kind} · {row.status}</td><td>{row.summary.counts.camera_cue || 0}</td><td>{row.summary.verification_answers}</td><td><button className="secondary" onClick={() => setSelected(row)}>Review assessment {row.id}</button></td></tr>)}</tbody></table></div>
    {!rows.length && <p>No assessments to review yet.</p>}
    {selected && <article className="topicEvidence"><h3>{selected.student} · Camera activity timeline</h3><button className="secondary" onClick={() => setSelected(null)}>Close activity timeline</button><ul className="cameraTimeline">{events.map(event => <li key={event.id}><time>{new Date(event.created_at).toLocaleString()}</time><strong>{event.kind.replaceAll("_", " ")}</strong>{event.detail.reason && <p>Observation: {event.detail.reason.replaceAll("_", " ")} · {Math.round((event.detail.duration_ms || 0) / 1000)} seconds</p>}<p>{event.detail.instruction}</p>{event.detail.verification && <><p><strong>Own-words check:</strong> {event.detail.verification.prompt}</p><p>{event.detail.verification.question_prompt}</p><SourceLinks items={event.detail.verification.resources} onSource={onSource} /><p>Status: {event.detail.verification.status} · Voluntary, ungraded</p>{event.detail.verification.answer && <p className="sourceText">{event.detail.verification.answer}</p>}</>}</li>)}</ul>{!events.length && <p>No camera observations recorded. This does not establish whether a student copied or understood the work.</p>}</article>}
  </section>;
}
