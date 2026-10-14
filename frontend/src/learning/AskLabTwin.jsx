import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { get, post, errorText } from "./api";
import SourceLinks from "./SourceLinks";
import { answerState, canCheckUnderstanding } from "./answerState";

export default function AskLabTwin({ course, role, material, onSource, onClearLecture, onCompleted }) {
  const [question, setQuestion] = useState(""), [history, setHistory] = useState([]), [busy, setBusy] = useState(false), [error, setError] = useState(""), [loadingHistory, setLoadingHistory] = useState(true);
  const submitting = useRef(false);
  const courseId = course?.id;
  useEffect(() => {
    let active = true; setHistory([]); setError(""); setLoadingHistory(true);
    if (courseId) get(`courses/${courseId}/ask/history/`).then(data => { if (active) setHistory(data.questions); }).catch(err => { if (active) setError(errorText(err)); }).finally(() => { if (active) setLoadingHistory(false); });
    else setLoadingHistory(false);
    return () => { active = false; };
  }, [courseId]);
  async function ask(event) {
    event.preventDefault();
    if (!course || !question.trim() || loadingHistory || submitting.current) return;
    const submittedQuestion = question.trim();
    submitting.current = true; setBusy(true); setError("");
    try {
      const result = await post(`courses/${course.id}/ask/`, { question: submittedQuestion, material_id: material?.id, source_id: material?.source_id });
      setHistory(previous => [{ ...result, question: submittedQuestion }, ...previous]); setQuestion("");
    } catch (err) { setError(errorText(err)); } finally { submitting.current = false; setBusy(false); }
  }
  return <section className="classroomBox askWorkspace">
    <p className="eyebrow">LEARN FROM YOUR TEACHER'S MATERIALS</p><h2>Ask LabTwin</h2>
    <p>Get explanations grounded in your course, with links to the exact page, slide or lecture moment.</p>
    {material && <p className="lectureScope">Asking this lecture: <strong>{material.title}</strong> <button className="secondary" disabled={busy} onClick={onClearLecture}>Ask the whole course</button></p>}
    <form onSubmit={ask} aria-busy={busy}><label>Your question<textarea required maxLength={3000} disabled={busy} value={question} onChange={e => setQuestion(e.target.value)} placeholder="Explain what my teacher taught about linked-list insertion." /></label><button disabled={!course || !question.trim() || busy || loadingHistory}>{busy ? "Finding course evidence…" : "Ask LabTwin"}</button></form>
    <div className="suggestedQuestions">{["Explain linked-list insertion", "Where did the teacher explain recursion?", "Explain JK flip-flop"].map(text => <button className="secondary" disabled={busy} key={text} onClick={() => setQuestion(text)}>{text}</button>)}</div>
    {error && <p role="alert">{error}</p>}
    {(loadingHistory || busy) && <p role="status">{busy ? "Searching the selected course materials…" : "Loading saved answers…"}</p>}
    {!history.length && !loadingHistory && !busy && <div className="learningEmpty">Your answers will appear here. If a topic is missing from the materials, LabTwin will say so.</div>}
    {history.map((item, index) => <article className="answerCard" key={item.id || index}>
      <h3>{item.question}</h3><AnswerContent item={item} onSource={onSource} />
      {item.tutoring_policy && <aside className="tutorScaffolding"><strong>{item.tutoring_policy.style} guidance</strong><p>{item.tutoring_policy.reason}</p><ol>{item.learning_steps?.map(step => <li key={step}>{step}</li>)}</ol></aside>}
      {canCheckUnderstanding(role, item) && <ConversationCheck exchange={item} onSource={onSource} onCompleted={onCompleted} />}
    </article>)}
  </section>;
}

