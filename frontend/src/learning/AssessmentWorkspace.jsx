import { useEffect, useRef, useState } from "react";
import { get, post, errorText } from "./api";
import SourceLinks from "./SourceLinks";
import AssessmentCamera from "../camera/AssessmentCamera";
import useAssessmentActivity from "./useAssessmentActivity";
import { SubmissionRecovery, answerLocked, restoreAssessment } from "./submissionRecovery";

export default function AssessmentWorkspace({ course, onSource, onCompleted }) {
  const [kind, setKind] = useState("diagnostic"), [scope, setScope] = useState("all"), [format, setFormat] = useState("mixed"), [count, setCount] = useState(3);
  const [session, setSession] = useState(null), [history, setHistory] = useState([]), [answers, setAnswers] = useState({}), [results, setResults] = useState({}), [busy, setBusy] = useState(""), [error, setError] = useState("");
  const recovery = useRef(new SubmissionRecovery()), working = useRef(false);
  const [focusedQuestion, setFocusedQuestion] = useState(null);
  const activity = useAssessmentActivity(session?.id, session?.status);
  const assessableTopics = course.topics.filter(topic => topic.assessment_eligible !== false);
  const withheldTopics = course.topics.length - assessableTopics.length;
  useEffect(() => { let active = true; get(`courses/${course.id}/assessments/`).then(data => { if (active) setHistory(data.assessments); }).catch(err => { if (active) setError(errorText(err)); }); return () => { active = false; }; }, [course.id]);
  function open(assessment) {
    const restored = restoreAssessment(assessment, recovery.current);
    setSession(assessment); setAnswers(restored.answers); setResults(restored.results);
    setFocusedQuestion(assessment.questions.find(question => !answerLocked(restored.results[question.id], assessment.status))?.id ?? assessment.questions[0]?.id);
    for (const attempt of assessment.attempts || []) if (attempt.status !== "processing") recovery.current.settle(attempt.question_id, attempt.request_id);
    setHistory(previous => [assessment, ...previous.filter(row => row.id !== assessment.id)]);
  }
  function edit(question, answer) {
    recovery.current.saveDraft(question.id, { code: "", answer });
    setAnswers(previous => ({ ...previous, [question.id]: answer }));
  }
  async function load(sessionId) {
    if (working.current) return;
    working.current = true; setBusy("refresh"); setError("");
    try { open((await get(`assessments/${sessionId}/`)).assessment); }
    catch (err) { setError(errorText(err)); }
    finally { working.current = false; setBusy(""); }
  }
  async function start(event) {
    event.preventDefault();
    if (working.current) return;
    working.current = true; setBusy("start"); setError("");
    try {
      const data = await post(`courses/${course.id}/assessments/`, { kind, count: Number(count), formats: format === "mixed" ? ["quiz", "short_answer", "numerical"] : [format], scope: scope === "all" || scope === "weak" ? { selection: scope } : { topic_ids: [Number(scope)] } });
      open(data.assessment);
    } catch (err) { setError(errorText(err)); } finally { working.current = false; setBusy(""); }
  }
  async function submit(question) {
    if (working.current || answerLocked(results[question.id], session.status)) return;
    working.current = true; setBusy("submit"); setError("");
    const payload = { code: "", answer: answers[question.id] ?? "" };
    let requestId;
    try {
      requestId = recovery.current.request(question.id, payload);
      const result = await post(`questions/${question.id}/attempts/`, { request_id: requestId, ...payload });
      setResults(previous => ({ ...previous, [question.id]: result.attempt }));
      if (result.attempt.status !== "processing") recovery.current.settle(question.id, requestId);
      open((await get(`assessments/${session.id}/`)).assessment); onCompleted();
    } catch (err) {
      if (err.response?.data?.attempt) {
        setResults(previous => ({ ...previous, [question.id]: err.response.data.attempt }));
        if (err.response.data.attempt.status !== "processing") recovery.current.settle(question.id, requestId);
      }
      setError(errorText(err));
    } finally { working.current = false; setBusy(""); }
  }
  return <section className="classroomBox assessmentWorkspace" data-camera-assessment><p className="eyebrow">SOURCE-CITED · VERIFIED · PERSONALIZED</p><h2>Assessments & diagnostic</h2><p>A diagnostic uses your answers to estimate starting knowledge. Unassessed topics remain unknown. Choose a module/topic or your weak topics for a quiz or mock exam.</p>
    <p className="methodNote">During an assessment, leaving this tab and losing window focus are recorded separately for teacher review. LabTwin cannot prevent tab switching. Copying and pasting into these answer editors is allowed. Activity does not change your grade or mastery; camera use is optional.</p>
    <form className="compactForm assessmentSetup" onSubmit={start}><label>Assessment mode<select aria-label="Assessment mode" value={kind} onChange={e => setKind(e.target.value)}><option value="diagnostic">Diagnostic assessment</option><option value="quiz">Quiz</option><option value="mock_exam">Mock exam</option></select></label><label>Assessment scope<select aria-label="Assessment scope" value={scope} onChange={e => setScope(e.target.value)}><option value="all">Entire course</option><option value="weak">Topics I am weak in</option>{assessableTopics.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}</select></label><label>Question format<select aria-label="Question format" value={format} onChange={e => setFormat(e.target.value)}><option value="mixed">Mixed formats</option><option value="quiz">Multiple choice</option><option value="short_answer">Short answer</option><option value="numerical">Numerical / problem solving</option></select></label><label>Questions<input aria-label="Questions" type="number" min="1" max="20" value={count} onChange={e => setCount(e.target.value)} /></label><button disabled={!!busy}>{busy === "start" ? "Preparing verified questions…" : "Start assessment"}</button></form>
    {withheldTopics > 0 && <p className="methodNote" role="status">{withheldTopics} automatically extracted topic label(s) appear unreadable and are excluded from new assessments until reviewed by your teacher. Original source files are unchanged.</p>}
    {session && <aside className="assessmentActivity" aria-label="Assessment activity"><strong>Assessment activity</strong><p>Browser activity is recorded for teacher review. These signals never automatically change your score or mastery.</p><p><strong>Tab switches: {activity.tabSwitches}</strong> · <strong>Window focus losses: {activity.focusLosses}</strong> · <strong>Allowed pastes: {activity.allowedPastes}</strong> · <strong>Blocked paste attempts: {activity.blockedPastes}</strong></p>{activity.syncError && <p role="status">{activity.syncError}</p>}</aside>}
    {error && <p role="alert">{error}</p>}
    {session && <div className="assessmentSessionStatus"><p><strong>Assessment {session.id} · {session.status === "completed" ? "Completed" : "In progress"}</strong></p><button className="secondary" disabled={!!busy} onClick={() => load(session.id)}>{busy === "refresh" ? "Checking saved work…" : "Refresh assessment status"}</button><p className="methodNote">Submitted answers and feedback are saved to your account. If a connection is interrupted, refresh the status before submitting again. Unsubmitted drafts stay in this tab when browser storage is available.</p></div>}
    {session?.status === "in_progress" && <AssessmentCamera key={session.id} policy={session.camera_policy || course.camera_policy}
      question={session.questions.find(q => q.id === focusedQuestion) || session.questions.find(q => !results[q.id])}
      onEvent={async item => (await post(`assessments/${session.id}/camera-events/`, { events: [item] })).events[0]}
      onResponse={(id, data) => post(`assessment-camera/events/${id}/response/`, data)}
      checkAccess={() => get(`assessments/${session.id}/camera-events/`).then(async data => {
        if (data.status !== session.status) open((await get(`assessments/${session.id}/`)).assessment);
        else setSession(previous => previous?.id === session.id ? { ...previous, camera_policy: data.policy } : previous);
        return { status: data.status, policy: data.policy };
      })} />}
    {session?.report.generation_notes?.map(note => <p key={note} className="methodNote">{note}</p>)}
    <div className="assessmentQuestions" data-question-count={session?.questions.length || 0}>
    {session?.questions.map((question, index) => <article className="practiceQuestion assessmentQuestion" data-kind={question.kind} key={question.id} onFocus={() => setFocusedQuestion(question.id)}><span className="statusTag">{question.topic} · {question.kind} · Difficulty {question.difficulty}/3 · {question.verification.status}</span><h3>{index + 1}. {question.prompt}</h3><SourceLinks items={question.resources} onSource={onSource} /><details><summary>Why am I getting this question?</summary><p>{question.reason}</p><p>Verified using {question.verification.method}.</p></details>
      {question.kind === "quiz" ? <fieldset disabled={!!busy || answerLocked(results[question.id], session.status)}><legend>Choose your answer</legend>{question.options.map((option, i) => <label className="quizOption" key={i}><input type="radio" name={`assessment-${question.id}`} checked={String(answers[question.id]) === String(i)} onChange={() => edit(question, String(i))} /><span>{option}</span></label>)}</fieldset> : <label>{question.kind === "numerical" ? "Numerical answer" : "Your short answer"}{question.kind === "numerical" ? <input data-assessment-answer="true" disabled={!!busy || answerLocked(results[question.id], session.status)} value={answers[question.id] ?? ""} onChange={e => edit(question, e.target.value)} /> : <textarea data-assessment-answer="true" aria-label="Your short answer" rows={5} maxLength={20000} disabled={!!busy || answerLocked(results[question.id], session.status)} value={answers[question.id] ?? ""} onChange={e => edit(question, e.target.value)} />}</label>}
      {!answerLocked(results[question.id], session.status) && <button disabled={!!busy || !answers[question.id]?.trim()} onClick={() => submit(question)}>{busy === "submit" ? "Saving answer…" : `Submit answer ${index + 1}`}</button>}
      {results[question.id] && <SavedAnswer result={results[question.id]} onSource={onSource} />}
    </article>)}
    </div>
    {session?.status === "completed" && <AssessmentReport report={session.report} onSource={onSource} />}
    {!!history.length && <details><summary>Saved assessments ({history.length})</summary>{history.map(row => <button className="secondary savedQuestion" disabled={!!busy} key={row.id} onClick={() => load(row.id)}>{row.kind} · {row.status} · {new Date(row.created_at).toLocaleDateString()}</button>)}</details>}
  </section>;
}

