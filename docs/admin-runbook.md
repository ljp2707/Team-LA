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
| `ORG_NAME` | Who runs the app | `No More Under`. Shown on the Privacy and Terms pages and in every email. |
| `CONTACT_EMAIL` | Where privacy questions and data requests go | An NMU inbox someone reads. Shown on the Privacy page and in every email. |
| `ORG_ADDRESS` | NMU's mailing address, one line | Shown on the Privacy page and in every email |

## Adding and removing people

Use **Users and roles** in the app:

- **Add a person**: their Google email, access level and roles. They get a welcome email.
- **Edit > Deactivate**: they can no longer sign in. Hand off their tasks first with **Hand off tasks**, or the tasks stay assigned to them.
- To give someone partner access to a launch, make their access level **Partner**, then tick them under **Partner access** in that launch's **Edit details**.

You can also edit the Airtable Users table directly. Changes apply within about 30 seconds.

## Checking the setup

The **System** box on **Users and roles** only shows in developer mode (`DEV_ALLOW_VIEW_SWITCH=true`), so it never appears in production. To use it, run the app on your own computer with that setting on. It runs against whatever values are in your `.env`, so to check production, put the production values there first.

In production, an admin who is signed in can open `/api/health/airtable` on the app's address to see whether Airtable is connected. The server log also prints the Google sign in redirect URI on startup.

## Rotating the Airtable token

Do this when the person who made the token leaves, or if the token may have leaked.

1. Sign in to Airtable as the NMU-owned account. Go to https://airtable.com/create/tokens and create a new token with the four scopes above and access to the NMU base.
2. Put it in `AIRTABLE_TOKEN` on both Railway services and redeploy.
3. Signed in as an admin, open `/api/health/airtable` on the app's address and check that `connected` is `true`.
4. Delete the old token in Airtable.

## Re-authorizing Gmail

Do this when the sender changes, or when the System box (developer mode) or the job logs say "The Gmail authorization has expired or been revoked".

1. On a laptop, with `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env`, run `python -m jobs.authorize_gmail` from the `backend` folder.
2. Sign in as the sending account. Click **Advanced**, then **Go to NMU Launches**. This warning is expected.
3. Put the printed token in `GMAIL_REFRESH_TOKEN`, and the account's address in `GMAIL_SENDER`, on both Railway services.
4. With the same values in your `.env`, run the app in developer mode and click **Send me a test email** on the System box (see **Checking the setup**).

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

1. Check the cron service's variables in Railway. Every Gmail variable must be set, and `REMINDERS_DRY_RUN` must be `false`.
2. With the same values in your `.env`, run the app in developer mode, open **Users and roles > System** and click **Send me a test email** (see **Checking the setup**). The message says what went wrong.
3. If it mentions an expired or revoked authorization, follow **Re-authorizing Gmail**.
4. Check the cron service's latest run in Railway. If it did not run, check its schedule and that it has the same variables as the website.
5. Look at the Reminders table for rows with Status **Failed** and read the Error column.
6. Rows with Status **Skipped** and "No one assigned" mean a task has nobody on it. Assign someone.

## Calendar sync for each person (calendar feed)

Anyone except Viewers can turn on **Sync all my tasks to Google Calendar** on My Tasks. The app then gives them a private link (an iCalendar feed) that Google Calendar subscribes to. The app builds the feed itself whenever Google asks for it; there is nothing to set up in Airtable or Google beyond one field.

**The field to add.** In the **Users** table, add **Calendar Feed Token** as a **Single line text** field (or run `python -m jobs.migrate_airtable --apply`). It holds the secret part of each person's link. Blank means their sync is off.

- **Treat it like a password.** Anyone who has it can read that person's task list. Do not copy it into other tables, exports or messages.
- To **switch off someone's feed** (for example if their link leaked), clear their Calendar Feed Token. Their link stops working at once. They can turn sync on again from My Tasks to get a new link.
- **Deactivate**, **Remove access** and **Remove personal details** all clear it automatically.

