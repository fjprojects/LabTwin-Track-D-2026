import { useEffect, useState } from "react";
import { get, post, errorText } from "./api";
import SourceLinks from "./SourceLinks";

export default function VivaWorkspace({ course, target, onSource, onCompleted }) {
  const [sessions, setSessions] = useState([]), [session, setSession] = useState(null), [topicId, setTopicId] = useState(target?.topic_id || ""), [answer, setAnswer] = useState(""), [busy, setBusy] = useState(false), [error, setError] = useState("");
  useEffect(() => { let active = true; setSession(null); setError(""); get(`courses/${course.id}/vivas/`).then(data => { if (active) setSessions(data.sessions); }).catch(err => { if (active) setError(errorText(err)); }); return () => { active = false; }; }, [course.id]);
  useEffect(() => { if (target?.topic_id) setTopicId(target.topic_id); }, [target]);
  async function start() {
    setBusy(true); setError("");
    try { const data = await post(`courses/${course.id}/vivas/`, target || { topic_id: topicId }); setSession(data.session); setSessions(previous => [data.session, ...previous]); setAnswer(""); }
    catch (err) { setError(errorText(err)); } finally { setBusy(false); }
  }
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError("");
    try { const data = await post(`vivas/${session.id}/answer/`, { turn_id: session.turns.find(t => t.score == null).id, answer }); setSession(data.session); setSessions(previous => previous.map(s => s.id === data.session.id ? data.session : s)); setAnswer(""); onCompleted(); }
    catch (err) { setError(errorText(err)); } finally { setBusy(false); }
  }
  const current = session?.turns.find(turn => turn.score == null);
  return <section className="classroomBox"><p className="eyebrow">EXPLAIN YOUR THINKING</p><h2>Adaptive AI Viva</h2><p>Questions connect your work, previous answers and course sources. AI feedback is provisional and available for teacher review.</p><p>For teacher-supervised camera, microphone and screen access, use Answer viva inside the classroom assignment. Those permission controls remain available there.</p><div className="compactForm"><label>Viva topic<select aria-label="Viva topic" value={topicId} onChange={e => setTopicId(e.target.value)} disabled={!!target}><option value="">Choose topic</option>{course.topics.map(topic => <option key={topic.id} value={topic.id}>{topic.name}</option>)}</select></label><button onClick={start} disabled={busy || (!topicId && !target)}>Start adaptive viva</button></div>{target && <p>Linked to your {target.assignment_attempt_id ? "classroom assignment" : "practice submission"}.</p>}{error && <p role="alert">{error}</p>}
    {session && <article className="vivaConversation"><p>{session.reason}</p><SourceLinks items={session.resources} onSource={onSource} />{session.turns.filter(t => t.score != null).map(turn => <details key={turn.id} open><summary>{turn.question}</summary><p className="sourceText">{turn.answer}</p><p>{turn.feedback}</p><span className="statusTag">{turn.score}% · {turn.assessment_mode === "teacher_reviewed" ? "Teacher reviewed" : "Provisional estimate"}</span></details>)}{current ? <form onSubmit={submit}><h3>{current.question}</h3><label>Your conceptual answer<textarea required maxLength={20000} value={answer} onChange={e => setAnswer(e.target.value)} /></label><button disabled={busy}>{busy ? "Saving your answer…" : "Save answer and continue"}</button></form> : <p>Viva complete. Review the feedback and follow your updated learning path.</p>}</article>}
    {!!sessions.length && <details><summary>Saved viva sessions</summary>{sessions.map(item => <button className="secondary savedQuestion" key={item.id} onClick={() => { setSession(item); setAnswer(""); }}>{item.topic} · {item.turns.filter(t => t.score != null).length} answers saved</button>)}</details>}
  </section>;
}
