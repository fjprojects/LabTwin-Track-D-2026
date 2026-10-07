# Verified phone password recovery

Phone OTP uses Twilio Verify alongside the existing email OTP/link recovery.
It does not replace LabTwin authentication, roles, classroom authorization or
the private deployment gate. No dependency versions change. Migration
`0011_recoveryphone_phoneotp` creates two tables without altering existing data.

## Configure delivery privately

Supply credentials for your own existing Twilio account and Verify service in
Render's **Environment** page. Never put credentials or real phone numbers in
GitHub, frontend variables, screenshots or chat. The assistant does not create
a paid Twilio account/service or send real SMS during automated tests.

| Server environment variable | Required value |
| --- | --- |
| `LABTWIN_PASSWORD_RESET_SMS_ENABLED` | `true` only when ready to permit SMS delivery |
| `TWILIO_ACCOUNT_SID` | Your `AC…` account SID |
| `TWILIO_VERIFY_SERVICE_SID` | Your `VA…` Verify service SID |
| `TWILIO_API_KEY_SID` | Your `SK…` API key authorized to use Verify |
| `TWILIO_API_KEY_SECRET` | The API key secret |
| `TWILIO_AUTH_TOKEN` | Alternative to the API key pair; leave empty when using that pair |

Enable SMS in that Verify service and check its destination permissions, sender
requirements, spending limits and trial restrictions. Verify may charge for
messages/verifications; configuring real delivery requires your provider setup.
There is no fake, console or public-code fallback. Missing configuration returns
503 with a useful message for every number. Email recovery requires its own SMTP
setup; adding a Gmail address does not itself configure email sending.

Twilio's API is HTTPS on port 443, separate from Render Free's blocked SMTP ports.
Every call has a ten-second network timeout, bounded response size and verified
TLS; redirects and automatic SMS-send retries are disabled. Provider errors are
redacted. A failed or delayed provider never changes a password or learning data.

## Enable recovery before forgetting the password

1. Sign in normally as a student or teacher and choose **Recovery phone**.
2. Enter your current password and a number including country code, such as
   `+919876543210`. Use your own phone; the example is formatting guidance.
3. Choose **Send verification code**, enter the SMS code and choose **Verify
   and save phone**. Only successfully verified numbers become credentials.
4. The saved number is masked. Replace it by verifying the new number, or remove
   it using your current password. These actions preserve the account's work.
5. If you later forget your password: **Forgot password? → Phone OTP**, enter
   the previously verified number, verify the SMS code, set/confirm a new
   password, and sign in with your original username. Existing sessions are revoked.

An account without a previously verified phone cannot be recovered by entering
an arbitrary number in this form. Use its existing registered-email recovery or
independently verified administrator assistance. A verified number belongs to
one account; proving access to it cannot transfer it from another account.

## Security and boundaries

- Public requests use the same generic response and random request ID for known,
  unknown and inactive numbers. Account lookup and delivery run after the response
  in the existing bounded delivery dispatcher.
- Requests require CSRF. Binding/inspecting/removing a recovery phone also requires
  the owner's existing bearer session; binding/removal rechecks the current password.
- Codes are generated/checked by Twilio, not by browser claims. LabTwin stores no
  plaintext SMS OTP. The check is bound to the exact provider verification SID,
  service, account, destination number and SMS channel, with `approved`/`valid=true`.
- Local challenges last at most ten minutes, have five verification attempts and
  consume atomically once. Provider time does not extend the deadline. User password,
  email, last-login or verified-phone changes invalidate pending challenges.
- Phone setup and password reset have separate purposes. A setup code cannot reset
  an account, and a reset code cannot save a phone or issue a login session. Successful
  recovery returns only the existing short-lived reset credential; existing Django
  password validation, single-use updates and session revocation remain in force.
- At most one request per number every ten minutes across both purposes, ten
  requests/IP/15 minutes and thirty verification attempts/IP/15 minutes. The longer
  resend cooldown avoids resetting attempts on Twilio's reused pending code.
- Recovery numbers are owner-only and masked in UI; roster/classroom responses do
  not expose them. Pending challenges are capped at two rows per existing account.
- Current cache limits assume the existing single-worker deployment. Configure a
  shared Django cache before adding application workers/instances. Protect the
  database as private personal data. For real-user recovery, persistent storage
  is necessary: ephemeral Free Render storage cannot preserve recovery phones.

| Route | Purpose |
| --- | --- |
| `POST /api/auth/password-reset/sms/` | Request reset proof for a previously verified number |
| `POST /api/auth/password-reset/sms/verify/` | Verify proof and issue reset-only uid/token |
| `GET/POST/DELETE /api/auth/recovery-phone/` | Owner status / request binding proof / remove |
| `POST /api/auth/recovery-phone/verify/` | Owner completes verified-phone binding |
| `POST /api/auth/password-reset/confirm/` | Existing secure password update |

## Test evidence and manual delivery acceptance

`labtwin.test_phone_recovery` mocks all external SMS calls, exercises actual
database/views and separately checks the HTTPS adapter. It covers uniform requests,
timeouts, configuration, exact provider identity, attempts/expiry/replay, account
and purpose isolation, password/phone changes, CSRF, rate limits, out-of-order jobs,
role/data preservation and owner-only masking. `labtwin.test_phone_migration`
verifies populated 0010 → 0011 migration preservation. Deployment tests ensure
all new recovery routes still require private access.

These are not proof of carrier delivery. After safe deployment and private
credential configuration, perform steps 1–5 with your own phone. Confirm wrong,
expired and reused codes fail, the new password works, the old session is revoked,
and roles/classroom data are unchanged. Record that separately as real delivery
acceptance; never publish the code, credential or reset link.

Provider references: [Twilio Verify](https://www.twilio.com/docs/verify/api/verification),
[Verification Check](https://www.twilio.com/docs/verify/api/verification-check),
[verification best practices](https://www.twilio.com/docs/verify/developer-best-practices).
