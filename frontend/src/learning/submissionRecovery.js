// Keep an unanswered request's identity across retries and refresh. Browser
// storage is optional; the same component also works entirely in memory.
const validPayload = value => value && typeof value.code === "string" && value.code.length <= 100000 && typeof value.answer === "string" && value.answer.length <= 20000;

export class SubmissionRecovery {
  constructor({ storage = () => globalThis.sessionStorage, uuid = () => crypto.randomUUID() } = {}) {
    this.storage = storage; this.uuid = uuid; this.memory = new Map();
  }
  read(key) {
    if (this.memory.has(key)) return this.memory.get(key);
    try { return JSON.parse(this.storage()?.getItem(key) || "null"); } catch { return null; }
  }
  write(key, value) {
    this.memory.set(key, value);
    try { if (value === null) this.storage()?.removeItem(key); else this.storage()?.setItem(key, JSON.stringify(value)); } catch { /* Continue safely in memory. */ }
  }
  draft(questionId) {
    const value = this.read(`labtwin_answer_${questionId}`);
    return validPayload(value) ? { code: value.code, answer: value.answer } : null;
  }
  saveDraft(questionId, payload) {
    if (validPayload(payload)) this.write(`labtwin_answer_${questionId}`, { code: payload.code, answer: payload.answer });
  }
  request(questionId, payload) {
    if (!validPayload(payload)) throw new Error("Enter a valid answer before submitting.");
    const key = `labtwin_submission_${questionId}`, prior = this.read(key);
    if (validPayload(prior) && typeof prior.request_id === "string" && /^[0-9a-f-]{36}$/i.test(prior.request_id) && prior.code === payload.code && prior.answer === payload.answer) return prior.request_id;
    const requestId = this.uuid();
    this.write(key, { request_id: requestId, code: payload.code, answer: payload.answer });
    return requestId;
  }
  settle(questionId, requestId) {
    const key = `labtwin_submission_${questionId}`;
    if (this.read(key)?.request_id === requestId) this.write(key, null);
  }
}

export const answerLocked = (attempt, sessionStatus) => sessionStatus === "completed" || ["processing", "pending_review", "completed"].includes(attempt?.status);

export function restoreAssessment(session, recovery) {
  const results = Object.fromEntries((session.attempts || []).map(attempt => [attempt.question_id, attempt]));
  const answers = Object.fromEntries(session.questions.map(question => {
    const saved = results[question.id];
    return [question.id, saved && saved.status !== "failed" ? saved.answer : recovery.draft(question.id)?.answer ?? saved?.answer ?? ""];
  }));
  return { answers, results };
}
