# NMU Launches security findings

Reviewed 2026-11-19. Read-only: no code was changed. Line numbers are for the current working
tree. See [threat-model.md](threat-model.md) for assets, actors and every entry point.

Severity: **High** = exploitable now by an outsider or a low-trust user, with serious impact.
**Medium** = real gap that needs a misconfiguration, an insider, or a second bug, or that is
mostly availability. **Low** = defence in depth or a small information leak.
**Info** = no action needed, recorded so nobody re-checks it.

No High findings. The existing baseline (listed in the task brief) held up everywhere I tested
it.

## Summary

| # | Finding | Severity | Status |
|---|---|---|---|
| F1 | No Content-Security-Policy or Strict-Transport-Security header | Medium | Partly fixed in `39baf62`: HSTS on, CSP report-only |
| F2 | `/docs`, `/redoc` and `/openapi.json` are public in production | Medium | Fixed in `3ae3248` |
| F3 | Calendar feed tokens (and OAuth codes) are written to the access log | Medium | Fixed in `39baf62` |
| F4 | `DEV_ALLOW_VIEW_SWITCH=true` is not refused in production | Medium | Fixed in `3ae3248` |
| F5 | No rate limiting on any endpoint | Medium | Fixed in `7d83c4c` |
| F6 | Upload bodies have no size limit and are parsed before sign-in is checked | Medium | Fixed in `39baf62` |
| F7 | URLs typed directly into Airtable are rendered as links without a scheme check | Medium | Fixed in `39baf62` |
| F8 | `GET /auth/logout` can be triggered from any website | Low | Fixed in `7d83c4c` |
| F9 | CSRF protection relies on SameSite=Lax alone; no Origin check | Low | Closed; Origin check added anyway in `66af153` |
| F10 | Uploaded file content is not checked against its extension | Low | Fixed in `7d83c4c` |
| F11 | Staff on a task can share another person's Internal note with partners | Low | Fixed in `7d83c4c` |
| F12 | `ENV` defaults to `development`, so production protections fail open if it is missing | Low | Fixed in `3ae3248` |
| F13 | Recipient email addresses are written to logs | Low | Fixed in `7d83c4c` |
| F14 | Proxy headers and allowed hosts are not configured for Railway | Low | Fixed in `7d83c4c` |
| F15 | Sessions cannot be revoked server-side; logout only clears the browser cookie | Low | Mitigated in `7d83c4c`: idle and 7-day limits |
| F16 | Note lookup skips the project check when a note has no launch | Low | Fixed in `7d83c4c` |
| F17 | `npm audit`: 2 moderate advisories in react-router | Low | Fixed in `7d83c4c` |
| F18 | Dependency and secret scans otherwise clean | Info | No action needed |
| F19 | Checks that passed: IDOR, partner isolation, role changes, error responses | Info | No action needed |

---

## Findings

### F1. No Content-Security-Policy or Strict-Transport-Security — Medium

**Status: Partly fixed in commit `39baf62`.** HSTS is sent in production. The CSP is sent as `Content-Security-Policy-Report-Only` while `CSP_MODE=report-only` (the default). It is fully fixed once the live site shows no CSP warnings in the browser console and `CSP_MODE=enforce` is set on Railway. Tests in `backend/tests/test_security_hardening.py`.

- **Where:** `backend/app/main.py:54-60` (`SECURITY_HEADERS`). Verified on the live site: the
  response has `nosniff`, `X-Frame-Options`, `Referrer-Policy` and `Permissions-Policy`, and no
  `Content-Security-Policy` or `Strict-Transport-Security`.
- **Exploit:** Any XSS bug (for example F7) runs with full access to the API as the victim,
  because nothing restricts scripts. Without HSTS, someone on hostile Wi-Fi can catch a user's
  first plain-`http://` request before Railway's redirect to https.
- **Fix:** Add `Strict-Transport-Security: max-age=31536000` (production only, so localhost is
  unaffected). Add a CSP that matches the built app: `default-src 'self'; script-src 'self';
  style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self';
  frame-ancestors 'none'; base-uri 'none'; form-action 'self'`. The built `index.html` has no
  inline scripts, and React `style={...}` props are set through the DOM, which CSP allows. Load
  the built site once with the header on and check the browser console for blocked resources
  before deploying. Keep the CSP off the Vite dev server so localhost is unaffected. Test: the
  header is present in production mode, and HSTS is absent on localhost.

### F2. API docs public in production — Medium

**Status: Fixed in commit `3ae3248`.** Tests in `backend/tests/test_security_settings.py`.

- **Where:** `backend/app/main.py:52` (`FastAPI(...)` uses the default `docs_url`,
  `redoc_url` and `openapi_url`). Live: `/docs`, `/redoc` and `/openapi.json` all answer 200.
- **Exploit:** A signed-out visitor gets a full map of every route, parameter and model,
  including admin-only ones such as `/api/users/{id}/erase`. It does not grant access, but it
  removes guesswork for anyone probing the app.
- **Fix:** In production pass `docs_url=None, redoc_url=None, openapi_url=None`. Keep them on
  localhost. Test: 404 in production mode, 200 in development.

### F3. Calendar tokens in access logs — Medium

**Status: Fixed in commit `39baf62`.** Tests in `backend/tests/test_security_hardening.py`. Filter in `backend/app/log_redaction.py`. Tokens logged before this fix stay in old Railway logs; see Manual steps.

- **Where:** `Dockerfile:21` runs uvicorn with its default access log, which writes the full
  request path. `/calendar/{token}.ics` (`backend/app/routers/calendar.py:38`) puts the token in
  the path. Google Calendar fetches it every few hours, so it lands in Railway logs repeatedly.
  `/auth/callback?code=...&state=...` is logged too (the code is single-use, so it matters less).
- **Exploit:** Anyone who can read Railway logs, or a log export or third-party log drain, can
  copy a feed URL and read that person's open tasks, due dates and launch names until the token
  is reset.
- **Fix:** Add a `logging.Filter` on the `uvicorn.access` logger that replaces the token
  segment with `<token>` and drops the query string on `/auth/callback`. Alternatively turn off
  uvicorn's access log and log method, redacted path and status ourselves. Test: a request to a
  feed URL produces a log record without the token.

### F4. `DEV_ALLOW_VIEW_SWITCH` allowed in production — Medium

**Status: Fixed in commit `3ae3248`.** Tests in `backend/tests/test_security_settings.py`.

- **Where:** `backend/app/config.py:35` (setting) and `:78-92` (the production validator checks
  `SESSION_SECRET` and `DEV_LOGIN_EMAIL`, not this). Used by `can_choose_view`,
  `backend/app/permissions.py:51`. The README says "Keep it false in production" but nothing
  enforces it.
- **Exploit:** If someone sets it to `true` on Railway (for a demo, say), every Staff and
  Viewer user can `POST /api/me/view {"view":"admin"}` and get real admin permissions: edit
  users, delete launches, export data.
- **Fix:** Refuse to start when `is_production` and `DEV_ALLOW_VIEW_SWITCH` are both true, the
  same way `DEV_LOGIN_EMAIL` is handled. Test: building `Settings(ENV="production",
  DEV_ALLOW_VIEW_SWITCH=True, ...)` raises.

### F5. No rate limiting — Medium

**Status: Fixed in commit `7d83c4c`.** In-memory limits in `backend/app/rate_limit.py`; the limits are listed in the README. Tests in `backend/tests/test_security_access.py`.

- **Where:** No limiter anywhere. Most relevant: `/auth/login` and `/auth/callback`
  (`backend/app/routers/auth.py:91,105`), the upload routes (F6), `/calendar/{token}.ics`,
  `/api/public/*`, and every write route.
