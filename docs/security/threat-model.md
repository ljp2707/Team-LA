# NMU Launches threat model

Reviewed 2026-11-19 against the code in this repo and the live deployment at
`https://team-la-production.up.railway.app` (read-only requests only). No code was changed.
Concrete issues are in [findings.md](findings.md); this file explains what we protect, from
whom, and where an attacker could get in.

## 1. What the app is

- **Backend:** FastAPI (`backend/app`), served by uvicorn in one Docker image on Railway. It also
  serves the built React app.
- **Database:** Airtable, through one personal access token. Reads are cached in memory for
  about 30 seconds (`app/airtable/client.py`).
- **Sign-in:** Google OAuth (authlib). The Airtable Users table decides who gets in. The session
  is a signed cookie (`nmu_session`, Starlette `SessionMiddleware`).
- **Email:** Gmail API, using a refresh token for one sender account.
- **Cron:** the same image runs `python -m jobs.send_reminders` on a schedule.

## 2. Assets

| Asset | Where it lives | Why it matters | Sensitivity |
|---|---|---|---|
| Airtable data: staff and partner names, emails, phone numbers, notes (Internal and Shared), task history, uploaded files | Airtable base; files on Airtable's CDN | Personal data of staff and partner organisations. Internal notes must never reach partners | High |
| Airtable token (`AIRTABLE_TOKEN`) | Railway variables, local `.env` | Full read and write on the base, with no app permission checks | Critical |
| Google OAuth client secret (`GOOGLE_CLIENT_SECRET`, possibly reused for Gmail) | Railway, `.env` | Lets someone impersonate the app to Google | High |
| Gmail refresh token (`GMAIL_REFRESH_TOKEN`) | Railway, `.env` | Send email as the sender account, to anyone | High |
| `SESSION_SECRET` | Railway, `.env` | Anyone who has it can forge a signed-in session as any user, including an Admin | Critical |
| Calendar feed tokens | Users table, `Calendar Feed Token` field; in each person's calendar app | Anyone with the link can read that person's open tasks, due dates and launch names | Medium |
| Session cookies | Users' browsers | A stolen cookie is a signed-in session for up to 7 days | High |
| Availability of the Airtable base | Airtable | Airtable allows 5 requests per second per base and locks the base for 30 seconds when that is exceeded | Medium |

## 3. Users and trust levels

| Actor | Trust | What they can do (from `app/permissions.py`) |
|---|---|---|
| Signed-out visitor | Untrusted | Home page, `/api/public/*`, `/api/health`, start Google sign-in, any calendar feed whose token they hold |
| Partner | Low. External organisation | Partner view only. Sees only launches where they are in Partner Access. Updates only their own tasks. Sees only Shared notes. No history, directory or archive |
| Viewer | Low. Internal, read only | Staff view. Sees every launch and task, changes nothing (`require_can_edit` refuses) |
| Staff | Medium. Internal | Sees every launch. Changes status, notes, links, files and reminders only on tasks assigned to them |
| Project Lead | No longer an access level (removed 2026-11-19). Airtable may still list it as an option. Anyone set to it is treated as an unknown level, which means read only | Same as Viewer |
| Admin | High | Everything, including users, roles, templates, launches, archive and exports. Can switch to staff view. Cannot remove their own admin access, and the last Active Admin cannot be removed |
| Cron job | High. Same image and same secrets as the web app | Reads everything, sends email, writes Reminders rows |
| Railway | Trusted platform | Holds every secret, terminates TLS, proxies traffic, keeps logs |
| Google | Trusted identity provider and mail transport | Says who someone is (`email_verified` is required); sends email |
| Airtable | Trusted data store | Holds all data. **Anyone with edit access to the base bypasses every app permission** |

Trust boundaries: browser ↔ Railway edge (TLS) ↔ uvicorn; uvicorn ↔ Airtable, Google and Gmail
over HTTPS with secrets; Google Calendar ↔ the public `.ics` feed; Airtable editors ↔ the app,
because values typed in Airtable are shown by the app.

