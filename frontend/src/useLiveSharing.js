import { useCallback, useEffect, useRef, useState } from "react";
import api, { API } from "./api";

export function useLiveSharing(attemptId, log) {
  const screenRef = useRef(null), cameraRef = useRef(null), peers = useRef(new Map());
  const [screen, setScreen] = useState(null), [camera, setCamera] = useState(null);
  const [session, setSession] = useState(null), [error, setError] = useState("");
  const [viewers, setViewers] = useState([]);
  const busy = useRef(false), generation = useRef(0);

  const mediaStatus = useCallback(() => ({
    screen_active: !!screenRef.current?.getVideoTracks().some(track => track.readyState === "live"),
    camera_active: !!cameraRef.current?.getVideoTracks().some(track => track.readyState === "live"),
  }), []);
  const announce = useCallback(async (reset = false) => {
    const result = await api[reset ? "post" : "patch"](`${API}/attempts/${attemptId}/live/`, mediaStatus());
    if (reset) {
      generation.current += 1;
      peers.current.forEach(peer => peer.pc.close()); peers.current.clear();
    }
    setSession(result.data); setError(""); return result.data;
  }, [attemptId, mediaStatus]);

  const stopScreen = useCallback(() => {
    const stream = screenRef.current;
    screenRef.current = null; setScreen(null);
    stream?.getTracks().forEach(track => { track.onended = null; track.stop(); });
    log("screen_stopped"); announce().catch(() => setError("Screen stopped. Could not sync the status."));
  }, [announce, log]);
  const stopCamera = useCallback(() => {
    const stream = cameraRef.current;
    cameraRef.current = null; setCamera(null);
    stream?.getTracks().forEach(track => { track.onended = null; track.stop(); });
    log("camera_stopped"); announce().catch(() => setError("Camera stopped. Could not sync the status."));
  }, [announce, log]);

  async function startScreen() {
    setError("");
    if (!navigator.mediaDevices?.getDisplayMedia) { setError("Screen sharing is unavailable in this browser. Use a supported desktop browser over HTTPS or localhost."); return; }
    let stream;
    try {
      stream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
      screenRef.current?.getTracks().forEach(track => track.stop());
      screenRef.current = stream; setScreen(stream);
      stream.getVideoTracks()[0].onended = stopScreen;
      log("screen_started", { surface: stream.getVideoTracks()[0].getSettings().displaySurface || "selected display" });
      await announce(true);
    } catch (err) {
      stream?.getTracks().forEach(track => track.stop()); screenRef.current = null; setScreen(null);
      log("permission_denied", { field: "screen" });
      setError(err.response?.data?.error || "Screen sharing was not started. Grant browser permission and try again.");
    }
  }
  async function startCamera() {
    setError("");
    if (!navigator.mediaDevices?.getUserMedia) { setError("Camera access needs a supported browser over HTTPS or localhost."); return; }
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      cameraRef.current?.getTracks().forEach(track => track.stop());
      cameraRef.current = stream; setCamera(stream);
      stream.getVideoTracks()[0].onended = stopCamera;
      log("camera_started"); await announce(true);
    } catch (err) {
      stream?.getTracks().forEach(track => track.stop()); cameraRef.current = null; setCamera(null);
      log("permission_denied", { field: "camera" });
      setError(err.response?.data?.error || "Camera/microphone was not started. Check your browser permissions.");
    }
  }

  const isSharing = Boolean(session);
  useEffect(() => {
    if (!isSharing) return;
    let cancelled = false;
    async function poll() {
      if (busy.current) return;
      busy.current = true;
      const current = generation.current;
      try {
        const { data } = await api.patch(`${API}/attempts/${attemptId}/live/`, mediaStatus());
        if (cancelled || current !== generation.current) return;
        setViewers(data.connections.map(c => c.teacher_name));
        const ids = new Set(data.connections.map(c => c.id));
        for (const [id, peer] of peers.current) if (!ids.has(id)) { peer.pc.close(); peers.current.delete(id); }
        for (const connection of data.connections) {
          if (cancelled || current !== generation.current) break;
          let peer = peers.current.get(connection.id);
          if (!peer) {
            const pc = new RTCPeerConnection({ iceServers: data.ice_servers });
            peer = { pc, after: 0, pending: [] }; peers.current.set(connection.id, peer);
            pc.onicecandidate = event => { if (event.candidate) api.post(`${API}/connections/${connection.id}/`, { candidate: event.candidate.toJSON() }).catch(() => {}); };
            const sources = {};
            for (const [stream, kind] of [[screenRef.current, "screen"], [cameraRef.current, "camera"]]) {
              stream?.getTracks().filter(track => track.readyState === "live").forEach(track => {
                pc.addTrack(track, stream); sources[track.id] = track.kind === "audio" ? "microphone" : kind;
              });
            }
            await pc.setLocalDescription(await pc.createOffer());
            await api.post(`${API}/connections/${connection.id}/`, { offer: pc.localDescription.toJSON(), track_sources: sources });
          }
          const { data: signal } = await api.get(`${API}/connections/${connection.id}/`, { params: { after: peer.after } });
          if (signal.answer?.sdp && !peer.pc.currentRemoteDescription) await peer.pc.setRemoteDescription(signal.answer);
          for (const candidate of signal.candidates) { peer.after = candidate.id; peer.pending.push(candidate.value); }
          if (peer.pc.remoteDescription) while (peer.pending.length) await peer.pc.addIceCandidate(peer.pending.shift());
        }
        setError("");
      } catch (err) {
        if (!cancelled) {
          setError(err.response?.data?.error || "Live connection is waiting to reconnect.");
          if ([401, 403, 404, 409].includes(err.response?.status)) {
            generation.current += 1;
            screenRef.current?.getTracks().forEach(track => { track.onended = null; track.stop(); });
            cameraRef.current?.getTracks().forEach(track => { track.onended = null; track.stop(); });
            screenRef.current = null; cameraRef.current = null; setScreen(null); setCamera(null); setSession(null);
            peers.current.forEach(peer => peer.pc.close()); peers.current.clear(); setViewers([]);
          }
        }
      } finally { busy.current = false; }
    }
    poll(); const timer = setInterval(poll, 1500);
    return () => { cancelled = true; clearInterval(timer); };
  }, [attemptId, isSharing, mediaStatus]);

  const stopAll = useCallback(async () => {
    generation.current += 1;
    screenRef.current?.getTracks().forEach(track => { track.onended = null; track.stop(); });
    cameraRef.current?.getTracks().forEach(track => { track.onended = null; track.stop(); });
    screenRef.current = null; cameraRef.current = null; setScreen(null); setCamera(null); setSession(null);
    peers.current.forEach(peer => peer.pc.close()); peers.current.clear(); setViewers([]);
    try { await api.delete(`${API}/attempts/${attemptId}/live/`); } catch { /* Local capture always stops. */ }
  }, [attemptId]);
  useEffect(() => {
    const stop = () => { stopAll(); };
    window.addEventListener("labtwin-stop-sharing", stop);
    return () => window.removeEventListener("labtwin-stop-sharing", stop);
  }, [stopAll]);
  useEffect(() => {
    window.dispatchEvent(new CustomEvent("labtwin-sharing", { detail: { active: !!screen || !!camera } }));
    return () => window.dispatchEvent(new CustomEvent("labtwin-sharing", { detail: { active: false } }));
  }, [screen, camera]);
  useEffect(() => () => {
    generation.current += 1;
    screenRef.current?.getTracks().forEach(track => { track.onended = null; track.stop(); });
    cameraRef.current?.getTracks().forEach(track => { track.onended = null; track.stop(); });
    peers.current.forEach(peer => peer.pc.close()); peers.current.clear();
    api.delete(`${API}/attempts/${attemptId}/live/`).catch(() => {});
  }, [attemptId]);
  return { screen, camera, viewers, error, startScreen, startCamera, stopScreen, stopCamera, stopAll, announce, mediaStatus };
}
