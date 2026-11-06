import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { listProjects } from "../api/projects";
import {
  deleteTemplate,
  discardDraft,
  duplicateTemplate,
  getTemplate,
  listTemplates,
  newTemplate,
  publishDraft,
  saveDraft,
  setTemplateStatus,
  templateFromProject,
  templateInsights,
  templateVersions,
} from "../api/templates";
import type { StepInput } from "../api/templates";
import type { InsightItem, Insights, TemplateDetail, TemplateStep } from "../api/types";
import type { ApiState } from "../hooks/useApi";
import { SectionLabel } from "../components/ui/Bits";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Dialog } from "../components/ui/Dialog";
import { Select, TextArea, TextInput } from "../components/ui/Field";
import { PageHeader } from "../components/ui/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/States";
import { Tag } from "../components/ui/Tag";
import { useToast } from "../components/ui/Toast";
import { useApi } from "../hooks/useApi";

function errorText(caught: unknown) {
  return caught instanceof Error ? caught.message : "That did not work. Please try again.";
}

/** "3 weeks before", "Day 1", "2 days after the last day". Matches the server's wording. */
export function whenText(anchor: "Start" | "End", days: number): string {
  if (days === 0) return anchor === "Start" ? "Day 1" : "Last day";
  const n = Math.abs(days);
  const amount = n % 7 === 0 ? `${n / 7} ${n === 7 ? "week" : "weeks"}` : `${n} ${n === 1 ? "day" : "days"}`;
  const side = days > 0 ? "before" : "after";
  return anchor === "Start" ? `${amount} ${side}` : `${amount} ${side} the last day`;
}

function toInput(step: TemplateStep): StepInput {
  return {
    key: step.key,
    name: step.name,
    description: step.description,
    anchor: step.anchor,
    days_before: step.days_before,
    role_id: step.role_id,
    depends_on: step.depends_on,
  };
}

type Open = null | "publish" | "versions" | "duplicate" | "new" | "from-project" | { edit: string };