- **Exploit:** A script can hit sign-in, uploads or write routes fast enough to exceed
  Airtable's 5 requests per second per base. Airtable then locks the base for 30 seconds,
  which takes the app down for everyone. Writes are not cached, so a signed-in user can do
  this alone. Reads are mostly served from the 30-second cache, so the public routes are the
  smaller risk.
- **Fix:** A small in-memory, per-IP and per-user limiter (one Railway instance, so memory is
  enough). Suggested limits: sign-in 10 per minute per IP; uploads 20 per hour per user; writes
  60 per minute per user; feed and public routes 60 per minute per IP. It needs the real client
  IP, so do F14 first. Prefer a few lines of our own code over a dependency. `slowapi` is the
  usual package, but it is thinly maintained.

### F6. Unlimited upload size, parsed before sign-in — Medium

**Status: Fixed in commit `39baf62`.** Tests in `backend/tests/test_security_hardening.py`. Middleware in `backend/app/request_limits.py`.

- **Where:** `backend/app/routers/tasks.py:477` and `backend/app/routers/projects.py:370` take
  `UploadFile`. FastAPI parses the multipart body (`fastapi/routing.py:455`, version 0.162.0)
  before it runs dependencies such as `current_user` (`:511`). Starlette spools file parts to a
  temporary file with no size cap. The 5 MB check is in `backend/app/services/links.py:94`,
  after all that. There is no request-size limit in uvicorn or the app.
- **Exploit:** A signed-out attacker sends multi-gigabyte multipart POSTs to
  `/api/tasks/anything/files`. Each is written to the container's disk before the 401, which
  can fill the disk or tie up workers.
- **Fix:** A small ASGI middleware that refuses any request whose `Content-Length` exceeds a
  limit (about 6 MB for upload paths, 1 MB elsewhere), and also counts bytes as they stream, in
  case `Content-Length` is missing or wrong. Answer 413. Test: a 7 MB body to an upload route
  gets 413 without reaching the handler, signed out and signed in.

### F7. Links from Airtable rendered without a scheme check — Medium

**Status: Fixed in commit `39baf62`.** Tests in `backend/tests/test_security_hardening.py`. `safe_link` in `backend/app/services/links.py`, `safeHref` in `frontend/src/lib/safeHref.ts`.

- **Where:** The API only accepts `https://` links (`backend/app/models/task.py:48-51`) and Drive
  folders (`backend/app/models/project.py:36-41`). But values typed directly into Airtable skip
  that: the template `Resource Link` (`backend/app/routers/tasks.py:174-178`, only ever set in
  Airtable), the `URL` field of Links rows, and `Drive Folder`. The frontend puts them straight
  into `href` (`frontend/src/pages/TaskDetail.tsx:243`, `frontend/src/pages/ProjectDetail.tsx:243`
  and `:304`). React 18 warns about `javascript:` URLs but still renders them.
- **Exploit:** Anyone with edit access to the Airtable base, or anyone who obtains the Airtable
  token, sets a link to `javascript:fetch('/api/users',...)`. When an admin clicks it, it runs
  as that admin in the app. With no CSP (F1), nothing stops it.
- **Fix:** Validate on the way out: in `link_dict` and the task payload, only return URLs that
  start with `https://` (otherwise return `null` and show the link as plain text). Add a small
  `safeHref()` helper in the frontend as a second check. Test: a Links row with a `javascript:`
  URL comes back with `url: null`.

### F8. Logout by GET — Low

**Status: Fixed in commit `7d83c4c`.** `POST /auth/logout` signs out; `GET` only goes home. The sidebar uses a form button. Tests in `backend/tests/test_security_access.py`.

- **Where:** `backend/app/routers/auth.py:132`.
- **Exploit:** Any website can include `<img src="https://…/auth/logout">`. A top-level
  navigation also carries the Lax cookie. Visitors to that page are signed out. This is a
  nuisance, not data access.
- **Fix:** Make logout `POST` (the sidebar link becomes a small form button). Keep `GET`
  answering with a redirect to the home page, without clearing the session, so old bookmarks
  do not break. Test: `GET /auth/logout` leaves the session intact; `POST` with a same-origin
  `Origin` clears it.

### F9. CSRF relies on SameSite=Lax alone — Low

**Status: Closed, not an issue. An Origin check was added anyway in commit `66af153` as defence in depth (`OriginCheck` in `backend/app/security.py`, tests in `backend/tests/test_security_requests.py`).** Confirmed by the project owner that `up.railway.app` is on the Public Suffix List, so other Railway apps are cross-site and the Lax cookie is never sent with their requests. Kept below for the record.

- **Where:** `backend/app/main.py:70-77` (session cookie). No Origin or Referer check on writes.
- **Exploit:** Today a cross-site attacker cannot send the cookie on a POST, PATCH or DELETE,
  because of Lax. JSON routes also need `Content-Type: application/json`: FastAPI's strict
  content-type check, verified live, means a cross-site form cannot send JSON, and the browser
  preflight is refused because there is no CORS. The gap is the multipart upload routes, which
  a plain HTML form can post, and anything "same-site": SameSite treats every host under one
  registrable domain as the same site. Whether that protects us depends on `up.railway.app`
  being on the Public Suffix List, so other people's Railway apps count as other sites. I
  believe it is listed, but check it. It also stops mattering once the app has its own domain.
- **Fix:** A middleware that, for POST, PUT, PATCH and DELETE, requires the `Origin` header,
  or `Referer` if `Origin` is missing, to match `APP_URL` or `FRONTEND_URL`. Allow both
  `localhost` origins in development so Vite and pytest keep working. Test: a write with
  `Origin: https://evil.example` gets 403; a same-origin write passes; a multipart upload with a
  foreign `Origin` gets 403.

### F10. File content not checked against extension — Low

**Status: Fixed in commit `7d83c4c`.** Signature check in `backend/app/services/links.py` (`_looks_like`). Tests in `backend/tests/test_security_access.py`.

- **Where:** `backend/app/services/links.py:85-99` (`read_upload` checks only the name and the
  size).
- **Exploit:** A Staff or Partner user uploads an `.exe` renamed to `report.pdf`. Another user
  downloads and opens it. Airtable serves files from its own domain, so this cannot attack the
  app itself; the risk is malware passed between users.
- **Fix:** Check the first bytes against the extension using the standard library only: PDF
  `%PDF-`; PNG `\x89PNG`; JPEG `\xFF\xD8\xFF`; GIF `GIF8`; WebP `RIFF....WEBP`; HEIC/HEIF
  `ftyp` box; DOCX/XLSX/PPTX `PK\x03\x04`; DOC/XLS/PPT `\xD0\xCF\x11\xE0`; TXT and CSV valid
  UTF-8 with no NUL bytes. Refuse mismatches with a clear message. Test: an executable header
  named `.pdf` is refused.

### F11. Staff can share someone else's Internal note — Low

**Status: Fixed in commit `7d83c4c`.** Decided 2026-11-19 that it was not intended: only the note's author or an admin may share an Internal note with partners (`can_share_note` in `backend/app/permissions.py`). Tests in `backend/tests/test_security_access.py`.

- **Where:** `backend/app/routers/links.py:100-109` (`share_note`). It checks
  `can_share_notes` (not a partner, not read-only) and `can_edit_task`, not authorship.
- **Exploit:** A Staff member assigned to a task flips an Admin's Internal note on that task to
  Shared, and the partner on that launch can now read it. It needs an insider and may be
  intended, but it is the one path where staff-only text reaches partners without an admin.
- **Fix (needs a product decision):** Allow sharing only by the note's author or an Admin.
  Test: Staff on the task gets 403 on another person's note.

### F12. `ENV` fails open — Low

