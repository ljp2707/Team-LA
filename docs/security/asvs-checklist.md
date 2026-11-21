# OWASP ASVS 5.0 Level 2 and API Security Top 10

How NMU Programs meets OWASP's Application Security Verification Standard 5.0 at Level 2 and
the OWASP API Security Top 10 (2023). Checked on 2026-11-20 against the `production-hardening`
branch. Findings (F1 to F42) are in `findings.md`.

**Status:** **Met**, **Partly** (met with a stated limit), **Gap** (not met; why, and what would
close it), **N/A** (the app does not have this feature).

This maps each ASVS chapter's Level 1 and 2 requirements to the controls that meet them, in
groups. It is not a formal audit; a reviewer should check the code and tests named here.

## ASVS 5.0

### V1 Encoding and sanitization

| Requirement area | Status | How |
|---|---|---|
| Output encoding for HTML | Met | React escapes all text. Email HTML is built with escaping (`app/email/templates.py`) |
| No injection into queries | Met | Airtable is never queried with formulas built from user text; the app filters cached rows in Python (`models/user.py`) |
| URL safety | Met | Links must be `https://` (or `http://`) and are checked before display and storage (F7) |
| No unsafe deserialization or templates | Met | JSON only, parsed by pydantic; no server-side template engine on user input |
| Log injection | Met | One JSON object per line; event values cleaned to one line (F36) |

### V2 Validation and business logic

| Requirement area | Status | How |
|---|---|---|
| Input validated on the server | Met | pydantic models with types, lengths (39 `max_length` limits) and patterns; record IDs must match `rec...` (F23) |
| Business rules enforced server-side | Met | Last-admin, self-demotion, open-task checks (`routers/users.py`); dependency and date rules (`services/`) |
| Anti-automation | Met | Rate limits per address and per person (F5), nudge limits per person and task (F20), one nudge at a time (F21) |
| Business logic limits | Partly | Limits are kept in memory, so they are per app instance. Fine for one Railway instance; scaling out needs a shared store (README) |

### V3 Web frontend security

| Requirement area | Status | How |
|---|---|---|
| Content-Security-Policy | Met | Enforced by default, `script-src 'self'`, no inline script, `frame-ancestors 'none'`, `form-action 'self'`; violations reported (F1, F25, F26, F28); a Playwright test opens every page under it |
| Other browser headers | Met | HSTS (production), `nosniff`, `X-Frame-Options: DENY`, Referrer-Policy, Permissions-Policy, COOP, CORP, `X-Permitted-Cross-Domain-Policies` (F1, F27) |
| Cookie attributes | Met | `__Host-` prefix, Secure, HttpOnly, SameSite=Lax, Path=/ (F29) |
| Cross-site request forgery | Met | Origin checked on every change (F9), SameSite cookie, sign out is POST only (F8) |
| Third-party content | Met | No third-party scripts or styles; fonts self-hosted (F26) |
| Sensitive data in the browser | Met | Nothing stored in localStorage; API answers are `Cache-Control: no-store` |

### V4 API and web service

| Requirement area | Status | How |
|---|---|---|
| Correct methods and status codes | Met | Changes need POST/PUT/PATCH/DELETE; GET changes nothing (access matrix checks read-only roles change nothing) |
| Content types | Met | JSON bodies; uploads multipart only, size-limited before parsing (F6) |
| API inventory | Met | `threat-model.md` lists every route; the access matrix fails if a route is added without a row. API docs off in production (F2) |
| GraphQL, WebSocket | N/A | Not used |

### V5 File handling

| Requirement area | Status | How |
|---|---|---|
| Size limits | Met | Per-request and per-file limits, enforced before parsing (F6) |
| Type checking | Met | File content must match its extension (F10) |
| Storage and serving | Met | Files are stored as Airtable attachments and served from Airtable's own domain, never from the app's origin; downloads check the person may see the task |
| Malware scanning | Partly | Not scanned. Files are only shared among staff and partners on the same program; Airtable serves them as downloads |

### V6 Authentication

