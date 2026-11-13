import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  addOneOff,
  addProjectFile,
  addProjectLink,
  closeProject,
  deleteProject,
  getProject,
  listInstructors,
  listSites,
  moveDayOne,
  projectHistory,
  removeLink,
  reopenProject,
  undoDayOne,
  updateProject,
} from "../api/projects";
import { templateFromProject } from "../api/templates";
import type { DayOneResult, HistoryEntry, ProjectDetail as Project, TaskRow, TaskStatus } from "../api/types";
import { listPeople, listRoles } from "../api/users";
import { useAuth } from "../auth/AuthContext";
import { checkDetails, ProjectFields } from "../components/ProjectFields";
import type { DetailsDraft } from "../components/ProjectFields";
import { changeStatus, ProjectTaskRow } from "../components/TaskRow";
import { SectionLabel, StatTile, UndoBanner } from "../components/ui/Bits";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Dialog } from "../components/ui/Dialog";
import { DateInput, Select, TextInput } from "../components/ui/Field";
import { PageHeader } from "../components/ui/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/States";
import { Tag } from "../components/ui/Tag";
import { useToast } from "../components/ui/Toast";
import { FileDialog, fileSize } from "../components/FileDialog";
import { LinkDialog } from "../components/LinkDialog";
import { PeoplePicker } from "../components/PeoplePicker";
import { useApi } from "../hooks/useApi";
import { formatDate, todayIso } from "../lib/dates";

type Open = null | "move" | "oneoff" | "edit" | "close" | "delete" | "history" | "link" | "file" | "template";

function errorText(caught: unknown) {
  return caught instanceof Error ? caught.message : "That did not work. Please try again.";
}