**Status: Fixed in commit `3ae3248`.** Tests in `backend/tests/test_security_settings.py`.

- **Where:** `backend/app/config.py:19` (`ENV: str = "development"`). `is_production` drives the
  Secure cookie flag (`backend/app/main.py:76`) and the `SESSION_SECRET` check.
- **Exploit:** If `ENV` is ever missing on Railway (a new service, a typo), the app starts with
  a non-Secure cookie and accepts the placeholder secret. Anyone who reads `.env.example`
  could then forge an admin session. Verified today: the live cookie has `secure`, so `ENV` is
  set.
- **Fix:** Treat any `https://` `APP_URL` as production for these checks. That covers a
  missing `ENV` without affecting localhost. Test: `Settings(APP_URL="https://x",
  SESSION_SECRET=<placeholder>)` raises.

### F13. Email addresses in logs — Low

**Status: Fixed in commit `7d83c4c`.** `mask_email` in `backend/app/log_redaction.py`. Tests in `backend/tests/test_security_access.py`.

- **Where:** `backend/app/email/gmail.py:126` and `backend/app/services/reminders.py:396,428`
  (`Dry run email to <address>`), and the cron output labels at
  `backend/app/services/reminders.py:202,286`, printed by `backend/jobs/send_reminders.py:34-43`.
- **Exploit:** Railway logs collect every staff and partner address. This breaks rule 7 and
  widens what a log reader learns.
- **Fix:** Log the Users record ID, or a masked address (`m***@example.org`), instead. Keep the
  full address only in the `--dry-run` command-line output, which a developer runs on purpose.
  Test: capture logs during a dry-run send and assert no address appears.

### F14. Proxy headers and allowed hosts — Low

**Status: Fixed in commit `7d83c4c`.** Allowed hosts are `APP_URL` and `FRONTEND_URL` hosts, localhost and `healthcheck.railway.app`. Update `APP_URL` and `FRONTEND_URL` if you add a custom domain. Tests in `backend/tests/test_security_access.py`.

- **Where:** `Dockerfile:21`. uvicorn trusts `X-Forwarded-*` only from 127.0.0.1, so behind
  Railway `request.client.host` is Railway's proxy and `request.url.scheme` is `http`. There is
  no `TrustedHostMiddleware`.
- **Exploit:** Nothing today. Redirect and callback URLs come from `APP_URL`, never the Host
  header, and the cookie's Secure flag is set from config. But any per-IP rate limit (F5) would
  treat every user as one IP, and future code that builds URLs from the request would get the
  wrong scheme or host.
- **Fix:** Run uvicorn with `--proxy-headers --forwarded-allow-ips='*'`. That is safe only
  because Railway's edge is the only way in; say so in a comment. Add
  `TrustedHostMiddleware(allowed_hosts=[host of APP_URL, "localhost", "127.0.0.1",
  "testserver"])`. Test: a request with `Host: evil.example` gets 400 in production mode.

### F15. Sessions cannot be revoked — Low (Fixed by F30)

**Status: Mitigated in commit `7d83c4c`.** Sessions now end after `SESSION_IDLE_HOURS` without use (default 24) and 7 days after sign in, however active. Before, the cookie lifetime renewed on every request, so an active session never ended. Logout still cannot cancel a copied cookie on the server; that needs Option A (a session version on the Users row), not done. Tests in `backend/tests/test_security_access.py`. **Update 2026-11-20:** Option A is now done; see F30.

- **Where:** `backend/app/routers/auth.py:132-135`. The signed cookie lasts 7 days
  (`backend/app/main.py:74`). Logout clears the browser's copy only.
- **Exploit:** A cookie copied before logout, from a shared computer or malware, keeps working
  until it expires, unless the person is deactivated (checked within 30 seconds).
- **Fix:** Option A: put a `session_version` in the cookie and on the Users row, and bump it on
  logout or "sign out everywhere". This costs one new Airtable field, added only. Option B:
  shorten the lifetime to 1 day and add an 8-hour idle timeout. B is simpler; A is stronger.

### F16. Note lookup without a launch skips the project check — Low

**Status: Fixed in commit `7d83c4c`.** Tests in `backend/tests/test_security_access.py`.

- **Where:** `backend/app/routers/links.py:71`. `check_project_access` runs only when
  `row.session_id` is set.
- **Exploit:** All notes are created on tasks today, so every note has a launch. A note row
  with no launch, typed in Airtable or left by a future feature, that is marked Shared could be
  deleted or reshared by a partner who knows its ID.
- **Fix:** Treat a note with no launch as not found for partners. Test: a partner gets 404 on
  such a note.

### F17. npm audit: react-router — Low

**Status: Fixed in commit `7d83c4c`.** Upgraded to `react-router-dom` 7.18.6, pinned exactly; no patched 6.x release exists. `npm audit`: 0 vulnerabilities. Checked in a browser that the home page renders and signed-out redirects still work. Checked by `npm audit` and the frontend build; there is no backend test for this one.

- **Result:** `npm audit` reports 2 moderate advisories, both from `react-router` 6.30.x (via
  `react-router-dom`): "Open redirect via backslash in `<Link>` and `useNavigate`" and
  "Arbitrary Constructor Injection via `deserializeErrors()` in SSR hydration". The affected
  range is 6.0.0 to 7.17.0.
- **Impact here:** Low. The app does no server-side rendering, and it never passes a
  user-controlled path to `<Link>` or `navigate()`. Every internal link is built from record
  IDs.
- **Fix:** Upgrade to a patched release when one exists for v6, or plan the move to v7. Then
  re-run `npm audit`.

### F18. Scans — Info

- **pip-audit** (2.x, run in a separate throwaway virtualenv against
  `backend/requirements.txt`): **No known vulnerabilities found.**
- **npm audit:** see F17. 0 high, 0 critical.
- **Secrets in git history:** gitleaks and trufflehog are not installed here. Instead I
  searched all 20 commits on all branches with regexes for Airtable PATs, Google client
  secrets (`GOCSPX-`), Google refresh tokens (`1//0`), Google API keys, private keys, and
  `SESSION_SECRET=`, `AIRTABLE_TOKEN=` and `GMAIL_REFRESH_TOKEN=` assignments. The only hits are
  the placeholders in `.env.example` and a test setting. No `.env` file was ever committed, and
  `.env` and `backend/.env` are gitignored. Running gitleaks in CI is still recommended
  (see Manual steps).
- **Frontend bundle:** no `import.meta.env` use and no secret patterns in `frontend/dist`.

### F19. Checks that passed — Info

- **IDOR:** Every route that takes a project, task, link, file, note or reminder ID loads it from
  the cached world and checks access. Partner launch access goes through
  `check_project_access` or `_visible_task`. Task edits go through `can_edit_task`. Reminders are
  limited to the caller's own (`backend/app/routers/reminders.py`). Users, roles, templates,
  sites and archive are admin-only at router level. IDs in bodies are checked as well:
  `depends_on` must be tasks in the same launch, `role_ids` and `partner_ids` are filtered to
  existing records, and assignees must be existing active users. Unknown IDs answer 404.
- **Partner isolation:** Partners get 404 on other launches, tasks, files and notes. Internal
  notes and history are filtered out, `/api/users/directory` is refused, and the calendar feed
  uses the same filter. Partners do see staff names on tasks and the launch team list; that is
  by design.
- **Role changes:** Only admins can change access levels or Users rows. The level must be one
  of Admin, Staff, Viewer or Partner. An admin cannot demote or deactivate themselves, and the
  last Active Admin cannot be removed. Nobody can edit their own Users row except the calendar
  token. A changed level takes effect within 30 seconds, and the stored view is re-checked on
  every request.
