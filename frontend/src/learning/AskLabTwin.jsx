import { useEffect, useState } from "react";
import { get, post, errorText } from "./api";
import SourceLinks from "./SourceLinks";

export default function AskLabTwin({ course, material, onSource, onClearLecture }) {
  const [question, setQuestion] = useState(""), [history, setHistory] = useState([]), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const courseId = course?.id;
  useEffect(() => {
    let active = true; setHistory([]); setError("");
    if (courseId) get(`courses/${courseId}/ask/history/`).then(data => { if (active) setHistory(data.questions); }).catch(err => { if (active) setError(errorText(err)); });
    return () => { active = false; };
  }, [courseId]);
  async function ask(event) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const result = await post(`courses/${course.id}/ask/`, { question, material_id: material?.id, source_id: material?.source_id });
      setHistory(previous => [{ ...result, question }, ...previous]); setQuestion("");
    } catch (err) { setError(errorText(err)); } finally { setBusy(false); }
  }
  return <section className="classroomBox askWorkspace">
    <p className="eyebrow">LEARN FROM YOUR TEACHER'S MATERIALS</p><h2>Ask LabTwin</h2>
    <p>Get explanations grounded in your course, with links to the exact page, slide or lecture moment.</p>
    {material && <p className="lectureScope">Asking this lecture: <strong>{material.title}</strong> <button className="secondary" onClick={onClearLecture}>Ask the whole course</button></p>}
    <form onSubmit={ask}><label>Your question<textarea required maxLength={3000} value={question} onChange={e => setQuestion(e.target.value)} placeholder="Explain what my teacher taught about linked-list insertion." /></label><button disabled={!course || busy}>{busy ? "Finding course evidence…" : "Ask LabTwin"}</button></form>
    <div className="suggestedQuestions">{["Explain linked-list insertion", "Where did the teacher explain recursion?", "Explain JK flip-flop"].map(text => <button className="secondary" key={text} onClick={() => setQuestion(text)}>{text}</button>)}</div>
    {error && <p role="alert">{error}</p>}
    {!history.length && <div className="learningEmpty">Your answers will appear here. If a topic is missing from the materials, LabTwin will say so.</div>}
    {history.map((item, index) => <article className="answerCard" key={item.id || index}><h3>{item.question}</h3><span className={`statusTag ${item.grounded ? "strong" : "needs"}`}>{item.mode === "source_excerpts" ? "Source excerpts" : item.grounded ? "Source-grounded answer" : "More material needed"}</span><p className="sourceText">{item.answer}</p><SourceLinks items={item.citations} onSource={onSource} />{item.tutoring_policy && <aside className="tutorScaffolding"><strong>{item.tutoring_policy.style} guidance</strong><p>{item.tutoring_policy.reason}</p><ol>{item.learning_steps?.map(step => <li key={step}>{step}</li>)}</ol></aside>}{item.grounded && <ConversationCheck exchange={item} onSource={onSource} />}</article>)}
  </section>;
}

function ConversationCheck({ exchange, onSource }) {
  const [question, setQuestion] = useState(null), [answer, setAnswer] = useState(""), [result, setResult] = useState(null), [error, setError] = useState("");
  return <aside className="tutorScaffolding"><p>Asking a question alone does not raise mastery. A source-based understanding check can provide scored conversation evidence.</p>{!question && <button className="secondary" onClick={async () => { try { setQuestion((await post(`exchanges/${exchange.id}/check/`, {})).question); } catch (err) { setError(errorText(err)); } }}>Check my understanding</button>}{question && <><h4>{question.prompt}</h4><SourceLinks items={question.resources} onSource={onSource} /><label>Your understanding-check answer<input value={answer} onChange={e => setAnswer(e.target.value)} /></label><button disabled={!answer.trim() || !!result} onClick={async () => { try { setResult((await post(`questions/${question.id}/attempts/`, { request_id: crypto.randomUUID(), answer })).attempt); } catch (err) { setError(errorText(err)); } }}>Submit understanding check</button></>}{result && <><p>{result.score === 100 ? "Correct" : result.score == null ? "Teacher review needed" : "Review the source definition"}</p><p>{result.feedback.explanation}</p><p>Mastery estimate: {result.feedback.mastery_impact.before ?? "Unknown"} → {result.feedback.mastery_impact.after}%</p></>}{error && <p role="alert">{error}</p>}</aside>;
}
