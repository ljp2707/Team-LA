import type { TaskStatus } from "../../api/types";
import { Tag } from "./Tag";
import type { TagTone } from "./Tag";

export const STATUS_LABELS: Record<TaskStatus, string> = {
  "Not Started": "Not started",
  "In Progress": "In progress",
  Blocked: "Blocked",
  Done: "Done",
  Skipped: "Skipped",
};

export const STATUS_TONES: Record<TaskStatus, TagTone> = {
  "Not Started": "idle",
  "In Progress": "progress",
  Blocked: "late",
  Done: "done",
  Skipped: "idle",
};

/**
 * A task's status as a tag. Always text, never color alone.
 * `late` shows "Late" for an overdue open task, as on the project page.
 */
export function StatusTag({
  status,
  late = false,
  short = false,
}: {
  status: TaskStatus;
  late?: boolean;
  short?: boolean;
}) {
  if (late && status !== "Done" && status !== "Skipped" && status !== "Blocked") {
    return <Tag tone="late">Late</Tag>;
  }
  const label = short && status === "Not Started" ? "To do" : STATUS_LABELS[status];
  return <Tag tone={STATUS_TONES[status]}>{label}</Tag>;
}