- **Errors:** Unhandled exceptions return FastAPI's plain "Internal Server Error". Airtable and
  Gmail errors are reduced to the exception type or a written sentence before logging or
  returning. Validation errors echo only the caller's own input.
- **Project Lead:** removed from the app on 2026-11-19. Any Users row still set to it is
  treated as an unknown level: staff view, read only.

---

## New routes since the review (sponsor changes, 2026-11-20)

Added after F1 to F19 were fixed. Each one has a row in
`backend/tests/test_access_matrix.py` and its rule in `app/permissions.py`, and sits behind
the Origin check. The Delete route counts toward the per-person write limit (60 a minute);
Nudge has its own rule instead (20 an hour per admin), because the rate limiter applies the
first rule that matches. Reviewed in Phase 0 below (F20 to F24).

| Route | Who | What it can change | Notes |
|---|---|---|---|
| `POST /api/tasks/{id}/nudge` | Admin view (`can_nudge`) | Sends one email to each Active assignee; writes a Reminders row (Kind Nudge) per email and one History row (Type Nudge) | Body `message` up to 500 characters, HTML-escaped in the email, never stored or logged. Once per person per task per 24 hours (read from Reminders, so it survives restarts; answers 429). 20 per admin per hour (`rate_limit.py`, in memory). Respects `REMINDERS_DRY_RUN`. Refused on finished tasks and closed programs. Gmail errors are returned to the admin as the safe `EmailError` text |
| `GET /api/tasks/mine` (changed) | Anyone signed in | Nothing (read only) | New query parameters `state`, `city`, `program_type` (length-capped) and `sort` (`due`, `program` or `location` only). They only narrow the caller's own task list, filtered in Python. Filter choices are built from the caller's own tasks, so they never reveal other people's sites |
| `DELETE /api/tasks/{id}` | Admin view (`can_delete_tasks`) | Deletes one Work row. Writes a History row first, removes it from other tasks' Depends On, cancels its Scheduled custom reminders, moves its Links rows to the program | Refused (409) on closed programs. Cannot be undone; no Airtable-side recovery other than Airtable's own trash. The task's Google Calendar event (shared-calendar sync) is not removed |

## Phase 0 review of the sponsor features (2026-11-20)

Reviewed: Nudge, Delete task, the My Tasks filters and sort, the Overdue section on a
program's page, and the Launches to Programs wording. Status for each finding is **Open**
until it is fixed and its commit and tests are listed here.

### F20. Nudge has no limit per person across tasks — Medium (Fixed)

**Problem.** The once-a-day limit is per person *per task*, and the 20-an-hour cap is per
*admin*. Nothing limits how many nudges one person receives in total. One admin can nudge
the same person about 20 different tasks in an hour, and every other admin can do the same,
so a staff member or partner can be flooded with email by a careless or compromised admin
account. It also risks the Gmail sender being marked as spam.

**Fix.** `reminders.nudge_blocks` decides who can be nudged now. Besides once per task per
day, nobody gets more than `NUDGES_PER_PERSON_PER_DAY` (3) nudges in 24 hours, from any
admin about any task, counted from Sent Nudge rows in the Reminders table so it survives a
restart. People at the limit are skipped with a note in the success message; if everyone
on the task is blocked the route answers 429 saying when to try again.

**Tests** (`test_nudge.py`): a 4th nudge to one person in a day is refused with the time it
frees up; nudges recorded from other admins count; nudges over a day old and failed ones do
not; someone else on the same task is still nudged while the person at the limit is
skipped; the limit resets after 24 hours. The hourly-cap test now uses a different person
per task so it still tests only the admin cap. With the limit switched off, 4 of these
tests fail.

**Commit.** "Limit nudges to 3 a day per person across tasks (F20)".

### F21. Two nudges at the same moment can both send — Low (Fixed)

**Problem.** The route reads Reminders, decides who may be nudged, sends, and only then
writes the Reminders row. Two requests at the same moment (a double click, or two admins)
both pass the check before either writes, so the person gets the email twice. FastAPI runs
these routes on a thread pool, so this can really happen.

**Fix.** `reminders.NUDGE_LOCK` is held from reading the Reminders table until the new
rows are written. It is one lock for all nudges rather than one per task, so the
per-person daily limit from F20 (which spans tasks) is exact too; nudges are rare, so
waiting is fine. It works because the app runs as one Railway instance; the code comment
and README say a shared lock is needed if it is ever scaled out.

**Tests** (`test_nudge.py`): two nudges started together on separate threads, with email
sending slowed down, give one 200 and one 429 and send one email. With the lock replaced by
a no-op the test fails (both get 200 and two emails go out).

**Commit.** "Send one nudge at a time so a double click cannot email twice (F21)".

### F22. A failed Delete task can leave a half-done delete — Low (Fixed)

**Problem.** Delete writes the history entry, clears dependencies, cancels reminders, moves
links, and deletes the row last. If Airtable fails part way (an outage, or its rate limit),
the history says the task was deleted while the task still exists, possibly with its
dependencies already cleared and its reminders cancelled. The admin sees a generic 500.

**Fix.** The order stays (history first). The steps after it run inside one `try` in
`routers/tasks.py`; on any failure the app logs a warning with the task's record ID and the
error type only, adds a history entry "could not finish deleting the task ...", and answers
502 "The task was not fully deleted. Please try again." Every step is safe to run again, so
a retry finishes the job. If Airtable is too broken to write that second entry, the 502 is
still returned and the log line is the record. The user guide tells admins to click Delete
task again.

**Tests** (`test_delete_task.py`): with the final Airtable delete failing once, the response
is 502 with that message, the task still exists, and both history entries exist; trying
again succeeds and leaves no dependency or scheduled reminder pointing at the task; with
history writes failing too, the route still answers 502. Without the `try`, 3 of these
tests fail.

**Commit.** "Report a half-finished task delete and let a retry finish it (F22)".

### F23. `project` filter on My Tasks has no format or length limit — Info (Fixed)

**Problem.** The new filters are length-capped, but the older `project` parameter is not.
It is only compared with the caller's own tasks, so it cannot reveal anything, but it is
the one unvalidated input on the route.

**Fix.** `security.RECORD_ID_PATTERN` (`rec` then 1 to 24 letters or digits) is now the
pattern for `project` on `GET /api/tasks/mine`; anything else gets 422. Real Airtable IDs
are `rec` plus exactly 14 characters; the pattern also accepts shorter ones so the readable
IDs in the tests keep working. It is in `security.py` so other routes can reuse it.

**Tests** (`test_my_tasks_filters.py`): quotes, spaces, slashes, newlines, a missing `rec`
prefix and a 43-character value all get 422; a real-shaped ID gets 200 and a valid one
still filters. Without the pattern, 7 of these fail.

**Commit.** "Accept only record IDs in the My Tasks project filter (F23)".

### F24. Checks that passed (Phase 0) — Info

- **Admin checks.** Nudge and Delete use `require_admin` and then `permissions.can_nudge` or
  `can_delete_tasks`. Staff, viewers, partners and an admin in staff view get 403; signed
  out gets 401 (tests in `test_nudge.py`, `test_delete_task.py`, access matrix).
- **Object access.** Both load the task through `_visible_task`. Unknown IDs get 404.
- **Origin check.** Covers every POST, PUT, PATCH and DELETE under `/api/` and `/auth/`,
  so both new routes are covered.
- **Access matrix.** Rows exist for `POST /api/tasks/{task_id}/nudge` and
  `DELETE /api/tasks/{task_id}`; the matrix's every-route check passes.
- **Nudge recipients.** Only the task's own assignees whose Users row is Active. There is no
  way to pass an address or user ID in the request. The body is only `message`.
