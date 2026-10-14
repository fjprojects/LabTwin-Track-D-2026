import { useEffect, useState } from "react";
import { get, post } from "./api";

// Lightweight, honest activity signals. They are not cheating findings, and
// neither tab changes nor paste attempts affect grades or mastery.
export default function useAssessmentActivity(sessionId, status) {
  const [activity, setActivity] = useState({ tabSwitches: 0, blockedPastes: 0, syncError: "" });

  useEffect(() => {
    if (!sessionId) {
      setActivity({ tabSwitches: 0, blockedPastes: 0, syncError: "" });
      return;
    }
    const key = `labtwin_assessment_activity_${sessionId}`;
    let alive = true;
    let sending = false;
    let storedTabs = 0;
    let storedPastes = 0;
    let queue = [];
    try {
      const saved = JSON.parse(sessionStorage.getItem(key) || "[]");
      if (Array.isArray(saved)) queue = saved.filter(row => row && ["tab_hidden", "paste_blocked"].includes(row.kind) && typeof row.event_id === "string");
    } catch { /* Bad local data must not break the assessment. */ }

    function persist() {
      try {
        if (queue.length) sessionStorage.setItem(key, JSON.stringify(queue));
        else sessionStorage.removeItem(key);
      } catch { /* Continue without storage if the browser rejects it. */ }
    }
    function count() {
      if (!alive) return;
      setActivity(previous => ({
        ...previous,
        tabSwitches: storedTabs + queue.filter(item => item.kind === "tab_hidden").length,
        blockedPastes: storedPastes + queue.filter(item => item.kind === "paste_blocked").length,
      }));
    }
    async function flush() {
      if (sending || !queue.length || status !== "in_progress") return;
      sending = true;
      try {
        const batch = queue.slice(0, 20);
        const data = await post(`assessments/${sessionId}/activity-events/`, { events: batch });
        if (!alive) return;
        const accepted = new Set((data.events || []).map(item => item.event_id));
        queue = queue.filter(item => !accepted.has(item.event_id));
        storedTabs = data.tab_switches || 0;
        storedPastes = data.blocked_pastes || 0;
        persist();
        count();
        setActivity(previous => ({ ...previous, syncError: "" }));
      } catch {
        if (alive) setActivity(previous => ({ ...previous, syncError: "Some activity counts are waiting to sync. Your answers remain available." }));
      } finally { sending = false; }
    }
    function record(kind, detail = {}) {
      if (!alive || status !== "in_progress") return;
      queue.push({ event_id: crypto.randomUUID(), kind, detail });
      persist();
      count();
      void flush();
    }
    // Reconcile saved browser events with idempotent server IDs after refresh.
    get(`assessments/${sessionId}/activity-events/`).then(data => {
      if (!alive) return;
      const seen = new Set((data.events || []).map(item => item.event_id));
      queue = queue.filter(item => !seen.has(item.event_id));
      storedTabs = data.tab_switches || 0;
      storedPastes = data.blocked_pastes || 0;
      persist();
      count();
      void flush();
    }).catch(() => {
      if (alive) setActivity(previous => ({ ...previous, syncError: "Activity history could not load. Your assessment answers are unaffected." }));
    });
    count();

    let away = document.hidden;
    const visibility = () => {
      if (document.hidden && !away) {
        away = true;
        record("tab_hidden");
      } else if (!document.hidden) {
        away = false;
        void flush();
      }
    };
    const preventPaste = event => {
      if (!event.target?.closest?.("[data-assessment-answer]")) return;
      event.preventDefault();
      record("paste_blocked", { characters: event.clipboardData?.getData("text/plain")?.length || 0 });
    };
    if (status === "in_progress") {
      document.addEventListener("visibilitychange", visibility);
      document.addEventListener("paste", preventPaste, true);
    }
    const timer = window.setInterval(() => { if (!document.hidden) void flush(); }, 5000);
    return () => {
      alive = false;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", visibility);
      document.removeEventListener("paste", preventPaste, true);
    };
  }, [sessionId, status]);

  return activity;
}
