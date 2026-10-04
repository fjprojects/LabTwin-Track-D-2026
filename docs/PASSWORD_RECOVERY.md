# Password recovery

This extends the existing Django User / LabTwin Account / bearer authentication.
It does not replace users, reset roles or migrate classrooms/materials to new
accounts. Django already stores `User.email`; no data migration is needed.

## Student and teacher workflow

1. Open the existing login page and select **Forgot password?**.
2. Enter the email saved on the account. Eligible active LabTwin accounts receive
   a private email. Known, unknown and inactive addresses get identical responses.
3. Open the emailed HTTPS link. For the private demo, first complete its separate
   deployment-password gate if prompted. That gate remains enforced.
4. Set and confirm the new password. Django's existing password validators apply.
5. Sign in normally with the original username and new password. Existing bearer
   sessions, including signed material links derived from them, are revoked.

New registration has an optional recovery-email field. Existing registration API
clients that omit email remain compatible. Legacy accounts without a saved email
cannot be recovered by guessing a username/address. An authorized administrator
must independently verify the account owner and associate their verified email
using the existing Django User administration; do not create a replacement
student profile or disclose a reset token in chat. Recovery cannot restore an
account/database that was already lost by temporary hosting.

## Security and failure behavior

- Reuses Django `PasswordResetTokenGenerator` and `SetPasswordForm`. Links expire
  after **30 minutes** (`PASSWORD_RESET_TIMEOUT=1800`). Changing the password
  invalidates the used link and other outstanding links for that user.
- The password hash update is conditional on the original password, email and
  login state inside a transaction. Parallel token uses cannot overwrite a
  password already changed by a successful reset. Token revocation is atomic.
- The HTTP request path does not query accounts or wait for SMTP. Two bounded
  daemon delivery threads do the lookup/delivery. Unknown and ineligible users
  receive no email. Busy delivery returns a generic, account-independent 503.
- Requests allow at most three sends per email and 20 per remote address per
  15 minutes. Confirmation allows 30 attempts per remote address per 15 minutes.
  Identifiers are keyed hashes in Django's cache; forwarded client-IP headers
  are not trusted. Use a shared cache before scaling beyond one application
  worker. The current default local cache resets on process restart, and the
  proxy's remote address can be shared by users. Neither is account evidence.
- Both mutations require CSRF. GET `/api/auth/password-reset/` supplies a masked
  CSRF token; POST there requests email. POST
  `/api/auth/password-reset/confirm/` submits uid/token/new_password1/new_password2.
  Password reset endpoints remain behind the private deployment gate.
- Tokens occur only in the private email and frontend URL fragment, not HTTP
  query strings. The private gate temporarily keeps a validated reset fragment
  in that tab's session storage. The frontend consumes it and clears that entry
  and the browser fragment. Refreshing the form requires reopening the email.
  Do not save those private links in reports, repositories or screenshots.
- Responses are no-store/no-referrer. Logs contain only generic failure types,
  never provider exception text, recipient addresses or reset links.
- Successful resets send a password-change notification without the password
  or another reset token. Failed delivery never changes an account's password.
  There is no automatic sign-in or new privileged session after recovery.

The bounded mail dispatcher is not a durable job queue: a server restart can
interrupt delivery. Users can request another link later. This is independent
of the existing extraction/evaluation workers and adds no external queue.

## Email configuration

Email delivery is **disabled by default**. Configure your existing provider's
credentials privately in the hosting environment, not GitHub:

| Variable | Requirement |
| --- | --- |
| `LABTWIN_PASSWORD_RESET_EMAIL_ENABLED` | `true`, after configuring and testing delivery |
| `EMAIL_HOST` | Your SMTP provider's hostname |
| `EMAIL_PORT` | The provider's supported submission port |
| `EMAIL_HOST_USER` | Your SMTP username |
| `EMAIL_HOST_PASSWORD` | Your provider's SMTP credential/app password |
| `EMAIL_USE_TLS` / `EMAIL_USE_SSL` | Exactly one must be `true`; certificate verification remains enabled |
| `DEFAULT_FROM_EMAIL` | A sender address authorized by your provider |
| `LABTWIN_PASSWORD_RESET_ORIGIN` | Trusted frontend HTTPS origin, without path/query; private Render deployment infers its own origin |

The SMTP timeout is 10 seconds. No console, file or dummy email backend is used
as a fallback. In-memory delivery is allowed only in disposable DEBUG tests,
never the deployment. Missing configuration returns the same clear 503 for all
valid addresses rather than pretending email was sent.

Render's **Free** web service blocks outbound SMTP ports **25, 465 and 587**.
For that service, a provider must offer encrypted submission on an allowed port
(for example 2525, if your provider supports STARTTLS there). Do not invent a
credential, disable TLS or create paid services to conceal this restriction.
No real email delivery is verified merely by automated in-memory email tests.
See [Render's documented limitations](https://render.com/docs/free).

For local development, use matching hostnames for frontend/API so CSRF cookies
are same-site: for example frontend `http://localhost:5173`,
`VITE_API_URL=http://localhost:8000/api`, `FRONTEND_URL=http://localhost:5173`
and reset origin `http://localhost:5173`. HTTP reset links are permitted only
in DEBUG on localhost/127.0.0.1; deployment links require HTTPS.

## Preserve data before deployment

The current Free Render Docker service stores SQLite and private files under
`/data` without a persistent disk. Render discards these local changes on a
redeploy, restart or spin-down, and Free services have neither disks nor shell
access. **A password-reset code change cannot correct that hosting behavior.**

Before deploying to a service with records to preserve, obtain and verify a
private database/file backup and a restoration plan, or arrange approved
persistent storage with a data transfer. Never commit a database, private uploads,
password hashes, provider credentials or reset links to GitHub. Do not redeploy
this Free service while claiming its existing records will be preserved.

## Regression checks

The full backend suite includes `labtwin.test_password_reset`: known/unknown
responses, deferred lookup, trusted links, missing email configuration, unsafe
backends, legacy/new email registration, expiry, replay, cross-user tampering,
weak passwords, role/data preservation, all-session revocation, CSRF, bounded
delivery, sanitized provider failures and transactional rollback.

Run the existing frontend camera/API tests, plus `npm run test:auth`, build and
lint. Run the two deployment suites separately as documented in
`deployment/README.md`; they additionally check that recovery does not unlock
the private gate and that its fragment handoff has a per-response CSP nonce.

An end-to-end external inbox click remains a separate acceptance check after
real email delivery and persistent hosting are configured.