**It only works on the live site.** Google fetches the feed from its own servers, so a link that points at `localhost` (a laptop) never loads in Google Calendar. `APP_URL` must be the public https address.

**Do not use it together with the shared calendar below for the same people.** The Airtable automations invite each person as a guest on the shared NMU calendar, so someone with both would see every task twice. The feed is the simpler and more reliable choice: finished and deleted tasks drop off on their own, and nothing depends on Airtable features we could not confirm.

## Google Calendar sync (Airtable automations)

Each task can appear as an all-day event on a shared NMU Google Calendar, on its due date, with the people on the task invited as guests so it shows on their own calendars too. **Airtable does this, not the app.** Two Airtable automations create and update the events, and save each event's ID on the task so they can find it again.

The app only reads what the automations write. A task that has an event shows a small calendar mark after its name. The app never creates, changes or clears an event or its ID, so editing a task in the app is always safe.

Set this up in a **copy of the base first** (Airtable: base name menu > **Duplicate base**), try it with a few tasks, then repeat it in the real base. Some steps depend on Airtable features we could not confirm; they are listed at the end under **Check these before relying on it**.

### Before you start

- **A shared calendar.** In Google Calendar, create a calendar named "NMU Launches" (Other calendars > **+** > **Create new calendar**). Share it with the Google account that will run the automation, with **Make changes to events**. Use an NMU-owned account, not a person's: if that person leaves, the events stop updating.
- **An Airtable plan with automations.** Every task that gets an event uses automation runs. A new launch creates all its tasks at once, which is one run per task plus one more each time a task changes. Check your plan's monthly run limit under the base's **Automations** tab.
- **Look for an older reminder automation.** The Work table has older "Reminder Date" and "Reminder Sent" fields that mention "the daily Airtable reminder automation". The app sends its own reminder emails now. In the **Automations** tab, make sure any old reminder automation is turned off, so people do not get two emails.

### Step 1: Add the fields to the Work table

Open the **Work** table. For each field below, click **+** at the right end of the column headers, type the name exactly as shown (spelling and capital letters matter), pick the type, and save.

**Two fields only the automations fill in.** Never type in these or clear them by hand. A developer can add both by running `python -m jobs.migrate_airtable --apply`.

| Name | Type |
|---|---|
| Calendar Event ID | Single line text |
| Calendar Synced Key | Long text |

**One field Airtable keeps up to date.** The app shows it as "last updated" when you hover over the calendar mark.

| Name | Type | Settings |
|---|---|---|
| Calendar Last Synced | Last modified time | Choose **Specific fields** and pick Calendar Event ID and Calendar Synced Key. Turn on **Include time**. |

**Four formula fields** that work out what each event should say and whether it needs to change. For each one, choose the **Formula** type and paste the formula exactly.

**Calendar Title**, the event's name. Finished tasks keep their event but get "Done:" or "Skipped:" in front.
```
IF(OR({Status} = "Done", {Status} = "Skipped"), {Status} & ": ", "") & {Task Name} & " · " & ARRAYJOIN({Session})
```

**Calendar Guests**, everyone on the task, as a comma-separated list of emails. Assignee Emails already looks these up from Assigned To.
```
ARRAYJOIN({Assignee Emails}, ",")
```

**Calendar Key**, a summary of everything the event shows. When it changes, the event needs updating.
```
{Task Name} & "|" & DATETIME_FORMAT({Due Date}, "YYYY-MM-DD") & "|" & {Calendar Guests} & "|" & {Status}
```

**Calendar Action** says **Create** when a task needs its first event, **Update** when its event is out of date, and stays blank otherwise. Both automations start from this field.
```
IF(
  {Calendar Event ID} = "",
  IF(AND({Due Date}, {Calendar Guests} != "", {Status} != "Done", {Status} != "Skipped"), "Create", ""),
  IF({Calendar Key} != {Calendar Synced Key}, "Update", "")
)
```

So a task gets an event once it has a due date and at least one person, unless it is already finished. After that, any change to its name, due date, people or status makes Calendar Action say Update.

