import { useEffect, useState } from "react";
import { get, post } from "./api";
import { ActivityQueue, visibilityTransition } from "./activityQueue";

// Lightweight, honest activity signals. They are not cheating findings, and
// neither tab changes nor paste attempts affect grades or mastery.
export default function useAssessmentActivity(sessionId, status, allowPaste = true) {
  const [activity, setActivity] = useState({ tabSwitches: 0, focusLosses: 0, allowedPastes: 0, blockedPastes: 0, syncError: "" });

  useEffect(() => {
    if (!sessionId) {
      setActivity({ tabSwitches: 0, focusLosses: 0, allowedPastes: 0, blockedPastes: 0, syncError: "" });
      return;
    }
    const key = `labtwin_assessment_activity_${sessionId}`;
    let alive = true;
    let saved = "[]";
    try { saved = sessionStorage.getItem(key) || "[]"; } catch { /* Storage can be unavailable. */ }
    const tracker = new ActivityQueue({ saved,
      send: events => post(`assessments/${sessionId}/activity-events/`, { events }),
      changed: setActivity,
      persist: value => { try { if (value === "[]") sessionStorage.removeItem(key); else sessionStorage.setItem(key, value); } catch { /* Continue in memory. */ } },
    });
    function record(kind, detail = {}) {
      if (!alive || status !== "in_progress") return;
      tracker.record(kind, detail, crypto.randomUUID(), new Date().toISOString());
    }
    // Reconcile saved browser events with idempotent server IDs after refresh.
    get(`assessments/${sessionId}/activity-events/`).then(data => {
      if (!alive) return;
      tracker.initialize(data);
    }).catch(() => {
      if (alive) tracker.initialize({}, "Activity history could not load. Your assessment answers are unaffected.");
    });
    tracker.publish();

    let away = document.hidden;
    const visibility = () => {
      const next = visibilityTransition(away, document.hidden); away = next.hidden;
      if (next.departed) record("tab_hidden");
      if (!document.hidden) void tracker.flush();
    };
    let focused = document.hasFocus();
    const blur = () => { if (focused) { focused = false; record("window_blur"); } };
    const focus = () => { if (!focused) { focused = true; record("window_focus"); } void tracker.flush(); };
    const paste = event => {
      if (!event.target?.closest?.("[data-assessment-answer]")) return;
      if (!allowPaste) event.preventDefault();
      record(allowPaste ? "paste_allowed" : "paste_blocked", { characters: event.clipboardData?.getData("text/plain")?.length || 0 });
    };
    if (status === "in_progress") {
      document.addEventListener("visibilitychange", visibility);
      document.addEventListener("paste", paste, true);
      window.addEventListener("blur", blur); window.addEventListener("focus", focus);
    }
    const online = () => void tracker.flush();
    window.addEventListener("online", online);
    const timer = window.setInterval(() => { if (!document.hidden) void tracker.flush(); }, 5000);
    return () => {
      alive = false;
      tracker.dispose();
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", visibility);
      document.removeEventListener("paste", paste, true);
      window.removeEventListener("blur", blur); window.removeEventListener("focus", focus); window.removeEventListener("online", online);
    };
  }, [sessionId, status, allowPaste]);

  return activity;
}
