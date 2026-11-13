/** Shapes the backend returns. Every computed field is worked out on the server. */

export type TaskStatus = "Not Started" | "In Progress" | "Blocked" | "Done" | "Skipped";

export interface TaskRow {
  id: string;
  name: string;
  project_id: string | null;
  project_name: string;
  site: string;
  program_type: string;
  status: TaskStatus;
  display_status: TaskStatus;
  due: string | null;
  due_text: string;
  due_short: string;
  overdue: boolean;
  days_late: number;
  waiting_text: string | null;
  /** Set when this task is due before a task it needs first. Dates never move on their own. */
  date_warning: string | null;
  waiting_on: { id: string; name: string; assignee: string | null }[];
  at_risk: boolean;
  dependents: number;
  one_off: boolean;
  role: string | null;
  role_id: string | null;
  assignee: { id: string; name: string } | null;
  /** Everyone on the task. `assignee` is the first of them. */
  assignees: { id: string; name: string }[];
  shared_with: string[];
  can_edit: boolean;
  phase: string;
  completed: string | null;
  /** True once the Airtable automation has put this task on the shared Google Calendar. */
  on_calendar: boolean;
  /** When the automation last wrote the event (ISO date-time), if ever. */
  calendar_last_synced: string | null;
}

export interface MilestoneRef {
  id: string;
  name: string;
  due_text: string;
}

export interface ProjectCard {
  id: string;
  name: string;
  site: string;
  site_id: string | null;
  region: string | null;
  region_id: string | null;
  program_type: string;
  template_id: string | null;
  site_type: string | null;
  day_one: string | null;
  day_one_text: string;
  end_date: string | null;
  complete: number;
  task_count: number;
  overdue: number;
  blocked: number;
  needs_owner: number;
  next_milestone: MilestoneRef | null;
  lead_instructor: string | null;
  status: string | null;
  closed: boolean;
  closed_date: string | null;
}

export interface ProjectList {
  projects: ProjectCard[];
  summary: {
    active: number;
    overdue: number;
    blocked: number;
    needs_owner: number;
    next_day_one: { date: string; text: string; site: string; project_id: string } | null;
  };
  regions: { id: string; name: string }[];
  program_types: string[];
}

export interface LinkItem {
  id: string | null;
  title: string;
  url: string;
  kind: string;
  /** Uploaded from someone's computer. url then opens it through the app. */
  is_file: boolean;
  file_name: string | null;
  file_size: number | null;
  added_by: string | null;
  can_remove: boolean;
}

export interface HistoryEntry {
  id: string;
  author: string;
  type: string;
  text: string;
  from: string;
  to: string;
  date_text: string;
  created: string | null;
}

export interface ProjectEdit {
  name: string;
  site_id: string | null;
  site_type: string | null;
  day_one: string | null;
  end_date: string | null;
  program_hours: string;
  location: string;
  instructor_ids: string[];
  partner_name: string;
  partner_email: string;
  partner_phone: string;
  shipping_address: string;
  drive_folder: string;
  partner_ids: string[];
}

export interface ProjectDetail extends ProjectCard {
  template_version: number | null;
  program_hours: string;
  location: string;
  partner: { name: string; email: string; phone: string };
  shipping_address: string;
  drive_folder: string;
  groups: { phase: string; tasks: TaskRow[] }[];
  links: LinkItem[];
  history: HistoryEntry[];
  history_count: number;
  can_see_history: boolean;
  team: { role_id: string; role: string | null; user_id: string; user: string | null }[];
  partners: { id: string; name: string | null }[];
  open_tasks: number;
  can_manage: boolean;
  can_delete: boolean;
  can_export: boolean;
  can_close: boolean;
  edit: ProjectEdit | null;
}

export interface Note {
  id: string;
  author: string;
  author_initial: string;
  date_text: string;
  created: string | null;
  text: string;
  visibility: "Internal" | "Shared";
  can_delete: boolean;
  can_share: boolean;
}

export interface ReminderPanel {
  automatic: { label: string; status: string }[];
  custom: {
    id: string;
    label: string;
    date: string | null;
    date_text: string;
    status: string;
    note: string;
    can_cancel: boolean;
  }[];
}

export interface TaskDetail extends TaskRow {
  description: string;
  timing: string;
  site_type: string | null;
  day_one: string | null;
  needs_first: { id: string; name: string; status: TaskStatus; overdue: boolean; due: string | null; due_short: string }[];
  waiting_on_this: { id: string; name: string; status: TaskStatus; due: string | null; due_short: string }[];
  date_warnings: string[];
  risk_note: string | null;
  notes: Note[];
  links: LinkItem[];
  reminders: ReminderPanel;
  calendar_url: string | null;
  can_admin: boolean;
  can_set_reminder: boolean;
  can_share_notes: boolean;
  back: { label: string; to: string };
  people: { id: string; name: string }[];
  project_tasks: { id: string; name: string }[];
  today: string;
}

