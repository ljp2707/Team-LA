import { Link } from "react-router-dom";
import type { TaskRow as Task, TaskStatus } from "../api/types";
import { setStatus } from "../api/tasks";
import { StatusMenu } from "./ui/StatusMenu";
import { StatusTag } from "./ui/StatusTag";
import { formatDate } from "../lib/dates";

const isFinished = (status: TaskStatus) => status === "Done" || status === "Skipped";

/**
 * A small calendar mark after a task's name when the Airtable automation has put
 * it on the shared NMU Google Calendar. The app never creates or edits the event.
 */
function CalendarMark({ task }: { task: Task }) {
  if (!task.on_calendar) return null;
  const synced = task.calendar_last_synced
    ? new Date(task.calendar_last_synced).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        timeZone: "America/Los_Angeles",
      })
    : null;
  const label = `On the NMU Google Calendar${synced ? `, last updated ${synced}` : ""}`;
  return (
    <span className="calendar-mark" title={label}>
      <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
        <rect x="1" y="2" width="10" height="9" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.3" />
        <path d="M1 5h10M4 1v2.2M8 1v2.2" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
      </svg>
      <span className="visually-hidden">{label}</span>
    </span>
  );
}

/**
 * Change a task's status right away on screen, then save it.
 * If saving fails the old status comes back and the error is shown.
 */
export async function changeStatus(
  task: Task,
  status: TaskStatus,
  update: (id: string, change: Partial<Task> | null, saved?: Task) => void,
  onError: (message: string) => void,
) {
  const before = { status: task.status, display_status: task.display_status };
  update(task.id, { status, display_status: status });
  try {
    const saved = await setStatus(task.id, status);
    update(task.id, null, saved);
  } catch (caught) {
    update(task.id, before);
    onError(caught instanceof Error ? caught.message : "That status did not save.");
  }
}

/**
 * A row on My Tasks: a done circle, the task, its due date and a status menu.
 * Under a launch heading (a person's page), pass showProject={false} to show the
 * task's role instead of repeating the launch name.
 */
export function MyTaskRow({
  task,
  onStatus,
  showProject = true,
}: {
  task: Task;
  onStatus: (task: Task, status: TaskStatus) => void;
  showProject?: boolean;
}) {
  const done = isFinished(task.status);
  const context = showProject ? [task.site || task.project_name, task.program_type] : [task.role];
  const details = [
    ...context,
    task.shared_with.length > 0 ? `shared with ${task.shared_with.join(", ")}` : null,
    task.one_off ? "added to this launch" : null,
  ].filter(Boolean);
  const subtitle = task.waiting_text ? (
    <span className="row-sub is-late">{task.waiting_text}</span>
  ) : details.length > 0 ? (
    <span className="row-sub">{details.join(" · ")}</span>
  ) : null;
  return (
    <li className={`task-row${done ? " is-done" : ""}`}>
      {task.can_edit ? (
        <button
          type="button"
          className={`check${done ? " is-checked" : ""}`}
          aria-pressed={task.status === "Done"}
          aria-label={task.status === "Done" ? `Mark ${task.name} not done` : `Mark ${task.name} done`}
          onClick={() => onStatus(task, task.status === "Done" ? "In Progress" : "Done")}
        >
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
            <path d="M3 7.5 6 10.5 11 4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
        </button>
      ) : (
        <span className="check check--static" aria-hidden="true" />
      )}
      <div className="row-main">
        <span>
          <Link to={`/tasks/${task.id}`} className="row-title">
            {task.name}
          </Link>
          <CalendarMark task={task} />
        </span>
        {subtitle}
      </div>
      <span className={`row-due${task.overdue ? " is-late" : ""}`}>
        {task.status === "Done" && task.completed ? `Done ${formatDate(task.completed)}` : task.due_text}
      </span>
      <StatusMenu
        status={task.display_status}
        taskName={task.name}
        canEdit={task.can_edit}
        onChange={(status) => onStatus(task, status)}
      />
    </li>
  );
}

/** A row on the project page: status tag, task, role and person, due date. */
export function ProjectTaskRow({
  task,
  onStatus,
}: {
  task: Task;
  onStatus: (task: Task, status: TaskStatus) => void;
}) {
  const late = task.overdue && !isFinished(task.status);
  const blocked = task.display_status === "Blocked";
  const note = task.date_warning
    ? task.date_warning
    : task.waiting_text
    ? task.waiting_text
    : late && task.dependents > 0
      ? `${task.dependents} ${task.dependents === 1 ? "task depends" : "tasks depend"} on this`
      : task.one_off
        ? "Added to this launch only"
        : !task.assignee
          ? "Needs an owner"
          : null;
  const noteLate = Boolean(task.date_warning || task.waiting_text) || (late && task.dependents > 0);
  const names = (task.assignees ?? []).map((a) => a.name);
  const people = names.length > 2 ? `${names[0]} and ${names.length - 1} more` : names.join(" and ");
  const who = [task.role, people].filter(Boolean).join(" · ") || "No owner yet";

  return (
    <li className={`project-row${blocked ? " is-blocked" : ""}${task.status === "Done" ? " is-done" : ""}`}>
      <span className="project-row-status">
        {task.can_edit ? (
          <StatusMenu
            status={task.display_status}
            taskName={task.name}
            canEdit
            onChange={(status) => onStatus(task, status)}
          />
        ) : (
          <StatusTag status={task.display_status} late={late} />
        )}
      </span>
      <div className="row-main">
        <span>
          <Link to={`/tasks/${task.id}`} className="row-title">
            {task.name}
          </Link>
          <CalendarMark task={task} />
        </span>
        {note && <span className={`row-sub${noteLate ? " is-late" : ""}`}>{note}</span>}
      </div>
      <span className="row-who">{who}</span>
      <span className={`row-due${late ? " is-late" : ""}`}>
        {late && <span className="visually-hidden">Late, due </span>}
        {task.due_short}
      </span>
    </li>
  );
}
