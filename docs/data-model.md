# Data model

Every Airtable table and field NMU Launches uses, and what it is for. Generated from `backend/app/airtable/schema.py` by `python -m jobs.data_model`. Fields marked *added* were added by `python -m jobs.migrate_airtable`. For the full live base, including fields the app does not use, see `airtable-schema.md`.

## Users

One row per person who can sign in. The Status and Access Level decide who gets in and what they can do.

Used by: Sign in, Users and roles, every assignment.

| Field | What it is for |
|---|---|
| Email Address | The Google email they sign in with. |
| First Name | Shown in the app. |
| Last Name | Shown in the app. |
| Status | Active can sign in. Inactive cannot. |
| Created | When the row was made. |
| Roles | The roles this person holds. One person can hold several. |
| Session | Link to the Session table. |
| Access Level | Admin, Project Lead, Staff, Viewer or Partner. Sets their view and permissions. |
| Work | Link to the Work table. |
| Session Team | Link to the Session Team table. |
| Activity Log | Link to the Activity Log table. |
| Welcome Email Sent *(added)* | Set when the welcome email goes out, so it is sent once. |

## Template List

One row per template (kind of launch), for example Swim Safely.

Used by: Templates, Start a launch.

| Field | What it is for |
|---|---|
| List Name (Unique) | Shown in the app. |
| Status | Inactive templates are hidden on Start a launch. |
| Created | When the row was made. |
| Steps | Link to the Steps table. |
| Session | Link to the Session table. |
| Live Version *(added)* | The version new launches use. |
| Description *(added)* | Read and written by the app. |

## Roles

Jobs such as Operations or Marketing. Template steps and launch teams point at roles, not people.

Used by: Users and roles, Templates, Start a launch.

| Field | What it is for |
|---|---|
| Role Name | Shown in the app. |
| Status | Active, On Hold or In Active. Only active roles can be picked. |
| Users | Link to the Users table. |
| Steps | Link to the Steps table. |
| Templates | Link to the Template List table. |
| Session Team | Link to the Session Team table. |

## Steps

The tasks inside a template, with their timing and default role.

Used by: Templates, Start a launch.

| Field | What it is for |
|---|---|
| Unique | Formula |
| Short Description | Read and written by the app. |
| Long Description | Read and written by the app. |
| Days Before Anchor | How many days before the anchor the task is due. Negative means after. |
| Template | Link to the Template List table. |
| Roles | Link to the Roles table. |
| Depends On | Steps that must be done first. |
| Blocks | Link to the Work table. |
| ID | Worked out by Airtable. The app only reads it. |
| Work | Link to the Work table. |
| Anchor | Start (Day 1) or End (the last day). |
| Retired | Removed from the template. Kept so old launches still make sense. |
| Sort Order *(added)* | The order on the Templates page. |
| Added In Version *(added)* | The template version that added this step. |
| Retired In Version *(added)* | The template version that removed this step. |

## Region

Groups of sites.

Used by: Dashboard region filter.

| Field | What it is for |
|---|---|
| Name | Shown in the app. |
| Site | Link to the Site table. |

## Site

A place where programs run, with its partner contact and shipping details (the site profile).

Used by: Start a launch, Archive search.

| Field | What it is for |
|---|---|
| Region Site | Formula: "Region - Program Name" |
| Program Name | The site's own name, for example Rainier Beach. |
| Program Location | The city, for example Seattle, WA. Fills in Location on a new launch. |
| Region | Link to the Region table. |
| Session | Link to the Session table. |
| Instructors | Link to the Instructors table. |
| Drive Folder | Read and written by the app. |
| Site Type *(added)* | City pool, YMCA pool, Community pool and so on. |
| Partner Contact Name *(added)* | Shown in the app. |
| Partner Contact Email *(added)* | Read and written by the app. |
| Partner Contact Phone *(added)* | Read and written by the app. |
| Shipping Address *(added)* | Read and written by the app. |
| Last Head Coach *(added)* | Shown on Start a launch as a reminder of who coached last season. |

## Session

One launch: one program at one site with a Day 1. The app calls this a project.

Used by: Dashboard, Projects, Project page, Archive.

| Field | What it is for |
|---|---|
| Session Name | A formula in Airtable. The app shows Program Name instead. |
| Start Date | Day 1. Every due date is worked out from it. |
| Duration (Days) | How long the program runs. End Date is worked out from it. |
| End Date | A formula: Start Date plus Duration, minus 1. |
| Site | Link to the Site table. |
| Region Site Session | Read and written by the app. |
| Status | Not started, In progress or Complete. Complete means closed and in the Archive. |
| Program Hours | Read and written by the app. |
| Instructors | Lead instructors |
| Work | Link to the Work table. |
| Template | Link to the Template List table. |
| Project Lead | Link to the Users table. |
| Timeline Generated At | Read and written by the app. |
| Session Team | Link to the Session Team table. |
| Activity Log | Link to the Activity Log table. |
| Drive Folder | Read and written by the app. |
| Lessons Learned | Read and written by the app. |
| Program Name *(added)* | The launch's name, for example Swim Safely Winter 2027. |
| Site Type *(added)* | Read and written by the app. |
| Location *(added)* | Read and written by the app. |
| Partner Contact Name *(added)* | Shown in the app. |
| Partner Contact Email *(added)* | Read and written by the app. |
| Partner Contact Phone *(added)* | Read and written by the app. |
| Shipping Address *(added)* | Read and written by the app. |
| Template Version *(added)* | The template version this launch was made from. Publishing a new version never changes it. |
| Created From *(added)* | The past launch it was copied from, if any. |
| Closed Date *(added)* | When an admin closed it. |
| Partners *(added)* | Partner users who can see this launch. |