function SavedAnswer({ result, onSource }) {
  const feedback = result.feedback || {}, impact = feedback.mastery_impact;
  const label = result.status === "processing" ? "Answer saved; assessment in progress" : result.status === "failed" ? "This answer could not be assessed" : result.score == null ? "Awaiting teacher review" : result.score === 100 ? "Correct" : "Review this answer";
  return <div className="practiceResult" role="status"><strong>{label}</strong>{result.error && <p>{result.error}</p>}<p>{feedback.explanation}</p><p>{feedback.review_note}</p><SourceLinks items={feedback.resources} onSource={onSource} />{impact && result.score != null && <p>Mastery estimate: {impact.before ?? "Unassessed"} → {impact.after}%</p>}</div>;
}

function AssessmentReport({ report, onSource }) {
  return <article className="topicEvidence"><h3>Assessment report</h3><p>Score: {report.score == null ? "Pending review" : `${report.score}%`} · {report.scored}/{report.total} scored · {report.pending_review} pending review</p><p>Strong topics: {report.strong_topics.join(", ") || "More evidence needed"}</p><p>Topics for revision: {report.weak_topics.join(", ") || "None identified"}</p>{report.misconceptions.map(m => <p key={m}>{m}</p>)}<div className="rosterScroll"><table><thead><tr><th>Topic</th><th>Before</th><th>After</th><th>State</th></tr></thead><tbody>{report.mastery_changes.map(change => <tr key={change.topic}><td>{change.topic}</td><td>{change.before ?? "Unknown"}</td><td>{change.after}%</td><td>{change.state}</td></tr>)}</tbody></table></div>{report.recommended_revision.map(topic => <div key={topic.topic_id}><strong>Review {topic.topic}</strong><SourceLinks items={topic.resources} onSource={onSource} /></div>)}<p className="methodNote">{report.interpretation}</p></article>;
}
