import { useState } from "react";
import api, { API } from "../api";

const failureMessage = error => typeof error.response?.data?.error === "string"
  ? error.response.data.error : "Password recovery could not complete. Please try again later.";

export default function PasswordReset({ target, onBack, onComplete, onRequestNew }) {
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [method, setMethod] = useState("otp");
  const [requestId, setRequestId] = useState("");
  const [code, setCode] = useState("");
  const [verifiedTarget, setVerifiedTarget] = useState(null);
  const [passwords, setPasswords] = useState({ new_password1: "", new_password2: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [done, setDone] = useState(false);
  const credential = target || verifiedTarget;
  const step = done ? "done" : credential ? "password" : requestId ? "otp" : "request";

  async function submit(event) {
    event.preventDefault();
    if (step === "password" && passwords.new_password1 !== passwords.new_password2) {
      setError("The two passwords must match."); return;
    }
    setBusy(true); setError(""); setNotice("");
    try {
      const { data: security } = await api.get(`${API}/auth/password-reset/`, { withCredentials: true });
      const suffix = step === "password" ? "confirm/" : method === "sms"
        ? step === "otp" ? "sms/verify/" : "sms/" : step === "otp" ? "otp/verify/" : "";
      const payload = step === "password" ? { ...credential, ...passwords }
        : step === "otp" ? { request_id: requestId, code } : method === "sms" ? { phone } : { email, method };
      const { data } = await api.post(`${API}/auth/password-reset/${suffix}`, payload,
        { headers: { "X-CSRFToken": security.csrf_token }, withCredentials: true });
      setNotice(data.message);
      if (step === "request" && method !== "link") setRequestId(data.request_id);
      else if (step === "otp") { setVerifiedTarget({ uid: data.uid, token: data.token }); setCode(""); }
      else {
        setDone(true); setPasswords({ new_password1: "", new_password2: "" }); setVerifiedTarget(null);
        if (step === "password") onComplete();
      }
    } catch (err) { setError(failureMessage(err)); }
    finally { setBusy(false); }
  }

  function requestNew() {
    setRequestId(""); setVerifiedTarget(null); setCode(""); setDone(false);
    setPasswords({ new_password1: "", new_password2: "" }); setError(""); setNotice("");
    if (target) onRequestNew();
  }

  return <main className="classroomPortal authCard">
    <p className="eyebrow">LABTWIN · CLASSROOMS</p>
    <h1>{step === "password" ? "Set a new password" : step === "otp" ? "Enter verification code" : "Forgot password?"}</h1>
    <p>{step === "password" ? "Choose a new password for your existing LabTwin account."
      : step === "otp" ? method === "sms"
        ? "Enter the code from your phone. It expires after 10 minutes and allows five attempts. Wait ten minutes before requesting another SMS."
        : "Enter the eight-digit code from your email. It expires after 10 minutes and allows five attempts."
        : "Recover your existing account using its saved email or previously verified phone."}</p>
    {notice && <p role="status">{notice}</p>}
    {step !== "done" && <form onSubmit={submit}>
      {step === "password" ? <>
        <label>New password<input required type="password" minLength={8} maxLength={1024} autoComplete="new-password"
          value={passwords.new_password1} onChange={e => setPasswords({ ...passwords, new_password1: e.target.value })} /></label>
        <label>Confirm new password<input required type="password" minLength={8} maxLength={1024} autoComplete="new-password"
          value={passwords.new_password2} onChange={e => setPasswords({ ...passwords, new_password2: e.target.value })} /></label>
      </> : step === "otp" ? <label>{method === "sms" ? "SMS" : "Email"} verification code<input required type="text" inputMode="numeric"
        pattern={method === "sms" ? "[0-9]{4,10}" : "[0-9]{8}"} minLength={method === "sms" ? 4 : 8} maxLength={method === "sms" ? 10 : 8} autoComplete="one-time-code"
        value={code} onChange={e => setCode(e.target.value)} /></label> : <>
        <label>Recovery method<select value={method} onChange={e => setMethod(e.target.value)}>
          <option value="otp">Email OTP</option><option value="link">Email reset link</option><option value="sms">Phone OTP</option>
        </select></label>
        {method === "sms" ? <label>Previously verified phone<input required type="tel" maxLength={16}
          pattern="\+[1-9][0-9]{7,14}" placeholder="+919876543210" autoComplete="tel"
          value={phone} onChange={e => setPhone(e.target.value)} /></label>
          : <label>Registered email<input required type="email" maxLength={254} autoComplete="email"
            value={email} onChange={e => setEmail(e.target.value)} /></label>}
      </>}
      {error && <p role="alert">{error}</p>}
      <button disabled={busy}>{busy ? "Please wait…" : step === "password" ? "Reset password"
        : step === "otp" ? "Verify code" : method !== "link" ? "Send verification code" : "Send reset link"}</button>
    </form>}
    {step === "request" && <p>Phone recovery must first be enabled from Recovery phone while signed in. Accounts without a saved email or verified phone need administrator-assisted recovery.</p>}
    {step !== "request" && <button type="button" className="secondary" disabled={busy} onClick={requestNew}>Request a new code or link</button>}
    <button type="button" className="secondary" disabled={busy} onClick={onBack}>Back to sign in</button>
  </main>;
}
