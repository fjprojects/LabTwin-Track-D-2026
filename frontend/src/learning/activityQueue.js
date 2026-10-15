// Only neutral metadata is persisted. Never include clipboard text, locations,
// pressed keys, video frames or an inferred misconduct verdict.
export const ACTIVITY_KINDS = new Set(["tab_hidden", "window_blur", "window_focus", "paste_allowed", "paste_blocked"]);
const COUNTERS = { tabSwitches: "tab_hidden", focusLosses: "window_blur", allowedPastes: "paste_allowed", blockedPastes: "paste_blocked" };
const SERVER = { tabSwitches: "tab_switches", focusLosses: "focus_losses", allowedPastes: "allowed_pastes", blockedPastes: "blocked_pastes" };

export function visibilityTransition(previousHidden, hidden) {
  return { hidden, departed: hidden && !previousHidden };
}

export class ActivityQueue {
  constructor({ saved = "[]", send, persist, changed }) {
    this.send = send; this.persist = persist; this.changed = changed;
    this.active = true; this.sending = false; this.initialized = false; this.error = "";
    this.counts = Object.fromEntries(Object.keys(COUNTERS).map(key => [key, 0]));
    try {
      const rows = JSON.parse(saved), ids = new Set();
      this.queue = Array.isArray(rows) ? rows.filter(row => {
        if (!row || !ACTIVITY_KINDS.has(row.kind) || typeof row.event_id !== "string" || ids.has(row.event_id)) return false;
        ids.add(row.event_id); return true;
      }).slice(0, 2000).map(row => ({ event_id: row.event_id, kind: row.kind, detail: this.safeDetail(row.detail) })) : [];
    } catch { this.queue = []; }
  }
  safeDetail(detail = {}) {
    const safe = {};
    if (typeof detail?.observed_at === "string" && detail.observed_at.length <= 40 && Number.isFinite(Date.parse(detail.observed_at))) safe.observed_at = detail.observed_at;
    if (Number.isInteger(detail?.characters) && detail.characters >= 0) safe.characters = Math.min(detail.characters, 1000000);
    return safe;
  }
  publish() {
    if (!this.active) return;
    this.persist(JSON.stringify(this.queue));
    this.changed({ ...Object.fromEntries(Object.entries(COUNTERS).map(([key, kind]) => [key, this.counts[key] + this.queue.filter(row => row.kind === kind).length])), syncError: this.error });
  }
  reconcile(data = {}) {
    const accepted = new Set((data.events || []).map(row => row.event_id));
    this.queue = this.queue.filter(row => !accepted.has(row.event_id));
    for (const [key, serverKey] of Object.entries(SERVER)) this.counts[key] = Math.max(this.counts[key], Number(data[serverKey]) || 0);
    this.publish();
  }
  initialize(data, error = "") {
    this.initialized = true; this.error = error;
    this.reconcile(data); void this.flush();
  }
  record(kind, detail, eventId, observedAt) {
    if (!this.active || !ACTIVITY_KINDS.has(kind)) return;
    if (this.queue.length >= 2000) { this.error = "Activity history is full. Your assessment remains usable."; this.publish(); return; }
    this.queue.push({ event_id: eventId, kind, detail: this.safeDetail({ ...detail, observed_at: observedAt }) });
    this.publish(); void this.flush();
  }
  async flush() {
    if (!this.active || !this.initialized || this.sending || !this.queue.length) return;
    this.sending = true;
    try {
      while (this.active && this.queue.length) {
        const data = await this.send(this.queue.slice(0, 20));
        if (!this.active) return;
        // A malformed response cannot create an endless successful retry loop.
        const before = this.queue.length;
        this.error = ""; this.reconcile(data);
        if (before === this.queue.length) throw new Error("No event receipts");
      }
    } catch {
      if (this.active) { this.error = "Activity is waiting to sync. Your answers remain available. Reconnect to retry."; this.publish(); }
    } finally { this.sending = false; }
  }
  dispose() { this.active = false; }
}
