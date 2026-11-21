# Backups and restore

All of NMU Programs' data lives in the Airtable base. The app itself keeps nothing it cannot
rebuild: the code is in GitHub, and the settings are Railway variables. So backing up means
backing up the base, and writing down the settings.

## What to back up

| What | Where it lives | How it is backed up |
|---|---|---|
| All program data (users, programs, tasks, notes, reminders, templates, audit log) | Airtable base | Airtable snapshots and history, plus a monthly CSV export (below) |
| Uploaded files on tasks | Airtable attachments | Included in snapshots. A CSV export only has links, which expire |
| The code | GitHub | Every clone is a full copy. NMU should own the repository |
| Settings | Railway variables | Keep a list of variable **names** (not values) in the admin runbook. Secrets can be made again (`secrets-runbook.md`) |
| The Gmail sender and Google sign-in setup | Google Cloud project | Documented in the README; can be recreated |

## Airtable's own protection

Check what your Airtable plan includes; retention periods depend on the plan.

- **Record revision history**: each record shows its past field values. Good for undoing a
  wrong edit to a few records.
- **Trash**: deleted records and tables can be restored for a while (base menu, **Trash**).
- **Snapshots**: base menu, **History > Snapshots** (or **Snapshots** in the base's menu).
  Airtable takes them automatically, and you can take one by hand. **Take a manual snapshot
  before** running `jobs.migrate_airtable`, before any bulk change in Airtable, and before a
  big app release.

Restoring a snapshot creates a **new base** with a new base ID. See "Restoring" below.

## Monthly export (an independent copy)

Airtable's history lives inside Airtable. Keep a copy outside it once a month, so the data
survives an account problem:

1. For each table, open its grid view, view menu, **Download CSV**. Do every table, including
   **Audit Log**.
2. Put the files in a dated folder on NMU's Google Drive, shared only with the people who look
   after the app. These files contain names and emails: treat them as confidential.
3. Delete exports older than a year, unless NMU's records policy says otherwise.

## Restoring

**A few records changed or deleted:** use the record's revision history, or the base's trash.
The app sees the change within about 30 seconds.

**Large damage:**

1. Pause the Railway web and cron services (so nothing writes to the damaged base).
2. Restore the most recent good snapshot. It becomes a new base with a new ID
   (`app...` in its address).
3. In the new base, check the tables look right, and turn its automations (calendar sync) back
   on if they were on.
4. Make a new `AIRTABLE_TOKEN` with access to the new base (scopes `data.records:read` and
   `data.records:write`), and set `AIRTABLE_BASE_ID` and `AIRTABLE_TOKEN` on both services.
5. Resume the services. Check `/api/health/airtable` as an admin, sign in, and look at a few
   programs.
6. Anything changed between the snapshot and the damage has to be entered again; the Audit
   page and the server log help find what that was.
7. Sessions point at Users record IDs. If the restored base keeps them, sessions carry on; if
   not, people are simply signed out and sign in again. Rotate `SESSION_SECRET` anyway if the
   damage was deliberate.
8. Calendar feed links and template version links also use record IDs; check one of each.

## Practise once a year

Restore a snapshot into a new base, point a **laptop** copy of the app at it (in your own
`.env`), and check you can sign in and see the data. Then delete the test base. Write down how
long it took.
