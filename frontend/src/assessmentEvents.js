import { useCallback, useEffect, useRef, useState } from "react";
import api, { API } from "./api";

export function useAssessmentEvents(attempt, stage) {
  const key = `labtwin_events_${attempt.id}`;
  const queue = useRef([]);
  const sending = useRef(null);
  const active = useRef(true);
  const currentStage = useRef(stage);
  const awayAt = useRef(null);
  const eyeClosureOptIn = useRef(false);
  const [reminder, setReminder] = useState("");
  const [logError, setLogError] = useState("");
  currentStage.current = stage;

  const persist = useCallback(() => {
    try { sessionStorage.setItem(key, JSON.stringify(queue.current)); } catch { /* Keep in memory if storage is unavailable. */ }
  }, [key]);
  const log = useCallback((kind, detail = {}) => {
    if (!active.current) return;
    if (kind === "camera_analysis_started") eyeClosureOptIn.current = detail.consent === true && detail.allow_eye_closure === true;
    if (kind === "camera_stopped" || kind === "camera_analysis_stopped") eyeClosureOptIn.current = false;
    queue.current.push({ event_id: crypto.randomUUID(), kind, stage: currentStage.current, detail: { ...detail, observed_at: new Date().toISOString() } });
    persist();
    if ((kind === "page_return" || kind === "paste" || kind === "paste_blocked") && currentStage.current === "viva") {
      const optional = attempt.assignment.camera_eye_closure && eyeClosureOptIn.current ? " If comfortable, pause writing, close your eyes briefly and tell the teacher how your code works. Keeping your eyes open is equally acceptable." : "";
      setReminder(`Please return to the viva and explain in your own words.${optional} This reminder is not a cheating verdict.`);
    }
  }, [persist, attempt.assignment.camera_eye_closure]);

  const flush = useCallback(async () => {
    if (sending.current) return sending.current;
    const task = (async () => {
    try {
      while (queue.current.length) {
        const batch = queue.current.slice(0, 50);
        await api.post(`${API}/attempts/${attempt.id}/events/`, { events: batch });
        queue.current = queue.current.filter(event => !batch.some(sent => sent.event_id === event.event_id));
        persist();
      }
      setLogError(""); return true;
    } catch {
      setLogError("Activity log is waiting to sync. Keep this page open and reconnect before submitting.");
      return false;
    }
    })();
    sending.current = task;
    try { return await task; } finally { sending.current = null; }
  }, [attempt.id, persist]);

  useEffect(() => {
    active.current = ["in_progress", "processing"].includes(attempt.status);
    if (!active.current) {
      queue.current = []; persist();
      return;
    }
    try { queue.current = JSON.parse(sessionStorage.getItem(key) || "[]"); } catch { queue.current = []; }
    const visibility = () => {
      if (document.hidden) { awayAt.current = Date.now(); log("page_hidden"); }
      else { log("page_return", { duration_ms: awayAt.current ? Date.now() - awayAt.current : 0 }); awayAt.current = null; flush(); }
    };
    const blur = () => log("window_blur");
    const focus = () => log("window_focus");
    const clipboard = event => {
      const field = event.target?.closest?.("[data-assessment-field]")?.dataset.assessmentField;
      if (!field) return;
      const blocked = event.type === "paste" && !attempt.assignment.allow_paste;
      if (blocked) event.preventDefault();
      log(blocked ? "paste_blocked" : event.type, {
        field, characters: event.type === "paste" ? (event.clipboardData?.getData("text") || "").length : 0,
      });
    };
    const exit = () => {
      log("page_exit");
      const token = sessionStorage.getItem("labtwin_access_token");
      if (queue.current.length && token) fetch(`${API}/attempts/${attempt.id}/events/`, {
        method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ events: queue.current.slice(-50) }), keepalive: true,
      }).catch(() => {});
    };
    document.addEventListener("visibilitychange", visibility);
    window.addEventListener("blur", blur); window.addEventListener("focus", focus);
    window.addEventListener("pagehide", exit);
    ["copy", "cut", "paste"].forEach(type => document.addEventListener(type, clipboard, true));
    const timer = setInterval(flush, 3000);
    return () => {
      active.current = false; clearInterval(timer);
      document.removeEventListener("visibilitychange", visibility);
      window.removeEventListener("blur", blur); window.removeEventListener("focus", focus); window.removeEventListener("pagehide", exit);
      ["copy", "cut", "paste"].forEach(type => document.removeEventListener(type, clipboard, true));
    };
  }, [attempt.id, attempt.status, attempt.assignment.allow_paste, key, log, flush, persist]);
  return { log, flush, reminder, setReminder, logError };
}