export function Templates() {
  const toast = useToast();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const list = useApi(listTemplates, []);
  const selectedId = params.get("id") ?? list.data?.templates[0]?.id ?? null;
  const detail = useApi(() => (selectedId ? getTemplate(selectedId) : Promise.resolve(null)), [selectedId]);
  const insights = useApi(() => (selectedId ? templateInsights(selectedId) : Promise.resolve(null)), [selectedId]);
  const [steps, setSteps] = useState<StepInput[] | null>(null);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<Open>(null);

  // Start from the saved draft (or nothing) whenever another template is picked.
  useEffect(() => {
    setSteps(detail.data?.draft ? detail.data.draft.steps.map(toInput) : null);
    setDirty(false);
  }, [detail.data]);

  if (list.error) return <ErrorState error={list.error} onRetry={list.reload} />;
  if (!list.data) return <LoadingState label="Loading templates" />;

  const t = detail.data;
  const editing = steps !== null;
  const roleNames = new Map((t?.roles ?? []).map((r) => [r.id, r.name]));
  const shown: StepInput[] = steps ?? (t ? t.steps.map(toInput) : []);
  const serverStep = new Map([...(t?.draft?.steps ?? []), ...(t?.steps ?? [])].map((s) => [s.key, s]));
  const names = new Map(shown.map((s) => [s.key, s.name]));
  const close = () => setOpen(null);

  function pick(id: string) {
    if (dirty && !window.confirm("You have unsaved changes to this draft. Leave without saving?")) return;
    setParams({ id });
  }

  function edit(change: (current: StepInput[]) => StepInput[]) {
    setSteps((current) => change(current ?? (t ? t.steps.map(toInput) : [])));
    setDirty(true);
  }

  async function save(next = steps): Promise<TemplateDetail | null> {
    if (!t || !next) return null;
    setBusy(true);
    try {
      const saved = await saveDraft(t.id, next);
      detail.setData(saved);
      setDirty(false);
      void list.reload();
      toast.show("Draft saved.");
      return saved;
    } catch (caught) {
      toast.error(errorText(caught));
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function discard() {
    if (!t) return;
    if (!t.draft) {
      setSteps(null);
      setDirty(false);
      return;
    }
    if (!window.confirm("Throw away this draft? The live version stays as it is.")) return;
    try {
      detail.setData(await discardDraft(t.id));
      void list.reload();
      toast.show("Draft discarded.");
    } catch (caught) {
      toast.error(errorText(caught));
    }
  }

  async function remove() {
    if (!t) return;
    if (!window.confirm(`Delete the template ${t.name}? Its tasks and version history are deleted too. This cannot be undone.`)) return;
    try {
      await deleteTemplate(t.id);
      await list.reload();
      setParams({});
      toast.show("Template deleted.");
    } catch (caught) {
      toast.error(errorText(caught));
    }
  }

  function addInsight(item: InsightItem) {
    const key = `new-${Date.now()}`;
    const next = [
      ...shown,
      { key, name: item.name, description: "", anchor: "Start" as const, days_before: item.days_before ?? 0, role_id: null, depends_on: [] },
    ];
    setSteps(next);
    void save(next);
  }

  const runningOnLive = t?.projects_on_live ?? [];

  return (
    <div className="page">
      <PageHeader
        title="Templates"
        action={
          <>
            <Button variant="outline" onClick={() => setOpen("from-project")}>
              Save a project as a template
            </Button>
            <Button variant="outline" onClick={() => setOpen("new")}>
              New template
            </Button>
            {t && (
              <Button variant="outline" onClick={() => setOpen("duplicate")}>
                Duplicate
              </Button>
            )}
          </>
        }
      />

      <div className="two-col two-col--list">
        <nav className="side-list" aria-label="Templates">
          {list.data.templates.length === 0 && <p className="muted">No templates yet.</p>}
          {list.data.templates.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`side-list-item${item.id === selectedId ? " is-selected" : ""}`}
              aria-current={item.id === selectedId ? "true" : undefined}
              onClick={() => pick(item.id)}
            >
              <strong>{item.name}</strong>
              <span className="muted small">
                {item.task_count} tasks
                {item.has_draft && " · draft"}
                {!item.active && " · inactive"}
              </span>
            </button>
          ))}
        </nav>

        {detail.error ? (
          <ErrorState error={detail.error} onRetry={detail.reload} />
        ) : !t ? (
          <LoadingState label="Loading the template" />
        ) : (
          <Card className="template-card">
            {editing ? (
              <div className="banner banner--inline" role="status">
                <p>
                  <strong>Editing a draft.</strong>{" "}
                  {runningOnLive.length
                    ? `${runningOnLive.map((p) => p.site || p.name).join(" and ")} ${runningOnLive.length === 1 ? "keeps its" : "keep their"} current tasks, so nothing changes for launches already running.`
                    : "Launches already running are not changed."}
                  {dirty && " You have unsaved changes."}
                </p>
                <div className="banner-actions">
                  <Button variant="light" size="sm" onClick={() => setOpen("versions")}>
                    Version history
                  </Button>
                  {dirty ? (
                    <Button size="sm" onClick={() => void save()} disabled={busy}>
                      {busy ? "Saving" : "Save draft"}
                    </Button>
                  ) : (
                    <Button size="sm" onClick={() => setOpen("publish")} disabled={!t.draft}>
                      Publish
                    </Button>
                  )}
                  <button type="button" className="text-button" onClick={() => void discard()}>
                    Discard
                  </button>
                </div>
              </div>
            ) : (
              <div className="split template-head">
                <div>
                  <h2>{t.name}</h2>
                  <p className="muted small">
                    {t.steps.length} tasks{" "}
                    {!t.active && <Tag tone="idle">Inactive</Tag>}
                  </p>
                </div>
                <div className="inline-actions">
                  <Button variant="outline" size="sm" onClick={() => setOpen("versions")}>
                    Version history
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      void setTemplateStatus(t.id, t.active ? "Inactive" : "Active")
                        .then((saved) => {
                          detail.setData(saved);
                          void list.reload();
                          toast.show(saved.active ? "Template is active." : "Template is inactive. It is hidden on Start a launch.");
                        })
                        .catch((caught) => toast.error(errorText(caught)))
                    }
                  >
                    {t.active ? "Make inactive" : "Make active"}
                  </Button>
                  <Button variant="danger" size="sm" onClick={() => void remove()}>
                    Delete
                  </Button>
                  <Button size="sm" onClick={() => setSteps(t.steps.map(toInput))}>
                    Edit
                  </Button>
                </div>
              </div>
            )}

            <div className="step-head" aria-hidden="true">
              <span>When</span>
              <span>Task, default role, needs first</span>
            </div>
            {shown.length === 0 ? (
              <EmptyState title="No tasks in this template">Add a task to get started.</EmptyState>
            ) : (
              <ol className="step-list">
                {shown.map((step, index) => {
                  const saved = serverStep.get(step.key);
                  const note = editing && !dirty ? saved?.note : null;
                  const needs = step.depends_on.map((d) => names.get(d)).filter(Boolean);
                  return (
                    <li key={step.key} className={`step-row${note ? " is-changed" : ""}`}>
                      <span className={`step-when${step.days_before === 0 || note ? " is-blue" : ""}`}>
                        {whenText(step.anchor, step.days_before)}
                      </span>
                      <div className="row-main">
                        <span className="row-title">{step.name}</span>
                        {(note || needs.length > 0) && (
                          <span className={`row-sub${note ? " is-blue" : ""}`}>
                            {[note, needs.length ? `Needs ${needs.join(", ")} first` : null].filter(Boolean).join(" · ")}
                          </span>
                        )}
                      </div>
                      {editing ? (
                        <div className="step-tools">
                          <label className="visually-hidden" htmlFor={`role-${step.key}`}>
                            Default role for {step.name}
                          </label>
                          <select
                            id={`role-${step.key}`}
                            className="input select select--pill"
                            value={step.role_id ?? ""}
                            onChange={(e) =>
                              edit((all) => all.map((s) => (s.key === step.key ? { ...s, role_id: e.target.value || null } : s)))
                            }
                          >
                            <option value="">No role</option>
                            {t.roles.map((r) => (
                              <option key={r.id} value={r.id}>
                                {r.name}
                              </option>
                            ))}
                          </select>
                          <button
                            type="button"
                            className="icon-button"
                            aria-label={`Move ${step.name} up`}
                            disabled={index === 0}
                            onClick={() =>
                              edit((all) => {
                                const next = [...all];
                                [next[index - 1], next[index]] = [next[index], next[index - 1]];
                                return next;
                              })
                            }
                          >
                            ↑
                          </button>
                          <button
                            type="button"
                            className="icon-button"
                            aria-label={`Move ${step.name} down`}
                            disabled={index === shown.length - 1}
                            onClick={() =>
                              edit((all) => {
                                const next = [...all];
                                [next[index + 1], next[index]] = [next[index], next[index + 1]];
                                return next;
                              })
                            }
                          >
                            ↓
                          </button>
                          <button type="button" className="text-button" onClick={() => setOpen({ edit: step.key })}>
                            Edit<span className="visually-hidden"> {step.name}</span>
                          </button>
                        </div>
                      ) : (
                        <span className="tag tag--idle">{(step.role_id && roleNames.get(step.role_id)) || "No role"}</span>
                      )}
                    </li>
                  );
                })}
              </ol>
            )}
            {editing && t.draft && t.draft.removed.length > 0 && !dirty && (
              <p className="muted small">Removed in this draft: {t.draft.removed.join(", ")}</p>
            )}
            {editing && (
              <Button variant="outline" onClick={() => setOpen({ edit: "" })}>
                Add a task
              </Button>
            )}
          </Card>
        )}
      </div>

      {t && <InsightsCard insights={insights} templateName={t.name} canAdd={!busy} onAdd={addInsight} />}

      {t && (
        <>
          <StepDialog
            open={typeof open === "object" && open !== null}
            stepKey={typeof open === "object" && open ? open.edit : ""}
            steps={shown}
            roles={t.roles}
            onClose={close}
            onSave={(step) => {
              edit((all) => (all.some((s) => s.key === step.key) ? all.map((s) => (s.key === step.key ? step : s)) : [...all, step]));
              close();
            }}
            onDelete={(key) => {
              edit((all) =>
                all.filter((s) => s.key !== key).map((s) => ({ ...s, depends_on: s.depends_on.filter((d) => d !== key) })),
              );
              close();
            }}
          />
          <PublishDialog
            open={open === "publish"}
            template={t}
            onClose={close}
            onPublished={(saved) => {
              close();
              detail.setData(saved);
              void list.reload();
              toast.show("Published. New launches use it from now on.");
            }}
          />
          <VersionsDialog open={open === "versions"} templateId={t.id} onClose={close} />
          <NameDialog
            open={open === "duplicate"}
            title="Duplicate this template"
            label="Name of the copy"
            initial={`${t.name} copy`}
            button="Duplicate"
            onClose={close}
            onSave={async (name) => {
              const created = await duplicateTemplate(t.id, name);
              close();
              await list.reload();
              setParams({ id: created.id });
              toast.show(`Made ${name}.`);
            }}
          />
        </>
      )}
      <NewTemplateDialog
        open={open === "new"}
        templates={list.data.templates.map((x) => ({ id: x.id, name: x.name }))}
        onClose={close}
        onCreated={async (id, name) => {
          close();
          await list.reload();
          setParams({ id });
          toast.show(`Made ${name}. Edit it, then publish.`);
        }}
      />
      <FromProjectDialog
        open={open === "from-project"}
        onClose={close}
        onCreated={async (id) => {
          close();
          await list.reload();
          navigate(`/templates?id=${id}`);
          toast.show("Template saved.");
        }}
      />
    </div>
  );
}