- **Nudge message.** Capped at 500 characters (422 above that), HTML-escaped by `_p` in the
  email (`<script>` test), and never stored in Airtable or written to logs (tests).
- **Nudge refusals.** Done and Skipped tasks, closed (archived) programs, and tasks with
  nobody Active get 409. Dry run sends nothing and writes nothing (test).
- **Delete task.** Refused on closed programs (archived programs are closed programs, status
  Complete). The history entry is written before the delete (test checks the order).
  Dependencies are cleared, Scheduled custom reminders are cancelled, and links move to the
  program (tests). Automatic reminders are worked out from existing tasks, so a deleted
  task gets none.
- **My Tasks filters.** The task list is the caller's own assigned tasks on programs they
  can see before any filter runs; filters only remove tasks. Filter choices come from that
  same list. `sort` accepts only three values; bad values get 422 (tests in
  `test_my_tasks_filters.py`, including other people's tasks never appearing).
- **Overdue section.** Built from the same task list the page already returned, so it shows
  nothing new to anyone.
- **Programs wording.** Text only. No routes, permissions or data changed.

Known and documented, not a finding: a deleted task's event on the shared Google Calendar
is not removed by the app (admin runbook says to remove it by hand).

## Phase 1: browser-side protection (2026-11-20)

### F25. Nowhere to collect CSP violation reports — Low (Fixed)

**Problem.** The Content-Security-Policy was in report-only mode, but browsers had nowhere
to send their reports, so the only way to see what it would block was to open the
developer console on each page. Without reports there is no evidence that enforcing it is
safe, and no warning if someone later manages to inject a script.

**Fix.** `POST /api/security/csp-report` (`routers/security_reports.py`) takes both formats
browsers use: the older report-uri one (`application/csp-report`, `{"csp-report": {...}}`)
and the Reporting API one (`application/reports+json`, a list). `security.parse_csp_reports`
keeps only three cleaned values per report and logs one line: the directive (plain
directive names only), what was blocked (only the site, such as `https://evil.example`, or
a keyword such as `inline`), and the page path (no query string, calendar tokens redacted,
control characters removed). Names, emails, query strings, full URLs and code samples are
never logged. Limits: 64 KB body (`request_limits.py`), 20 reports per request, 30 requests
a minute per address (`rate_limit.py`). It is exempt from the Origin check
(`security.ORIGIN_CHECK_EXEMPT`) because browsers may send reports without an Origin header
and the route changes nothing. The policy now ends with `report-uri` and `report-to`, and a
`Reporting-Endpoints` header names the endpoint.

**Tests** (`test_csp_reports.py`, access matrix row): both formats produce the expected
single log lines; emails, tokens, query strings, blocked script names and code samples never
appear in the log; newlines, escape codes and odd values are replaced; requests without or
with a foreign Origin are accepted while other routes still refuse a foreign Origin; bad
JSON, other shapes and other content types get 400; over 64 KB gets 413; only 20 reports per
request are logged; the 31st request in a minute gets 429; nothing is written to Airtable;
the policy and `Reporting-Endpoints` header point at the endpoint in both CSP modes and are
absent when CSP is off.

**Commit.** "Collect CSP violation reports (F25)".

### F26. CSP could be tighter in production, and nothing stopped it being widened — Low (Fixed)

**Problem.** The policy was already close to the minimum, and the fonts were already
self-hosted (Bricolage Grotesque and Figtree, SIL Open Font License 1.1, which allows
bundling them with the app as long as the license goes with them; both license files are
in `frontend/public/fonts` and the build copies them out). Two gaps were left: production did
not send `upgrade-insecure-requests`, and no test pinned the policy, so a later change could
quietly add a host or `'unsafe-inline'`.

**Fix.** `security.content_security_policy(production)` builds the policy from
`CSP_DIRECTIVES`, each with a comment saying why it is there, and adds
`upgrade-insecure-requests` in production only (on `http://localhost` it would break every
request). Checked against the built app: `dist/index.html` has no inline scripts or styles,
the only `data:` image is the drop-down arrow, and no page shows images from Airtable or any
other site (files open through the `/api/links` redirect), so `img-src` needs no other hosts.

**Tests** (`test_csp_policy.py`): the policy is exactly the expected list locally, and that
list plus `upgrade-insecure-requests` in production; no `'unsafe-inline'`, `'unsafe-eval'`,
wildcards, `blob:` or Google Fonts hosts, and Google sign-in is the only other site named;
`index.html` has no inline code and loads nothing from other sites; stylesheets load fonts
only from `/fonts` and both license files exist; the frontend source never uses `eval`,
`new Function`, `dangerouslySetInnerHTML` or fetches another site. Without the production
directive, 2 of these fail.

**Commit.** "Pin the CSP to the minimum and upgrade requests in production (F26)".

### F27. No cross-origin isolation headers, and the Server header names uvicorn — Low (Fixed)

**Problem.** Answers did not send `Cross-Origin-Opener-Policy` or
`Cross-Origin-Resource-Policy`, so another site could keep a handle on an app window it
opened, or load the app's responses into its own pages (the basis of some side-channel
attacks such as Spectre-style reads). Uvicorn also sent `server: uvicorn`, telling visitors
what software to look up vulnerabilities for.

**Fix.** `SECURITY_HEADERS` in `security.py` adds `Cross-Origin-Opener-Policy: same-origin`,
`Cross-Origin-Resource-Policy: same-origin` and `X-Permitted-Cross-Domain-Policies: none` to
every answer, errors included. Sign-in uses full-page redirects, not popups, so the opener
policy breaks nothing; Google Calendar reads the feed from its own servers, which the
resource policy does not affect. The Dockerfile now runs uvicorn with `--no-server-header`.
`Cross-Origin-Embedder-Policy` is not added: the app needs nothing it would unlock, and it
would make every cross-origin resource opt in. Railway's proxy may add its own
`server: railway-edge`, which reveals nothing about the app.

**Tests** (`test_cross_origin_headers.py`): the three headers are on API answers, 401s,
404s, the frontend, a refused cross-site request and a 413; no embedder policy; the
Dockerfile's single `CMD` has `--no-server-header`; the real app under uvicorn sends no
`server` header with that setting and does send `server: uvicorn` without it, which shows
the check works. The browser test (F28) runs every page with these headers on.

**Commit.** "Add cross-origin isolation headers and drop the Server header (F27)".

### F28. The CSP was only reported, never enforced, and nothing tested it in a browser — Medium (Fixed)

**Problem.** `CSP_MODE` defaulted to `report-only`, so browsers only warned and blocked
nothing: an injected script would still have run. Moving to `enforce` was a manual step
("click through the live site with the console open"), with nothing to catch a page the
policy breaks.

**Fix.** A Playwright browser test (`frontend/e2e/csp.spec.ts`, `@playwright/test` pinned
to 1.64.1 as a dev dependency only; it is the standard tool for this and there is no
reasonable hand-written alternative) builds the app and runs it with `CSP_MODE=enforce`
through `backend/tests/e2e_server.py`, which serves the built frontend on the in-memory
fake Airtable from the backend tests, so real data, Google and Gmail are never touched.
Three servers run, signed in as an admin, a staff member and a partner through
`DEV_LOGIN_EMAIL`. The test visits every page each can reach, opens the Nudge and Delete task
dialogs (reaching the task from Assignments, then a person, as admins do), uses every My
Tasks filter and sort, checks the choices go into the address and survive a refresh, and
checks staff do not see the admin buttons. It fails on any CSP violation, console error,
uncaught error, failed request or HTTP error, checks each page carries the enforced
header, and checks both self-hosted fonts load. With that passing, `enforce` is now the
default in `config.py` and `.env.example`; `report-only` stays as an opt-in for trying a
policy change on the live site.

