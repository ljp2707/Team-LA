# Monitoring and the audit trail

This page is for whoever looks after NMU Programs. It explains where to look when something
seems wrong, what the app writes down, and which signs mean someone should act.

There are two records:

| | Server log | Audit Log |
|---|---|---|
| Where | Railway, **web service > Deployments > View logs** (and **Observability > Logs**) | The **Audit** page in the app (admins), or the Audit Log table in Airtable |
| What | Every request, every security event, every error | One row per admin change |
| Kept | However long Railway keeps logs on your plan (days, not years) | For good. Nobody can change it through the app |
| Holds | Record IDs, masked emails (`m***@example.org`), routes, IP addresses | Record IDs only |

## The server log

In production every line is one JSON object (findings F36). For example:

```json
{"time": "2026-11-20T17:00:00.123Z", "level": "WARNING", "logger": "app.security.events",
 "message": "security_event access_denied status=403 ...", "request_id": "3f2a9c...",
 "event": "access_denied", "status": 403, "method": "GET", "route": "/api/users",
 "user": "recAbc123", "client": "203.0.113.7"}
```

- **`request_id`** is on every line written while a request was handled. The same ID is in
  the `X-Request-ID` header, in the "request" number people see on an error message, and in
  the Audit Log. Search for it to see everything that happened in that one request.
- **`event`** marks a security event. Search Railway's logs for `event` and a name below,
  for example `"event":"sign_in_denied"`.
- **`user`** is a Users record ID. Look it up in Airtable (Users table, search by record ID)
  or on the Audit page.

On a laptop the same lines are plain text: `WARNING app.security.events: security_event ...`.

### Never in the log

Secrets, tokens, cookies, Google sign-in codes, calendar feed tokens (replaced by
`[redacted]`), request bodies, note text and full email addresses. If you ever see one,
treat it as an incident (`incident-response.md`): rotate the secret and fix the code that
logged it.

## Security events

| Event | Level | What it means | Act when |
|---|---|---|---|
| `sign_in` | INFO | Someone signed in. Fields: `user`, `access_level` | An admin signs in at an odd hour or from an unexpected place |
| `sign_in_denied` | WARNING | A sign in was refused. `reason`: `not_an_active_user`, `wrong_domain`, `email_not_verified`, `google_error`, `airtable_unreachable`. `email` is masked | More than about 20 an hour, or many for one masked address: someone is trying accounts. `airtable_unreachable`: check Airtable |
| `sign_out` | INFO | Someone clicked Sign out | Never on its own |
| `sign_out_everywhere` | INFO | Someone ended all their sessions | Ask them if it was a lost device; check their recent activity |
| `session_revoked` | WARNING | A cookie from before "sign out everywhere" (or an access change) was refused | Several for one `user` after they signed out everywhere: someone else may hold a copy of their cookie. Make sure they changed their Google password |
| `session_ended_inactive_user` | WARNING | A deactivated person's open session was ended | Repeats for the same `user`: they, or someone with their cookie, keep trying |
| `session_expired` | INFO | A session passed its idle or 7-day limit | Never on its own |
| `access_denied` | WARNING | A 403: wrong role, another program's data, or a request from another website. Fields: `route`, `user`, `client` | More than about 10 in 10 minutes from one `user` or `client`: someone is probing. A steady trickle after a release: a page may be calling a route it should not |
| `rate_limited` | WARNING | A 429: too many requests | Many from one `client`: an attack or a broken script. Check the nudge and sign-in limits in the README |
| `request_too_large` | WARNING | A 413: an upload or body over the limit | Many in a row: someone is testing limits |
| `csp_violation` | WARNING | The browser blocked something the page tried to load. Fields: `directive`, `blocked`, `page` | Any `script-src` from an unknown origin: possible injected script. After a release: the policy may need a change (`docs/security/findings.md` F25-F28) |
| `admin_action` | INFO | An admin changed something. Also in the Audit Log | Changes nobody expected (see "Review the audit trail" below) |
| `audit_write_failed` | ERROR | Airtable did not take an Audit Log row. The line has the same details, so the log is the record for it | Always: check Airtable and its API limits. Copy the line into your notes until the table is written again |
| `bootstrap_admins_still_set` | WARNING | `BOOTSTRAP_ADMIN_EMAILS` is set though an Active Admin exists | Remove the variable on Railway |
| `unexpected_error` | ERROR | A 500. The line before it has the stack trace | More than a few an hour, or any right after a release |

### Setting up alerts

Railway can watch logs for you: **Observability > Alerts** (or a log drain to a tool such
as Better Stack, Axiom or Datadog, which all read these JSON lines). Start with:

1. Any `audit_write_failed` or `unexpected_error`: notify right away.
2. `sign_in_denied` more than 20 in an hour: notify.
3. `access_denied` more than 10 in 10 minutes for one `user` or `client`: notify.
4. Any `csp_violation` with `"directive":"script-src"`: notify.
5. Any `session_revoked` more than 3 times in a day for one `user`: notify.

Also turn on Railway's deploy-failure and service-crash emails, and an uptime check on
`https://YOUR-APP-DOMAIN/api/health` (Railway, UptimeRobot or similar).

## Review the audit trail

Once a month, an admin other than the one who made most of the changes opens **Audit**,
chooses **Last 90 days** and checks:

- Every **Changed a person**, **Removed a person's access** and **Signed a person out
  everywhere** matches a real request (a new hire, a leaver, a lost laptop).
- Nobody was made an Admin without a reason.
- **Removed a person's personal details** matches a deletion request.
- Deleted programs and tasks were meant to be deleted.

Anything unexplained: follow `incident-response.md`.

The Audit Log in Airtable cannot be protected from a base editor (Airtable has no
append-only tables). Keep the number of people with editor access to the base small, and
look at the table's **record history** in Airtable if a row ever seems wrong.

## Health checks

- `GET /api/health`: the app is running. Railway's deploy check uses it.
- `GET /api/health/airtable` and `/api/health/auth` (admins): Airtable and Google sign-in.
- The admin dashboard shows an Airtable status card.
