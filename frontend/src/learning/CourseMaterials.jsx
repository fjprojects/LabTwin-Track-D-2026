import { useEffect, useRef, useState } from "react";
import api from "../api";
import { base, get, post, errorText } from "./api";
import SourceLinks from "./SourceLinks";

export function CourseSetup({ courses, onRefresh, onSelect }) {
  const [rooms, setRooms] = useState([]), [form, setForm] = useState({ classroom_id: "", name: "", language: "Python" }), [error, setError] = useState(""), [busy, setBusy] = useState(false);
  useEffect(() => { api.get(base.replace(/\/learning$/, "/classrooms/")).then(({ data }) => setRooms(data.classrooms)).catch(err => setError(errorText(err))); }, []);
  async function create(event) {
    event.preventDefault(); setBusy(true); setError("");
    try { const data = await post("courses/", form); await onRefresh(); onSelect(data.course.id); setForm(previous => ({ ...previous, name: "" })); }
    catch (err) { setError(errorText(err)); } finally { setBusy(false); }
  }
  return <section className="classroomBox"><h2>Courses in your classrooms</h2><p>A course groups your topics, source materials and adaptive assessments.</p>
    <form onSubmit={create} className="compactForm"><label>Classroom<select aria-label="Classroom" required value={form.classroom_id} onChange={e => setForm({ ...form, classroom_id: e.target.value })}><option value="">Choose classroom</option>{rooms.map(room => <option key={room.id} value={room.id}>{room.name}</option>)}</select></label><label>Course name<input required maxLength={160} value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="Data Structures" /></label><label>Lab language<select aria-label="Lab language" value={form.language} onChange={e => setForm({ ...form, language: e.target.value })}>{["Python", "C", "Java"].map(language => <option key={language}>{language}</option>)}</select></label><button disabled={busy || !rooms.length}>Create course</button></form>
    {!rooms.length && <p>Create a classroom from Classes first.</p>}{error && <p role="alert">{error}</p>}
    <div className="materialGrid">{courses.map(course => <button className="courseCard secondary" key={course.id} onClick={() => onSelect(course.id)}><strong>{course.name}</strong><span>{course.classroom_name} · {course.topics.length} topics · {course.material_count} materials</span></button>)}</div>
  </section>;
}

