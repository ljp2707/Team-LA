import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  addNote,
  addReminder,
  addTaskFile,
  addTaskLink,
  assignTask,
  cancelReminder,
  deleteNote,
  getTask,
  setStatus,
  shareNote,
  updateTask,
} from "../api/tasks";
import { removeLink } from "../api/projects";
import type { TaskDetail as Task, TaskStatus } from "../api/types";
import { Avatar } from "../components/ui/Bits";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Dialog } from "../components/ui/Dialog";
import { DateInput, TextInput } from "../components/ui/Field";
import { PageHeader } from "../components/ui/PageHeader";
import { ErrorState, LoadingState } from "../components/ui/States";
import { StatusTag } from "../components/ui/StatusTag";
import { useToast } from "../components/ui/Toast";
import { useApi } from "../hooks/useApi";
import { addDays, formatDate } from "../lib/dates";
import { FileDialog, fileSize } from "../components/FileDialog";
import { LinkDialog } from "../components/LinkDialog";
import { PeoplePicker } from "../components/PeoplePicker";

const SEGMENTS: { value: TaskStatus; label: string }[] = [
  { value: "Not Started", label: "Not started" },
  { value: "In Progress", label: "In progress" },
  { value: "Blocked", label: "Blocked" },
  { value: "Done", label: "Done" },
];

function errorText(caught: unknown) {
  return caught instanceof Error ? caught.message : "That did not work. Please try again.";
}

type Open = null | "link" | "file" | "reminder" | "assign" | "due" | "rename";