### Step 2: The "Create calendar event" automation

1. Open the **Automations** tab and click **Create automation**. Name it "Calendar: create event".
2. **Trigger:** choose **When a record matches conditions**. Table: **Work**. Condition: **Calendar Action** *is* `Create`.
3. Click **Test trigger** to load a sample task. If none match, open a test task in Airtable, give it a due date and a person, and test again.
4. **Action 1:** click **+ Add advanced logic or action**, choose **Google Calendar**, then **Create event**. Connect the NMU Google account and fill in:

   | Event setting | Use |
   |---|---|
   | Calendar | NMU Launches |
   | Title / Summary | **Calendar Title** (click **+** next to the box and pick it from the trigger record) |
   | All day | Yes (see the note on all-day events below) |
   | Start date | **Due Date** |
   | End date | **Due Date** |
   | Guests / Attendees | **Calendar Guests** |
   | Description | Type the text below and insert the fields where shown |

   Description:
   ```
   Launch: [Session]
   Status: [Status]
   Open in NMU Launches: https://YOUR-APP-ADDRESS/tasks/[Airtable record ID]
   ```
   Replace `YOUR-APP-ADDRESS` with the app's address (the `APP_URL` setting, without `https://`). The parts in brackets are inserted with **+**; "Airtable record ID" is listed under the trigger record.

5. **Action 2:** add **Update record**. Table: **Work**. Record ID: the trigger record's **Airtable record ID**. Click **+ Choose field** twice and set:

   | Field | Value |
   |---|---|
   | Calendar Event ID | The event's **ID** from Action 1 (click **+**, open Action 1's results) |
   | Calendar Synced Key | **Calendar Key** from the trigger record |

6. Test each action, check that the event appears on the NMU Launches calendar, then switch the automation **On**.

### Step 3: The "Update calendar event" automation

1. Create another automation named "Calendar: update event".
2. **Trigger:** **When a record matches conditions**. Table: **Work**. Condition: **Calendar Action** *is* `Update`.
3. **Action 1:** **Google Calendar > Update event**. Event ID: **Calendar Event ID** from the trigger record. Fill in Calendar, Title, All day, Start and End date, Guests and Description exactly as in Step 2.
4. **Action 2:** **Update record** on the trigger record. Set only **Calendar Synced Key** to **Calendar Key**. Leave Calendar Event ID alone.
5. Test it by renaming a test task in the app: Calendar Action should switch to Update, the event's title should change, and Calendar Action should go blank again. Then switch it **On**.

### When a task is done or skipped

Nothing extra is needed. Status is part of Calendar Key, so the update automation renames the event "Done: …" or "Skipped: …". The event stays on everyone's calendar as a record. Closing a launch with "Mark the open tasks as skipped" does this for every open task at once.

If you would rather remove finished tasks from calendars and Airtable offers a **Delete event** action, see the last item under **Check these before relying on it**.

### When a task or launch is deleted

**Airtable cannot react to deleted records**, so a deleted task's event stays on the calendar. This happens when an admin uses **Delete launch** in the app, or someone deletes a Work row in Airtable.

- Where possible, **close** a launch instead of deleting it. Its events then show as Done or Skipped instead of disappearing without a trace.
- After deleting a launch, open the NMU Launches calendar, search for the launch's name (it is in every event title), and delete those events by hand.

### When someone is removed from a task, or leaves

Changing who is on a task updates the event's guest list. If **every** person is removed, the guest list is empty and Google may keep the old guests; check that event by hand.

For a **"Delete my information"** privacy request, also remove the person as a guest from events on the NMU Launches calendar. Remove personal details in the app does not reach Google Calendar.

### Turning it off

Switch both automations **Off**. Existing events stay. Do **not** clear Calendar Event ID across many tasks unless you also delete their events: once the ID is blank, turning the automations back on would create duplicates.

### Check these before relying on it

We could not confirm these in Airtable's interface. Try each in the copy of the base.