export default function CourseMaterials({ course, teacher, onRefresh, onAsk, onSource }) {
  const [materials, setMaterials] = useState([]), [version, setVersion] = useState(0), [detail, setDetail] = useState(null), [error, setError] = useState(""), [busy, setBusy] = useState(false);
  const [upload, setUpload] = useState(null), [topicId, setTopicId] = useState(""), [captions, setCaptions] = useState(""), [topicName, setTopicName] = useState(""), [prerequisite, setPrerequisite] = useState("");
  const [search, setSearch] = useState(""); const media = useRef(null), input = useRef(null);
  const refresh = useRef(onRefresh);
  useEffect(() => { refresh.current = onRefresh; }, [onRefresh]);
  useEffect(() => {
    let active = true, loading = false;
    let previousStatuses = new Map();
    const load = async () => {
      if (loading) return;
      loading = true;
      try {
        const data = await get(`courses/${course.id}/materials/`);
        if (!active) return;
        const completed = data.materials.some(item => previousStatuses.has(item.id) && previousStatuses.get(item.id) !== "ready" && item.status === "ready");
        previousStatuses = new Map(data.materials.map(item => [item.id, item.status]));
        setMaterials(data.materials);
        if (completed) await refresh.current?.();
      } catch (err) { if (active) setError(errorText(err)); }
      finally { loading = false; }
    };
    load(); const timer = setInterval(load, 5000);
    return () => { active = false; clearInterval(timer); };
  }, [course.id, version]);
  useEffect(() => { setDetail(null); setError(""); setTopicId(""); }, [course.id]);
  async function add(event) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const body = new FormData(); body.append("file", upload); if (topicId) body.append("topic_id", topicId); if (captions.trim()) body.append("captions", captions);
      const data = await post(`courses/${course.id}/materials/`, body); setVersion(v => v + 1); setUpload(null); setCaptions(""); input.current.value = "";
      if (data.material.status === "failed") setError(data.material.error);
      await onRefresh();
    } catch (err) { setError(errorText(err)); } finally { setBusy(false); }
  }
  async function addTopic(event) {
    event.preventDefault(); setBusy(true); setError("");
    try { await post(`courses/${course.id}/topics/`, { name: topicName, prerequisites: prerequisite ? [Number(prerequisite)] : [] }); setTopicName(""); await onRefresh(); }
    catch (err) { setError(errorText(err)); } finally { setBusy(false); }
  }
  async function open(item) { try { const data = await get(`materials/${item.id}/`); setDetail(data.material); setSearch(""); } catch (err) { setError(errorText(err)); } }
  async function retry(item) { setBusy(true); setError(""); try { const data = await post(`materials/${item.id}/retry/`, captions.trim() ? { captions: JSON.parse(captions) } : {}); setVersion(v => v + 1); if (data.material.status === "failed") setError(data.material.error); await onRefresh(); } catch (err) { setError(errorText(err)); } finally { setBusy(false); } }
  const units = detail?.units?.filter(unit => !search.trim() || unit.text.toLowerCase().includes(search.toLowerCase())) || [];
  return <>
    {teacher && <section className="classroomBox"><h2>Course topics and settings</h2><form className="compactForm" onSubmit={addTopic}><label>New topic<input required maxLength={200} value={topicName} onChange={e => setTopicName(e.target.value)} /></label><label>Prerequisite<select aria-label="Prerequisite" value={prerequisite} onChange={e => setPrerequisite(e.target.value)}><option value="">None</option>{course.topics.map(topic => <option value={topic.id} key={topic.id}>{topic.name}</option>)}</select></label><button disabled={busy}>Add topic</button></form><p>{course.topics.map(t => t.name).join(" → ") || "Add topics to enable mastery and adaptive practice."}</p>
      <label className="checkLabel"><input type="checkbox" checked={course.allow_solutions} onChange={async e => { try { await api.patch(`${base}/courses/${course.id}/`, { allow_solutions: e.target.checked }); await onRefresh(); } catch (err) { setError(errorText(err)); } }} />Allow complete practice solutions after coaching</label>
      <label className="checkLabel"><input type="checkbox" checked={course.activity_verification} onChange={async e => { try { await api.patch(`${base}/courses/${course.id}/`, { activity_verification: e.target.checked }); await onRefresh(); } catch (err) { setError(errorText(err)); } }} />Offer fresh conceptual verification questions when assignment activity warrants review</label>
    </section>}
    <section className="classroomBox"><p className="eyebrow">ONE COURSE KNOWLEDGE BASE</p><h2>{teacher ? "Course Materials" : "Explore your course"}</h2>
      {teacher && <form onSubmit={add}><label>Upload textbook, notes, slides or lecture<input ref={input} required type="file" accept=".pdf,.ppt,.pptx,.txt,.md,.mp4,.webm,.mov,.mkv,.mp3,.wav,.m4a,.ogg,.flac" onChange={e => setUpload(e.target.files[0])} /></label><label>Topic<select aria-label="Topic" value={topicId} onChange={e => setTopicId(e.target.value)}><option value="">Identify from course topics</option>{course.topics.map(topic => <option key={topic.id} value={topic.id}>{topic.name}</option>)}</select></label><details><summary>Optional timestamped lecture captions</summary><label>Caption segments (JSON)<textarea value={captions} onChange={e => setCaptions(e.target.value)} placeholder={'[{"start":0,"end":12,"text":"Teacher explanation…"}]'} /></label><p>Use supplied captions when speech transcription is unavailable. Timestamps are validated against the uploaded lecture.</p></details><button disabled={!upload || busy}>{busy ? "Uploading…" : "Upload course material"}</button><p>PDF and scanned PDF, PPT/PPTX, text, audio and video. Processing continues in the background; check the status below.</p></form>}
      {error && <p role="alert">{error}</p>}
      {!materials.length && <div className="learningEmpty">No course materials yet. {teacher ? "Upload the first resource to enable grounded answers." : "Your teacher can upload resources here."}</div>}
      <div className="materialGrid">{materials.map(item => <article className="materialCard" key={item.id}><span className="materialKind">{item.kind.toUpperCase()}</span><h3>{item.title}</h3><MaterialProgress material={item} /><p>{item.key_topics.join(" · ")}</p>{item.error && <p role="alert">{item.error}</p>}{item.status === "ready" && <><button onClick={() => open(item)}>Explore material</button>{" "}<button className="secondary" onClick={() => onAsk(item)}>Ask this {item.kind === "video" || item.kind === "audio" ? "lecture" : "material"}</button></>}{teacher && ["failed", "queued"].includes(item.status) && <button disabled={busy} onClick={() => retry(item)}>{item.status === "failed" ? "Retry processing" : "Resume processing"}</button>}{item.warnings.map((warning, index) => <small key={index}>{warning}</small>)}</article>)}</div>
    </section>
    {detail && <section className="classroomBox lectureDetail"><header><h2>{detail.title}</h2><button className="secondary" onClick={() => setDetail(null)}>Close material</button></header><p className="sourceText">{detail.summary}</p>
      {["video", "audio"].includes(detail.kind) && <><p>Transcript: {detail.transcript_origin === "automatic_speech" ? "Automatically transcribed speech" : detail.transcript_origin === "embedded_captions" ? "Automatically extracted embedded captions" : "Teacher-provided timestamped captions"}</p>{detail.kind === "video" ? <video controls ref={media} src={detail.media_url} /> : <audio controls ref={media} src={detail.media_url} />}<div className="chapterList">{detail.chapters.map((chapter, i) => <button className="secondary" key={i} onClick={() => { media.current.currentTime = chapter.start; }}>{formatTime(chapter.start)} · {chapter.title}</button>)}</div></>}
      <button onClick={() => onAsk(detail)}>Ask this lecture / material</button><label>Search within material<input type="search" value={search} onChange={e => setSearch(e.target.value)} placeholder="Binary trees, insertion…" /></label>
      <div className="transcriptList">{units.map(unit => <article key={unit.id}><strong>{unit.page ? `Page ${unit.page}` : unit.slide ? `Slide ${unit.slide}` : unit.start != null ? formatTime(unit.start) : `Section ${unit.number}`}</strong><p>{unit.text}</p><SourceLinks items={unit.source_id ? [{ id: unit.source_id, label: `${detail.title} — ${unit.page ? `Page ${unit.page}` : unit.slide ? `Slide ${unit.slide}` : formatTime(unit.start)}` }] : []} onSource={onSource} />{unit.start != null && <button className="secondary" onClick={() => { media.current.currentTime = unit.start; media.current.play().catch(() => {}); }}>Jump to timestamp</button>}</article>)}</div>
    </section>}
  </>;
}