**Tests.** `npm run test:e2e` (3 tests, all pass). With `font-src 'none'` put into the policy
the test fails, so it does catch violations. Backend: CSP is enforced by default, the
setting's default is `enforce`, and `report-only` still works when chosen. The shared
header check in `test_security_requests.py` now expects the enforced header.

**Manual step.** If Railway has `CSP_MODE=report-only` set, remove it or set it to
`enforce`, then redeploy.

**Commit.** "Test every page under an enforced CSP and enforce it by default (F28)".

### F29. The session cookie could be replaced from another subdomain — Low (Fixed)

**Problem.** The production cookie `nmu_session` was Secure, HttpOnly and SameSite=Lax, but
a plain name lets a page on a sibling subdomain (any other app on `*.up.railway.app`, or a
future NMU subdomain) set a cookie with the same name for the parent domain. That can
force a visitor into a session of the attacker's choosing (session fixation) or knock them
out.

**Fix.** In production the cookie is `__Host-nmu_session` (`security.session_cookie_name`).
Browsers only accept a `__Host-` cookie that is Secure, has `Path=/` and no Domain, and only
from the host itself, so no other subdomain can set it. `security.session_cookie_options`
gives SessionMiddleware the name, `Path=/`, SameSite=Lax and Secure in production, and
`main.py` uses it. Localhost keeps `nmu_session` without Secure so http development works.
The switch signs everyone out once: the old cookie is no longer read, and
`security.RetireOldSessionCookie` deletes it (`Max-Age=0`) the next time a browser sends it
in production. The privacy page and threat model name the new cookie.

**Tests** (`test_session_cookie.py`): the production cookie starts with
`__Host-nmu_session=` and is Secure, HttpOnly, SameSite=Lax, `Path=/` with no Domain; the
local one is `nmu_session` without Secure; the app still signs in locally; in production a
request carrying the old cookie gets it deleted, one carrying only the new cookie does not,
and localhost never deletes it; a validly signed old cookie signs nobody in under the new
name. The browser test still passes.

**Manual step.** After deploying, everyone signs in again once. Tell staff and partners
beforehand.

**Commit.** "Use a __Host- session cookie in production (F29)".

## Phase 2: sessions and accounts (2026-11-20)

### F30. A copied session could not be ended on the server — Medium (Fixed)

**Problem.** F15, option A. The session is a signed cookie, so signing out only cleared the
browser's copy. A cookie copied from a shared computer, a lost laptop or malware kept working
for up to 7 days. Admins had no way to end someone's sessions short of deactivating them,
and a change of access level or roles did not end sessions opened under the old ones.

**Fix.** A **Session Version** number on each Users row (blank counts as 0, so nobody was
signed out by the upgrade). Sign-in copies it into the cookie; `current_user` compares the two
on every request through the existing cached Users lookup, before the cookie is refreshed, and
answers 401 if the row's number is higher. All rules are in `app/auth/revocation.py`. The number
goes up when:

- the person clicks **Sign out of all devices** (new `POST /auth/logout-everywhere`, POST only,
  Origin-checked; only a still-valid session can use it, so an ended copy cannot keep signing
  its owner out);
- an admin clicks **Sign out everywhere** in the person's Edit dialog (new
  `POST /api/users/{id}/sign-out-everywhere`, admin only via `permissions.can_sign_out_others`,
  written to the history);
- an admin deactivates them, removes their access, changes their access level, removes a role
  from them, or erases their personal details. Adding a role or renaming does not sign them out.

The Users cache is updated on write, so it takes effect on the next request on this instance.

**Airtable.** New field **Users > Session Version** (Number, no decimals), added by
`python -m jobs.migrate_airtable --apply` (it only adds). Added to the shared test/production
base on 2026-11-20. The app writes it; nobody should edit it by hand.

**Tests** (`test_session_revocation.py`, access matrix rows): signing out of all devices ends a
second device's session and raises the number; signing in again works; other people stay signed
in; an ended cookie cannot raise it again; a signed-out visitor writes nothing; GET and a foreign
Origin are refused; an admin's sign-out ends the person's session, not the admin's, and is in
the history; staff, viewers and partners get 403; unknown person 404; a new access level or a
removed role ends sessions; an added role or a rename does not; deactivating, removing access
and erasing raise the number; a blank number keeps existing sessions working; a number set in
Airtable ends older cookies; unit tests for the rules. With the check disabled, 7 fail.

**Commit.** "Sign people out everywhere with a Session Version (F30)".

### F31. Changing view kept the same session — Low (Fixed)

**Problem.** ASVS asks for a new session whenever someone's powers change. Sign in already
started from an empty session, but switching between admin and staff view (allowed on
localhost and staging only; production refuses `DEV_ALLOW_VIEW_SWITCH`) only rewrote one key,
so any other data in the session, such as leftover Google sign-in state, carried over.

**Fix.** `auth/session.regenerate_session` keeps only the four keys a signed-in session needs
(who the person is, their view, and the sign-in and last-seen times), drops everything else,
and sets a new random session ID (`sid`, 16 random bytes), so the cookie is always a new value.
It runs at every sign in and after every allowed view switch. The 7-day limit still counts
from sign in. A signed cookie cannot be cancelled on the server, so older copies are ended by
Session Version (F30), which changes of access level and roles already raise.

**Tests** (`test_session_regeneration.py`): only the kept keys survive and the ID changes;
each sign in gets a new ID; a view switch gives a new cookie and ID with the same user and
sign-in time and still works; a refused switch changes nothing; the ID is not sent to the
page. With the call removed from the view switch, the view switch test fails.

**Commit.** "New session at sign in and on view switch (F31)".

### F32. The domain rule trusted the email alone — Low (Fixed)

**Problem.** With `ALLOWED_EMAIL_DOMAIN` set, sign in only checked that the email ended in
that domain. Anyone can create a personal Google account with a work address (a former
employee before their mailbox closes, for example), and Google marks that email verified.

**Fix.** `auth/google.email_allowed(email, hosted_domain)` now also requires Google's `hd`
(hosted domain) claim to equal the domain. Google only sends `hd` for accounts that the
organisation's Google Workspace manages. `/auth/login` passes `hd` to Google as a hint so the
work account is offered first; the callback is what enforces it. Nothing changes while the
setting is blank, which is how NMU runs today because partners sign in with their own
accounts. Local `DEV_LOGIN_EMAIL` sign in treats the address's own domain as its `hd`.

**Tests** (`test_hosted_domain.py`): a Workspace account gets in; a personal account with a
work address, another Workspace, and a wrong email with the right `hd` are refused; a blank
setting still allows personal accounts; case is ignored and subdomains do not match; the
sign-in redirect carries the hint; dev login still works. With the `hd` check removed, 5 fail.

**Commit.** "Require Google's hosted domain claim when a domain is set (F32)".

### F33. Some unsafe production settings were accepted silently — Low (Fixed)

**Problem.** Production already refused a weak `SESSION_SECRET`, `DEV_LOGIN_EMAIL` and the view
switch. It still started with an `http://` `APP_URL` or `FRONTEND_URL` (no encryption, and the
Secure `__Host-` cookie would never be sent back), with real email on but no Gmail settings
(every reminder fails quietly), with a bootstrap admin address that `ALLOWED_EMAIL_DOMAIN`
would never let in (a typo, or an address that should not be there), and gave no sign that
`BOOTSTRAP_ADMIN_EMAILS` was still set long after the first admin existed.