function InsightsCard({
  insights,
  templateName,
  canAdd,
  onAdd,
}: {
  insights: ApiState<Insights | null>;
  templateName: string;
  canAdd: boolean;
  onAdd: (item: InsightItem) => void;
}) {
  const data = insights.data;
  if (insights.error) return null;
  return (
    <Card>
      <h2>From past launches</h2>
      {!data ? (
        <LoadingState label="Looking at past launches" />
      ) : data.launches < 3 ? (
        <p className="muted small">
          After 3 finished {templateName} launches, this shows which tasks run late, get skipped or get added. So far:{" "}
          {data.launches}.
        </p>
      ) : (
        <>
          <p className="muted small">
            What happened to this template's tasks across {data.launches} finished {templateName} launches.
          </p>
          {!data.often_late.length && !data.often_skipped.length && !data.often_added.length && (
            <p className="muted">Nothing stands out. The template is working.</p>
          )}
          <InsightGroup label="Often late" tone="late" items={data.often_late} />
          <InsightGroup label="Often skipped" items={data.often_skipped} />
          <InsightGroup
            label="Often added"
            tone="done"
            items={data.often_added}
            action={(item) =>
              item.in_template ? (
                <span className="muted small">Already in the template</span>
              ) : (
                <Button variant="outline" size="sm" disabled={!canAdd} onClick={() => onAdd(item)}>
                  Add to this template
                </Button>
              )
            }
          />
        </>
      )}
    </Card>
  );
}

