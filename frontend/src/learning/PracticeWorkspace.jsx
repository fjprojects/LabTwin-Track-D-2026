import { useEffect, useState } from "react";
import { get, post, errorText } from "./api";
import SourceLinks from "./SourceLinks";

export function CoachingPanel({ questionId, assignmentAttemptId, code = "", onSource = () => {}, onHint }) {
  const [hints, setHints] = useState([]), [busy, setBusy] = useState(false), [error, setError] = useState("");
  async function askHint(level) {
    setBusy(true); setError("");
    try { const data = await post("hint/", { question_id: questionId, assignment_attempt_id: assignmentAttemptId, code, level }); setHints(previous => [...previous.filter(hint => hint.level !== level), data].sort((a, b) => a.level - b.level)); onHint?.(); }
    catch (err) { setError(errorText(err)); } finally { setBusy(false); }
  }
  return <aside className="coachingPanel"><h3>Explain my mistake</h3><p>Build understanding one hint at a time.</p><div className="hintButtons">{[1, 2, 3].map(level => <button key={level} className="secondary" disabled={busy || (level > 1 && !hints.some(h => h.level === level - 1))} onClick={() => askHint(level)}>Hint {level}</button>)}</div>{error && <p role="alert">{error}</p>}{hints.map(hint => <div key={hint.id}><strong>Hint {hint.level}</strong><p>{hint.message}</p><SourceLinks items={hint.resources} onSource={onSource} /></div>)}</aside>;
}

export default function PracticeWorkspace({ course, onSource, onCompleted, onViva, initialTopic }) {
  const [topicId, setTopicId] = useState(initialTopic || ""), [question, setQuestion] = useState(null), [code, setCode] = useState(""), [answer, setAnswer] = useState(""), [result, setResult] = useState(null), [history, setHistory] = useState([]), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [kind, setKind] = useState("");
  useEffect(() => { setQuestion(null); setResult(null); setTopicId(initialTopic || ""); }, [course.id, initialTopic]);
  useEffect(() => { let active = true; get(`courses/${course.id}/practice/`).then(data => { if (active) setHistory(data.questions); }).catch(err => { if (active) setError(errorText(err)); }); return () => { active = false; }; }, [course.id]);
  function open(item) {
    setQuestion(item); setResult(null); setError(""); setAnswer("");
    setCode(sessionStorage.getItem(`labtwin_draft_practice_${item.id}`) || item.starter_code);
  }
  async function generate() {
    setBusy(true); setError("");
    try { const data = await post(`courses/${course.id}/practice/`, { topic_id: topicId || undefined, kind: kind || undefined }); open(data.question); setHistory(previous => [data.question, ...previous]); }
    catch (err) { setError(errorText(err)); } finally { setBusy(false); }
  }
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError("");
    try { const data = await post(`questions/${question.id}/attempts/`, { request_id: crypto.randomUUID(), code, answer }); setResult(data); onCompleted(); }
    catch (err) { if (err.response?.data?.attempt) setResult(err.response.data); setError(errorText(err)); } finally { setBusy(false); }
  }
  return <section className="classroomBox"><p className="eyebrow">ADAPTS TO YOUR EVIDENCE</p><h2>Personalized practice</h2><p>Questions adjust to mastery, prerequisite gaps and recent results. Hidden checks remain private.</p><div className="compactForm"><label>Topic<select aria-label="Practice topic" value={topicId} onChange={e => setTopicId(e.target.value)}><option value="">Choose based on my weaknesses</option>{course.topics.map(topic => <option key={topic.id} value={topic.id}>{topic.name}</option>)}</select></label><button disabled={busy} onClick={generate}>Get adaptive question</button></div>
    <label>Practice format<select value={kind} onChange={e => setKind(e.target.value)}><option value="">Best available question</option><option value="quiz">MCQ</option><option value="short_answer">Short answer</option><option value="numerical">Numerical</option><option value="code">Programming</option></select></label>{error && <p role="alert">{error}</p>}
    {question && <article className="practiceQuestion"><span className="statusTag">{question.topic} · Difficulty {question.difficulty}/3 · {question.kind}</span><h3>{question.prompt}</h3><details className="whyQuestion"><summary>Why am I getting this question?</summary><p>{question.reason}</p><SourceLinks items={question.resources} onSource={onSource} /></details>
      <p className="methodNote">Verification: {question.verification.status} · {question.verification.method}{question.subtopic && ` · ${question.subtopic}`}</p><form onSubmit={submit}>{question.kind === "code" ? <label>Your {question.language} practice code<textarea aria-label="Practice code" className="codeEditor" spellCheck={false} value={code} onChange={e => { setCode(e.target.value); sessionStorage.setItem(`labtwin_draft_practice_${question.id}`, e.target.value); }} /></label> : question.kind === "quiz" ? <fieldset><legend>Choose the supported answer</legend>{question.options.map((option, index) => <label className="quizOption" key={index}><input type="radio" name={`question-${question.id}`} value={index} checked={answer === String(index)} onChange={e => setAnswer(e.target.value)} /><span>{option}</span></label>)}</fieldset> : <label>{question.kind === "numerical" ? "Numerical answer" : "Your short answer"}<input value={answer} onChange={e => setAnswer(e.target.value)} /></label>}<button disabled={busy || (question.kind === "quiz" && answer === "")}>{busy ? "Saving and assessing…" : "Submit practice"}</button></form>
      {result && <div className="practiceResult" role="status"><h3>{result.attempt.score === 100 ? "Passed · understanding improved" : "Review this attempt"}</h3><p>Score: {result.attempt.score ?? "Pending"}{result.attempt.score != null && "%"} · {result.attempt.status}</p>{result.attempt.mistake && <p>{result.attempt.mistake}</p>}{result.attempt.error && <p>{result.attempt.error}</p>}{result.attempt.test_results.map(test => <span className={`statusTag ${test.passed ? "strong" : "needs"}`} key={test.test}>Check {test.test}: {test.passed ? "passed" : "needs attention"}</span>)}{result.mastery && <p>Topic mastery: {result.mastery.score}% · {result.mastery.state}</p>}</div>}
      <CoachingPanel key={question.id} questionId={question.id} code={code} onSource={onSource} />
      {result?.attempt.feedback && <div className="practiceResult"><p>{result.attempt.feedback.explanation}</p><p>{result.attempt.feedback.review_note}</p><SourceLinks items={result.attempt.feedback.resources} onSource={onSource} /></div>}
      <button className="secondary" onClick={() => onViva({ question_id: question.id, topic_id: question.topic_id })}>Explain this work in viva</button>{question.solution_available && <button className="secondary" onClick={async () => { try { const data = await get(`questions/${question.id}/solution/`); setCode(data.solution); } catch (err) { setError(errorText(err)); } }}>View teacher-allowed solution</button>}
    </article>}
    {!!history.length && <details><summary>Saved practice questions ({history.length})</summary>{history.map(item => <button key={item.id} className="secondary savedQuestion" onClick={() => open(item)}>{item.topic} · {item.prompt.slice(0, 90)}</button>)}</details>}
  </section>;
}