**Fix.** In `config.py`, `_refuse_unsafe_production_settings` refuses to start production
without `https://` for both addresses, or with `REMINDERS_DRY_RUN=false` and any of
`GMAIL_SENDER`, `GMAIL_REFRESH_TOKEN`, the client ID or the client secret missing; the error
names what is missing. `_refuse_bootstrap_outside_domain` refuses a bootstrap address outside
the domain, everywhere. `CSP_MODE` was already limited to its three values; it now has tests.
At startup, `auth.warn_if_bootstrap_not_needed` (in a background thread, so a slow Airtable
never delays startup) logs a warning, with no emails, when the bootstrap list is set and an
Active Admin exists. Local development is unchanged.

**Tests** (`test_production_settings.py`): a correct config starts; http for either address is
refused in production and allowed locally; unknown `CSP_MODE` values are refused; each missing
Gmail setting is refused when real email is on; the separate Gmail client counts; dry run and
localhost need none; bootstrap outside the domain is refused (also locally), inside or with no
domain it is fine; the warning appears with an Active Admin and logs no email, not before the
first admin or with an empty list, and Airtable being down only logs. Three older tests in
`test_security_settings.py` built production with localhost addresses; they now use https and
check the same things. With the new checks removed, 8 fail.

**Manual step.** Check that Railway's `APP_URL` and `FRONTEND_URL` start with `https://`, and
remove `BOOTSTRAP_ADMIN_EMAILS` there if the warning appears.

**Commit.** "Refuse unsafe production settings at startup (F33)".

## Phase 3: audit trail and monitoring (2026-11-20)

### F34. Admin actions left no trail that could not be changed — Medium (Fixed)

**Problem.** Admin actions (changing someone's access, erasing a person, deleting a program,
publishing a template) were only described in the project history, the Activity Log. That
table is meant to be edited: "Remove personal details" rewrites names in it, and admins can
delete notes. Nothing recorded who did what in a way that could not later be changed, and
many admin routes wrote no history at all.

**Decision.** A new **Audit Log** table rather than the Activity Log, because an audit trail
must never be rewritten, and the Activity Log has to be (erasure). The audit rows hold record
IDs only, so erasing someone never needs to touch them.

**Fix.** `app/audit.py`:
- `require_admin` marks the request with the admin's record ID.
- The `AuditTrail` middleware writes one row after every **successful** (status below 400)
  POST, PUT, PATCH or DELETE that was marked: method and route
  (`PATCH /api/users/{user_id}`), the admin's ID, the record IDs from the address, the status,
  the time (UTC) and the request ID. Never the body, names or emails. The row is written
  after the answer, so the admin does not wait.
- Routes that turn out to change nothing call `audit.nothing_changed`: the new-program
  preview, the Day 1 move preview and a nudge in dry run mode.
- **Append only:** `client.APPEND_ONLY_TABLES` makes `update_records` and `delete_records`
  refuse the Audit Log before any request to Airtable. (Airtable itself cannot enforce this:
  a base editor can still change rows by hand. Limit who has editor access to the base.)
- If Airtable refuses the row, the action stands and an `audit_write_failed` security event
  (ERROR) carries the same details in the server log, so the log is the backup copy.
- Every admin action also writes an `admin_action` security event (`app/security_events.py`).