function InsightGroup({
  label,
  tone,
  items,
  action,
}: {
  label: string;
  tone?: "late" | "done";
  items: InsightItem[];
  action?: (item: InsightItem) => ReactNode;
}) {
  if (!items.length) return null;
  return (
    <section className="insight-group">
      <h3 className={`section-label${tone === "late" ? " is-late" : tone === "done" ? " is-done" : ""}`}>{label}</h3>
      <ul className="plain-list">
        {items.map((item) => (
          <li key={item.step_id ?? item.name}>
            <strong>{item.name}</strong>
            <span className="muted small">{item.text}</span>
            {action?.(item)}
          </li>
        ))}
      </ul>
    </section>
  );
}

function StepDialog({
  open,
  stepKey,
  steps,
  roles,
  onClose,
  onSave,
  onDelete,
}: {
  open: boolean;
  stepKey: string;
  steps: StepInput[];
  roles: { id: string; name: string }[];
  onClose: () => void;
  onSave: (step: StepInput) => void;
  onDelete: (key: string) => void;
}) {
  const existing = steps.find((s) => s.key === stepKey);
  const [draft, setDraft] = useState<StepInput | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setDraft(
      existing ?? {
        key: `new-${Date.now()}`,
        name: "",
        description: "",
        anchor: "Start",
        days_before: 7,
        role_id: null,
        depends_on: [],
      },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, stepKey]);

  const others = useMemo(() => steps.filter((s) => s.key !== draft?.key), [steps, draft?.key]);
  if (!draft) return null;
  const before = draft.days_before >= 0;

  function save() {
    if (!draft) return;
    if (!draft.name.trim()) {
      setError("Give the task a name.");
      return;
    }
    onSave({ ...draft, name: draft.name.trim() });
  }

  return (
    <Dialog
      open={open}
      title={existing ? `Edit ${existing.name}` : "Add a task"}
      description="Changes stay in the draft until you publish."
      onClose={onClose}
      wide
      actions={
        <>
          {existing && (
            <Button variant="danger" className="push-left" onClick={() => onDelete(existing.key)}>
              Remove task
            </Button>
          )}
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={save}>{existing ? "Done" : "Add task"}</Button>
        </>
      }
    >
      <div className="form">
        <TextInput
          label="Task name"
          value={draft.name}
          maxLength={200}
          error={error}
          onChange={(e) => setDraft({ ...draft, name: e.target.value })}
        />
        <TextArea
          label="Description (optional)"
          rows={3}
          maxLength={5000}
          value={draft.description}
          onChange={(e) => setDraft({ ...draft, description: e.target.value })}
        />
        <div className="form-grid form-grid--3">
          <TextInput
            label="Days"
            type="number"
            min={0}
            max={365}
            value={Math.abs(draft.days_before)}
            onChange={(e) => {
              const n = Math.min(365, Math.max(0, Number(e.target.value) || 0));
              setDraft({ ...draft, days_before: before ? n : -n });
            }}
          />
          <Select
            label="Before or after"
            value={before ? "before" : "after"}
            onChange={(e) => setDraft({ ...draft, days_before: e.target.value === "before" ? Math.abs(draft.days_before) : -Math.abs(draft.days_before) })}
            options={[
              { value: "before", label: "Before" },
              { value: "after", label: "After" },
            ]}
          />
          <Select
            label="Counted from"
            value={draft.anchor}
            onChange={(e) => setDraft({ ...draft, anchor: e.target.value as "Start" | "End" })}
            options={[
              { value: "Start", label: "Day 1" },
              { value: "End", label: "The last day" },
            ]}
          />
        </div>
        <p className="muted small">Due {whenText(draft.anchor, draft.days_before)}.</p>
        <Select
          label="Default role"
          value={draft.role_id ?? ""}
          placeholder="No role"
          onChange={(e) => setDraft({ ...draft, role_id: e.target.value || null })}
          options={roles.map((r) => ({ value: r.id, label: r.name }))}
        />
        {others.length > 0 && (
          <fieldset className="check-group check-group--scroll">
            <legend>Needs first</legend>
            {others.map((s) => (
              <label key={s.key} className="check-option">
                <input
                  type="checkbox"
                  checked={draft.depends_on.includes(s.key)}
                  onChange={() =>
                    setDraft({
                      ...draft,
                      depends_on: draft.depends_on.includes(s.key)
                        ? draft.depends_on.filter((d) => d !== s.key)
                        : [...draft.depends_on, s.key],
                    })
                  }
                />
                {s.name}
              </label>
            ))}
          </fieldset>
        )}
      </div>
    </Dialog>
  );
}