function AnswerContent({ item, onSource }) {
  const state = answerState(item);
  const claims = Array.isArray(item.claims) ? item.claims : [];
  return <>
    <span className={`statusTag ${state.kind === "unsupported" ? "needs" : "strong"}`}>{state.label}</span>
    {state.kind === "excerpts" ? <>
      <p>LabTwin returned extracted source text. Expand a passage below or open its citation to read the original material.</p>
      {claims.length ? claims.map((claim, index) => <details className="sourceExcerpt" key={index}><summary>Read excerpt {index + 1}{claim.citation?.label && ` · ${claim.citation.label}`}</summary><p className="sourceText">{claim.text}</p>{claim.citation && <SourceLinks items={[claim.citation]} onSource={onSource} />}</details>) : <details className="sourceExcerpt"><summary>Read extracted source text</summary><p className="sourceText">{item.answer}</p></details>}
    </> : state.kind === "unsupported" ? <div className="unsupportedAnswer"><p>{item.answer}</p><p>Check the selected course or material. Your teacher can upload notes covering this question.</p></div> : <div className="answerExplanation"><ReactMarkdown skipHtml>{item.answer || ""}</ReactMarkdown></div>}
    <SourceLinks items={item.citations} onSource={onSource} />
    {state.kind === "ai" && claims.length > 0 && <details className="answerEvidence"><summary>Supporting source quotes</summary>{claims.map((claim, index) => <div key={index}><blockquote className="sourceText">{claim.quote}</blockquote>{claim.citation && <SourceLinks items={[claim.citation]} onSource={onSource} />}</div>)}</details>}
  </>;
}

function ConversationCheck({ exchange, onSource, onCompleted }) {
  const [question, setQuestion] = useState(null), [answer, setAnswer] = useState(""), [result, setResult] = useState(null), [error, setError] = useState(""), [busy, setBusy] = useState(false);
  const submitting = useRef(false), requestId = useRef(null);
  async function start() {
    if (submitting.current) return;
    submitting.current = true; setBusy(true); setError("");
    try { setQuestion((await post(`exchanges/${exchange.id}/check/`, {})).question); requestId.current = null; }
    catch (err) { setError(errorText(err)); }
    finally { submitting.current = false; setBusy(false); }
  }
  async function submit(event) {
    event.preventDefault();
    if (submitting.current || !answer.trim() || result) return;
    submitting.current = true; setBusy(true); setError("");
    // Retain this ID on a timed-out retry so one answer gives one mastery update.
    requestId.current ||= crypto.randomUUID();
    try {
      setResult((await post(`questions/${question.id}/attempts/`, { request_id: requestId.current, answer })).attempt);
      onCompleted?.();
    } catch (err) { setError(errorText(err)); }
    finally { submitting.current = false; setBusy(false); }
  }
  const impact = result?.feedback?.mastery_impact;
  return <aside className="tutorScaffolding" aria-busy={busy}>
    <p>Asking a question alone does not raise mastery. A source-based understanding check can provide scored conversation evidence.</p>
    {!question && <button className="secondary" disabled={busy} onClick={start}>{busy ? "Preparing understanding check…" : "Check my understanding"}</button>}
    {question && <><h4>{question.prompt}</h4><SourceLinks items={question.resources} onSource={onSource} /><form onSubmit={submit}><label>Your understanding-check answer<input disabled={busy || !!result} value={answer} onChange={e => { setAnswer(e.target.value); requestId.current = null; }} /></label><button disabled={!answer.trim() || busy || !!result}>{busy ? "Saving understanding check…" : "Submit understanding check"}</button></form></>}
    {result && <div className="practiceResult" role="status"><strong>{result.score === 100 ? "Correct" : result.score == null ? "Teacher review needed" : "Review the source definition"}</strong><p>{result.feedback?.explanation}</p><SourceLinks items={result.feedback?.resources} onSource={onSource} /><p>{impact?.after == null ? "Mastery is unchanged while this answer awaits review." : `Mastery estimate: ${impact.before ?? "Unassessed"} → ${impact.after}%`}</p></div>}
    {error && <p role="alert">{error}</p>}
  </aside>;
}