## Instructors

Lead instructors, linked to sites and launches.

Used by: Start a launch, project cards.

| Field | What it is for |
|---|---|
| Instructor Name | Shown in the app. |
| Site | Link to the Site table. |
| Email | Read and written by the app. |
| Session | Link to the Session table. |

## Work

One task in one launch, made from a template step or added as a one-off.

Used by: My Tasks, Task page, Project page, reminders.

| Field | What it is for |
|---|---|
| Unique | Formula |
| Steps | Link to the Steps table. |
| Session | Link to the Session table. |
| Start Date (from Session) | Worked out by Airtable. The app only reads it. |
| Calculated Due Date | Formula |
| Due Date | A formula: the override if there is one, otherwise the calculated date. |
| Due Date Override | The due date the app writes. Moving Day 1 and changing a due date both write here. |
| Completed Date | Set when the task is marked Done. |
| Assignee | A lookup of the step's roles, not a person. The app does not use it for assignment. |
| Notes | A notes field from the original base. The app keeps notes in the Activity Log instead. |
| Assigned To | The people doing the task. Usually one, but can be several; each gets the reminders. |
| Task Name | Shown in the app. |
| Anchor | Text: Start or End |
| Days Before Anchor | Read and written by the app. |
| Status | Not Started, In Progress, Blocked, Done or Skipped. |
| End Date (from Session) | Worked out by Airtable. The app only reads it. |
| Activity Log | Link to the Activity Log table. |
| Depends On | Tasks that must be done first. An open task waiting on an open task shows as Blocked. |
| Blocks | The other side of Depends On |
| Resource Link | A single link field from the original base. New links go in the Links table. |
| Role *(added)* | The role responsible for the task. |
| One-off *(added)* | Added to this launch only, not from the template. |
| Sort Order *(added)* | Read and written by the app. |
| Completed By *(added)* | Who marked it Done. |
| Calendar Event ID *(added)* | The task's Google Calendar event. Written only by the Airtable calendar automations; the app reads it and never writes it. |
| Calendar Synced Key *(added)* | What the calendar event showed when it was last written. Written only by the Airtable calendar automations. |
| Calendar Last Synced | Last modified time of the two calendar fields, made by hand. Shown when hovering over a task's calendar mark. |

## Session Team

Who fills each role on one launch.

Used by: Start a launch, hand-off, reminders when a task has no assignee.

| Field | What it is for |
|---|---|
| ID | Worked out by Airtable. The app only reads it. |
| Session | Link to the Session table. |
| Role | Link to the Roles table. |
| User | Link to the Users table. |
| Assignment | Read and written by the app. |

## Activity Log

Every change and every note. Notes are rows with Type Note.

Used by: Project history, notes, Move Day 1 undo, Archive.

| Field | What it is for |
|---|---|
| ID | Worked out by Airtable. The app only reads it. |
| Session | Link to the Session table. |
| Work | Link to the Work table. |
| Author | Link to the Users table. |
| Type | What happened: Status Change, Date Change, Note, Reassignment and so on. |
| Text | Read and written by the app. |
| From | Read and written by the app. |
| To | Read and written by the app. |
| Created | When the row was made. |
| Visibility *(added)* | Internal or Shared. Partners only see Shared notes. |
| Batch *(added)* | Groups the rows of one Day 1 move, so it can be undone. |

## Links

Google Drive, Canva and other links on tasks and launches.

Used by: Task page, Project page.

| Field | What it is for |
|---|---|
| Title | Primary field |
| URL | Read and written by the app. |
| Kind | Google Drive, Canva or Other, worked out from the address. |
| Work | Link to the Work table. |
| Session | Link to the Session table. |
| Added By | Link to the Users table. |
| File | Attachment. Only filled for Kind File, uploaded from someone's computer |

## Reminders

Custom reminders people set, and a log of every reminder email sent, failed or skipped.

Used by: Reminders panel, the daily job.

| Field | What it is for |
|---|---|
| Name | Primary field |
| Work | Link to the Work table. |
| Recipient | Link to the Users table. |
| Kind | 7 Days Before, Due Date, Custom, Weekly Digest, Assignment or Welcome. |
| Send On | Read and written by the app. |
| Status | Scheduled, Sent, Failed, Skipped or Cancelled. A Sent row stops the same email going out twice. |
| Sent At | Read and written by the app. |
| Error | Read and written by the app. |
| Created By | Link to the Users table. |
| Note | Read and written by the app. |

## Template Versions

A frozen copy of a template's steps for each published version, plus the current draft.

Used by: Templates: drafts, publishing, version history.

| Field | What it is for |
|---|---|
| Name | Primary field |
| Template | Link to the Template List table. |
| Version | Read and written by the app. |
| Status | Draft, Live or Retired. |
| Steps JSON | Every step in that version, saved as JSON. |
| Change Note | Read and written by the app. |
| Published At | Read and written by the app. |
| Published By | Link to the Users table. |