| Requirement area | Status | How |
|---|---|---|
| Single, external identity provider | Met | Google only; no passwords stored |
| Account allow-list | Met | An Active row in Users is required; bootstrap list only for the first admin, warned about afterwards and checked against the domain (F33) |
| Domain restriction | Met | With `ALLOWED_EMAIL_DOMAIN` set, both the email and Google's `hd` claim must match (F32) |
| Multi-factor authentication | Partly | Delegated to Google. The app cannot see or require it. **Action:** enforce 2-Step Verification in NMU's Google Workspace for all staff, and ask partners to turn it on |
| Account lifecycle | Met | Deactivation ends sessions and calendar links at once (F30); erasure for deletion requests |

### V7 Session management

| Requirement area | Status | How |
|---|---|---|
| Session tokens | Met | Signed cookie with a random ID per session (F31); no tokens in URLs (calendar links are separate, revocable, and redacted from logs, F3) |
| Timeouts | Met | 24 hours idle and 7 days absolute (F15) |
| Termination | Met | Sign out; sign out of all devices; admin "sign out everywhere"; automatic on deactivation, access level change, role removal, erasure (F30) |
| New session on sign in and privilege change | Met | F31 |
| Re-authentication before sensitive actions | Gap | Admin actions do not ask the admin to sign in again. **Would close it:** a "recent sign in" check (for example under 15 minutes) on erase, access level changes and sign-out-everywhere, sending the admin through Google with `prompt=login` |

### V8 Authorization

| Requirement area | Status | How |
|---|---|---|
| Server-side checks on every route | Met | Dependencies in `auth/deps.py` and rules in `permissions.py`; the access matrix tests every route for seven roles (743 tests) |
| Object-level checks | Met | Partners see only their programs (404 elsewhere), staff only change their own tasks, note visibility rules (F11, F16) |
| Field-level checks | Met | Only allowed fields are written; automation-owned fields are refused by the client |
| Changes to access take effect at once | Met | Status and level are re-read on every request (30-second cache) and sessions end on change (F30) |

### V9 Self-contained tokens

