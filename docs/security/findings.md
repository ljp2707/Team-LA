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

### F15. Sessions cannot be revoked — Low

**Status: Mitigated in commit `7d83c4c`.** Sessions now end after `SESSION_IDLE_HOURS` without use (default 24) and 7 days after sign in, however active. Before, the cookie lifetime renewed on every request, so an active session never ended. Logout still cannot cancel a copied cookie on the server; that needs Option A (a session version on the Users row), not done. Tests in `backend/tests/test_security_access.py`.

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

### F20. Nudge has no limit per person across tasks — Medium (Open)

**Problem.** The once-a-day limit is per person *per task*, and the 20-an-hour cap is per
*admin*. Nothing limits how many nudges one person receives in total. One admin can nudge
the same person about 20 different tasks in an hour, and every other admin can do the same,
so a staff member or partner can be flooded with email by a careless or compromised admin
account. It also risks the Gmail sender being marked as spam.

**Proposed fix.** A limit per recipient across all tasks and all admins (proposed: 3 nudges
per person per 24 hours), counted from the Reminders table like the per-task limit, so it
survives a restart. People already at the limit are skipped with a clear message, and the
route answers 429 if everyone is. The logic goes in `services/reminders.py` next to
`recent_nudges`.

**Tests.** Nudging one person about a 4th task within a day is refused; a different person
on the same task is still nudged; the limit counts nudges from every admin; it resets after
24 hours.

### F21. Two nudges at the same moment can both send — Low (Open)

**Problem.** The route reads Reminders, decides who may be nudged, sends, and only then
writes the Reminders row. Two requests at the same moment (a double click, or two admins)
both pass the check before either writes, so the person gets the email twice. FastAPI runs
these routes on a thread pool, so this can really happen.

**Proposed fix.** A lock held from the check through the write, one per task, in
`services/reminders.py`. This works because the app runs as one Railway instance; the code
comment and README will say a shared lock is needed if it is ever scaled to several.

**Tests.** Two nudges started together on separate threads send one email and get one 200
and one 429.

### F22. A failed Delete task can leave a half-done delete — Low (Open)

**Problem.** Delete writes the history entry, clears dependencies, cancels reminders, moves
links, and deletes the row last. If Airtable fails part way (an outage, or its rate limit),
the history says the task was deleted while the task still exists, possibly with its
dependencies already cleared and its reminders cancelled. The admin sees a generic 500.

**Proposed fix.** Keep the order (history first, as required). If a later step fails, write
a second history entry saying the delete did not finish, and answer 502 with "The task was
not fully deleted. Please try again." Every step can safely run again, so a retry finishes
the job.

**Tests.** With the final Airtable delete made to fail: the response is 502 with that
message, both history entries exist, and a retry succeeds and leaves no dependencies or
scheduled reminders pointing at the task.

### F23. `project` filter on My Tasks has no format or length limit — Info (Open)

**Problem.** The new filters are length-capped, but the older `project` parameter is not.
It is only compared with the caller's own tasks, so it cannot reveal anything, but it is
the one unvalidated input on the route.

**Proposed fix.** Require the shape of an Airtable record ID (`rec` and 14 letters or
digits); anything else gets 422. No route checks this shape yet, so this adds one shared
pattern that later routes can reuse.

**Tests.** A malformed or very long `project` value gets 422; a valid one still filters.

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