export function TaskDetail() {
  const { id = "" } = useParams();
  const toast = useToast();
  const task = useApi(() => getTask(id), [id]);
  const [note, setNote] = useState("");
  const [posting, setPosting] = useState(false);
  const [open, setOpen] = useState<Open>(null);

  if (task.error) return <ErrorState error={task.error} onRetry={task.reload} />;
  if (!task.data) return <LoadingState label="Loading the task" />;
  const t = task.data;
  const close = () => setOpen(null);

  async function changeTo(status: TaskStatus) {
    if (status === t.status) return;
    const before = t.status;
    task.setData((current) => (current ? { ...current, status, display_status: status } : current));
    try {
      await setStatus(t.id, status);
      if (status === "Done") toast.show("Marked done. It is in the project history.");
      await task.reload();
    } catch (caught) {
      task.setData((current) => (current ? { ...current, status: before, display_status: before } : current));
      toast.error(errorText(caught));
    }
  }

  async function post() {
    if (!note.trim()) return;
    setPosting(true);
    try {
      const result = await addNote(t.id, note.trim());
      task.setData((current) => (current ? { ...current, notes: result.notes } : current));
      setNote("");
    } catch (caught) {
      toast.error(errorText(caught));
    } finally {
      setPosting(false);
    }
  }

  const late = t.overdue && t.status !== "Done" && t.status !== "Skipped";
  const subtitle = [t.site || t.project_name, t.program_type].filter(Boolean).join(" · ");
  const done = t.status === "Done" || t.status === "Skipped";

  return (
    <div className="page">
      <PageHeader
        back={{ to: t.back.to, label: t.back.label }}
        title={t.name}
        description={
          <>
            {t.project_id ? <Link to={`/projects/${t.project_id}`}>{subtitle}</Link> : subtitle}
            {late && (
              <>
                {" · "}
                <strong className="is-late">
                  {t.days_late} {t.days_late === 1 ? "day" : "days"} late
                </strong>
              </>
            )}
            {t.one_off && " · Added to this launch only"}
          </>
        }
        action={
          t.can_admin ? (
            <Button variant="outline" onClick={() => setOpen("rename")}>
              Rename
            </Button>
          ) : undefined
        }
      />

      <div className="two-col two-col--task">
        <div className="stack">
          <Card>
            <h2>Status</h2>
            {t.can_edit ? (
              <>
                <div className="segmented segmented--status" role="radiogroup" aria-label="Status">
                  {SEGMENTS.map((s) => (
                    <button
                      key={s.value}
                      type="button"
                      role="radio"
                      aria-checked={t.status === s.value}
                      onClick={() => void changeTo(s.value)}
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
                <p className="muted small">
                  {t.status === "Skipped"
                    ? "This task was skipped. Pick a status to bring it back."
                    : "Marking it done records you and today's date in the project history."}
                </p>
                {t.can_admin && t.status !== "Skipped" && (
                  <button type="button" className="text-button" onClick={() => void changeTo("Skipped")}>
                    Skip this task for this launch
                  </button>
                )}
              </>
            ) : (
              <p>
                <StatusTag status={t.display_status} late={late} />{" "}
                <span className="muted small">Only the person it is assigned to can change this.</span>
              </p>
            )}
            {t.description && <p className="task-description">{t.description}</p>}
          </Card>

          <Card>
            <h2>Notes</h2>
            {t.notes.length === 0 ? (
              <p className="muted">No notes yet.</p>
            ) : (
              <ul className="note-list">
                {t.notes.map((n) => (
                  <li key={n.id}>
                    <Avatar name={n.author} size="sm" />
                    <div>
                      <p className="small">
                        <strong>{n.author}</strong> <span className="muted">· {n.date_text}</span>
                        {t.can_share_notes && (
                          <span className="muted"> · {n.visibility === "Shared" ? "Shared with partners" : "Internal"}</span>
                        )}
                      </p>
                      <p className="pre-line">{n.text}</p>
                      {(n.can_share || n.can_delete) && (
                        <div className="inline-actions">
                          {n.can_share && (
                            <button
                              type="button"
                              className="text-button"
                              onClick={() =>
                                void shareNote(n.id, n.visibility === "Shared" ? "Internal" : "Shared")
                                  .then(() => task.reload())
                                  .catch((caught) => toast.error(errorText(caught)))
                              }
                            >
                              {n.visibility === "Shared" ? "Make internal" : "Share with partners"}
                            </button>
                          )}
                          {n.can_delete && (
                            <button
                              type="button"
                              className="text-button"
                              onClick={() =>
                                void deleteNote(n.id)
                                  .then(() => task.reload())
                                  .catch((caught) => toast.error(errorText(caught)))
                              }
                            >
                              Delete
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {t.can_edit && (
              <form
                className="note-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  void post();
                }}
              >
                <label htmlFor="new-note" className="visually-hidden">
                  Add a note for the team
                </label>
                <textarea
                  id="new-note"
                  className="input textarea"
                  rows={1}
                  placeholder="Add a note for the team"
                  value={note}
                  maxLength={2000}
                  onChange={(e) => setNote(e.target.value)}
                />
                <Button type="submit" disabled={posting || !note.trim()}>
                  {posting ? "Posting" : "Post note"}
                </Button>
              </form>
            )}
          </Card>

          <Card>
            <h2>Links and files</h2>
            {t.links.length > 0 && (
              <ul className="link-list link-list--boxed">
                {t.links.map((link) => (
                  <li key={link.id ?? link.url}>
                    <a href={link.url} target="_blank" rel="noreferrer">
                      <strong>{link.title}</strong>
                      <span className="muted">{link.is_file ? ["File", fileSize(link.file_size)].filter(Boolean).join(" · ") : link.kind}</span>
                    </a>
                    {link.can_remove && link.id && (
                      <button
                        type="button"
                        className="text-button"
                        aria-label={`Remove ${link.title}`}
                        onClick={() =>
                          void removeLink(link.id!)
                            .then(() => task.reload())
                            .catch((caught) => toast.error(errorText(caught)))
                        }
                      >
                        Remove
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
            {t.links.length === 0 && <p className="muted">No links or files yet.</p>}
            {t.can_edit && (
              <div className="inline-actions">
                <Button variant="outline" onClick={() => setOpen("link")}>
                  Attach a Drive or Canva link
                </Button>
                <Button variant="outline" onClick={() => setOpen("file")}>
                  Upload a file or photo
                </Button>
              </div>
            )}
          </Card>
        </div>

        <div className="stack">
          <Card>
            <dl className="facts facts--rows">
              <div>
                <dt>Due</dt>
                <dd>
                  <span className={late ? "is-late" : undefined}>{t.due ? formatDate(t.due, { weekday: true }) : "Not set"}</span>
                  {t.can_admin && !done && (
                    <button type="button" className="text-button" onClick={() => setOpen("due")}>
                      Change
                    </button>
                  )}
                </dd>
              </div>
              <div>
                <dt>Timing</dt>
                <dd>{t.timing || "Not set"}</dd>
              </div>
              <div>
                <dt>Role</dt>
                <dd>{t.role || "None"}</dd>
              </div>
              <div>
                <dt>Assigned to</dt>
                <dd>
                  {t.assignees.length ? t.assignees.map((a) => a.name).join(", ") : "Nobody yet"}
                  {t.can_admin && (
                    <button type="button" className="text-button" onClick={() => setOpen("assign")}>
                      Change
                    </button>
                  )}
                </dd>
              </div>
            </dl>
            {!t.can_admin && <p className="muted small">Only admins can reassign tasks.</p>}
            {t.calendar_url && !done && (
              <a href={t.calendar_url} target="_blank" rel="noreferrer" className="strong-link small">
                Add to Google Calendar
              </a>
            )}
          </Card>

          <Card>
            <h2>Order of work</h2>
            <h3 className="section-label">Needs first</h3>
            {t.needs_first.length === 0 ? (
              <p className="muted small">Nothing. You can start any time.</p>
            ) : (
              <ul className="plain-list">
                {t.needs_first.map((n) => (
                  <li key={n.id} className="split">
                    <Link to={`/tasks/${n.id}`} className="row-title">
                      {n.name}
                    </Link>
                    <StatusTag status={n.status} late={n.overdue} />
                  </li>
                ))}
              </ul>
            )}
            {t.waiting_on_this.length > 0 && (
              <>
                <h3 className="section-label">Waiting on this</h3>
                <ul className="plain-list">
                  {t.waiting_on_this.map((n) => (
                    <li key={n.id} className="split">
                      <Link to={`/tasks/${n.id}`} className="row-title">
                        {n.name}
                      </Link>
                      <StatusTag status={n.status} />
                    </li>
                  ))}
                </ul>
              </>
            )}
            {t.date_warnings.length > 0 && (
              <p className="note-box note-box--late" role="note">
                {t.date_warnings.join(" ")} No dates were moved. Change the date that is wrong.
              </p>
            )}
            {t.risk_note && (
              <p className="note-box note-box--late" role="note">
                {t.risk_note}
              </p>
            )}
          </Card>

          <Card>
            <h2>Reminders</h2>
            <dl className="facts facts--rows">
              {t.reminders.automatic.map((r) => (
                <div key={r.label}>
                  <dt>{r.label}</dt>
                  <dd className="muted">{r.status}</dd>
                </div>
              ))}
              {t.reminders.custom.map((r) => (
                <div key={r.id}>
                  <dt>{r.label}</dt>
                  <dd>
                    <strong>{r.date_text}</strong>
                    {r.status !== "Scheduled" && <span className="muted"> {r.status}</span>}
                    {r.can_cancel && (
                      <button
                        type="button"
                        className="text-button"
                        aria-label={`Cancel reminder on ${r.date_text}`}
                        onClick={() =>
                          void cancelReminder(r.id)
                            .then(() => task.reload())
                            .catch((caught) => toast.error(errorText(caught)))
                        }
                      >
                        Cancel
                      </button>
                    )}
                  </dd>
                </div>
              ))}
            </dl>
            {t.can_set_reminder && !done && (
              <Button variant="outline" onClick={() => setOpen("reminder")}>
                Set a reminder
              </Button>
            )}
          </Card>
        </div>
      </div>

      <LinkDialog
        open={open === "link"}
        onClose={close}
        onSave={async (title, url) => {
          await addTaskLink(t.id, title, url);
          close();
          await task.reload();
        }}
      />
      <FileDialog
        open={open === "file"}
        onClose={close}
        onSave={async (file, title) => {
          await addTaskFile(t.id, file, title);
          close();
          toast.show("File uploaded.");
          await task.reload();
        }}
      />
      <ReminderDialog
        open={open === "reminder"}
        task={t}
        onClose={close}
        onSaved={(reminders) => {
          close();
          task.setData((current) => (current ? { ...current, reminders } : current));
          toast.show("Reminder set. It comes by email in the morning.");
        }}
      />
      {t.can_admin && (
        <>
          <AssignDialog
            open={open === "assign"}
            task={t}
            onClose={close}
            onSaved={() => {
              close();
              toast.show("Reassigned.");
              void task.reload();
            }}
          />
          <DueDialog
            open={open === "due"}
            task={t}
            onClose={close}
            onSaved={() => {
              close();
              toast.show("Due date changed.");
              void task.reload();
            }}
          />
          <RenameDialog
            open={open === "rename"}
            task={t}
            onClose={close}
            onSaved={() => {
              close();
              void task.reload();
            }}
          />
        </>
      )}
    </div>
  );
}

function ReminderDialog({
  open,
  task,
  onClose,
  onSaved,
}: {
  open: boolean;
  task: Task;
  onClose: () => void;
  onSaved: (reminders: Task["reminders"]) => void;
}) {
  const [date, setDate] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const tomorrow = addDays(task.today, 1);

  async function save() {
    if (!date) {
      setError("Pick a date.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onSaved(await addReminder(task.id, date, note.trim()));
      setDate("");
      setNote("");
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      title="Set a reminder"
      description="We email you on that morning. It stops if the task is done first."
      onClose={onClose}
      actions={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => void save()} disabled={busy}>
            {busy ? "Saving" : "Set reminder"}
          </Button>
        </>
      }
    >
      <DateInput label="Send on" value={date} min={tomorrow} onChange={(e) => setDate(e.target.value)} error={error} />
      <TextInput label="Note (optional)" value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />
    </Dialog>
  );
}

function AssignDialog({
  open,
  task,
  onClose,
  onSaved,
}: {
  open: boolean;
  task: Task;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [userIds, setUserIds] = useState<string[]>(task.assignees.map((a) => a.id));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await assignTask(task.id, userIds.filter(Boolean));
      onSaved();
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      title="Assign this task"
      description="Anyone you add gets an email about it, and everyone on the task gets its reminders."
      onClose={onClose}
      actions={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => void save()} disabled={busy}>
            {busy ? "Saving" : "Save"}
          </Button>
        </>
      }
    >
      <PeoplePicker people={task.people} value={userIds} onChange={setUserIds} error={error} />
    </Dialog>
  );
}

function DueDialog({
  open,
  task,
  onClose,
  onSaved,
}: {
  open: boolean;
  task: Task;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [date, setDate] = useState(task.due ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isOpenStatus = (s: string) => s !== "Done" && s !== "Skipped";
  const warnings = date
    ? [
        ...task.needs_first
          .filter((d) => isOpenStatus(d.status) && d.due && d.due > date)
          .map((d) => `This would be due before ${d.name} (${d.due_short}), which it needs first.`),
        ...task.waiting_on_this
          .filter((d) => isOpenStatus(d.status) && d.due && d.due < date)
          .map((d) => `${d.name} (${d.due_short}) waits on this but would be due first.`),
      ]
    : [];

  async function save() {
    if (!date) return;
    setBusy(true);
    setError(null);
    try {
      await updateTask(task.id, { due_date: date });
      onSaved();
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      title="Change the due date"
      description="Only this task moves. To move the whole launch, use Move Day 1 on the project."
      onClose={onClose}
      actions={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => void save()} disabled={busy || !date}>
            {busy ? "Saving" : "Save"}
          </Button>
        </>
      }
    >
      <DateInput label="Due date" value={date} onChange={(e) => setDate(e.target.value)} error={error} />
      {warnings.length > 0 && (
        <div className="note-box note-box--late" role="note">
          {warnings.join(" ")} You can still save it. The other tasks keep their dates.
        </div>
      )}
    </Dialog>
  );
}

function RenameDialog({
  open,
  task,
  onClose,
  onSaved,
}: {
  open: boolean;
  task: Task;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(task.name);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    if (!name.trim()) {
      setError("Give the task a name.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await updateTask(task.id, { name: name.trim() });
      onSaved();
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      title="Rename this task"
      description="Only this launch changes. Edit the template to rename it for future launches."
      onClose={onClose}
      actions={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => void save()} disabled={busy}>
            {busy ? "Saving" : "Save"}
          </Button>
        </>
      }
    >
      <TextInput label="Task name" value={name} maxLength={200} onChange={(e) => setName(e.target.value)} error={error} />
    </Dialog>
  );
}