**Airtable.** New table **Audit Log** (Action, When, Actor ID, Target, Status Code, Request
ID), added by `python -m jobs.migrate_airtable --apply`. Created in the shared base on
2026-11-20 (only the table; the migration's other pending items were left alone). It grows by
one row per admin change. Check the plan's record limit per base once a year; export old rows
to CSV before any clean-up rather than deleting them through the app.

**Tests** (`test_audit.py`, and `test_every_admin_change_is_audited` in the access matrix,
which runs every admin-only change in the matrix, so a new admin route is covered
automatically): one row with the right action, actor, target, status, request ID and time;
no names, emails or body text; reads, refusals, failures and staff changes leave no row; the
three no-change calls leave none and their real versions leave one; a failed audit write
keeps the action and logs `audit_write_failed`; edits and deletes are refused by the fake and
by the real client; erasure does not touch the table. With the write removed, 32 fail.

**Commit.** "Append-only audit trail of admin actions (F34)".

### F35. Admins could not see the audit trail — Low (Fixed)

**Problem.** The Audit Log is only useful if someone reads it, and NMU admins should not need
Airtable access to do so (fewer base editors also protects the trail, see F34).

**Fix.** A read-only **Audit** page for admins (`/audit`, in the admin menu), backed by
`GET /api/audit` (`routers/audit_log.py`, admin only). Newest first, the last 30 days by
default, filterable by admin and period (7 days to everything), at most 500 entries with a
note when there are more. Names are looked up when the page is read, so audit rows keep only
IDs and an erased person shows as "Former team member". Actions show in plain words
(`audit.ACTION_LABELS`), with the route and request ID on hover. The filters are validated
(`actor` must be a record ID, `days` 1 to 3660). There is no route that changes or deletes
audit rows: any other method on `/api/audit` is 405. Reading the page is not itself audited.

**Tests** (`test_audit_page.py`, the access matrix and the browser test): newest first with
names; task and program names, and IDs kept for deleted records; the period and admin
filters; bad filters 422; erased people shown as "Former team member"; rows without a valid
time skipped; the 500 cut-off flagged; POST, PUT, PATCH and DELETE are 405; reading writes
nothing; admin only (matrix); the page loads under the enforced CSP and shows a seeded entry.

**Commit.** "Read-only Audit page for admins (F35)".

### F36. Logs were hard to search and security events were not marked — Low (Fixed)

**Problem.** Logs were plain text from `logging.basicConfig`, with uvicorn's lines in a second
format. There was no way to filter for security events (refused sign ins, 403s, rate limits,
revoked sessions) or to follow one request through the log, and no guide saying what to watch.
A message with a line break could look like two log lines.

**Fix.**
- `app/logging_setup.py`: in production every line, the app's and uvicorn's, is one JSON
  object (time in UTC, level, logger, message, and the exception on the same line). Locally,
  plain text. Line breaks inside a message stay inside the JSON string.
- Every line written during a request has its `request_id` (a context variable set by
  `RequestContext`, which follows sync routes onto their worker thread), the same ID as the
  `X-Request-ID` header and the Audit Log row.
- `app/security_events.py`: `security_event(name, **fields)` writes one event with cleaned
  one-line values (at most 200 characters). Events: `sign_in`, `sign_in_denied` (with a
  reason and a masked email), `sign_out`, `sign_out_everywhere`, `session_revoked`,
  `session_ended_inactive_user`, `session_expired`, `access_denied` (403), `rate_limited`
  (429), `request_too_large` (413), `csp_violation`, `admin_action`, `audit_write_failed`,
  `bootstrap_admins_still_set`, `unexpected_error`. 401s are not events: every signed-out
  visit makes one. Refusals carry the declared route, the user's record ID and the client
  address.
- `docs/security/monitoring.md`: where the logs are, every event, when to act, five alerts to
  set up in Railway, and a monthly review of the audit trail.

**Tests** (`test_security_logging.py`): JSON lines are valid and single-line, including line
breaks and exceptions; the request ID is added during a request and cleared after, also in a
sync route; event fields become JSON fields without replacing the basic ones; uvicorn's
loggers go through the same handler and keep the token redaction; values are cleaned; each
event above fires with the right fields; emails are masked; signed-out 401s are not events;
CSP events keep query strings out; the session cookie never reaches the log. With the refusal
events removed, 3 fail; with the request ID not set, 1 fails.

**Manual step.** Set up the alerts in `monitoring.md` on Railway.

**Commit.** "JSON logs with request IDs and security events (F36)".

## Phase 4: least privilege (2026-11-20)

### F37. The app's Airtable token could change the base's structure — Medium (Fixed)

**Problem.** The README told people to give the app's one Airtable token four scopes,
including `schema.bases:write`, because the migration script used the same token. Anyone
holding the production token (from a leaked Railway variable or a log) could add, rename or
delete fields and tables, which would break the app and could destroy data. The reminder cron
service was told to copy every variable from the web service, including ones it never uses.

**Fix.**
- The app's `AIRTABLE_TOKEN` needs only `data.records:read` and `data.records:write`
  (README, `.env.example`).
- `client.migration_base()` opens the base with a new `AIRTABLE_MIGRATION_TOKEN`, a separate,
  short-lived token with the schema scopes. `jobs.migrate_airtable` and `jobs.dump_schema`
  use only it: without it, or with the app's own token in it, they stop and say why.
- Production refuses to start with `AIRTABLE_MIGRATION_TOKEN` set: it is for a laptop only.
- In production, a background check at startup (`client.warn_if_token_too_broad`) tries one
  harmless read of the base's structure. Airtable does not report a personal token's scopes,
  so this is the way to tell; if it works, an `airtable_token_too_broad` security event says
  the token has more than it needs.
- Gmail: `jobs.authorize_gmail` already asked only for `gmail.send` (a leaked refresh token can
  send mail but not read the inbox); a test now keeps it that way.
- The README lists exactly which variables the cron service needs, and gives it its own
  `SESSION_SECRET`, so a leak from that service cannot forge web sign ins.

**Tests** (`test_least_privilege.py`): both scripts refuse without a migration token and with
the app's token; `migration_base` uses the migration token; production refuses it and a
laptop allows it; the startup check reads 403 and 401 as narrow, a successful read as too
broad, and other errors as unknown; the warning names no token; Gmail asks only to send.
With the same-token refusal removed, 2 fail.

**Manual steps.**
1. In Airtable, create a new token for the app with only `data.records:read` and
   `data.records:write` and the NMU base, from an NMU-owned account. Put it in Railway's
   `AIRTABLE_TOKEN` (web and cron), redeploy, check the app works, then delete the old
   four-scope token.
2. Give the cron service only the variables in the README table, with its own `SESSION_SECRET`.

**Commit.** "Least-privilege Airtable token and a separate migration token (F37)".

## Phase 5: CI and supply chain (2026-11-20)

### F38. The example settings named a real admin, and stray files were in git — Medium (Fixed)

**Problem.** `.env.example`, the file everyone copies to set up a server, had
`BOOTSTRAP_ADMIN_EMAILS` and `GMAIL_SENDER` set to a developer's personal Gmail address. An
NMU maintainer copying it to Railway would make that personal account an Admin on first
sign in. Git also tracked three macOS `.DS_Store` files (they list folder contents),
`frontend/tsconfig.tsbuildinfo` (build output) and `.claude/launch.json`, a teammate's local
editor settings with their home folder path.

**Fix.** Both settings are blank in `.env.example`, with a note to remove the bootstrap list
once used. The test data uses `example.org` addresses. The five files are removed from git
(they stay on disk) and `.gitignore` now covers `.DS_Store`, `*.tsbuildinfo`,
`.claude/launch.json` and `.claude/settings.local.json`. They remain in old commits; nothing
in them is a secret, so the history was not rewritten.

The README and the admin runbook still name that address on purpose, as the current owner of
the Google Cloud project and the Gmail sender; the runbook's handoff table says what replaces
it.

**Tests** (`test_repo_hygiene.py`): every secret, address and person setting is blank in
`.env.example`; it contains no email address outside `example.org`/`example.com`; git tracks no
`.DS_Store`, `.tsbuildinfo`, `.env`, key, credential or editor-settings files. Against the old
`.env.example`, 3 fail.

**Commit.** "Remove a real address from .env.example and stray files from git (F38)".

### F39. Dependencies were not locked to exact files — Medium (Fixed)

**Problem.** `requirements.txt` pinned only the top-level Python packages; everything they
depend on floated, and nothing checked that a downloaded file was the one that was tested. A
compromised or replaced release on PyPI would have gone straight into the image. pytest and
the Gmail setup library were installed on the server. Five npm devDependencies used `^`
ranges.

**Fix.**
- `backend/requirements.in` (runtime) and `requirements-dev.in` (tests and tools) list exact
  top-level versions. `uv pip compile --universal --generate-hashes` turns them into
  `requirements.txt` and `requirements-dev.txt`: every package, including indirect ones, at an
  exact version with its SHA-256 hashes, valid on Windows, Mac and Linux.
- The Dockerfile installs `requirements.txt` with `--require-hashes --no-deps`, so any file
  that does not match fails the build. Test tools and `google-auth-oauthlib` (laptop only) are
  no longer in the image.
- `package.json` uses exact versions; `frontend/.npmrc` has `save-exact=true`; builds use `npm ci`.
- The README explains how to update dependencies.

**Tests** (`test_dependency_pins.py`): every `.in` line is `name==version`; every lock entry has
hashes; the runtime lock matches the `.in` pins; no test tools in the runtime lock; the
Dockerfile uses `--require-hashes` and `npm ci`; npm versions are exact and match the lock.
Against the old `package.json`, the npm test fails. The image builds with the hash check,
imports the app, and contains no pytest or Google OAuth library.

**Commit.** "Hash-locked Python dependencies and exact npm pins (F39)".

## Manual steps outside the code

1. **Airtable:** make sure the production token is a personal access token scoped to this one
   base, with only `data.records:read`, `data.records:write` and `schema.bases:read`. Review who
   has edit access to the base; they bypass the app's permissions (see F7).
2. **Google Cloud:** publish the OAuth app so the Gmail token stops expiring weekly. Use a
   separate Desktop client for Gmail (see project notes). Move the sender to an NMU-owned
   account instead of a personal Gmail.
3. **Railway:** confirm `ENV=production` and `DEV_ALLOW_VIEW_SWITCH` unset or false on *both*
   services; restrict who can read logs; after F3 is fixed, consider resetting calendar feed
   tokens that may already be in logs (each person can do it from the app).
4. **GitHub:** turn on secret scanning and Dependabot alerts; add gitleaks to CI.
5. **Domain:** a custom domain removes the shared-`railway.app` question in F9 and allows HSTS
   preload later.

## Prioritized fix order

All three batches are done. F9 is closed. Still open: switching the CSP from report-only to enforce (F1), and server-side session cancelling (F15, Option A). Commits: batch 1 `3ae3248`, batch 2 `39baf62`, batch 3 `7d83c4c`.

1. ~~**F4**~~ (fixed) Refuse `DEV_ALLOW_VIEW_SWITCH` in production. A few lines, and it closes the only
   one-setting path to admin.
2. ~~**F2**~~ (fixed) Turn off `/docs`, `/redoc` and `/openapi.json` in production. One line.
3. ~~**F12**~~ (fixed) Treat an `https://` `APP_URL` as production for the secret and cookie checks. A few
   lines; makes F4 and the existing checks hard to switch off by accident.
4. ~~**F3**~~ (fixed) Redact calendar tokens and OAuth codes in access logs. Then reset any tokens already
   logged.
5. ~~**F6**~~ (fixed) Request size limit middleware. Stops a signed-out disk-filling attack.
6. **F1** (HSTS done; CSP report-only, switch to enforce after checking the console) Add HSTS and CSP. Test the CSP against the built frontend before deploying.
7. ~~**F7**~~ (fixed) Return only `https://` URLs from the API, plus a `safeHref` check in the frontend.
8. **F14** then **F5**. Proxy headers first, so the limiter sees real client IPs, then rate
   limits.
9. **F8**. POST-only logout. (F9 closed.)
10. **F13** Mask emails in logs.
11. **F10** Check file signatures against extensions.
12. **F11**, **F15**, **F16**, **F17**. Author-or-admin note sharing, session revocation, small
    fix, and the react-router upgrade.
