# Admin runbook

How to keep NMU Launches running. This is for whoever looks after the app at NMU. It assumes you can sign in to the accounts below, not that you write code.

## Who owns what

| Account | What it is for | Owner now | Owner at handoff |
|---|---|---|---|
| GitHub repository | The code. Pushing to `main` updates the live site once Railway is set up. | The student team | An NMU GitHub organization |
| Railway | Runs the website and the daily reminder job | Not set up yet | An NMU account with billing |
| Google Cloud project "NMU Launches" | Google sign in, and the Gmail API for sending email | avanthi.arun@gmail.com | An NMU Google account |
| Gmail sender | The address reminders come from | avanthi.arun@gmail.com | An NMU address, for example launches@ |
| Airtable base | All the data | NMU | NMU |
| Airtable token | Lets the app read and write the base | Each developer has their own | One token from an NMU-owned Airtable account |

When an owner leaves, move the account first. A token or Gmail authorization tied to a person stops working when that person loses access.

## Settings (environment variables)

On a laptop these live in the `.env` file in the top folder. On Railway they live under each service's **Variables**. Both Railway services (the website and the reminder job) need the same values.

| Variable | What it is | Notes |
|---|---|---|
| `ENV` | `development` or `production` | `production` on Railway |
| `APP_URL` | The backend's address | The Railway https domain in production |
| `FRONTEND_URL` | The website's address | Same as `APP_URL` in production |
| `SESSION_SECRET` | Signs the sign-in cookie | A random string of 32+ characters. Changing it signs everyone out. |
| `APP_TIMEZONE` | Time zone for dates and the daily job | `America/Los_Angeles` |
| `AIRTABLE_TOKEN` | Airtable personal access token | Scopes: `data.records:read`, `data.records:write`, `schema.bases:read`, `schema.bases:write` |
| `AIRTABLE_BASE_ID` | The base, starting with `app` | |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | The Google sign in client | From Google Auth Platform > Clients |
| `ALLOWED_EMAIL_DOMAIN` | Limit sign in to one email domain | Leave blank. The Users table decides who gets in. |
| `BOOTSTRAP_ADMIN_EMAILS` | First admins | Creates an Admin row for these emails if they have none |
| `DEV_ALLOW_VIEW_SWITCH` | Lets anyone switch to admin view | `false` in production |
| `DEV_LOGIN_EMAIL` | Skips Google on a laptop | Never set on Railway. The app refuses to start with it in production. |
| `GMAIL_SENDER` | The address emails come from | Must be the account that authorized Gmail |
| `GMAIL_CLIENT_ID` / `GMAIL_CLIENT_SECRET` | Optional | Leave blank to use the Google sign in client |
| `GMAIL_REFRESH_TOKEN` | Lets the app send as the sender | From `python -m jobs.authorize_gmail` |
| `REMINDERS_DRY_RUN` | `true` logs emails without sending | `false` once the test email works |

## Adding and removing people

Use **Users and roles** in the app:

- **Add a person**: their Google email, access level and roles. They get a welcome email.
- **Edit > Deactivate**: they can no longer sign in. Hand off their tasks first with **Hand off tasks**, or the tasks stay assigned to them.
- To give someone partner access to a launch, make their access level **Partner**, then tick them under **Partner access** in that launch's **Edit details**.

You can also edit the Airtable Users table directly. Changes apply within about 30 seconds.

## Rotating the Airtable token

Do this when the person who made the token leaves, or if the token may have leaked.

1. Sign in to Airtable as the NMU-owned account. Go to https://airtable.com/create/tokens and create a new token with the four scopes above and access to the NMU base.
2. Put it in `AIRTABLE_TOKEN` on both Railway services and redeploy.
3. Open **Users and roles > System** and check that Airtable says **Connected**.
4. Delete the old token in Airtable.

## Re-authorizing Gmail

Do this when the sender changes, or when the System card or the job logs say "The Gmail authorization has expired or been revoked".

1. On a laptop, with `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env`, run `python -m jobs.authorize_gmail` from the `backend` folder.
2. Sign in as the sending account. Click **Advanced**, then **Go to NMU Launches**. This warning is expected.
3. Put the printed token in `GMAIL_REFRESH_TOKEN`, and the account's address in `GMAIL_SENDER`, on both Railway services.
4. Click **Send me a test email** on the System card.

The authorization breaks if the sender changes their Google password, removes the app's access in their Google account settings, or the Google Cloud app is moved back to Testing. Keep the app **In production** on the Audience page.

## The daily reminder job

The job runs `python -m jobs.send_reminders` once a day (8 AM Pacific in summer, 7 AM in winter). Each day it sends the 7-day and due-today emails and custom reminders. On Mondays it also sends the weekly digest.

Every email it sends, fails or skips is written to the Airtable **Reminders** table with its Status and any error. That table is the best place to check what went out. Because of it, running the job twice in a day never sends anything twice.

**Reading the logs.** In Railway, open the cron service, then **Deployments**, then the latest run. The last lines are a summary of how many emails were sent, skipped and failed. A failed run is marked red.

**Trying it on a laptop.** From `backend`:

- `python -m jobs.send_reminders --dry-run` shows what today would send.
- `python -m jobs.send_reminders --dry-run --date 2026-11-09` shows another day (a Monday includes the digest).
- `--only auto`, `--only custom` or `--only weekly` limits it to one kind.

## When emails stop

1. Open **Users and roles > System**. If Email says **Not set up**, a Gmail variable is missing. If **Dry run is on**, set `REMINDERS_DRY_RUN=false`.
2. Click **Send me a test email**. The message says what went wrong.
3. If it mentions an expired or revoked authorization, follow **Re-authorizing Gmail**.
4. Check the cron service's latest run in Railway. If it did not run, check its schedule and that it has the same variables as the website.
5. Look at the Reminders table for rows with Status **Failed** and read the Error column.
6. Rows with Status **Skipped** and "No one assigned" mean a task has nobody on it. Assign someone.

## Deploying and rolling back on Railway

The README's **Deploy on Railway** section covers the first setup. After that:

- **Deploying:** merge to `main` on GitHub. Railway builds and deploys both services automatically, usually within a few minutes.
- **Rolling back:** in Railway, open the service, then **Deployments**, find the last good deployment and choose **Redeploy**. Do the same for the cron service if it changed. Then fix the problem in GitHub, since the next push deploys again.
- **After changing a variable**, click **Deploy** if Railway asks, so the services pick it up.

## Changing the Airtable base

The app expects the tables and fields listed in `docs/data-model.md`. Renaming or deleting one of them breaks the parts of the app that use it. Adding fields and tables is safe.

If the code adds new fields, run `python -m jobs.migrate_airtable` to see what it would add, then `--apply`. It only ever adds.
