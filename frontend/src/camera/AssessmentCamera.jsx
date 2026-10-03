import { useCallback, useEffect, useRef, useState } from "react";
import { CameraCuePolicy, cueInstruction } from "./cuePolicy.js";
import "./AssessmentCamera.css";

const labels = { calibrating: "Look at the assessment screen for a few seconds to calibrate.", face_visible: "Face visible. Camera cues are active.", face_absent: "Face is not currently visible; lighting or framing may affect detection.", head_turned: "Head position differs from calibration.", paused: "Camera cues paused for a source or reasoning check.", unavailable: "Face position could not be estimated reliably." };
const isAccessError = error => [401, 403, 404, 410].includes(error.response?.status);

export default function AssessmentCamera({ policy, question, onEvent, onResponse, checkAccess, externalStream, browserSignals = true }) {
  const [phase, setPhase] = useState("off"), [consent, setConsent] = useState(false), [eyeClosure, setEyeClosure] = useState(false);
  const [status, setStatus] = useState(""), [error, setError] = useState(""), [notice, setNotice] = useState(null), [answer, setAnswer] = useState(""), [saving, setSaving] = useState(false);
  const video = useRef(null), run = useRef({ epoch: 0 }), mounted = useRef(true), props = useRef(null), emitRef = useRef(null);
  props.current = { policy, question, onEvent, onResponse, checkAccess, externalStream, browserSignals };

  const shutdown = useCallback((notify = true, update = true) => {
    const current = run.current;
    run.current = { epoch: current.epoch + 1 };
    clearInterval(current.timer); clearInterval(current.accessTimer); clearTimeout(current.timeout);
    current.worker?.terminate();
    if (current.owned) current.stream?.getTracks().forEach(track => { track.onended = null; track.stop(); });
    if (video.current) video.current.srcObject = null;
    if (notify && current.started) emitRef.current?.("camera_stopped").catch(() => {});
    if (mounted.current && update) { setPhase("off"); setStatus(""); }
  }, []);

  const emit = useCallback(async (kind, detail = {}) => {
    const data = { event_id: crypto.randomUUID(), kind, question_id: props.current.question?.id ?? null,
      detail: { ...detail, observed_at: new Date().toISOString() } };
    try { return await props.current.onEvent?.(data); }
    catch (err) {
      if (mounted.current) setError(isAccessError(err) ? "Camera stopped because assessment access ended." : "Camera events could not sync. Your assessment answers remain available; reconnect to retry camera cues.");
      if (isAccessError(err)) shutdown(false);
      throw err;
    }
  }, [shutdown]);
  emitRef.current = emit;

  const offerPrompt = useCallback(async (kind, detail) => {
    const current = run.current;
    if (!current.started || current.verificationActive || performance.now() - (current.lastPrompt ?? -Infinity) < 60000) return;
    current.verificationActive = true;
    current.lastPrompt = performance.now(); current.detector?.pause(current.lastPrompt, 60000);
    const prompt = props.current.question?.topic
      ? `Explain your reasoning about ${props.current.question.topic} in your own words.`
      : "Explain how you reached your answer in your own words.";
    setAnswer(""); setNotice({ instruction: cueInstruction(detail.reason), prompt, event: null, eyeClosure: !!props.current.policy?.offer_eye_closure && eyeClosure });
    try {
      const saved = await emit(kind, detail);
      if (mounted.current && run.current.epoch === current.epoch) setNotice(previous => previous ? {
        ...previous, event: saved, instruction: saved?.detail?.instruction || previous.instruction,
        prompt: saved?.detail?.verification?.prompt || previous.prompt,
        eyeClosure: saved?.detail?.verification?.offer_eye_closure ?? previous.eyeClosure,
      } : null);
    } catch { /* Keep the visible neutral instruction; never imply it was synced. */ }
  }, [emit, eyeClosure]);
  const offerRef = useRef(offerPrompt); offerRef.current = offerPrompt;

  async function start() {
    if (!consent || run.current.pending || run.current.started) return;
    const current = { epoch: run.current.epoch + 1, pending: true, owned: externalStream === undefined, started: false, busy: false, detector: new CameraCuePolicy(policy), lastVideoTime: -1 };
    run.current = current; setPhase("starting"); setError(""); setNotice(null); setStatus("Requesting camera permission…");
    try {
      if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) throw new Error("Use HTTPS or localhost and a browser with camera support.");
      if (current.owned) current.stream = await navigator.mediaDevices.getUserMedia({ audio: false, video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 15 } } });
      else current.stream = externalStream;
      if (run.current.epoch !== current.epoch) { if (current.owned) current.stream?.getTracks().forEach(track => track.stop()); return; }
      if (!current.stream?.getVideoTracks().some(track => track.readyState === "live")) throw new Error("Turn on the assessment camera first.");
      video.current.srcObject = current.stream;
      await video.current.play();
      await emit("camera_started", { consent: true, analysis_enabled: !!policy?.enabled, allow_eye_closure: !!policy?.offer_eye_closure && eyeClosure });
      if (run.current.epoch !== current.epoch) { if (current.owned) current.stream.getTracks().forEach(track => track.stop()); emit("camera_stopped").catch(() => {}); return; }
      current.started = true; current.pending = false;
      if (current.owned) current.stream.getVideoTracks()[0].onended = () => shutdown();
      if (!policy?.enabled) { setPhase("on"); setStatus("Local camera preview. Your teacher has disabled automatic cues."); }
      else {
        if (!window.Worker || !window.createImageBitmap) throw new Error("This browser cannot run local camera analysis. Try a recent browser.");
        setStatus("Loading the local camera model…");
        // Vite bundles this as a classic worker so MediaPipe can load its WASM
        // helper with importScripts. Inference never blocks answer editing.
        current.worker = new Worker(new URL("./cameraWorker.js", import.meta.url));
        current.timeout = setTimeout(() => { if (run.current.epoch === current.epoch) { setError("Camera model loading timed out. Retry when the local model files are reachable."); shutdown(); } }, 45000);
        current.worker.onerror = () => { if (run.current.epoch === current.epoch) { setError("Camera analysis is unavailable. Your assessment remains available."); emit("camera_analysis_error").catch(() => {}); shutdown(); } };
        current.worker.onmessage = ({ data }) => {
          if (run.current.epoch !== current.epoch) return;
          if (data.type === "error") { setError(data.message); emit("camera_analysis_error").catch(() => {}); shutdown(); return; }
          if (data.type === "ready") {
            clearTimeout(current.timeout); setPhase("on"); setStatus(labels.calibrating);
            current.timer = setInterval(async () => {
              if (document.hidden || current.verificationActive || document.querySelector('[role="dialog"]')) { current.detector.pause(performance.now()); setStatus(labels.paused); return; }
              const element = video.current;
              if (current.busy || !element || element.readyState < 2 || element.currentTime === current.lastVideoTime) return;
              current.busy = true; current.lastVideoTime = element.currentTime;
              try {
                const frame = await createImageBitmap(element);
                if (run.current.epoch !== current.epoch) { frame.close(); return; }
                current.worker.postMessage({ type: "frame", frame, timestamp: performance.now() }, [frame]);
              } catch { current.busy = false; setError("The camera frame could not be read. Stop and retry the camera."); shutdown(); }
            }, 250);
          } else if (data.type === "sample") {
            current.busy = false;
            if (document.hidden || current.verificationActive || document.querySelector('[role="dialog"]')) { current.detector.pause(performance.now()); setStatus(labels.paused); return; }
            const observation = current.detector.observe(data.pose, data.timestamp);
            setStatus(labels[observation.state] || labels.unavailable);
            if (observation.calibrated) emit("camera_calibrated").catch(() => {});
            if (observation.cue) offerRef.current("camera_cue", observation.cue);
          }
        };
        const assetBase = new URL(`${import.meta.env.BASE_URL}camera/`, location.origin).href;
        current.worker.postMessage({ type: "init", wasmUrl: `${assetBase}wasm`, modelUrl: `${assetBase}face_landmarker.task` });
      }
      // Revocation, teacher disabling and completed assessments stop capture.
      let checking = false;
      if (props.current.checkAccess) current.accessTimer = setInterval(async () => {
        if (checking || run.current.epoch !== current.epoch) return;
        checking = true;
        try {
          const fresh = await props.current.checkAccess();
          if (run.current.epoch !== current.epoch) return;
          if (fresh.status !== "in_progress" || (!!fresh.policy?.enabled !== !!policy?.enabled)) shutdown();
        } catch (err) { if (isAccessError(err)) { shutdown(false); setError("Camera stopped because assessment access ended."); } }
        finally { checking = false; }
      }, 5000);
    } catch (err) {
      if (run.current.epoch !== current.epoch) return;
      emit(err.name === "NotAllowedError" ? "permission_denied" : "camera_unavailable").catch(() => {});
      setError(err.name === "NotAllowedError" ? "Camera permission was denied. You can continue the assessment and retry if you choose." : err.response?.data?.error || err.message || "Camera could not start.");
      shutdown();
    }
  }

  useEffect(() => {
    mounted.current = true;
    const stop = () => shutdown();
    window.addEventListener("labtwin-stop-sharing", stop); window.addEventListener("pagehide", stop);
    return () => { mounted.current = false; shutdown(true, false); window.removeEventListener("labtwin-stop-sharing", stop); window.removeEventListener("pagehide", stop); };
  }, [shutdown]);
  useEffect(() => {
    if (externalStream !== undefined && run.current.started && externalStream !== run.current.stream) shutdown();
  }, [externalStream, shutdown]);
  useEffect(() => {
    if (phase !== "on" || !browserSignals || !policy?.enabled) return;
    let hiddenAt = null;
    const visibility = () => {
      run.current.detector?.pause(performance.now());
      if (document.hidden) hiddenAt = performance.now();
      else if (hiddenAt != null) { const duration = Math.round(performance.now() - hiddenAt); hiddenAt = null; if (duration >= 2000) offerRef.current("page_return", { duration_ms: duration }); }
    };
    const paste = event => { if (event.target.closest?.("[data-camera-assessment]")) offerRef.current("paste", { characters: event.clipboardData?.getData("text")?.length || 0 }); };
    document.addEventListener("visibilitychange", visibility); document.addEventListener("paste", paste, true);
    return () => { document.removeEventListener("visibilitychange", visibility); document.removeEventListener("paste", paste, true); };
  }, [phase, browserSignals, policy?.enabled]);

  async function respond(action) {
    setSaving(true);
    try {
      if (props.current.onResponse && notice.event?.detail?.verification) await props.current.onResponse(notice.event.id, { action, answer: action === "answer" ? answer : "" });
      else if (action === "answer") throw new Error("Wait for the reasoning check to sync before saving an explanation.");
      else if (!props.current.onResponse) await emit("coach_reminder", { message: "Own-words camera reminder acknowledged" });
      setNotice(null); setAnswer(""); run.current.verificationActive = false; run.current.detector?.pause(performance.now(), 5000);
    } catch (err) { setError(err.response?.data?.error || err.message || "Explanation could not save. Please retry."); if (isAccessError(err)) shutdown(false); }
    finally { setSaving(false); }
  }

  return <section className="assessmentCamera" aria-label="Assessment camera">
    <h3>{externalStream === undefined ? "Assessment camera" : "Automatic camera reminders"}</h3>
    <p>{externalStream === undefined ? "Camera frames stay on this device. LabTwin does not record or upload this preview. Only event metadata and explanations you save are visible to your classroom teacher." : "This analyzes your existing shared camera locally. Live camera/microphone sharing remains controlled above; these reminders do not record video."}</p>
    <p className="methodNote">Head position and face visibility cannot establish copying or understanding. Camera cues never change your grade or mastery.</p>
    <div className="cameraLayout"><video className="cameraPreview" ref={video} muted autoPlay playsInline aria-label="Local assessment camera preview" hidden={phase === "off"} /><div className="cameraChecks">
      <label><input type="checkbox" checked={consent} disabled={phase !== "off"} onChange={e => setConsent(e.target.checked)} />I agree to the optional local camera {policy?.enabled ? "analysis" : "preview"} and saving event metadata for teacher review.</label>
      {policy?.offer_eye_closure && <label><input type="checkbox" checked={eyeClosure} disabled={phase !== "off"} onChange={e => setEyeClosure(e.target.checked)} />Offer optional eyes-closed, own-words checks. I can keep my eyes open.</label>}
      <div className="cameraControls">{phase === "off" ? <button type="button" disabled={!consent} onClick={start}>{externalStream === undefined ? "Turn on assessment camera" : "Start camera reminders"}</button> : <><button type="button" className="secondary" onClick={() => shutdown()}>{externalStream === undefined ? "Stop assessment camera" : "Stop camera reminders"}</button>{phase === "on" && policy?.enabled && <button type="button" className="secondary" onClick={() => { run.current.detector?.recalibrate(); setStatus(labels.calibrating); }}>Recalibrate camera</button>}</>}</div>
      <p className="cameraLive" role="status">{phase === "starting" ? `Camera starting · ${status}` : phase === "on" ? `Camera on · ${status}` : "Assessment camera analysis is off."}</p>
    </div></div>
    {error && <p role="alert">{error}</p>}
    {notice && <aside className="cameraInstruction" aria-label="Camera instruction" aria-live="polite"><strong>Pause and explain your reasoning</strong><p>{notice.instruction}</p><p>{notice.prompt}</p>
      {notice.eyeClosure && <p>If comfortable, pause writing, briefly close your eyes and explain aloud in your own words. Keeping your eyes open is equally acceptable; eye closure is not checked or graded.</p>}
      {notice.eyeClosure && phase === "on" && <button type="button" className="secondary" onClick={() => { run.current.detector?.pause(performance.now(), 15000); setStatus("Camera cues paused for 15 seconds for your optional own-words explanation."); }}>Pause cues for my explanation</button>}
      {onResponse && notice.event?.detail?.verification && <><label>Optional reasoning explanation<textarea maxLength={5000} value={answer} onChange={e => setAnswer(e.target.value)} /></label><button type="button" disabled={saving || !answer.trim()} onClick={() => respond("answer")}>{saving ? "Saving explanation…" : "Save reasoning explanation"}</button></>}
      <button type="button" className="secondary" disabled={saving} onClick={() => respond("dismiss")}>Keep my eyes open and continue</button>
    </aside>}
  </section>;
}
