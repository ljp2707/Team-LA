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
2. Add these three scopes: `data.records:read`, `data.records:write`, `schema.bases:read`.
3. Under **Access**, add the NMU base.
4. Copy the token into `AIRTABLE_TOKEN`.

A token belongs to the person who made it and has that person's access, so:

- Each developer should make their own token for their own `.env`. Do not pass tokens around. `.env` is never saved to GitHub, so teammates need to create their own copy.
- The live app needs one token, set in Railway. Make it from an NMU-owned account, not a person's or a student's, because it stops working if that person loses access to the base.
- Staff using the app never need a token or an Airtable seat.

To find the base ID, open the base in your browser. The address looks like `airtable.com/appXXXXXXXXXXXXXX/...`. The part starting with `app` goes in `AIRTABLE_BASE_ID`. Copy only that part, and stop before the next `/`. If you include the `tbl...` part after it, the app cannot connect.

## Create the Google sign in client

1. Go to https://console.cloud.google.com and create or choose a project.
2. Open **APIs and Services > OAuth consent screen**. Choose **Internal** if everyone is on the NMU Google Workspace. Otherwise choose **External** and add test users.
3. Open **APIs and Services > Credentials > Create credentials > OAuth client ID**. Choose **Web application**.
4. Under **Authorized redirect URIs**, add all of these:
   - Two terminals: `http://localhost:8000/auth/callback`
   - Docker: `http://localhost:8080/auth/callback`
   - Production: `https://YOUR-APP-DOMAIN/auth/callback`
5. Copy the client ID and secret into `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.

## Adding and removing people

There is no signup page. The Airtable **Users** table decides who can get in.

- **To add someone,** create a row with their Google email as Email Address, their First Name and Last Name, Status set to **Active**, and an Access Level. They can then click **Sign in with Google**, with no password to set.
- **To remove someone,** set their Status to **Inactive**.

Both changes apply within about 30 seconds.

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
3. Under **Settings > Networking**, choose **Generate Domain**.
4. Set both `APP_URL` and `FRONTEND_URL` to that domain, starting with `https://`.
5. Add `https://YOUR-APP-DOMAIN/auth/callback` to the Google OAuth client's redirect URIs.

After changing a variable in Railway, click **Deploy** if it asks you to apply the change, so the app picks up the new value.

**The reminder cron service**

1. In the same Railway project, add a second service from the same GitHub repo.
2. Under **Settings > Config-as-code**, set the config file path to `/railway.cron.json`. This runs `python -m jobs.send_reminders` on the schedule `0 15 * * *`, and leaves out the web health check.
3. Copy the variables from the web service.

Railway schedules in UTC, so `0 15 * * *` is 8 AM Pacific during daylight time and 7 AM in winter. For now the job is a dry run that only prints, so it sends nothing.

## Roles and the view switch

Each person's **Access Level** in the Airtable Users table sets what they can do:

| Access Level | Starts in | Notes |
|---|---|---|
| Admin | Admin view | Full access |
| Project Lead | Admin view | Assumption, still being decided |
| Staff | Staff view | Can update their own tasks |
| Viewer | Staff view | Read only |
| Blank or anything else | Staff view | Read only |

Admins and Project Leads can use the switch in the sidebar to see the app exactly as staff do. While in staff view they have staff permissions, on the server as well as on screen.

Changes to someone's Status or Access Level in Airtable apply within about 30 seconds, with no need to sign in again.

**To change the Project Lead mapping,** edit the `"Project Lead"` line of `BASE_VIEW_BY_ACCESS_LEVEL` in `backend/app/permissions.py`, and update `test_project_lead_is_treated_as_admin_for_now` in `backend/tests/test_permissions.py` to match.

For demos, setting `DEV_ALLOW_VIEW_SWITCH=true` lets **anyone** signed in use admin view, with real admin permissions. Keep it `false` in production.

## Airtable fields to add later

The wireframes need these, but the base does not have them yet. They were not added in this pass:

- Google Drive link on tasks and on projects
- Canva link on tasks
- Partner contact on projects
- Site type on sites
- Template versions
- Custom reminders

## Project structure

| Folder | What is in it |
|---|---|
| `backend/app/` | The FastAPI app. `main.py` starts it, and `permissions.py` holds every role rule |
| `backend/app/airtable/` | The Airtable connection, and `schema.py` with every table and field name |
| `backend/app/auth/` | Google sign in, sessions, and the checks that protect routes |
| `backend/app/models/` | The shapes of users, projects, tasks and templates |
| `backend/app/routers/` | The URLs the app answers |
| `backend/app/services/` | Timeline, history and reminder logic (not built yet) |
| `backend/app/email/` | Sending email through Gmail (not built yet) |
| `backend/jobs/` | The daily reminder job |
| `backend/tests/` | Automated tests |
| `frontend/src/api/` | How the website calls the backend |
| `frontend/src/auth/` | Who is signed in, and the page guards |
| `frontend/src/components/` | The sidebar and shared pieces like buttons and cards |
| `frontend/src/pages/` | One file per page |
| `frontend/src/styles/` | Colors, fonts and spacing (`tokens.css`) and page styles |
| `docs/design/` | The wireframes |
