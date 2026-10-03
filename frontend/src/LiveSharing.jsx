import { useEffect, useRef, useState } from "react";
import api, { API } from "./api";
import AssessmentCamera from "./camera/AssessmentCamera";

function Video({ stream, label, muted = true }) {
  const ref = useRef(null);
  useEffect(() => { if (ref.current) ref.current.srcObject = stream; }, [stream]);
  return <div><p>{label}</p><video ref={ref} autoPlay playsInline muted={muted} controls={!muted} style={{ width: "100%", maxHeight: 360, background: "#162332", borderRadius: 8 }} /></div>;
}

export function SharingControls({ sharing, assignment, stage, onCameraEvent }) {
  return <section className="classroomBox">
    <h3>Screen and viva camera</h3>
    <p>Only your classroom teacher can watch while sharing is on. Screen/camera content is sent live and is not recorded by LabTwin. Your microphone is shared with the camera.</p>
    <p>Screen: {assignment.require_screen ? "required" : "optional"} · Viva camera: {assignment.require_camera ? "required" : "optional"}</p>
    <p>For an assessment that asks for the entire screen, choose the entire screen in the browser picker. Sharing one tab does not show your other apps.</p>
    <button onClick={sharing.screen ? sharing.stopScreen : sharing.startScreen}>{sharing.screen ? "Stop screen sharing" : "Start screen sharing"}</button>{" "}
    <button onClick={sharing.camera ? sharing.stopCamera : sharing.startCamera}>{sharing.camera ? "Stop camera / microphone" : "Turn on camera / microphone"}</button>
    {sharing.error && <p role="alert">{sharing.error}</p>}
    <p>{sharing.viewers.length ? `Teacher watching: ${sharing.viewers.join(", ")}` : "No teacher is currently watching."}</p>
    {stage === "viva" && sharing.camera && <Video stream={sharing.camera} label="Your viva camera (local preview)" />}
    {sharing.camera && onCameraEvent && <AssessmentCamera key={stage} externalStream={sharing.camera} browserSignals={false}
      policy={{ enabled: assignment.camera_cues_enabled, offer_eye_closure: stage === "viva" && assignment.camera_eye_closure }}
      question={{ topic: assignment.title }} onEvent={item => {
        const kind = item.kind === "camera_started" ? "camera_analysis_started" : item.kind === "camera_stopped" ? "camera_analysis_stopped" : item.kind;
        onCameraEvent(kind, item.detail); return null;
      }} />}
  </section>;
}

export function TeacherLiveView({ session, onClose }) {
  const [screen, setScreen] = useState(null), [camera, setCamera] = useState(null), [audio, setAudio] = useState(null);
  const [error, setError] = useState("Connecting to student…");
  const audioRef = useRef(null);
  const onCloseRef = useRef(onClose);
  useEffect(() => { onCloseRef.current = onClose; }, [onClose]);
  useEffect(() => { if (audioRef.current) audioRef.current.srcObject = audio; }, [audio]);
  useEffect(() => {
    let cancelled = false, pc = null, id = null, after = 0, pending = [], polling = false;
    const closePeer = () => {
      if (pc) { pc.ontrack = null; pc.onicecandidate = null; pc.onconnectionstatechange = null; pc.close(); }
      pc = null; after = 0; pending = [];
    };
    async function poll() {
      if (polling || cancelled) return;
      polling = true;
      try {
        if (!id) {
          const { data } = await api.post(`${API}/live/${session.id}/watch/`, {});
          if (cancelled) { api.delete(`${API}/connections/${data.connection_id}/`).catch(() => {}); return; }
          id = data.connection_id; pc = new RTCPeerConnection({ iceServers: data.ice_servers });
          pc.onicecandidate = event => { if (event.candidate && id) api.post(`${API}/connections/${id}/`, { candidate: event.candidate.toJSON() }).catch(() => {}); };
          pc.onconnectionstatechange = () => { if (pc?.connectionState === "connected") setError(""); else if (pc?.connectionState === "failed") setError("Connection failed. Ask the administrator to configure a TURN relay or try another network."); };
        }
        const { data } = await api.get(`${API}/connections/${id}/`, { params: { after } });
        if (cancelled) return;
        if (data.offer?.sdp && !pc.remoteDescription) {
          pc.ontrack = event => {
            // A queued track event must not restore media after access was
            // revoked or this watch panel was closed.
            if (cancelled || !pc || pc.signalingState === "closed") return;
            const type = data.track_sources[event.track.id];
            const stream = new MediaStream([event.track]);
            if (type === "screen") setScreen(stream); else if (type === "camera") setCamera(stream); else if (event.track.kind === "audio") setAudio(stream);
          };
          await pc.setRemoteDescription(data.offer);
          await pc.setLocalDescription(await pc.createAnswer());
          await api.post(`${API}/connections/${id}/`, { answer: pc.localDescription.toJSON() });
        }
        for (const candidate of data.candidates) { after = candidate.id; pending.push(candidate.value); }
        if (pc.remoteDescription) while (pending.length) await pc.addIceCandidate(pending.shift());
      } catch (err) {
        if (!cancelled) {
          setError(err.response?.data?.error || "Unable to connect to live sharing.");
          if ([401, 403, 404, 409, 410].includes(err.response?.status)) {
            closePeer(); id = null; setScreen(null); setCamera(null); setAudio(null);
            if (err.response?.status !== 410) { cancelled = true; onCloseRef.current(); }
          }
        }
      } finally { polling = false; }
    }
    poll(); const timer = setInterval(poll, 1500);
    return () => { cancelled = true; clearInterval(timer); closePeer(); if (id) api.delete(`${API}/connections/${id}/`).catch(() => {}); };
  }, [session.id]);
  return <section className="classroomBox"><h3>Live: {session.student_name}</h3><button onClick={onClose}>Stop watching</button>
    {error && <p role="status">{error}</p>}
    <div className="classroomColumns">{screen && <Video stream={screen} label="Shared screen" />}{camera && <Video stream={camera} label="Viva camera" />}</div>
    {audio && <><p>Viva microphone (press play to listen)</p><audio ref={audioRef} controls autoPlay /></>}
  </section>;
}
