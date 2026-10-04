import { useState } from "react";
import api, { API } from "../api";

const failureMessage = error => typeof error.response?.data?.error === "string"
  ? error.response.data.error : "Password recovery could not complete. Please try again later.";

export default function PasswordReset({ target, onBack, onComplete, onRequestNew }) {
  const [email, setEmail] = useState("");
  const [passwords, setPasswords] = useState({ new_password1: "", new_password2: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function submit(event) {
    event.preventDefault();
    if (target && passwords.new_password1 !== passwords.new_password2) {
      setError("The two passwords must match."); return;
    }
    setBusy(true); setError(""); setNotice("");
    try {
      // These two new endpoints use Django CSRF protection without changing
      // the application's existing bearer-based authentication.
      const { data: security } = await api.get(`${API}/auth/password-reset/`, { withCredentials: true });
      const { data } = await api.post(
        `${API}/auth/password-reset/${target ? "confirm/" : ""}`,
        target ? { ...target, ...passwords } : { email },
        { headers: { "X-CSRFToken": security.csrf_token }, withCredentials: true },
      );
      setNotice(data.message);
      setPasswords({ new_password1: "", new_password2: "" });
      if (target) onComplete();
    } catch (err) { setError(failureMessage(err)); }
    finally { setBusy(false); }
  }

  return <main className="classroomPortal authCard">
    <p className="eyebrow">LABTWIN · CLASSROOMS</p>
    <h1>{target ? "Set a new password" : "Forgot password?"}</h1>
    <p>{target ? "Choose a new password for your existing LabTwin account."
      : "Enter your registered email to request a password reset link."}</p>
    {!notice && <form onSubmit={submit}>
      {target ? <>
        <label>New password<input required type="password" minLength={8} maxLength={1024} autoComplete="new-password"
          value={passwords.new_password1} onChange={e => setPasswords({ ...passwords, new_password1: e.target.value })} /></label>
        <label>Confirm new password<input required type="password" minLength={8} maxLength={1024} autoComplete="new-password"
          value={passwords.new_password2} onChange={e => setPasswords({ ...passwords, new_password2: e.target.value })} /></label>
      </> : <label>Registered email<input required type="email" maxLength={254} autoComplete="email"
        value={email} onChange={e => setEmail(e.target.value)} /></label>}
      {error && <p role="alert">{error}</p>}
      <button disabled={busy}>{busy ? "Please wait…" : target ? "Reset password" : "Send reset link"}</button>
    </form>}
    {notice && <p role="status">{notice}</p>}
    {!target && <p>Older accounts without a saved email need administrator-assisted recovery.</p>}
    {target && !notice && <button type="button" className="secondary" disabled={busy} onClick={onRequestNew}>Request a new reset link</button>}
    <button type="button" className="secondary" disabled={busy} onClick={onBack}>Back to sign in</button>
  </main>;
}
