# Incident response

What to do when something may have gone wrong: a leaked secret, an account someone else is
using, data changed that nobody meant to change, the site down, or a vulnerability report.

Keep calm, write down what you see as you go (times, request IDs, what you did), and do not
delete logs or audit rows: they are the evidence.

## 1. Decide how serious it is

| Level | Examples | Start |
|---|---|---|
| **High** | Someone who should not be is signed in as an admin; `SESSION_SECRET`, the Airtable token or a Google secret leaked; data deleted or changed on purpose; personal data seen by an outsider | At once, same day |
| **Medium** | A staff or partner account used by someone else; a calendar feed link shared publicly; repeated `access_denied` or `sign_in_denied` events from one place | Within a day |
| **Low** | A vulnerability report with no sign of use; a single odd event | Within a week |

## 2. Contain

Pick what fits. Each step is safe to do even if it turns out to be a false alarm.

- **One person's account:** Users and roles, **Edit > Sign out everywhere** (ends every session
  at once). If they should not have access at all, **Deactivate**. Ask them to change their
  Google password and check their Google account's recent activity.
- **Every session (an admin account misused, or `SESSION_SECRET` leaked):** rotate
  `SESSION_SECRET` (`secrets-runbook.md`). Everyone signs in again.
- **A leaked credential:** rotate it now, following `secrets-runbook.md`. Rotating first and
  investigating second is right.
- **Someone is hammering the site:** Railway can pause the service (**Settings > Pause**) while
  you look. The rate limits already slow most attacks.
- **Email being misused:** set `REMINDERS_DRY_RUN=true` on both services and redeploy; nothing
  more is sent. Revoke the Gmail authorization if the refresh token may have leaked.
- **A bad deploy:** roll back on Railway (admin runbook, "Deploying and rolling back").

## 3. Investigate

- **Audit page** (admins): every admin change with who, what and when. Filter by the admin and
  the period.
- **Server log** (Railway, `monitoring.md`): search for `"event":` and the user's record ID,
  the client address, or a request ID from the Audit page or an error message.
- **Airtable**: each record's **revision history** (expand a record, then the clock icon)
  shows field changes, including any made directly in Airtable outside the app. The base's
  trash holds recently deleted records.
- **Railway**: the project's activity shows variable changes and deploys.
- **GitHub**: recent commits, pull requests and Settings changes.

Questions to answer: what was accessed or changed, by which account, from when to when, and how
they got in.

## 4. Recover

- Restore changed or deleted data (`backups.md`).
- Fix the cause: a code fix through a pull request (CI must pass), a setting, or removing
  someone's access.
- Check the alerts in `monitoring.md` would catch it next time.

## 5. Tell people

- **NMU leadership**: for anything High.
- **The people affected**: if their personal data (name, email, notes) was seen by someone who
  should not have seen it, tell them what happened, what data, and what was done.
- **Legal duties**: personal data breaches can have legal notice deadlines depending on where
  the people live (for example 30 days in Washington State for residents' personal information,
  shorter in some places). NMU should check with its advisor whenever personal data may have
  been exposed.
- **A vulnerability reporter**: thank them, say when it is fixed.

## 6. Afterwards

Within two weeks, write a short note: what happened, the timeline, the cause, what was fixed,
and what changes so it does not happen again. Add a finding to `findings.md` if the code or
setup changed.
