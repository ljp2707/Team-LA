# Decisions

Where the real Airtable base, the wireframes and the build plan disagreed, these are the choices that were made. The rule was: follow the real base for data and the wireframes for the screens. Each entry says what was decided and why, so NMU can change it later.

## Data (following the real base)

**Due dates are written to Due Date Override.** In the base, the Work table's `Due Date` is a formula: the override if there is one, otherwise `Calculated Due Date`. A formula cannot be written to, so the app always writes `Due Date Override`. Before Day 1 moves, finished tasks that only had a calculated date get their date written into the override first, so they keep it.

**Launch length is stored as Duration (Days).** `End Date` on Session is a formula (Start Date + Duration − 1), so the app saves the number of days and Airtable works out the last day.

**Launches have a new Program Name field.** `Session Name` is a formula ("date - region - site") and cannot be set, so a `Program Name` field was added for names like "Swim Safely Winter 2027".

**The person on a task is Assigned To, not Assignee.** `Assignee` in the base is a lookup of the step's roles. `Assigned To` (a link to Users) is the person, and it is what the app reads and writes.

**One-off tasks use a new One-off checkbox.** The base had an `Is Custom` field on some tables, but it was not clearly about tasks added to one launch, so a dedicated `One-off` field was added and `Is Custom` is left alone.

**Retired steps use the existing Retired checkbox.** The base already had `Retired` on Steps. The app treats it as retired, alongside the new `Retired In Version` field.

**Existing status options were kept as they are.** Session Status uses "Not started", "In progress" and "Complete" (a closed launch is Complete). Roles Status includes "In Active" with a space. New options that did not exist yet (for example the Partner access level and new Activity Log types) are added by Airtable when the app first writes them, because the Airtable API cannot add options to an existing field.

**Some tables are left untouched.** "Templates - >", "Programs - >" and "WIP - >" are dividers in the base and the app does not use them.

**Demo data reuses some real roles.** The seed script linked demo people into the existing Program Manager, Program Assistant and Executive Director roles instead of creating copies. It added Marketing, Operations, Development and Grants, which did not exist. It never changed or deleted an existing row.

**The existing Seattle University launch is treated like any other.** It is an active launch in the base, so it appears on the dashboard and its assignees can get reminder emails once email is switched on. Close it on its project page if it is finished.

## Rules

**Blocked means waiting on an open task.** Any open task that depends on another open task shows as Blocked, whatever its stored status, with "Waiting on …" underneath. This follows the build plan. It means the dashboard's "tasks blocked" count includes tasks that are not due for weeks. If NMU would rather see only tasks someone marked Blocked, change `display_status` in `backend/app/services/logic.py`.

**Dates never move on their own, except with Move Day 1.** Changing one task's date, or adding a task in between two others, does not move the tasks after it. NMU asked for this because moving other people's deadlines silently causes problems. Instead, a task due before a task it needs first shows a warning on its row, on its page, in the date and add-task dialogs, and in a banner on the launch page. The admin decides which date to change.

**A task can have several people.** The base's `Assigned To` already allows more than one person, so the app now uses all of them. Everyone on a task sees it in My Tasks, can update it, and gets its reminders. Places with room for one name show the first person and "and N more". Starting a launch still gives each task the one person who fills its role; add more people on the task afterward.

**Tasks can be added to a closed launch.** Admins can add a task to a launch after it is closed, for example to record follow-up work. Closed launches send no reminders, so the person gets no new-task email either, and the due date can be in the past.

**Overdue follow-up is the weekly digest only.** The midterm left open what happens after a task goes overdue. For now overdue tasks are listed first in the Monday digest and there is no separate overdue email. This is `OVERDUE_FOLLOW_UP` in `backend/app/services/reminders.py`.

**Viewers cannot set reminders.** Viewers are read only, and a reminder is a row the app writes, so they cannot set one. Everyone else who can see a task can set a reminder for themselves.

**Staff cannot skip tasks.** Skipping takes a task out of a launch, so only admins can mark a task Skipped. Staff can choose Not started, In progress, Blocked or Done on their own tasks.

**Partners get "Not found" for other launches.** A partner who opens a launch they are not on sees "Not found" rather than "No access", so the app does not confirm that the launch exists. They never see internal notes or the project history.

**Undoing a Day 1 move.** Only the most recent move can be undone, and only within 24 hours. Each move writes one history row for the launch plus one hidden row per task (sharing a Batch value), which is what Undo uses. The per-task rows do not show in the history list.

**Closing a launch with open tasks.** A launch can be closed once Day 1 has passed. If tasks are still open, the admin can tick "Mark the open tasks as skipped", or leave them as they are so the archive shows them unfinished. Either way the history records it, and custom reminders on skipped tasks are cancelled.

**Changing Day 1 only happens through Move Day 1.** Edit details does not offer Day 1, so the tasks and reminders always move with it.

**New templates start from a copy.** "New template" copies an existing template under a new name, so the timing is already close. There is no blank template.

**Season stats on the home page count closed launches.** "Launched so far" counts launches this year whose Day 1 has passed, including ones that are now Complete.

## Screens (following the wireframes)

**"On track" is green on project cards.** The wireframe shows it green. Green is otherwise kept for Done.

**One label for not started tasks.** The project page wireframe says "To do" and My Tasks says "Not started". The app says "Not started" everywhere so the same status never has two names.

**The project page shows a Team card and a Links card.** The wireframe does not show them, but the build plan needs a place to see who holds each role and to attach project links. They sit under Site and partner and use the same card style.

**Status menus on rows.** Where the person can change a task, the status tag on a row is a small menu, as on My Tasks in the wireframe. Where they cannot, it is a plain tag.

**Template steps show in the template's own order.** Steps are listed in their Sort Order, which admins change with the up and down buttons while editing, not sorted by date.
