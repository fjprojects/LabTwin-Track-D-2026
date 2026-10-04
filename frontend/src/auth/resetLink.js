export const RESET_STORAGE_KEY = "labtwin_password_reset";

// Reset credentials stay in the fragment/tab, never in an API URL or a log.
export function parseResetFragment(fragment) {
  if (typeof fragment !== "string") return null;
  const match = /^#password-reset=([A-Za-z0-9_-]{1,64}):([a-z0-9]{1,13}-[0-9a-f]{32})$/.exec(fragment);
  return match ? { uid: match[1], token: match[2] } : null;
}

export function initialResetTarget() {
  const direct = parseResetFragment(window.location.hash);
  if (direct) return direct;
  try { return parseResetFragment(sessionStorage.getItem(RESET_STORAGE_KEY)); }
  catch { return null; }
}
