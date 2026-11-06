# NMU Launches

NMU Launches is where No More Under plans and tracks every new swim program site. An admin picks a template and a Day 1, and the app creates every task with a due date and an owner, so staff only need to look at their own list.

Airtable holds all the data. Staff never need Airtable seats, because only this app's server talks to Airtable.

## Running the app

There are two ways to run the app on your computer. Use one at a time.

| Way | Use it when | Open this address |
|---|---|---|
| Docker | You just want to run or try the app | http://localhost:8080 |
| Two terminals | You are changing the code and want to see edits right away | http://localhost:5173 |

Both need a `.env` file first. Copy `.env.example` to a new file named `.env` in the top folder, then fill it in using the sections below. Never commit this file.

### Docker (one command)

You need [Docker Desktop](https://www.docker.com/products/docker-desktop/), and it must be open.

1. From the top folder, run:

   ```
   docker compose up --build
   ```

2. Open http://localhost:8080.
3. Press `Ctrl+C` to stop.

After changing code or `.env`, run the command again.

### Two terminals (for changing code)

You need [Python 3.12](https://www.python.org/downloads/) and [Node.js 22](https://nodejs.org/).

1. Start the backend in one terminal:

   ```
   cd backend
   python -m venv .venv
   .venv\Scripts\activate          (Windows)
   source .venv/bin/activate       (Mac)
   pip install -r requirements.txt
   uvicorn app.main:app --reload --port 8000
   ```

   The `python -m venv` and `pip install` lines are only needed the first time.

2. Start the frontend in a second terminal:

   ```
   cd frontend
   npm install
   npm run dev
   ```

   The `npm install` line is only needed the first time.

3. Open http://localhost:5173. Do not open port 8000 in your browser.
4. Press `Ctrl+C` in each terminal to stop.

Frontend edits appear right away, and the backend restarts itself when its code changes. After changing `.env`, restart the backend yourself.

### If something else is using a port

Port 8000 must be free for the two terminals way, and port 8080 for Docker. If you see `{"detail":"Not Found"}` or a different app, run `docker ps` to see what else is running, then stop it with `docker stop NAME`.

### Running the tests

From the `backend` folder, with `.venv` activated, run `pytest`.

## Testing without Google

Google sign in needs a Google OAuth client. Until you have one, you can test locally with just Airtable:

1. In `.env`, set `DEV_LOGIN_EMAIL` to an email from the Airtable Users table. That person must be Active.
2. Restart the app.
3. Click **Sign in with Google**. It skips Google and signs you in as that person.

To test as someone else, change the email and restart the app, then sign out and back in. Setting `DEV_ALLOW_VIEW_SWITCH=true` also lets you flip between admin and staff views.

This only works on localhost. The app refuses to start if `DEV_LOGIN_EMAIL` is set in production, so never add it to Railway.

## Create the Airtable token

1. Go to https://airtable.com/create/tokens and choose **Create token**.
2. Add these four scopes: `data.records:read`, `data.records:write`, `schema.bases:read`, `schema.bases:write`. The last one is only used by the migration script that adds new fields (see **Updating the Airtable base**).
3. Under **Access**, add the NMU base.
4. Copy the token into `AIRTABLE_TOKEN`.

A token belongs to the person who made it and has that person's access, so:

- Each developer should make their own token for their own `.env`. Do not pass tokens around. `.env` is never saved to GitHub, so teammates need to create their own copy.
- The live app needs one token, set in Railway. Make it from an NMU-owned account, not a person's or a student's, because it stops working if that person loses access to the base.
- Staff using the app never need a token or an Airtable seat.

To find the base ID, open the base in your browser. The address looks like `airtable.com/appXXXXXXXXXXXXXX/...`. The part starting with `app` goes in `AIRTABLE_BASE_ID`. Copy only that part, and stop before the next `/`. If you include the `tbl...` part after it, the app cannot connect.

## Create the Google sign in client

Google now calls this part of the console **Google Auth Platform**.

1. Sign in to https://console.cloud.google.com with the Google account that will own the app (for now avanthi.arun@gmail.com, and an NMU-owned account at handoff). Create a project named **NMU Launches**.
2. Open **Google Auth Platform**, then **Branding**. Set the app name to **NMU Launches** and choose a support email. Leave the logo empty, because a logo triggers brand verification. Once the app is deployed, also fill in **Application home page** (`https://YOUR-APP-DOMAIN/`), **Application privacy policy link** (`https://YOUR-APP-DOMAIN/privacy`) and **Application terms of service link** (`https://YOUR-APP-DOMAIN/terms`). Google expects these for an app that is In production.
3. **Audience:** choose **External**.
4. **Data Access:** add the `openid`, `.../auth/userinfo.email` and `.../auth/userinfo.profile` scopes.
5. **Clients**, then **Create client**, then **Web application**. Under **Authorized redirect URIs**, add these, matching exactly with no trailing slash except on the last one:
   - `http://localhost:8000/auth/callback` for the two-terminal setup
   - `http://localhost:8080/auth/callback` for Docker
   - `https://YOUR-RAILWAY-DOMAIN/auth/callback` for production
   - `http://localhost:8765/` for the one-time Gmail authorization in **Set up email**, where the trailing slash is required
6. Copy the client ID and the secret right away, because the secret is only shown in full once. Put them in `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.
7. **Audience**, then **Publish app**, to set the status to **In production**. Sign in only uses basic scopes, so no verification is needed. In Testing mode only listed test users can sign in. Publishing also stops the Gmail refresh token from expiring every 7 days.
8. Leave `ALLOWED_EMAIL_DOMAIN` blank. Any Google account can try to sign in, and the Airtable Users table decides who gets in.

When the backend starts, it prints the redirect URI it uses, for example `Google sign in redirect URI: http://localhost:8000/auth/callback`. That exact address must be on the client. In developer mode, admins can also see it on **Users and roles > System**.

`BOOTSTRAP_ADMIN_EMAILS` makes sure the first admin can get in: if one of those emails has no row in the Users table, signing in creates an Active Admin row for it. An existing row is never changed.

| What you see | Fix |
|---|---|
| `Error 400: redirect_uri_mismatch` | The URI the server logged on startup is not on the client. Add it exactly. Changes can take a few minutes to apply. |
| `Error 401: invalid_client` | The client ID or secret is wrong or still the placeholder. |
| `Access blocked: app has not completed verification` or `access_denied` | The app is still in Testing. Publish it, or add the person as a test user. |
| `mismatching_state` / sent back to Not Authorized with `reason=google` | The sign in started on `127.0.0.1` and finished on `localhost`, or the other way round. Always open `http://localhost:5173` (or `:8080`). |
| "You do not have access yet" | That Google email has no Active row in Users. Add the row, or sign in with the right account. |

## Set up email

All email (reminders, the weekly digest, assignment and welcome emails) goes through the Gmail API. Railway blocks outbound SMTP below its Pro plan, and the Gmail API works over HTTPS on any plan.

1. In the same Google Cloud project, open **APIs and Services**, then **Library**, then **Gmail API**, and click **Enable**.
2. Make sure `http://localhost:8765/` is on the OAuth client's redirect URIs, and that the app is **In production** (Audience page).
3. On your computer, with `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env`, run `python -m jobs.authorize_gmail` from `backend`. Sign in as the account that should send the emails (for now avanthi.arun@gmail.com, and later an NMU-owned account), then click through the unverified-app screen (**Advanced**, then **Go to NMU Launches**). This screen appears once, only for the sender, because `gmail.send` is a sensitive scope. Staff signing in never see it.
4. Put the printed token in `GMAIL_REFRESH_TOKEN`, set `GMAIL_SENDER` to that same address, and set `REMINDERS_DRY_RUN=false`.
5. Run the app on your computer in developer mode (`DEV_ALLOW_VIEW_SWITCH=true`), go to **Users and roles**, then **System**, then **Send me a test email**. The System box only shows in developer mode, never in production.
6. When the app is deployed later, set the same variables on **both** Railway services, the web service and the cron service.
7. To change the sender later, run step 3 again with the new account and replace both variables.
8. The refresh token stops working if the sender changes their Google password, revokes access, or does not use it for 6 months. The daily job uses it, so the last case should not happen.

**Trying the reminder job.** From `backend`, `python -m jobs.send_reminders --dry-run --date 2026-11-09` prints every email that would go out that day. `--only weekly`, `--only auto` or `--only custom` limits it to one kind. The job writes a Reminders row for every email it sends, fails or skips, so running it twice never sends anything twice. It exits with an error if any email failed.

**Decision for NMU: overdue follow-up.** The midterm left open what happens after a task goes overdue. For now, overdue tasks are listed first in the Monday weekly digest, and there is no separate overdue email. This is the `OVERDUE_FOLLOW_UP` constant in `backend/app/services/reminders.py`.

## Updating the Airtable base

The app needs some fields and tables the original base did not have: the Links, Reminders and Template Versions tables, and fields such as Due Date Override and One-off on tasks and Program Name and Duration on sessions. A script adds them. It only adds; it never changes or deletes existing fields or rows.

1. Make sure your token has the `schema.bases:write` scope.
2. From `backend`, run `python -m jobs.migrate_airtable` to see what it would add. Nothing changes yet.
3. Run `python -m jobs.migrate_airtable --apply` to add them. Running it again prints "Nothing to add".
4. `python -m jobs.dump_schema` rewrites `docs/airtable-schema.md` from the live base, so you can check the result.

On a test base only, `python -m jobs.seed_demo --yes-this-is-a-test-base` adds demo people, sites, templates and launches, all with `@example.org` emails. It refuses to run in production, and refuses to run twice.

`docs/data-model.md` explains every table and field the app uses.

## How the app reads Airtable

Airtable answers at most 5 requests a second per base and sends 100 rows per request, so loading every table straight from Airtable takes several seconds. To keep pages quick, the server keeps a copy of each table in memory. All of this is in `backend/app/airtable/client.py`.

- **On start,** the server fetches every table in the background, so the first sign in does not wait.
- **A copy under 30 seconds old** is used as is.
- **A copy between 30 seconds and 5 minutes old** is shown straight away, and a fresh one is fetched in the background for the next page. After 5 minutes with nobody using the app, the next page waits for Airtable (a few seconds).
- **Only one download of a table runs at a time.** Other requests for it wait for that one.
- **Every request to Airtable waits its turn,** at most 4 a second, so the base is never locked out for going over the limit.

**Edits made in the app show right away.** After a write, the rows Airtable sends back go straight into that table's copy, and the tables that were changed are fetched again in the background a second later.

**Edits made directly in Airtable** show within about 30 seconds. Sometimes the first page after that still shows the old copy, and the page after it shows the change.

**Fields that come from another table.** Some fields are filled in by Airtable from a different table. For example, a task's due date follows its launch's Day 1, and a site's name includes its region. So when one table is edited, the app also throws away its copy of any table that takes fields from it. `DEPENDS_ON_WRITES_TO` in `client.py` lists these, for example "after editing Session, fetch Work again". If you make the app read a new formula, lookup or linked field that comes from another table, add that pair to the list. Otherwise that field can show its old value for about a second after an edit, until the background refresh catches up.

## Adding and removing people

Admins add people on **Users and roles > Add a person**. The new person gets a welcome email and can then click **Sign in with Google**, with no password to set. **Edit > Deactivate** stops someone signing in. Before deactivating someone, use **Hand off tasks** to move their open tasks to someone else.

The API also has a stricter **remove access** (`DELETE /api/users/{id}`), which sets Status to Inactive but is refused while the person still has open tasks, and `POST /api/tasks/reassign` to move chosen open tasks to one active person. These came from the user management prototype and have no buttons in the app yet.

You can also do this straight in the Airtable **Users** table: a row with their Google email as Email Address, First Name, Last Name, Status **Active** and an Access Level lets them in, and Status **Inactive** keeps them out. Changes apply within about 30 seconds (see **How the app reads Airtable**).

## Deploy on Railway

Once this is set up, every push to the `main` branch on GitHub updates the live site automatically, usually within a few minutes. Changes on your own computer do not go live until they are pushed.

The live site needs real Google sign in, because the test login only works on your own computer. Nobody can sign in there until `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are set.

**The web app**

1. In Railway, choose **New Project > Deploy from GitHub repo** and pick this repo. Railway reads `railway.json` and builds the `Dockerfile`.
2. Under **Variables**, add everything from `.env.example`, with these production values:
   - `ENV=production`
   - `SESSION_SECRET`: a new random string of at least 32 characters. The app will not start without one. You can make one with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
   - `DEV_ALLOW_VIEW_SWITCH=false`
   - `DEV_LOGIN_EMAIL`: leave this out or blank
   - `BOOTSTRAP_ADMIN_EMAILS`: the first admin's Google email
   - `CONTACT_EMAIL` and `ORG_ADDRESS`: NMU's contact inbox and mailing address, shown on the Privacy page and in every email
3. Under **Settings > Networking**, choose **Generate Domain**.
4. Set both `APP_URL` and `FRONTEND_URL` to that domain, starting with `https://`.
5. Add `https://YOUR-APP-DOMAIN/auth/callback` to the Google OAuth client's redirect URIs.

After changing a variable in Railway, click **Deploy** if it asks you to apply the change, so the app picks up the new value.

**The reminder cron service**

1. In the same Railway project, add a second service from the same GitHub repo.
2. Under **Settings > Config-as-code**, set the config file path to `/railway.cron.json`. This runs `python -m jobs.send_reminders` on the schedule `0 15 * * *`, and leaves out the web health check.
3. Copy the variables from the web service.

Railway schedules in UTC, so `0 15 * * *` is 8 AM Pacific during daylight time and 7 AM in winter. While `REMINDERS_DRY_RUN=true` the job only prints. Set it to `false` once the test email works.

## Roles and the view switch

Each person's **Access Level** in the Airtable Users table sets what they can do:

| Access Level | Starts in | Notes |
|---|---|---|
| Admin | Admin view | Full access |
| Project Lead | Admin view | Assumption, still being decided |
| Staff | Staff view | Can update their own tasks |
| Viewer | Staff view | Read only |
| Partner | Partner view | Sees only the launches they are added to, and updates their own tasks. Never sees internal notes or history |
| Blank or anything else | Staff view | Read only |

Admins and Project Leads can use the switch in the sidebar to see the app exactly as staff do. While in staff view they have staff permissions, on the server as well as on screen.

Changes to someone's Status or Access Level in Airtable apply within about 30 seconds (see **How the app reads Airtable**), with no need to sign in again.

**To change the Project Lead mapping,** edit the `"Project Lead"` line of `BASE_VIEW_BY_ACCESS_LEVEL` in `backend/app/permissions.py`, and update `test_project_lead_is_treated_as_admin_for_now` in `backend/tests/test_permissions.py` to match.

For demos, setting `DEV_ALLOW_VIEW_SWITCH=true` lets **anyone** signed in use admin view, with real admin permissions. It also shows the **What each level can do** table and the **System** box on **Users and roles**, which are hidden otherwise. Keep it `false` in production.

## Project structure

| Folder | What is in it |
|---|---|
| `backend/app/` | The FastAPI app. `main.py` starts it, and `permissions.py` holds every role rule |
| `backend/app/airtable/` | The Airtable connection and its cache (`client.py`), and `schema.py` with every table and field name |
| `backend/app/auth/` | Google sign in, sessions, and the checks that protect routes |
| `backend/app/models/` | The shapes of users, projects, tasks and templates |
| `backend/app/routers/` | The URLs the app answers |
| `backend/app/services/` | The rules: timelines and Day 1 moves, history, reminders, templates, dates in Pacific time |
| `backend/app/email/` | Sending email through the Gmail API, and the wording of every email |
| `backend/jobs/` | The daily reminder job, Gmail authorization, the Airtable migration, the schema dump and demo data |
| `backend/tests/` | Automated tests |
| `frontend/src/api/` | How the website calls the backend |
| `frontend/src/auth/` | Who is signed in, and the page guards |
| `frontend/src/components/` | The sidebar and shared pieces: status menu, task rows, project cards, dialogs, form fields, toasts |
| `frontend/src/pages/` | One file per page |
| `frontend/src/styles/` | Colors, fonts and spacing (`tokens.css`) and page styles |
| `docs/` | The user guide, admin runbook, data model, decisions and next steps to production |
| `docs/design/` | The wireframes |