function PublishDialog({
  open,
  template,
  onClose,
  onPublished,
}: {
  open: boolean;
  template: TemplateDetail;
  onClose: () => void;
  onPublished: (saved: TemplateDetail) => void;
}) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function publish() {
    setBusy(true);
    setError(null);
    try {
      const saved = await publishDraft(template.id, note.trim());
      setNote("");
      onPublished(saved);
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      title="Publish changes"
      description={`New ${template.name} launches use these changes. Launches already running keep their tasks.`}
      onClose={onClose}
      actions={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => void publish()} disabled={busy}>
            {busy ? "Publishing" : "Publish"}
          </Button>
        </>
      }
    >
      <TextArea
        label="What changed (optional)"
        rows={3}
        maxLength={1000}
        placeholder="Moved community outreach a week earlier."
        value={note}
        onChange={(e) => setNote(e.target.value)}
        error={error}
      />
    </Dialog>
  );
}

function VersionsDialog({ open, templateId, onClose }: { open: boolean; templateId: string; onClose: () => void }) {
  const versions = useApi(() => (open ? templateVersions(templateId) : Promise.resolve(null)), [open, templateId]);
  return (
    <Dialog open={open} title="Version history" onClose={onClose} wide>
      {versions.error ? (
        <ErrorState error={versions.error} onRetry={versions.reload} />
      ) : !versions.data ? (
        <LoadingState />
      ) : versions.data.versions.length === 0 ? (
        <EmptyState title="No versions yet" />
      ) : (
        <ul className="version-list">
          {versions.data.versions.map((v) => (
            <li key={`${v.version}-${v.status}`}>
              <details>
                <summary>
                  <strong>v{v.version}</strong>{" "}
                  <Tag tone={v.status === "Live" ? "done" : v.status === "Draft" ? "progress" : "idle"}>{v.status ?? "Old"}</Tag>{" "}
                  <span className="muted small">
                    {v.task_count} tasks
                    {v.published_text && ` · published ${v.published_text}`}
                    {v.published_by && ` by ${v.published_by}`}
                  </span>
                  {v.change_note && <span className="version-note">{v.change_note}</span>}
                </summary>
                <ol className="plain-list small">
                  {v.steps.map((s) => (
                    <li key={s.key}>
                      <span className="muted">{s.when}</span> {s.name}
                      {s.role && <span className="muted"> · {s.role}</span>}
                    </li>
                  ))}
                </ol>
              </details>
            </li>
          ))}
        </ul>
      )}
    </Dialog>
  );
}

