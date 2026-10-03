import { useEffect, useRef, useState } from "react";
import axios from "../api";

const preStyle = { whiteSpace: "pre-wrap", overflowWrap: "anywhere", maxHeight: 320, overflow: "auto" };
const labels = { analysis: "Initial submission", retest: "Correction and viva", hint: "Hint requested" };

export default function ResponseHistory({ api, studentId, version, title = "My response history" }) {
  const [rows, setRows] = useState([]);
  const [cursor, setCursor] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const generation = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    generation.current += 1;
    setRows([]);
    setCursor(null);
    setError("");
    setLoading(true);
    axios.get(`${api}/response-history/`, {
      params: { student_id: studentId }, signal: controller.signal,
    }).then(({ data }) => {
      setRows(data.responses);
      setCursor(data.next_before);
    }).catch(err => {
      if (!controller.signal.aborted) setError(err.response?.data?.error || "Could not load response history. Please retry.");
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => { controller.abort(); generation.current += 1; };
  }, [api, studentId, version, refresh]);

  async function loadMore() {
    if (loading || !cursor) return;
    const current = generation.current;
    setLoading(true);
    setError("");
    try {
      const { data } = await axios.get(`${api}/response-history/`, {
        params: { student_id: studentId, before: cursor },
      });
      if (current !== generation.current) return;
      setRows(previous => [...previous, ...data.responses]);
      setCursor(data.next_before);
    } catch (err) {
      if (current === generation.current) setError(err.response?.data?.error || "Could not load older responses.");
    } finally {
      if (current === generation.current) setLoading(false);
    }
  }

  return <section className="card" aria-label="Student response history">
    <h2>{title}</h2>
    <p>Submitted code, corrections, viva answers and hints are saved here.</p>
    <button disabled={loading} onClick={() => setRefresh(value => value + 1)}>Refresh history</button>
    {error && <p role="alert">{error}</p>}
    {loading && <p role="status">Loading responses…</p>}
    {!loading && !error && !rows.length && <p>No saved responses yet. New submissions will appear here.</p>}
    {rows.map(row => <details key={row.id} style={{ marginTop: 16 }}>
      <summary>{labels[row.stage] || row.stage} · {row.topic} · {new Date(row.created_at).toLocaleString()} · {row.status}</summary>
      <p>{row.question}</p>
      {row.code && <><h3>Submitted code ({row.language})</h3><pre style={preStyle}>{row.code}</pre></>}
      {row.context.viva_question && <p><strong>Viva question:</strong> {row.context.viva_question}</p>}
      {row.viva_answer && <><h3>Your viva answer</h3><pre style={preStyle}>{row.viva_answer}</pre></>}
      {row.context.hint_level != null && <p>Hint level used: {row.context.hint_level}</p>}
      {row.context.current_hint && <p><strong>Previous hint:</strong> {row.context.current_hint}</p>}
      {row.context.first_hint && <p><strong>First hint:</strong> {row.context.first_hint}</p>}
      {(row.result.hint || row.result.diagnosis?.hint) && <p><strong>Hint:</strong> {row.result.hint || row.result.diagnosis.hint}</p>}
      {row.test_results.map((test, index) => <div key={index}>
        <h3>Test {test.test ?? index + 1}: {test.passed ? "Passed" : "Failed"}</h3>
        {test.hidden ? <p>Hidden test details remain private.</p> : <><p>Output</p><pre style={preStyle}>{test.stdout || "(no output)"}</pre></>}
        {test.stderr && <><p>Error</p><pre style={preStyle}>{test.stderr}</pre></>}
      </div>)}
      <h3>Evaluation and feedback</h3>
      {row.result.test_score != null && <p>Test score: {row.result.test_score}%</p>}
      {row.result.retest_score != null && <p>Retest score: {row.result.retest_score}%</p>}
      {row.result.evaluation?.score != null && <p>Viva score: {row.result.evaluation.score}%</p>}
      {row.result.evaluation?.status && <p>Evaluation: {row.result.evaluation.status}</p>}
      {row.result.evaluation?.reason && <p>{row.result.evaluation.reason}</p>}
      {row.result.diagnosis?.misconception && <p>{row.result.diagnosis.misconception}</p>}
      {row.result.error && <p role="alert">{row.result.error}</p>}
      {row.status === "processing" && <p>This response was saved, but evaluation has not completed. Refresh to check again.</p>}
    </details>)}
    {cursor && <button disabled={loading} onClick={loadMore}>Load older responses</button>}
  </section>;
}