function formatTime(seconds) { return `${Math.floor((seconds || 0) / 60)}:${String(Math.floor((seconds || 0) % 60)).padStart(2, "0")}`; }

const processingStages = { starting: "Starting extraction", extracting: "Reading the uploaded file", pdf_text: "Extracting PDF text", pdf_ocr: "Reading scanned pages with OCR", pdf_visuals: "Extracting figures and diagrams", slides: "Reading slide contents", transcribing: "Extracting lecture transcript", video_visuals: "Reading lecture visuals", topics: "Identifying topics and prerequisites", saving: "Saving source sections", indexing: "Building the searchable knowledge base", summary: "Preparing the material summary" };

function MaterialProgress({ material }) {
  const job = material.processing;
  if (material.status === "ready") return <p className="statusTag">Ready · {material.unit_count} sections</p>;
  if (material.status === "failed") return <p className="statusTag">Processing failed · original upload retained</p>;
  if (material.status === "queued") return <div role="status"><p className="statusTag">Waiting to start extraction</p>{job?.mode === "external" && <small>This server uses a separate extraction worker. If the status does not change, ask the administrator to start that worker using the setup guide.</small>}</div>;
  return <div role="status"><p className="statusTag">{processingStages[job?.stage] || "Processing course material"}{job?.total > 0 && ` · ${job.completed}/${job.total} ${job.unit}`}</p>{job?.total > 0 && <progress aria-label={processingStages[job.stage] || "Current processing stage"} max={job.total} value={job.completed} />}{job?.stage === "indexing" && <small>The first upload can take longer while the embedding model initializes.</small>}</div>;
}
