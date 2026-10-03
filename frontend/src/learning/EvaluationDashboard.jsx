import { useEffect, useRef, useState } from "react";
import { get, post, errorText } from "./api";
import { Stat } from "./LearningViews";

export default function EvaluationDashboard({ course, onCompleted }) {
  const [runs, setRuns] = useState([]), [run, setRun] = useState(null), [mode, setMode] = useState("deterministic"), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const selectedRun = useRef(null), notifiedRun = useRef(null);
  useEffect(() => {
    let active = true;
    selectedRun.current = null;
    async function refresh() {
      try {
        const data = await get(`courses/${course.id}/evaluations/`);
        if (!active) return;
        setRuns(data.runs);
        const selected = data.runs.find(row => row.id === selectedRun.current) || data.runs[0];
        if (selected) {
          const detail = await get(`evaluations/${selected.id}/`);
          if (active && (selectedRun.current === null || selectedRun.current === selected.id)) {
            selectedRun.current = selected.id; setRun(detail.run);
          }
        }
      } catch (err) { if (active) setError(errorText(err)); }
    }
    refresh(); const timer = setInterval(refresh, 5000);
    return () => { active = false; clearInterval(timer); };
  }, [course.id]);
  useEffect(() => {
    if (run?.status === "completed" && notifiedRun.current !== run.id) {
      notifiedRun.current = run.id; onCompleted?.(run);
    }
  }, [run, onCompleted]);
  async function execute() { setBusy(true); setError(""); try { const data = await post(`courses/${course.id}/evaluations/`, { mode }); selectedRun.current = data.run.id; setRun(data.run); setRuns(previous => [data.run, ...previous]); } catch (err) { setError(errorText(err)); } finally { setBusy(false); } }
  function download() { const blob = new Blob([JSON.stringify(run, null, 2)], { type: "application/json" }); const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = `labtwin-evaluation-${run.id}.json`; link.click(); URL.revokeObjectURL(url); }
  const results = run?.results;
  return <section className="classroomBox"><p className="eyebrow">MEASURED RESULTS · INTERNAL TEACHER VIEW</p><h2>System Evaluation</h2><p>Run the team benchmark through ingestion, retrieval and tutoring in an isolated database. Results come from an executed DeepEval run. Production student records are excluded.</p><div className="compactForm"><label>Evaluation method<select aria-label="Evaluation method" value={mode} onChange={e => setMode(e.target.value)}><option value="deterministic">DeepEval · deterministic proxies</option><option value="llm">DeepEval · semantic LLM judge</option></select></label><button disabled={busy || run?.status === "queued" || run?.status === "running"} onClick={execute}>{busy ? "Executing benchmark…" : "Run evaluation"}</button></div>{error && <p role="alert">{error}</p>}
    {run && <><p>Run #{run.id} · {run.status} · {new Date(run.created_at).toLocaleString()}</p>{run.error && <p role="alert">{run.error}</p>}</>}
    {run?.status === "completed" && <><p className="methodNote">{results.framework} {results.framework_version} · {results.metric_interpretation} · {results.dataset_version}</p><div className="statGrid">{Object.entries(results.metrics).map(([name, value]) => <Stat key={name} label={name.replaceAll("_", " ")} value={value == null ? "Unavailable" : `${(value * 100).toFixed(1)}%`} />)}<Stat label="Unsupported queries handled" value={`${results.unsupported_queries.correct}/${results.unsupported_queries.total}`} /></div><p>{results.mode === "deterministic" ? "Deterministic faithfulness checks supporting quotes; relevancy checks reference concepts. These are transparent proxies. Use the configured semantic judge for paraphrase/entailment evaluation." : "These are semantic DeepEval judge measurements. Inspect per-case explanations and the recorded judge model; model judgments can still be wrong."}</p><button className="secondary" onClick={download}>Download evaluation evidence</button>
      <h3>Benchmark cases & source evidence</h3><div className="rosterScroll"><table><thead><tr><th>Question</th><th>Expected coverage</th><th>Actual behavior</th><th>Inspect</th></tr></thead><tbody>{results.cases.map(row => <tr key={row.id}><td>{row.question}</td><td>{row.supported ? "Source-backed" : "Off-material"}</td><td>{row.grounded ? "Answered with sources" : "Declined"}</td><td><details><summary>Evidence</summary><p>{row.answer}</p><p>Gold: {row.gold_locations.join(", ") || "None"}</p><p>Retrieved: {row.retrieved_locations.join(", ") || "None"}</p>{row.evaluation.map(metric => <p key={metric.name}>{metric.name}: {metric.score?.toFixed(3) ?? "Unavailable"} · {metric.reason}</p>)}</details></td></tr>)}</tbody></table></div>
      <h3>Personalization across sessions</h3><p className="methodNote">{results.personalization.method} {results.personalization.limitation}</p>{results.personalization.profiles.map(profile => <article className="topicEvidence" key={profile.profile}><h4>{profile.profile}</h4><p>Question repetition: {profile.question_repetition.repeated}/{profile.question_repetition.delivered} · {profile.question_repetition.method}</p><p>Next-answer prediction Brier loss (lower is better): {profile.prediction_brier?.toFixed(3)} · static-prior baseline {profile.static_prior_prediction_brier?.toFixed(3)}. Session 1 → 4 reduction: {profile.session1_to4_brier_reduction?.toFixed(3)}.</p><p>Model mastery changes: {Object.entries(profile.mastery_gain).map(([topic, gain]) => `${topic}: ${gain > 0 ? "+" : ""}${gain} points`).join(" · ")}</p><div className="rosterScroll"><table><thead><tr><th>Session</th><th>Selected topic / difficulty</th><th>Mastery estimates</th><th>Next recommendation</th></tr></thead><tbody>{profile.sessions.map(session => <tr key={session.session}><td>{session.session}<small>{session.scored_evidence_count} scored observations · prediction loss {session.prediction_brier?.toFixed(3)} · uncertainty {session.mean_model_uncertainty_bits} bits</small></td><td>{session.questions.map((q, i) => <details key={i}><summary>{q.topic} · Level {q.difficulty}</summary><p>{q.question}</p><p>{q.reason}</p><p>{q.mastery_before}% → {q.mastery_after}%</p></details>)}</td><td>{Object.entries(session.mastery).map(([topic, value]) => <p key={topic}>{topic}: {value}%</p>)}</td><td>{session.recommendations.map(r => r.topic).join(", ") || "Consolidate strong topics"}</td></tr>)}</tbody></table></div></article>)}<p className="methodNote">{results.limitations.join(" ")}</p>
    </>}
    {!!runs.length && <details><summary>Saved evaluation runs ({runs.length})</summary>{runs.map(row => <button className="secondary savedQuestion" key={row.id} onClick={async () => { selectedRun.current = row.id; try { setRun((await get(`evaluations/${row.id}/`)).run); } catch (err) { setError(errorText(err)); } }}>#{row.id} · {row.mode} · {row.status}</button>)}</details>}
  </section>;
}
