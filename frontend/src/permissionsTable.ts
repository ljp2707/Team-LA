/**
 * The "What each level can do" table on the Users page.
 *
 * This mirrors backend/app/permissions.py for display only. The backend rules are
 * the ones that count. If you change a rule there, change the matching row here.
 */

export interface PermissionRow {
  action: string;
  admin: string;
  staff: string;
  partner: string;
}

export const PERMISSION_TABLE: PermissionRow[] = [
  {
    action: "Who",
    admin: "Executive Director, Program Manager",
    staff: "Program Asst, Ops, Marketing, Grants",
    partner: "YMCA staff, swim team leads",
  },
  {
    // can_update_own_tasks, can_edit_task
    action: "Update their own tasks, notes and links",
    admin: "Yes",
    staff: "Yes",
    partner: "Yes",
  },
  {
    // can_view_all_projects, can_view_project
    action: "View projects",
    admin: "All",
    staff: "All, read only",
    partner: "Their program only",
  },
  {
    // can_manage_projects
    action: "Create projects and move Day 1",
    admin: "Yes",
    staff: "No",
    partner: "No",
  },
  {
    // can_assign_tasks
    action: "Assign or change anyone's task",
    admin: "Yes",
    staff: "No",
    partner: "No",
  },
  {
    // can_edit_setup
    action: "Edit templates, users and roles",
    admin: "Yes",
    staff: "No",
    partner: "No",
  },
  {
    // can_see_internal_notes, can_see_archive
    action: "See internal notes and the archive",
    admin: "Yes",
    staff: "Notes only",
    partner: "No",
  },
];