export function ProjectDetail() {
  const { id = "" } = useParams();
  const { me } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const project = useApi(() => getProject(id), [id]);
  const [open, setOpen] = useState<Open>(null);
  const [moved, setMoved] = useState<DayOneResult | null>(null);
  const [undoing, setUndoing] = useState(false);

  if (project.error) return <ErrorState error={project.error} onRetry={project.reload} />;
  if (!project.data) return <LoadingState label="Loading the launch" />;
  const p = project.data;
  const close = () => setOpen(null);

  function update(taskId: string, change: Partial<TaskRow> | null, saved?: TaskRow) {
    project.setData((current) =>
      current
        ? {
            ...current,
            groups: current.groups.map((g) => ({
              ...g,
              tasks: g.tasks.map((t) => (t.id === taskId ? (saved ?? { ...t, ...change }) : t)),
            })),
          }
        : current,
    );
  }

  function onStatus(task: TaskRow, status: TaskStatus) {
    void changeStatus(task, status, update, toast.error).then(() => void project.reload());
  }

  async function undo() {
    if (!moved?.batch) return;
    setUndoing(true);
    try {
      const result = await undoDayOne(p.id, moved.batch);
      setMoved(null);
      toast.show(result.message);
      await project.reload();
    } catch (caught) {
      toast.error(errorText(caught));
    } finally {
      setUndoing(false);
    }
  }

  const back = me?.view === "admin" ? { to: p.closed ? "/archive" : "/dashboard", label: p.closed ? "Archive" : "Dashboard" } : { to: "/projects", label: me?.view === "partner" ? "Your program" : "Projects" };
  const subtitle = [p.program_type, p.site_type, p.template_version ? `Template v${p.template_version}` : null]
    .filter(Boolean)
    .join(" · ");
  const taskCount = p.groups.reduce((sum, g) => sum + g.tasks.length, 0);
  const dateProblems = p.groups.flatMap((g) => g.tasks).filter((t) => t.date_warning);

  return (
    <div className="page">
      <PageHeader
        back={back}
        title={p.site || p.name}
        description={
          <>
            {subtitle}
            {p.closed && (
              <>
                {" "}
                <Tag tone="done">Closed {p.closed_date ? formatDate(p.closed_date) : ""}</Tag>
              </>
            )}
          </>
        }
        action={
          p.can_manage && !p.closed ? (
            <>
              <Button variant="outline" onClick={() => setOpen("move")}>
                Move Day 1
              </Button>
              <Button onClick={() => setOpen("oneoff")}>Add task</Button>
            </>
          ) : p.can_manage && p.closed ? (
            <>
              <Button variant="outline" onClick={() => setOpen("template")}>
                Save as a template
              </Button>
              <Button variant="outline" onClick={() => setOpen("oneoff")}>
                Add task
              </Button>
              <Button to={`/projects/new?from=${p.id}`}>Start a new launch from this</Button>
            </>
          ) : undefined
        }
      />

      <Card className="stat-strip">
        <StatTile value={p.day_one ? formatDate(p.day_one) : "Not set"} label="Day 1" />
        <StatTile value={`${p.complete}%`} label="Complete" />
        <StatTile value={p.overdue} label="Overdue" tone={p.overdue ? "late" : undefined} />
        <StatTile value={<span className="stat-small">{p.program_hours || "Not set"}</span>} label="Hours" />
        <StatTile value={<span className="stat-small">{p.lead_instructor || "Not set"}</span>} label="Lead instructor" />
      </Card>

      {dateProblems.length > 0 && (
        <div className="note-box note-box--late" role="note">
          <strong>
            {dateProblems.length === 1
              ? "1 task is due before a task it needs first."
              : `${dateProblems.length} tasks are due before a task they need first.`}
          </strong>{" "}
          No dates were moved. Open each one to fix the date that is wrong:{" "}
          {dateProblems.map((t, i) => (
            <span key={t.id}>
              {i > 0 && ", "}
              <Link to={`/tasks/${t.id}`}>{t.name}</Link>
            </span>
          ))}
          .
        </div>
      )}

      {moved && (
        <UndoBanner message={moved.message} onUndo={moved.batch ? () => void undo() : undefined} onDismiss={() => setMoved(null)} busy={undoing} />
      )}

      <div className="two-col">
        <Card className="task-card">
          {taskCount === 0 ? (
            <EmptyState title="No tasks yet">{p.can_manage ? "Add a task to get started." : "An admin has not added tasks yet."}</EmptyState>
          ) : (
            p.groups.map(
              (group) =>
                group.tasks.length > 0 && (
                  <section key={group.phase} className="task-group" aria-label={group.phase}>
                    <SectionLabel>{group.phase}</SectionLabel>
                    <ul className="rows">
                      {group.tasks.map((task) => (
                        <ProjectTaskRow key={task.id} task={task} onStatus={onStatus} />
                      ))}
                    </ul>
                  </section>
                ),
            )
          )}
        </Card>

        <div className="stack">
          <Card>
            <h2>Site and partner</h2>
            <dl className="facts">
              <div>
                <dt>Partner contact</dt>
                <dd>
                  {[p.partner.name, p.partner.email, p.partner.phone].filter(Boolean).join(", ") || "Not set"}
                </dd>
              </div>
              <div>
                <dt>Ships to</dt>
                <dd className="pre-line">{p.shipping_address || "Not set"}</dd>
              </div>
              {p.location && (
                <div>
                  <dt>Location</dt>
                  <dd>{p.location}</dd>
                </div>
              )}
              {p.partners.length > 0 && (
                <div>
                  <dt>Partner access</dt>
                  <dd>{p.partners.map((x) => x.name).join(", ")}</dd>
                </div>
              )}
            </dl>
            {p.drive_folder && (
              <a href={p.drive_folder} target="_blank" rel="noreferrer" className="strong-link">
                Open Google Drive folder
              </a>
            )}
            {p.can_manage && (
              <div className="card-actions">
                <Button variant="outline" size="sm" onClick={() => setOpen("edit")}>
                  Edit details
                </Button>
                {p.can_close && (
                  <Button variant="outline" size="sm" onClick={() => setOpen("close")}>
                    Close launch
                  </Button>
                )}
                {p.closed && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      void reopenProject(p.id)
                        .then(() => {
                          toast.show("Launch reopened.");
                          return project.reload();
                        })
                        .catch((caught) => toast.error(errorText(caught)))
                    }
                  >
                    Reopen
                  </Button>
                )}
                {p.can_delete && (
                  <Button variant="danger" size="sm" onClick={() => setOpen("delete")}>
                    Delete launch
                  </Button>
                )}
              </div>
            )}
          </Card>

          {p.team.length > 0 && me?.view !== "partner" && (
            <Card>
              <h2>Team</h2>
              <dl className="facts facts--rows">
                {p.team.map((t) => (
                  <div key={`${t.role_id}-${t.user_id}`}>
                    <dt>{t.role ?? "Role"}</dt>
                    <dd>{t.user ?? "No one yet"}</dd>
                  </div>
                ))}
              </dl>
            </Card>
          )}

          <Card>
            <h2>Links and files</h2>
            {p.links.length === 0 ? (
              <p className="muted">No links or files yet.</p>
            ) : (
              <ul className="link-list">
                {p.links.map((link) => (
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
                            .then(() => project.reload())
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
            {p.can_manage && (
              <div className="inline-actions">
                <Button variant="outline" size="sm" onClick={() => setOpen("link")}>
                  Add a link
                </Button>
                <Button variant="outline" size="sm" onClick={() => setOpen("file")}>
                  Upload a file
                </Button>
              </div>
            )}
          </Card>

          {p.can_see_history && (
            <Card>
              <div className="split">
                <h2>History</h2>
                {p.history_count > p.history.length && (
                  <button type="button" className="text-button strong-link" onClick={() => setOpen("history")}>
                    See all
                  </button>
                )}
              </div>
              {p.history.length === 0 ? (
                <p className="muted">Nothing has happened yet.</p>
              ) : (
                <HistoryList entries={p.history} />
              )}
            </Card>
          )}
        </div>
      </div>

      {p.can_manage && (
        <>
          <MoveDayOneDialog
            open={open === "move"}
            project={p}
            onClose={close}
            onMoved={(result) => {
              close();
              setMoved(result);
              void project.reload();
            }}
          />
          <OneOffDialog
            open={open === "oneoff"}
            project={p}
            onClose={close}
            onAdded={(name, warnings) => {
              close();
              toast.show(warnings.length ? `Added ${name}. ${warnings.join(" ")} No dates were moved.` : `Added ${name}.`);
              void project.reload();
            }}
          />
          <EditDialog
            open={open === "edit"}
            project={p}
            onClose={close}
            onSaved={(saved) => {
              close();
              project.setData(saved);
              toast.show("Saved.");
            }}
          />
          <CloseDialog
            open={open === "close"}
            project={p}
            onClose={close}
            onClosed={() => {
              close();
              toast.show("Launch closed. It is in the archive now.");
              void project.reload();
            }}
          />
          <LinkDialog
            open={open === "link"}
            onClose={close}
            onSave={async (title, url) => {
              await addProjectLink(p.id, title, url);
              close();
              await project.reload();
            }}
          />
          <FileDialog
            open={open === "file"}
            onClose={close}
            onSave={async (file, title) => {
              await addProjectFile(p.id, file, title);
              close();
              toast.show("File uploaded.");
              await project.reload();
            }}
          />
          <TemplateDialog open={open === "template"} project={p} onClose={close} />
        </>
      )}
      {p.can_delete && (
        <DeleteDialog
          open={open === "delete"}
          project={p}
          onClose={close}
          onDeleted={(name) => {
            close();
            toast.show(`Deleted ${name}.`);
            navigate(back.to, { replace: true });
          }}
        />
      )}
      {p.can_see_history && <HistoryDialog open={open === "history"} projectId={p.id} onClose={close} />}
    </div>
  );
}

function HistoryList({ entries }: { entries: HistoryEntry[] }) {
  return (
    <ul className="history-list">
      {entries.map((entry) => (
        <li key={entry.id}>
          <p>
            <strong>{entry.author}</strong> {entry.text}
          </p>
          <span className="muted small">{entry.date_text}</span>
        </li>
      ))}
    </ul>
  );
}

function HistoryDialog({ open, projectId, onClose }: { open: boolean; projectId: string; onClose: () => void }) {
  const [page, setPage] = useState(1);
  const history = useApi(() => (open ? projectHistory(projectId, page) : Promise.resolve(null)), [open, projectId, page]);
  const data = history.data;
  return (
    <Dialog open={open} title="History" onClose={onClose} wide>
      {history.error ? (
        <ErrorState error={history.error} onRetry={history.reload} />
      ) : !data ? (
        <LoadingState />
      ) : (
        <>
          <HistoryList entries={data.entries} />
          {data.pages > 1 && (
            <div className="pager">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                Newer
              </Button>
              <span className="muted small">
                Page {data.page} of {data.pages}
              </span>
              <Button variant="outline" size="sm" disabled={page >= data.pages} onClick={() => setPage(page + 1)}>
                Older
              </Button>
            </div>
          )}
        </>
      )}
    </Dialog>
  );
}

function MoveDayOneDialog({
  open,
  project,
  onClose,
  onMoved,
}: {
  open: boolean;
  project: Project;
  onClose: () => void;
  onMoved: (result: DayOneResult) => void;
}) {
  const [date, setDate] = useState("");
  const [preview, setPreview] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function check(value: string) {
    setDate(value);
    setPreview(null);
    setError(null);
    if (!value || value === project.day_one) return;
    try {
      const result = await moveDayOne(project.id, value, true);
      setPreview(result.message);
    } catch (caught) {
      setError(errorText(caught));
    }
  }

  async function confirm() {
    setBusy(true);
    try {
      const result = await moveDayOne(project.id, date, false);
      setDate("");
      setPreview(null);
      onMoved(result);
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      title="Move Day 1"
      description={`Day 1 is ${project.day_one ? formatDate(project.day_one, { weekday: true }) : "not set"}. Open tasks and their reminders move with it. Finished tasks keep their dates.`}
      onClose={onClose}
      actions={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => void confirm()} disabled={!preview || busy}>
            {busy ? "Moving" : "Move Day 1"}
          </Button>
        </>
      }
    >
      <DateInput label="New Day 1" value={date} onChange={(e) => void check(e.target.value)} error={error} />
      {preview && (
        <p className="note-box" role="status">
          {preview}
        </p>
      )}
    </Dialog>
  );
}

function OneOffDialog({
  open,
  project,
  onClose,
  onAdded,
}: {
  open: boolean;
  project: Project;
  onClose: () => void;
  onAdded: (name: string, warnings: string[]) => void;
}) {
  const [name, setName] = useState("");
  const [due, setDue] = useState("");
  const [roleId, setRoleId] = useState("");
  const [userIds, setUserIds] = useState<string[]>([]);
  const [needsFirst, setNeedsFirst] = useState("");
  const [comesBefore, setComesBefore] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const roles = useApi(() => (open ? listRoles() : Promise.resolve(null)), [open]);
  const people = useApi(() => (open ? listPeople(false) : Promise.resolve(null)), [open]);
  const tasks = project.groups.flatMap((g) => g.tasks);
  const isOpenTask = (t: TaskRow) => t.status !== "Done" && t.status !== "Skipped";
  const first = tasks.find((t) => t.id === needsFirst);
  const later = tasks.find((t) => t.id === comesBefore);
  const shown = name.trim() || "This task";
  const warnings = [
    due && first?.due && isOpenTask(first) && first.due > due
      ? `${shown} would be due before ${first.name} (${first.due_short}), which it needs first.`
      : null,
    due && later?.due && later.due < due
      ? `${later.name} (${later.due_short}) would be due before ${shown}, which it would wait on.`
      : null,
  ].filter((w): w is string => Boolean(w));
  const label = (t: TaskRow) => `${t.name} (${t.due_short || "no date"})`;

  async function save() {
    if (!name.trim() || !due) {
      setError("Give the task a name and a due date.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await addOneOff(project.id, {
        name: name.trim(),
        due_date: due,
        role_id: roleId || null,
        user_ids: userIds.filter(Boolean),
        needs_first: needsFirst ? [needsFirst] : [],
        comes_before: comesBefore ? [comesBefore] : [],
      });
      onAdded(name.trim(), result.warnings ?? []);
      setName("");
      setDue("");
      setRoleId("");
      setUserIds([]);
      setNeedsFirst("");
      setComesBefore("");
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      title="Add task"
      description={
        project.closed
          ? "This launch is closed, so the task gets no reminders or emails. The template stays the same."
          : "Only this launch gets it. The template stays the same."
      }
      onClose={onClose}
      actions={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="oneoff-form" disabled={busy}>
            {busy ? "Adding" : "Add task"}
          </Button>
        </>
      }
    >
      <form
        id="oneoff-form"
        className="form"
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}
      >
        <TextInput label="Task name" value={name} onChange={(e) => setName(e.target.value)} required maxLength={200} />
        <DateInput
          label="Due date"
          value={due}
          onChange={(e) => setDue(e.target.value)}
          required
          min={project.closed ? undefined : todayIso()}
        />
        <Select
          label="Role"
          value={roleId}
          onChange={(e) => setRoleId(e.target.value)}
          placeholder="No role"
          options={(roles.data?.roles ?? []).filter((r) => r.active).map((r) => ({ value: r.id, label: r.name }))}
        />
        <PeoplePicker
          label="Assign to"
          hint="Leave blank to use the person on the team for that role."
          emptyLabel="Nobody yet"
          people={(people.data?.people ?? []).map((u) => ({ id: u.id, name: u.name }))}
          value={userIds}
          onChange={setUserIds}
        />
        <Select
          label="Needs first (optional)"
          value={needsFirst}
          onChange={(e) => setNeedsFirst(e.target.value)}
          placeholder="Nothing"
          options={tasks.filter((t) => t.id !== comesBefore).map((t) => ({ value: t.id, label: label(t) }))}
        />
        <Select
          label="Comes before (optional)"
          hint="That task will wait on this one. Its due date does not change."
          value={comesBefore}
          onChange={(e) => setComesBefore(e.target.value)}
          placeholder="Nothing"
          options={tasks.filter((t) => isOpenTask(t) && t.id !== needsFirst).map((t) => ({ value: t.id, label: label(t) }))}
        />
        {warnings.length > 0 && (
          <div className="note-box note-box--late" role="note">
            {warnings.join(" ")} You can still add it. No dates will move.
          </div>
        )}
        {error && (
          <p className="field-error" role="alert">
            {error}
          </p>
        )}
      </form>
    </Dialog>
  );
}

function EditDialog({
  open,
  project,
  onClose,
  onSaved,
}: {
  open: boolean;
  project: Project;
  onClose: () => void;
  onSaved: (saved: Project) => void;
}) {
  const [draft, setDraft] = useState<DetailsDraft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const sites = useApi(() => (open ? listSites() : Promise.resolve(null)), [open]);
  const instructors = useApi(() => (open ? listInstructors() : Promise.resolve(null)), [open]);
  const people = useApi(() => (open ? listPeople(false) : Promise.resolve(null)), [open]);
  const value = draft ?? (project.edit as DetailsDraft);
  const errors = checkDetails(value);

  async function save() {
    if (Object.keys(errors).length) {
      setError("Fix the fields marked below.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const { day_one: _skip, ...body } = value;
      void _skip;
      const saved = await updateProject(project.id, body);
      setDraft(null);
      onSaved(saved);
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      title="Edit details"
      description="To change Day 1, use Move Day 1 so the tasks move too."
      onClose={() => {
        setDraft(null);
        onClose();
      }}
      wide
      actions={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="edit-form" disabled={busy}>
            {busy ? "Saving" : "Save"}
          </Button>
        </>
      }
    >
      <form
        id="edit-form"
        className="form"
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}
      >
        <TextInput
          label="Program name"
          value={value.name}
          onChange={(e) => setDraft({ ...value, name: e.target.value })}
          maxLength={200}
        />
        <ProjectFields
          value={value}
          onChange={(change) => setDraft({ ...value, ...change })}
          siteTypes={sites.data?.site_types ?? (value.site_type ? [value.site_type] : [])}
          instructors={instructors.data?.instructors ?? []}
          partners={(people.data?.people ?? []).filter((u) => u.access_level === "Partner")}
          errors={errors}
        />
        {error && (
          <p className="field-error" role="alert">
            {error}
          </p>
        )}
      </form>
    </Dialog>
  );
}

function CloseDialog({
  open,
  project,
  onClose,
  onClosed,
}: {
  open: boolean;
  project: Project;
  onClose: () => void;
  onClosed: () => void;
}) {
  const [skip, setSkip] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      await closeProject(project.id, skip);
      onClosed();
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      title="Close this launch"
      description="Closed launches move to the archive. Reminders stop. You can reopen it later."
      onClose={onClose}
      actions={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => void confirm()} disabled={busy}>
            {busy ? "Closing" : "Close launch"}
          </Button>
        </>
      }
    >
      {project.open_tasks > 0 && (
        <label className="check-option">
          <input type="checkbox" checked={skip} onChange={(e) => setSkip(e.target.checked)} />
          Mark the {project.open_tasks} open {project.open_tasks === 1 ? "task" : "tasks"} as skipped
        </label>
      )}
      {project.open_tasks > 0 && !skip && (
        <p className="muted small">Left unticked, the open tasks stay as they are and show as unfinished in the archive.</p>
      )}
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
    </Dialog>
  );
}

function DeleteDialog({
  open,
  project,
  onClose,
  onDeleted,
}: {
  open: boolean;
  project: Project;
  onClose: () => void;
  onDeleted: (name: string) => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const name = project.site || project.name;
  const taskCount = project.groups.reduce((sum, g) => sum + g.tasks.length, 0);
  const label = project.day_one ? `${name} (Day 1 ${formatDate(project.day_one)})` : name;

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      await deleteProject(project.id);
      onDeleted(name);
    } catch (caught) {
      setError(errorText(caught));
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      title={`Delete ${name}?`}
      onClose={() => {
        setError(null);
        onClose();
      }}
      actions={
        <>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button variant="danger" onClick={() => void confirm()} disabled={busy}>
            {busy ? "Deleting" : "Delete launch"}
          </Button>
        </>
      }
    >
      <p>
        This permanently deletes <strong>{label}</strong> with its{" "}
        {taskCount === 1 ? "1 task" : `${taskCount} tasks`}, its team, notes, history, links and reminders.{" "}
        <strong>This cannot be undone.</strong>
      </p>
      {!project.closed && (
        <p className="muted small">
          To keep a record of it instead, close the launch. Closed launches stay in the archive.
        </p>
      )}
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
    </Dialog>
  );
}

function TemplateDialog({ open, project, onClose }: { open: boolean; project: Project; onClose: () => void }) {
  const navigate = useNavigate();
  const toast = useToast();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    if (!name.trim()) {
      setError("Give the template a name.");
      return;
    }
    setBusy(true);
    try {
      const created = await templateFromProject(project.id, name.trim());
      toast.show(`Saved ${name.trim()} as a template.`);
      navigate(`/templates?id=${created.id}`);
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      title="Save as a template"
      description={`Makes a new template from the ${project.site || project.name} tasks and their timing, including tasks added to this launch.`}
      onClose={onClose}
      actions={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => void save()} disabled={busy}>
            {busy ? "Saving" : "Save template"}
          </Button>
        </>
      }
    >
      <TextInput label="Template name" value={name} onChange={(e) => setName(e.target.value)} error={error} maxLength={200} />
      <p className="muted small">
        It starts as a draft you can edit. <Link to="/templates">See all templates</Link>
      </p>
    </Dialog>
  );
}