export interface MyTasks {
  groups: {
    overdue: TaskRow[];
    this_week: TaskRow[];
    later: TaskRow[];
    done_recently: TaskRow[];
  };
  counts: { overdue: number; this_week: number; open: number };
  projects: { id: string; name: string }[];
  do_this_first: { id: string; name: string; reason: string } | null;
  can_edit: boolean;
}

export interface MyReminder {
  date: string;
  when: string;
  text: string;
  task_id: string | null;
  sent: boolean;
}

export interface Site {
  id: string;
  name: string;
  site_type: string | null;
  location: string;
  region: string | null;
  region_id: string | null;
  partner_name: string;
  partner_email: string;
  partner_phone: string;
  shipping_address: string;
  last_head_coach: string;
  drive_folder: string;
}

export interface PreviewTask {
  key: string;
  name: string;
  due: string | null;
  due_text: string;
  group: string;
  role_id: string | null;
  role: string | null;
  user_id: string | null;
  user: string | null;
  override: string | null;
  one_off: boolean;
  after: string[];
}

export interface ProjectPreview {
  template_id: string | null;
  template_name: string | null;
  from_project: { id: string; name: string; day_one: string | null } | null;
  count: number;
  tasks: PreviewTask[];
  first: number;
  last_task: { name: string; due_text: string } | null;
  roles: {
    role_id: string;
    role: string;
    candidates: { id: string; name: string }[];
    user_id: string | null;
  }[];
  needs_owner: number;
}

export interface TemplateSummary {
  id: string;
  name: string;
  status: string;
  active: boolean;
  live_version: number;
  description: string;
  task_count: number;
  lead_text: string;
  has_draft: boolean;
}

export interface TemplateStep {
  key: string;
  name: string;
  description: string;
  anchor: "Start" | "End";
  days_before: number;
  role_id: string | null;
  depends_on: string[];
  when: string;
  timing: string;
  role: string | null;
  needs_first: string[];
  note: string | null;
}

export interface TemplateDetail {
  id: string;
  name: string;
  status: string;
  active: boolean;
  description: string;
  live_version: number;
  steps: TemplateStep[];
  draft: { id: string; version: number; steps: TemplateStep[]; removed: string[] } | null;
  projects_on_live: { id: string; site: string; name: string }[];
  roles: { id: string; name: string }[];
}

export interface TemplateVersion {
  id: string | null;
  version: number;
  status: string | null;
  published_at: string | null;
  published_text: string | null;
  published_by: string | null;
  change_note: string;
  task_count: number;
  steps: TemplateStep[];
}

export interface InsightItem {
  step_id?: string;
  name: string;
  count: number;
  text: string;
  days_before?: number;
  in_template?: boolean;
}

export interface Insights {
  launches: number;
  often_late: InsightItem[];
  often_skipped: InsightItem[];
  often_added: InsightItem[];
}

export interface Person {
  id: string;
  name: string;
  first_name: string;
  last_name: string;
  email: string;
  access_level: string | null;
  status: string | null;
  active: boolean;
  roles: { id: string; name: string | null }[];
  open_tasks: number;
}

/** One active launch on a person's page, with their open tasks on it. */
export interface PersonLaunch {
  id: string;
  name: string;
  site: string;
  program_type: string;
  day_one: string | null;
  /** Their roles on the launch team, if any. */
  roles: string[];
  tasks: TaskRow[];
  /** How many of their tasks on this launch are already done or skipped. */
  done: number;
}

export interface PersonWork {
  person: Person;
  launches: PersonLaunch[];
}

export interface PeopleList {
  people: Person[];
  counts: { people: number; roles: number };
  roles: { id: string; name: string }[];
  access_levels: string[];
}

export interface RoleRow {
  id: string;
  name: string;
  status: string;
  active: boolean;
  people: number;
  steps: number;
}

export interface HandOffPreview {
  count: number;
  tasks: string[];
  preview: string;
  team_rows: number;
  button: string;
  moved?: number;
}

export interface ArchiveRow {
  id: string;
  name: string;
  site: string;
  program_type: string;
  day_one: string | null;
  day_one_text: string;
  on_time: number | null;
}

export interface ArchiveDetail extends ArchiveRow {
  subtitle: string;
  counts: { tasks: number; late: number; skipped: number; added: number };
  tasks: {
    id: string;
    name: string;
    label: string;
    tone: "done" | "late" | "idle" | "progress";
    planned: string;
    actual: string;
    actual_late: boolean;
    done_by: string | null;
  }[];
  history: HistoryEntry[];
}

export interface DayOneResult {
  moved_tasks: number;
  kept_tasks: number;
  moved_reminders: number;
  batch?: string;
  delta_days?: number;
  message: string;
}
