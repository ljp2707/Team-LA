# Next steps to production

Technical input for NMU's grant application: what NMU Launches does today, what is left before NMU staff and partners rely on it, and what it costs to run.

## What is built

NMU Launches is a web app on NMU's existing Airtable base. Staff sign in with Google. Airtable stays the one place the data lives, so NMU can still see and edit everything there.

All eleven features from the midterm plan work and run locally:

1. **Project creation and auto-timeline.** An admin picks a template (or a past launch), a site and a Day 1. Every task is created with a due date, a role and a person, and the site's details fill in from its profile.
2. **Dependencies and date changes.** Tasks know what they wait on. Moving Day 1 moves every open task and reminder at once, keeps finished tasks as they were, and can be undone.
3. **My Tasks.** Each person sees only their own tasks, grouped by overdue, this week and later, with one-click status and a "Do this first" pointer.
4. **All-projects dashboard.** One card per launch with progress, overdue counts and the next milestone.
5. **Notes and links.** Notes and Google Drive or Canva links on every task, with internal and shared notes.
6. **Email reminders.** Seven days before, on the due date, custom reminders, a Monday digest, and emails for new assignments and new people, sent through Gmail. A daily job sends them and never sends the same email twice.
7. **Project history and archive.** Every change is logged. Closed launches move to an archive with planned and actual dates.
8. **Templates.** Versioned templates: edit a draft, publish it without touching running launches, see the history, and learn from past launches which tasks run late or get skipped.
9. **Users and roles.** Admins add people, manage roles, hand off tasks, and staff use a simpler view.
10. **Partner logins.** YMCA staff and swim team leads can sign in and see only their own program.
11. **Documentation.** A user guide, an admin runbook, a data model and this document.

It has automated tests for its rules (dates, timelines, reminders, permissions and the API), and every page works on a phone.

## What is left

**Deploy it.** The app is ready for Railway, which the code is already set up for, but it has only run on laptops so far. Deploying means creating the Railway project, setting its variables and adding the live address to the Google sign in client. The README walks through it.

**Move everything to NMU-owned accounts.** Today the Google Cloud project and the email sender belong to a student's personal account, and the Airtable tokens belong to individual developers. Before launch, NMU should own the GitHub repository, the Railway project, the Google Cloud project, the sending email address and the Airtable token. The admin runbook lists each one.

**Roll out partner access.** Partner logins work, but NMU still needs to decide which partners to invite first, what they should be able to see, and which notes to share with them. A small pilot with one YMCA and one swim team lead is the suggested start.

**Google verification, only if needed.** Sign in uses basic Google permissions, which need no verification. Sending email uses one sensitive permission, but only for the single sending account, which approves it once. If NMU ever adds more Google permissions (for example reading Calendar or Drive), Google will require a verification review, which takes time and should be planned for.

**Backups of the Airtable base.** Airtable keeps a short history of changes, but NMU should take regular snapshots or exports of the base, and decide how long to keep them, because the base is the only copy of the data.

**Accessibility testing.** The app was built to be usable with a keyboard and screen reader, with labels on every control and statuses that never rely on color alone. It has not yet been tested by people who use assistive technology, and that testing should happen before wider rollout.

**Decisions for NMU.** `docs/decisions.md` lists choices made during the build that NMU may want to change, such as what happens after a task goes overdue and what counts as "blocked".

## Running costs

The app needs two paid services. Check current prices at handoff, because both change.

- **Railway** runs the website and the daily reminder job. It charges on a usage-based plan: a monthly subscription plus the memory, CPU and network used. An app this size, used by a small team, should sit near the bottom of that range.
- **Airtable** holds the data. NMU already uses Airtable. The app does not need an Airtable seat for each staff member, because staff use the app, not Airtable. Check that NMU's plan allows the number of records and the API use the app needs, and the record history NMU wants for backups.

Google sign in and the Gmail API cost nothing at this scale. GitHub is free for this use.
