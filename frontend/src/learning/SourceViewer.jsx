import { useEffect, useRef, useState } from "react";
import { get, post, errorText } from "./api";

export default function SourceViewer({ sourceId, onClose, onAsk }) {
  const [data, setData] = useState(null), [error, setError] = useState("");
  const modal = useRef(null), media = useRef(null);
  useEffect(() => {
    setData(null); setError("");
    if (!sourceId) { modal.current?.close(); return; }
    let active = true;
    get(`sources/${sourceId}/`).then(result => {
      if (active) {
        setData(result);
        post(`sources/${sourceId}/`, { seconds_viewed: 0 }).catch(() => {});
      }
    }).catch(err => { if (active) setError(errorText(err)); });
    if (modal.current && !modal.current.open) modal.current.showModal();
    return () => { active = false; };
  }, [sourceId]);
  const source = data?.source;
  const page = Number.isSafeInteger(source?.page_number) && source.page_number > 0 ? source.page_number : null;
  const originalUrl = source?.kind === "pdf" && page ? `${data.media_url}#page=${page}` : data?.media_url;
  return <dialog className="sourceModal" ref={modal} onCancel={event => { event.preventDefault(); onClose(); }} aria-label="Course source viewer">
    <header><div><p className="eyebrow">VERIFIED COURSE SOURCE</p><h2>{source?.label || (error ? "Source unavailable" : "Opening source…")}</h2></div><button className="secondary" autoFocus onClick={onClose}>Close source</button></header>
    <div className="sourceModalBody">
    {error && <p role="alert">{error}</p>}
    {!data && !error && <p role="status">Opening the cited course source…</p>}
    {data && <>
      {data.visual_url && <figure className="sourceFigure"><img src={data.visual_url} alt={data.visual_description || "Extracted educational figure"} /><figcaption>{data.visual_description}<p className="methodNote">Extraction: {data.analysis_method}. {data.layout?.analysis?.semantic_status === "limited" && "Visual interpretation was unavailable. Any readable labels are preserved."}</p>{data.layout?.analysis?.warning && <p role="status">{data.layout.analysis.warning}</p>}</figcaption></figure>}
      {source.kind === "pdf" && <><p className="sourceLocation">{page ? `Page ${page} of ${source.title}` : source.label}</p><iframe key={source.id} title={page ? `${source.title} page ${page}` : source.title} src={page ? `${originalUrl}&zoom=page-width` : originalUrl} /><p>If the PDF is difficult to read in the embedded viewer, open the original material or expand the source text below.</p></>}
      {source.kind === "slides" && data.layout?.shapes && <div className="sourceSlide" style={{ aspectRatio: data.layout.ratio }}>{data.layout.shapes.map((shape, index) => <div key={index} style={{ left: `${shape.x}%`, top: `${shape.y}%`, width: `${shape.w}%`, height: `${shape.h}%` }}>{shape.image ? <img alt="Slide illustration" src={shape.image} /> : <p>{shape.text}</p>}</div>)}</div>}
      {["video", "audio"].includes(source.kind) && <>{source.kind === "video" ? <video ref={media} controls src={data.media_url} onLoadedMetadata={() => { media.current.currentTime = source.start_seconds || 0; }} /> : <audio ref={media} controls src={data.media_url} onLoadedMetadata={() => { media.current.currentTime = source.start_seconds || 0; }} />}<p>Jumped to the cited timestamp. Source links expire after five minutes; reopen this citation to refresh.</p></>}
      <details open={source.kind === "text"}><summary>Extracted source text</summary><p className="sourceText">{data.text}</p></details>
      <a href={originalUrl} target="_blank" rel="noreferrer">Open original material</a>
      {onAsk && <button className="secondary" onClick={() => onAsk(source)}>Ask about this source</button>}
    </>}
    </div>
  </dialog>;
}
