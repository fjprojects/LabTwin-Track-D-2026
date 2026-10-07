import { useEffect, useState } from "react";
import api, { API } from "../api";

const errorText = error => typeof error.response?.data?.error === "string"
  ? error.response.data.error : "Recovery phone could not be updated. Please try again later.";

export default function RecoveryPhone() {
  const [status, setStatus] = useState(null), [phone, setPhone] = useState("");
  const [password, setPassword] = useState(""), [code, setCode] = useState("");
  const [requestId, setRequestId] = useState(""), [busy, setBusy] = useState(false);
  const [error, setError] = useState(""), [notice, setNotice] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    api.get(`${API}/auth/recovery-phone/`, { signal: controller.signal, withCredentials: true })
      .then(({ data }) => setStatus(data)).catch(err => { if (!controller.signal.aborted) setError(errorText(err)); });
    return () => controller.abort();
  }, []);

  async function update(event, remove = false) {
    event.preventDefault(); setBusy(true); setError(""); setNotice("");
    try {
      const { data: security } = await api.get(`${API}/auth/password-reset/`, { withCredentials: true });
      const options = { withCredentials: true, headers: { "X-CSRFToken": security.csrf_token } };
      const { data } = remove
        ? await api.delete(`${API}/auth/recovery-phone/`, { ...options, data: { password } })
        : await api.post(`${API}/auth/recovery-phone/${requestId ? "verify/" : ""}`,
          requestId ? { request_id: requestId, code } : { phone, password }, options);
      setNotice(data.message); setPassword(""); setCode("");
      if (!remove && !requestId) setRequestId(data.request_id);
      else {
        setRequestId(""); setPhone("");
        const { data: saved } = await api.get(`${API}/auth/recovery-phone/`, { withCredentials: true });
        setStatus(saved);
      }
    } catch (err) { setError(errorText(err)); }
    finally { setBusy(false); }
  }

  return <section className="classroomBox">
    <h2>Recovery phone</h2>
    <p>Verify a phone you control before using it to reset a forgotten password. This does not change your role, classrooms or saved work.</p>
    {status?.verified && <p>Verified recovery phone: {status.masked_phone}</p>}
    {status && !status.available && <p role="status">Phone OTP is unavailable until the administrator configures Twilio Verify. Email recovery remains available where configured.</p>}
    {!status && !error && <p role="status">Loading recovery phone…</p>}
    {notice && <p role="status">{notice}</p>}
    {error && <p role="alert">{error}</p>}
    {status && <form onSubmit={update}>
      {requestId ? <label>SMS verification code<input required type="text" inputMode="numeric" autoComplete="one-time-code"
        pattern="[0-9]{4,10}" minLength={4} maxLength={10} value={code} onChange={e => setCode(e.target.value)} /></label> : <>
        <label>Phone including country code<input required type="tel" autoComplete="tel" placeholder="+919876543210"
          pattern="\+[1-9][0-9]{7,14}" maxLength={16} value={phone} onChange={e => setPhone(e.target.value)} /></label>
        <label>Current password<input required type="password" autoComplete="current-password" maxLength={1024}
          value={password} onChange={e => setPassword(e.target.value)} /></label>
      </>}
      <button disabled={busy || !status.available}>{busy ? "Please wait…" : requestId ? "Verify and save phone" : "Send verification code"}</button>
      {requestId && <><p>The code expires after ten minutes with five attempts. SMS requests are limited to one per number every ten minutes.</p>
        <button type="button" className="secondary" disabled={busy} onClick={() => { setRequestId(""); setCode(""); setNotice(""); }}>Cancel verification</button></>}
      {!requestId && status.verified && <button type="button" className="secondary" disabled={busy || !password}
        onClick={event => update(event, true)}>Remove recovery phone using current password</button>}
    </form>}
  </section>;
}