## 4. Entry points

"Role" is the weakest role the route lets in. Object-level checks (for example, "only your own
task") are listed under Notes. "Changes data" means it writes to Airtable or sends email.
`current_user` = any Active signed-in user, partners included. `require_can_edit` = not Viewer.
`require_internal` = not Partner. `require_admin` = currently in admin view.

### 4.1 Sign-in, session and public routes

| Method | Path | Role | Changes data | Notes |
|---|---|---|---|---|
| GET | `/auth/login` | Anyone | Session only | Starts Google OAuth (state and nonce kept in the session). With `DEV_LOGIN_EMAIL` set it signs in without Google; config refuses that outside localhost |
| GET | `/auth/callback` | Anyone | Session; may create the first Admin row (`BOOTSTRAP_ADMIN_EMAILS`) | Needs `email_verified` and an Active Users row. Clears the session before signing in |
| GET | `/auth/denied` | Anyone | Session | Returns the refused email stored in the caller's own session |
| POST | `/auth/logout` | Anyone | Session | Signs out. POST only (findings F8) |
| GET | `/auth/logout` | Anyone | No | Old links: goes home without signing out |
| GET | `/api/health` | Anyone | No | Railway health check |
| GET | `/api/public/season-stats` | Anyone | No | Three counts for the home page, cached for 5 minutes |
| GET | `/api/public/about` | Anyone | No | Org name, contact email, address, app URL |
| GET | `/calendar/{token}.ics` | Anyone holding the token | No | Token is 32 random bytes, checked with a regex and then `hmac.compare_digest`. Unknown token → 404 |
| GET | `/docs`, `/redoc`, `/openapi.json`, `/docs/oauth2-redirect` | Anyone, local development only | No | Turned off in production (F2) |
| GET | `/{path}` | Anyone | No | Static frontend; path is resolved and must stay inside `static/` |

### 4.2 The signed-in user

| Method | Path | Role | Changes data | Notes |
|---|---|---|---|---|
| GET | `/api/me` | current_user | No | |
| POST | `/api/me/view` | current_user | Session | `can_choose_view`: partners stay partner; admin view needs Admin or `DEV_ALLOW_VIEW_SWITCH` (F4) |
| GET | `/api/me/calendar-feed` | current_user | No | Returns the caller's own feed URL |
| POST | `/api/me/calendar-feed` | require_can_edit | Yes (own Users row token) | New random token; the old link stops working |
| DELETE | `/api/me/calendar-feed` | require_can_edit | Yes (own Users row) | Viewers were allowed until the access matrix test found it |
| GET | `/api/users/directory` | current_user, not Partner | No | Names, levels and statuses of everyone |

### 4.3 Projects (launches)

| Method | Path | Role | Changes data | Notes |
|---|---|---|---|---|
| GET | `/api/projects` | current_user | No | Partners: only their launches. `status=closed` needs Admin |
| GET | `/api/projects/{id}` | current_user | No | `check_project_access` (partners get 404 for other programs). History hidden from partners; edit block admin only. Changed 2026-11-20: overdue tasks move into `overdue_tasks`, the same task list split differently, so nothing new is shown |
| GET | `/api/projects/{id}/history` | require_internal | No | |
| POST | `/api/projects/preview` | Admin | No | |
| POST | `/api/projects` | Admin | Yes; sends assignment emails | |
| PATCH | `/api/projects/{id}` | Admin | Yes | `partner_ids` filtered to existing users; Drive folder must be `https://drive.google.com/` |
| DELETE | `/api/projects/{id}` | Admin | Yes (deletes tasks, team, history, links, reminders) | |
| POST | `/api/projects/{id}/move-day-one` | Admin | Yes | |
| POST | `/api/projects/{id}/move-day-one/undo` | Admin | Yes | |
| POST | `/api/projects/{id}/tasks` | Admin | Yes; may send email | |
| POST | `/api/projects/{id}/close` | Admin | Yes | |
| POST | `/api/projects/{id}/reopen` | Admin | Yes | |
| POST | `/api/projects/{id}/links` | Admin | Yes | `https://` only |
| POST | `/api/projects/{id}/files` | Admin | Yes (Airtable attachment) | Multipart. Extension allowlist, 5 MB cap |
| GET | `/api/projects/{id}/export.csv` | Admin | No | Formula-injection safe (`services/export.py`) |

### 4.4 Tasks, notes, links, files, reminders

| Method | Path | Role | Changes data | Notes |
|---|---|---|---|---|
| GET | `/api/tasks/mine` | current_user | No | Own tasks on programs the caller can see. Changed 2026-11-20: optional `state` (max 50), `city` (max 100), `program_type` (max 200) and `sort` (`due`, `program` or `location` only) only narrow that list; filter choices come from the caller's own tasks |
| GET | `/api/tasks/{id}` | current_user | No | `_visible_task` (partner program check). Notes filtered by visibility. People list only for admins. Changed 2026-11-20: adds `can_delete` and `can_nudge` (admin view only) and `last_nudge` (hidden from partners) |
| PATCH | `/api/tasks/{id}` | require_can_edit | Yes | Status: only assignees (or Admin); Skip, due date, name and depends-on: Admin only |
| POST | `/api/tasks/{id}/nudge` | Admin | Yes; email | Open task, open program, Active assignees only. Once per person per task per day (from Reminders); 20 per admin per hour (its own rule, so it does not also count toward the 60 a minute write limit). Message escaped, not stored. See F20 and F21 |
| DELETE | `/api/tasks/{id}` | Admin | Yes (deletes) | Refused on closed programs. History row written first; dependencies cleared; scheduled reminders cancelled; links moved to the program |
| POST | `/api/tasks/{id}/assign` | Admin | Yes; email | Only existing, active users |
| POST | `/api/tasks/reassign` | Admin | Yes; email | All-or-nothing; open tasks on open launches only |
| POST | `/api/tasks/{id}/notes` | require_can_edit | Yes | Assignee or Admin. Partners' notes default to Shared |
| POST | `/api/tasks/{id}/links` | require_can_edit | Yes | Assignee or Admin; `https://` only |
| POST | `/api/tasks/{id}/files` | require_can_edit | Yes | Assignee or Admin; multipart; allowlist; 5 MB |
| POST | `/api/tasks/{id}/reminders` | require_can_edit | Yes (Reminders row for self) | Any task the caller can see; recipient is always the caller |
| GET | `/api/links/{id}/file` | current_user | No | Project access check, then 302 to Airtable's CDN |
| DELETE | `/api/links/{id}` | require_can_edit | Yes | Task link: assignee or Admin. Launch link: Admin |
| DELETE | `/api/notes/{id}` | require_can_edit | Yes | Admin any; author within 15 minutes |
| PATCH | `/api/notes/{id}` | require_can_edit | Yes (Internal ↔ Shared) | Not partners; the note's author or an Admin, who can also edit the task (F11) |
| GET | `/api/reminders/mine` | current_user | No | |
| DELETE | `/api/reminders/{id}` | require_can_edit | Yes | Only the caller's own custom reminders |

### 4.5 Admin-only setup

All of these use `require_admin`. Every one except the GETs changes data.

| Method | Path |
|---|---|
| GET, POST | `/api/templates` |
| GET, PATCH, DELETE | `/api/templates/{id}` |
| PUT, DELETE | `/api/templates/{id}/draft` |
| POST | `/api/templates/{id}/publish`, `/api/templates/{id}/duplicate`, `/api/templates/from-project` |
| GET | `/api/templates/{id}/versions`, `/api/templates/{id}/insights` |
| GET, POST | `/api/users` |
| PATCH, DELETE | `/api/users/{id}` (self-demotion, self-deactivation and zero-admin all refused) |
| GET | `/api/users/{id}/work` |
| POST | `/api/users/hand-off`, `/api/users/{id}/erase` (sends welcome email on POST `/api/users`) |
| GET, POST | `/api/roles`; PATCH `/api/roles/{id}` |
| GET | `/api/archive`, `/api/archive/{id}` |
| GET, POST | `/api/sites`; GET `/api/sites/{id}`; GET `/api/instructors` |
| GET | `/api/health/airtable`, `/api/health/auth` |
| POST | `/api/admin/test-email` (to the caller only) |

### 4.6 Not HTTP

| Entry point | Who | Notes |
|---|---|---|
| Cron `jobs.send_reminders` | Railway schedule | Same secrets as the web app. Prints recipient emails to its log (F13) |
| `jobs.authorize_gmail`, `jobs.migrate_airtable`, `jobs.seed_demo`, `jobs.dump_schema` | A developer's laptop | Need the real secrets in `.env` |
| Direct edits in Airtable | Anyone with base access | Not controlled by the app. Values typed there are rendered by the app (F7) |

**Checked automatically.** `backend/tests/test_access_matrix.py` has one row per route above, with the expected status for Admin, Admin in staff view, Staff, Viewer, a legacy "Project Lead" level, Partner and signed out. It fails if a route is added without a row, so a new route cannot ship without a permission decision.

## 5. Threats by entry point (STRIDE)

Ratings are for this deployment as it stands today, after the existing controls. **S**poofing,
**T**ampering, **R**epudiation, **I**nformation disclosure, **D**enial of service,
**E**levation of privilege.

### 5.1 Google sign-in (`/auth/login`, `/auth/callback`)

| | Threat | Existing control | Rating |
|---|---|---|---|
| S | Sign in as someone else with an unverified email | `email_verified` required; Users table must have an Active row | Low |
| S | Login CSRF (attacker's account forced on a victim) | authlib state in session; session cleared on sign-in | Low |
| S | Bootstrap admin email re-creates an Admin if its row is deleted | Only creates when no row exists for that email | Low |
| T | Session fixation | Session cleared before the user is stored | Low |
| R | No record of who signed in when | Nothing logged on success | Low |
| I | OAuth `code` and `state` written to the access log | Single use, short lived | Low |
| D | Repeated sign-in attempts hammer Airtable | Airtable cache; no rate limit (F5) | Medium |
| E | `DEV_LOGIN_EMAIL` in production | Config refuses unless `APP_URL` is `http://localhost` and not production | Low |

### 5.2 Session cookie and `/api/me/view`

| | Threat | Existing control | Rating |
|---|---|---|---|
| S | Forged cookie | HMAC-signed with `SESSION_SECRET` (32+ characters enforced in production) | Low |
| S | Stolen cookie reused after logout | Logout only deletes the browser copy; cookie valid up to 7 days. Deactivation takes effect within 30 seconds | Low (F15) |
| E | Staff or Viewer switches to admin view | Refused unless Admin, **or `DEV_ALLOW_VIEW_SWITCH=true`, which nothing stops in production** | Medium (F4) |
| E | Partner switches to staff view | Refused | Low |
| T | CSRF on state-changing routes | SameSite=Lax cookie; JSON bodies need `application/json` (FastAPI strict content type), which forces a CORS preflight; no CORS allowed. No Origin check | Low (F9) |
| T | Forced logout | `GET /auth/logout` works from any site | Low (F8) |

### 5.3 Projects and tasks (`/api/projects*`, `/api/tasks*`)

| | Threat | Existing control | Rating |
|---|---|---|---|
| E/I | IDOR: partner opens another launch's project, task, link or file by ID | `check_project_access` on project, task, link, file, note and history routes. Returns 404 | Low |
| E/T | IDOR: Staff changes a task not assigned to them | `can_edit_task` on status, notes, links, files, link removal and note sharing | Low |
| E | Staff edits due date, name, dependencies, or skips | Admin only | Low |
| I | Partner reads Internal notes or history | `visible_to`; history route is `require_internal` | Low |
| I | Staff shares someone else's Internal note with partners | Allowed when the Staff member is on the task | Low (F11) |
| I | Partner learns staff names via assignee labels and the team list | By design (names only, no emails) | Low |
| T | Stored XSS through a link URL | API accepts `https://` only. **URLs typed directly into Airtable are not checked** and no CSP | Medium (F7) |
| T | CSV formula injection in exports | Cells starting with `= + - @` are prefixed | Low |
| R | Who changed what | Activity Log row on every change | Low |
| D | Many writes exhaust Airtable's 5 requests/second | No rate limit | Medium (F5) |

### 5.4 File uploads (`POST /api/tasks/{id}/files`, `POST /api/projects/{id}/files`) and `GET /api/links/{id}/file`

| | Threat | Existing control | Rating |
|---|---|---|---|
| T | Script or HTML uploaded and run on the app's origin | Extension allowlist; files live on Airtable's CDN, not our origin | Low |
| T | File content does not match its extension (for example, an executable named `.pdf`) | None | Low (F10) |
| D | Very large upload fills disk or memory | 5 MB check runs only after the whole multipart body is parsed. **The body is parsed before authentication runs**, and there is no request size limit | Medium (F6) |
| I | Old file URL shared outside the app | Airtable URLs expire after a few hours; the app re-checks access on every open | Low |

### 5.5 Public calendar feed (`GET /calendar/{token}.ics`)

| | Threat | Existing control | Rating |
|---|---|---|---|
| S | Guess a token | 32 random bytes; format check; constant-time compare | Low |
| I | Token leaks through logs | **uvicorn's access log writes the full path, token included, to Railway logs** | Medium (F3) |
| I | Token leaks through caches or search engines | `Cache-Control: private`, `X-Robots-Tag: noindex` | Low |
| I | Feed shows tasks from launches the person may no longer see | Same partner filter as My Tasks | Low |
| D | Flooding the feed | Airtable reads are cached; no rate limit | Low |

### 5.6 Public home page stats and `/api/public/about`

| | Threat | Existing control | Rating |
|---|---|---|---|
| I | Personal data in public responses | Counts only; contact details are meant to be public | Low |
| D | Flooding | Stats cached for 5 minutes | Low |

### 5.7 Admin routes (users, roles, templates, archive, sites, health, test email)

| | Threat | Existing control | Rating |
|---|---|---|---|
| E | Non-admin raises their own access level or edits their own Users row | All user changes are `require_admin`; level must be in the `AccessLevel` list | Low |
| E | Admin locks everyone out | Self-demotion and zero-admin refused | Low |
| I | `/api/health/auth` reveals settings | Admin only; shows flags and the sender address, never secrets | Low |
| I | API structure published | `/docs`, `/redoc`, `/openapi.json` public in production | Medium (F2) |

### 5.8 Cron job and secrets

| | Threat | Existing control | Rating |
|---|---|---|---|
| I | Recipient emails in cron and dry-run logs | None | Low (F13) |
| I | Secrets committed to git | `.env` is gitignored; history scan found only placeholders | Low |
| E | Leaked Airtable token gives full base access | Token kept in Railway only | Medium (scope it; see findings, manual steps) |
| D | Gmail refresh token expires weekly (OAuth app in Testing) | Failures logged to Reminders | Medium (operational) |

### 5.9 Platform (headers, proxy, errors)

| | Threat | Existing control | Rating |
|---|---|---|---|
| T | XSS has no second line of defence | `nosniff`, `X-Frame-Options: DENY`, Referrer-Policy, Permissions-Policy. **No CSP** | Medium (F1) |
| T | SSL stripping on first visit | Railway redirects HTTP to HTTPS (verified). **No HSTS** | Medium (F1) |
| S | Spoofed `X-Forwarded-For` or `Host` | Not trusted (uvicorn trusts only 127.0.0.1); URLs come from `APP_URL`, never the Host header | Low (F14) |
| I | Stack traces in error responses | FastAPI returns a plain "Internal Server Error"; known errors are short sentences | Low |
| E | Production protections switched off by a missing `ENV` | `ENV` defaults to `development`, which turns off the Secure cookie and the secret-strength check | Low today: verified `Secure` on the live cookie (F12) |