1. **Guests.** Does Airtable's Google Calendar **Create event** action have a guests or attendees setting, and does it take a comma-separated list? This is the most important one: without it, events only appear on the shared calendar, not on each person's own calendar. In that case each person can subscribe to the NMU Launches calendar instead, but they will see everyone's tasks.
2. **Invitation emails.** If guests do work, Google may email an invitation for every event. A new launch creates dozens of tasks at once, so check whether the action has a "send notifications" option and turn it off if so.
3. **All-day events.** Check that the action can make all-day events. If it asks for times instead, use the due date for both and see how it looks. In Google an all-day event's end is the next day; if the event shows one day short, set End date to a formula field `DATEADD({Due Date}, 1, 'days')`.
4. **Event ID output.** Check that Create event lists an event **ID** among its results for Action 2 to use.
5. **Update event.** Check that Google Calendar offers an **Update event** action that takes an event ID.
6. **Matching conditions.** Check that **When a record matches conditions** fires again each time a record re-enters the condition (Calendar Action blank, then Update again). Also check whether tasks that *already* match when you switch an automation on get an event. If they do not, existing tasks only get events after their next change.
7. **Formulas.** Check that `AND({Due Date}, ...)` treats a blank Due Date as false, and that Calendar Guests is blank (not a stray comma) for a task with nobody on it.
8. **Delete event (optional).** If you want finished tasks removed from calendars, check whether Google Calendar offers a **Delete event** action. If so, add a third automation: trigger when **Status** is Done or Skipped *and* **Calendar Event ID** is not empty; action **Delete event** with Calendar Event ID. Do **not** clear Calendar Event ID afterwards. Calendar Action only says Create while the ID is blank, so clearing it would make a new event if the task were ever reopened.

## Deploying and rolling back on Railway

The README's **Deploy on Railway** section covers the first setup. After that:

- **Deploying:** merge to `main` on GitHub. Railway builds and deploys both services automatically, usually within a few minutes.
- **Rolling back:** in Railway, open the service, then **Deployments**, find the last good deployment and choose **Redeploy**. Do the same for the cron service if it changed. Then fix the problem in GitHub, since the next push deploys again.
- **After changing a variable**, click **Deploy** if Railway asks, so the services pick it up.

## Privacy requests

The Privacy page (`/privacy`) promises an answer within 30 days. Requests arrive at `CONTACT_EMAIL`, as replies to app emails, or through a mail app's Unsubscribe button (which emails `CONTACT_EMAIL` with the subject "Stop NMU Launches emails").

- **"What do you have about me?"** Look at their row in **Users and roles**, and filter the Work table in Airtable by Assigned To to list their tasks. Send them what you find.
- **"Stop emailing me."** If they still work with NMU, talk with them first, since reminders are how tasks get done. Otherwise, **Hand off tasks** to someone else, then **Edit > Deactivate**. Deactivated people get no email.
- **"Delete my information."**
  1. **Hand off tasks** to someone else.
  2. **Edit > Deactivate**.
  3. Open them again (tick **Show inactive people**) and click **Remove personal details**. This replaces their name and email with "Former team member" everywhere in the app, including the history text, removes them from partner access and from any partner contact fields that use their email, and cancels their reminders. Finished work stays, without their name.
  4. If Google Calendar sync is on, remove them as a guest from events on the NMU Launches calendar (see **Google Calendar sync**). Their own calendar feed link is cleared automatically.
  5. Airtable keeps its own change history for a while. If the request needs that gone too, ask Airtable support, or delete and recreate the affected rows.
  6. Reply to say it is done.

Never put sensitive information (health details, anything about program participants) in notes. If someone does, delete the note in Airtable's Activity Log table.

## Changing the Airtable base

The app expects the tables and fields listed in `docs/data-model.md`. Renaming or deleting one of them breaks the parts of the app that use it. Adding fields and tables is safe.

If the code adds new fields, run `python -m jobs.migrate_airtable` to see what it would add, then `--apply`. It only ever adds.
