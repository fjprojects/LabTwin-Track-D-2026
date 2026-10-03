import { useEffect, useState } from "react";
import { get, post, errorText } from "./api";
import SourceLinks from "./SourceLinks";
import AssessmentCamera from "../camera/AssessmentCamera";

export default function AssessmentWorkspace({ course, onSource, onCompleted }) {
  const [kind, setKind] = useState("diagnostic"), [scope, setScope] = useState("all"), [format, setFormat] = useState("mixed"), [count, setCount] = useState(3);
  const [session, setSession] = useState(null), [history, setHistory] = useState([]), [answers, setAnswers] = useState({}), [results, setResults] = useState({}), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [focusedQuestion, setFocusedQuestion] = useState(null);
  useEffect(() => { let active = true; get(`courses/${course.id}/assessments/`).then(data => { if (active) setHistory(data.assessments); }).catch(err => { if (active) setError(errorText(err)); }); return () => { active = false; }; }, [course.id]);
  async function start(event) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const data = await post(`courses/${course.id}/assessments/`, { kind, count: Number(count), formats: format === "mixed" ? ["quiz", "short_answer", "numerical"] : [format], scope: scope === "all" || scope === "weak" ? { selection: scope } : { topic_ids: [Number(scope)] } });
      setSession(data.assessment); setFocusedQuestion(data.assessment.questions[0]?.id); setAnswers({}); setResults({}); setHistory(previous => [data.assessment, ...previous]);
    } catch (err) { setError(errorText(err)); } finally { setBusy(false); }
  }
  async function submit(question) {
    setBusy(true); setError("");
    try {
      const result = await post(`questions/${question.id}/attempts/`, { request_id: crypto.randomUUID(), answer: answers[question.id] ?? "" });
      setResults(previous => ({ ...previous, [question.id]: result.attempt }));
      const data = await get(`assessments/${session.id}/`); setSession(data.assessment); onCompleted();
    } catch (err) { setError(errorText(err)); } finally { setBusy(false); }
  }
  return <section className="classroomBox" data-camera-assessment><p className="eyebrow">SOURCE-CITED · VERIFIED · PERSONALIZED</p><h2>Assessments & diagnostic</h2><p>A diagnostic uses your answers to estimate starting knowledge. Unassessed topics remain unknown. Choose a module/topic or your weak topics for a quiz or mock exam.</p>
    <form className="compactForm" onSubmit={start}><label>Assessment mode<select aria-label="Assessment mode" value={kind} onChange={e => setKind(e.target.value)}><option value="diagnostic">Diagnostic assessment</option><option value="quiz">Quiz</option><option value="mock_exam">Mock exam</option></select></label><label>Assessment scope<select aria-label="Assessment scope" value={scope} onChange={e => setScope(e.target.value)}><option value="all">Entire course</option><option value="weak">Topics I am weak in</option>{course.topics.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}</select></label><label>Question format<select aria-label="Question format" value={format} onChange={e => setFormat(e.target.value)}><option value="mixed">Mixed formats</option><option value="quiz">Multiple choice</option><option value="short_answer">Short answer</option><option value="numerical">Numerical / problem solving</option></select></label><label>Questions<input aria-label="Questions" type="number" min="1" max="20" value={count} onChange={e => setCount(e.target.value)} /></label><button disabled={busy}>{busy ? "Preparing verified questions…" : "Start assessment"}</button></form>
    {error && <p role="alert">{error}</p>}
    {session?.status === "in_progress" && <AssessmentCamera key={session.id} policy={session.camera_policy || course.camera_policy}
      question={session.questions.find(q => q.id === focusedQuestion) || session.questions.find(q => !results[q.id])}
      onEvent={async item => (await post(`assessments/${session.id}/camera-events/`, { events: [item] })).events[0]}
      onResponse={(id, data) => post(`assessment-camera/events/${id}/response/`, data)}
      checkAccess={() => get(`assessments/${session.id}/camera-events/`).then(data => {
        setSession(previous => previous?.id === session.id ? { ...previous, camera_policy: data.policy, status: data.status } : previous);
        return { status: data.status, policy: data.policy };
      })} />}
    {session?.report.generation_notes?.map(note => <p key={note} className="methodNote">{note}</p>)}
    {session?.questions.map((question, index) => <article className="practiceQuestion" key={question.id} onFocus={() => setFocusedQuestion(question.id)}><span className="statusTag">{question.topic} · {question.kind} · Difficulty {question.difficulty}/3 · {question.verification.status}</span><h3>{index + 1}. {question.prompt}</h3><SourceLinks items={question.resources} onSource={onSource} /><details><summary>Why am I getting this question?</summary><p>{question.reason}</p><p>Verified using {question.verification.method}.</p></details>
      {question.kind === "quiz" ? <fieldset disabled={busy || !!results[question.id]}><legend>Choose your answer</legend>{question.options.map((option, i) => <label className="quizOption" key={i}><input type="radio" name={`assessment-${question.id}`} checked={String(answers[question.id]) === String(i)} onChange={() => setAnswers(previous => ({ ...previous, [question.id]: String(i) }))} /><span>{option}</span></label>)}</fieldset> : <label>{question.kind === "numerical" ? "Numerical answer" : "Your short answer"}<input disabled={busy || !!results[question.id]} value={answers[question.id] ?? ""} onChange={e => setAnswers(previous => ({ ...previous, [question.id]: e.target.value }))} /></label>}
      {!results[question.id] && <button disabled={busy || answers[question.id] === undefined || answers[question.id] === ""} onClick={() => submit(question)}>Submit answer {index + 1}</button>}
      {results[question.id] && <div className="practiceResult"><strong>{results[question.id].score == null ? "Awaiting teacher review" : results[question.id].score === 100 ? "Correct" : "Review this answer"}</strong><p>{results[question.id].feedback.explanation}</p><p>{results[question.id].feedback.review_note}</p><SourceLinks items={results[question.id].feedback.resources} onSource={onSource} /><p>Mastery estimate: {results[question.id].feedback.mastery_impact?.before ?? "Unassessed"} → {results[question.id].feedback.mastery_impact?.after}%</p></div>}
    </article>)}
    {session?.status === "completed" && <AssessmentReport report={session.report} onSource={onSource} />}
    {!!history.length && <details><summary>Saved assessments ({history.length})</summary>{history.map(row => <button className="secondary savedQuestion" key={row.id} onClick={async () => { try { const data = await get(`assessments/${row.id}/`); setSession(data.assessment); setResults({}); setAnswers({}); } catch (err) { setError(errorText(err)); } }}>{row.kind} · {row.status} · {new Date(row.created_at).toLocaleDateString()}</button>)}</details>}
  </section>;
}

function AssessmentReport({ report, onSource }) {
  return <article className="topicEvidence"><h3>Assessment report</h3><p>Score: {report.score == null ? "Pending review" : `${report.score}%`} · {report.scored}/{report.total} scored · {report.pending_review} pending review</p><p>Strong topics: {report.strong_topics.join(", ") || "More evidence needed"}</p><p>Topics for revision: {report.weak_topics.join(", ") || "None identified"}</p>{report.misconceptions.map(m => <p key={m}>{m}</p>)}<div className="rosterScroll"><table><thead><tr><th>Topic</th><th>Before</th><th>After</th><th>State</th></tr></thead><tbody>{report.mastery_changes.map(change => <tr key={change.topic}><td>{change.topic}</td><td>{change.before ?? "Unknown"}</td><td>{change.after}%</td><td>{change.state}</td></tr>)}</tbody></table></div>{report.recommended_revision.map(topic => <div key={topic.topic_id}><strong>Review {topic.topic}</strong><SourceLinks items={topic.resources} onSource={onSource} /></div>)}<p className="methodNote">{report.interpretation}</p></article>;
}