function NameDialog({
  open,
  title,
  label,
  initial,
  button,
  onClose,
  onSave,
}: {
  open: boolean;
  title: string;
  label: string;
  initial: string;
  button: string;
  onClose: () => void;
  onSave: (name: string) => Promise<void>;
}) {
  const [name, setName] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setName(initial);
      setError(null);
    }
  }, [open, initial]);

  async function save() {
    if (!name.trim()) {
      setError("Give it a name.");
      return;
    }
    setBusy(true);
    try {
      await onSave(name.trim());
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      title={title}
      onClose={onClose}
      actions={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => void save()} disabled={busy}>
            {busy ? "Saving" : button}
          </Button>
        </>
      }
    >
      <TextInput label={label} value={name} maxLength={200} onChange={(e) => setName(e.target.value)} error={error} />
    </Dialog>
  );
}

export function NewTemplateDialog({
  open,
  templates,
  onClose,
  onCreated,
}: {
  open: boolean;
  templates: { id: string; name: string }[];
  onClose: () => void;
  onCreated: (id: string, name: string) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [copyFrom, setCopyFrom] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    if (!name.trim() || !copyFrom) {
      setError("Give it a name and pick a template to start from.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const created = await newTemplate(copyFrom, name.trim());
      setName("");
      await onCreated(created.id, name.trim());
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      title="New template"
      description="New templates start as a copy of one you have, so the timing is already close."
      onClose={onClose}
      actions={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => void save()} disabled={busy}>
            {busy ? "Making" : "Make template"}
          </Button>
        </>
      }
    >
      <TextInput label="Template name" value={name} maxLength={200} onChange={(e) => setName(e.target.value)} />
      <Select
        label="Start from"
        value={copyFrom}
        placeholder="Pick a template"
        onChange={(e) => setCopyFrom(e.target.value)}
        options={templates.map((x) => ({ value: x.id, label: x.name }))}
      />
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
    </Dialog>
  );
}

function FromProjectDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (id: string) => Promise<void>;
}) {
  const active = useApi(() => (open ? listProjects() : Promise.resolve(null)), [open]);
  const closed = useApi(() => (open ? listProjects({ status: "closed" }) : Promise.resolve(null)), [open]);
  const [projectId, setProjectId] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const projects = [...(active.data?.projects ?? []), ...(closed.data?.projects ?? [])];

  async function save() {
    if (!projectId || !name.trim()) {
      setError("Pick a launch and give the template a name.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const created = await templateFromProject(projectId, name.trim());
      setName("");
      setProjectId("");
      await onCreated(created.id);
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      title="Save a project as a template"
      description="Copies the launch's tasks, roles, order and timing, including tasks added to the launch."
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
      <Select
        label="Launch"
        value={projectId}
        placeholder={active.data ? "Pick a launch" : "Loading launches"}
        onChange={(e) => setProjectId(e.target.value)}
        options={projects.map((p) => ({
          value: p.id,
          label: `${p.site || p.name} · ${p.program_type}${p.closed ? " (closed)" : ""}`,
        }))}
      />
      <TextInput label="Template name" value={name} maxLength={200} onChange={(e) => setName(e.target.value)} />
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
      <SectionLabel>Tip</SectionLabel>
      <p className="muted small">It starts as v1. You can edit it before using it.</p>
    </Dialog>
  );
}