| Requirement area | Status | How |
|---|---|---|
| Signed tokens | Partly | The session cookie is signed with HMAC-SHA1 (Starlette's default through itsdangerous) and checked on every request; its content is only trusted for the record ID, and the Session Version allows revocation. HMAC-SHA1 is still sound for signing, but ASVS prefers SHA-256. **Would close it:** a SessionMiddleware subclass with a SHA-256 signer (this signs everyone out once) |
| JWTs | N/A | The app issues none. Google's ID token is checked by authlib |

### V10 OAuth and OIDC

| Requirement area | Status | How |
|---|---|---|
| Authorization code flow with state and nonce | Met | authlib handles state and nonce; the callback URL is fixed; Google's sign-in code is redacted from logs (F3) |
| Verified email only | Met | `email_verified` required |
| Minimal scopes | Met | Sign in: `openid email profile`. Gmail: `gmail.send` only (F37) |

### V11 Cryptography

| Requirement area | Status | How |
|---|---|---|
| Random values | Met | `secrets` for session IDs and calendar tokens; UUID4 for request IDs |
| Secret strength | Met | `SESSION_SECRET` must be 32+ characters in production (F12) |
| Algorithms | Partly | See V9 (HMAC-SHA1 cookie signature) |

### V12 Secure communication

| Requirement area | Status | How |
|---|---|---|
| TLS everywhere | Met | Railway terminates TLS; production refuses `http://` addresses (F33); HSTS; Secure cookie |
| Outbound TLS | Met | Airtable, Google and Gmail over HTTPS with certificate checks (library defaults) |

### V13 Configuration

| Requirement area | Status | How |
|---|---|---|
| Fail closed in production | Met | Refuses to start with weak secrets, dev login, view switch, http addresses, incomplete email settings, the migration token, or bootstrap addresses outside the domain (F4, F12, F33, F37) |
| Least privilege for credentials | Met | Airtable token data-only, separate migration token, Gmail send-only, cron service gets only what it needs (F37) |
| Secrets management | Partly | Railway variables, not a vault; rotation documented (`secrets-runbook.md`) |
| No debug information exposed | Met | API docs off, no stack traces to users (request ID only), no Server header (F2, F27) |
| Allowed hosts | Met | Unknown hosts get 400 (F14) |

### V14 Data protection

| Requirement area | Status | How |
|---|---|---|
| Personal data minimised | Met | Names, work emails, task notes only; masked emails in logs (F13); audit rows hold IDs only (F34) |
| Deletion requests | Met | "Remove personal details" (admin runbook, Privacy requests) |
| Data at rest | Partly | Encrypted by Airtable; the app stores nothing itself. Monthly exports must be kept confidential (`backups.md`) |
| Privacy notice | Met | Privacy and Terms pages |

### V15 Secure coding and architecture

| Requirement area | Status | How |
|---|---|---|
| Security logic in few places | Met | `auth/`, `permissions.py`, `security.py`, `audit.py`, `rate_limit.py`, `request_limits.py` |
| Dependencies pinned and checked | Met | Hash-locked Python, exact npm with a 7-day release age, pip-audit, npm audit, Trivy, Dependabot (F39, F42) |
| Software bill of materials | Partly | The lock files list every package; no SBOM file is published. Trivy can produce one (`trivy image --format cyclonedx`) |
| Concurrency | Met | One nudge at a time (F21); half-finished deletes reported (F22) |
| Static analysis | Met | ruff with Bandit rules, Semgrep, in CI (F41, F42) |

### V16 Security logging and error handling

| Requirement area | Status | How |
|---|---|---|
| Security events logged | Met | Sign in and refusals, session ends, 403, 429, 413, CSP, admin actions, errors (F36) |
| No sensitive data in logs | Met | Tokens and codes redacted, emails masked, no bodies (F3, F13, F36) |
| Log format and correlation | Met | JSON lines with request IDs (F36) |
| Audit trail | Met | Append-only Audit Log with a read-only page (F34, F35) |
| Log retention and protection | Partly | Railway keeps logs for a limited time and anyone with Railway access can read them. **Action:** a log drain to a store NMU controls (`monitoring.md`) |
| Errors fail safely | Met | Generic message and request ID; Airtable down gives 503 |

### V17 WebRTC

N/A: not used.

## OWASP API Security Top 10 (2023)

| Risk | Status | How |
|---|---|---|
| API1 Broken object level authorization | Met | Object checks on tasks, notes, links, programs; partner isolation; access matrix object tests (F11, F16) |
| API2 Broken authentication | Met | Google only, allow-list, `hd` check, revocable sessions (F29 to F32). MFA via Google (see V6) |
| API3 Broken object property level authorization | Met | pydantic input models list allowed fields; only allowed fields written; responses built per role |
| API4 Unrestricted resource consumption | Met | Rate limits, size limits, nudge limits, email caps (F5, F6, F20) |
| API5 Broken function level authorization | Met | Admin routes behind `require_admin`; matrix tests every role on every route; every admin change audited (F34) |
| API6 Unrestricted access to sensitive business flows | Met | Nudges limited per person and task (F20, F21); reminders deduplicated |
| API7 Server-side request forgery | Met | The app fetches only fixed hosts (Airtable, Google); user URLs are stored and shown, never fetched |
| API8 Security misconfiguration | Met | Fail-closed settings, headers, CSP, no docs or Server header in production (F1, F2, F27, F33) |
| API9 Improper inventory management | Met | One API, one version; every route in `threat-model.md` and the access matrix |
| API10 Unsafe consumption of APIs | Met | Airtable and Google answers are validated; Airtable links are scheme-checked before display (F7) |

## Open items

1. **Re-authentication for sensitive admin actions** (V7). Gap.
2. **SHA-256 session signature** (V9, V11). Partly.
3. **MFA** enforced through Google Workspace (V6). Manual, NMU.
4. **Log drain** to NMU-controlled storage (V16). Manual, NMU.
5. **Shared rate-limit store** if the app ever runs on more than one instance (V2).
