import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  createProject,
  createSite,
  listInstructors,
  listProjects,
  listSites,
  previewProject,
} from "../api/projects";
import type { OneOffInput } from "../api/projects";
import { listTemplates } from "../api/templates";
import { NewTemplateDialog } from "./Templates";
import type { ProjectPreview, Site } from "../api/types";
import { listPeople, listRoles } from "../api/users";
import { checkDetails, ProjectFields } from "../components/ProjectFields";
import type { DetailsDraft } from "../components/ProjectFields";
import { SectionLabel } from "../components/ui/Bits";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Segmented } from "../components/ui/Chips";
import { Combobox } from "../components/ui/Combobox";
import { Dialog } from "../components/ui/Dialog";
import { DateInput, Select, TextInput } from "../components/ui/Field";
import { PageHeader } from "../components/ui/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/States";
import { useToast } from "../components/ui/Toast";
import { useApi } from "../hooks/useApi";
import { formatDate, seasonName, todayIso } from "../lib/dates";

type Source = "template" | "past";

const EMPTY_DETAILS: DetailsDraft = {
  name: "",
  site_type: null,
  end_date: null,
  program_hours: "",
  location: "",
  instructor_ids: [],
  partner_name: "",
  partner_email: "",
  partner_phone: "",
  shipping_address: "",
  drive_folder: "",
  partner_ids: [],
};

function errorText(caught: unknown) {
  return caught instanceof Error ? caught.message : "That did not work. Please try again.";
}

export function NewProject() {
  const navigate = useNavigate();
  const toast = useToast();
  const [params] = useSearchParams();
  const fromParam = params.get("from");

  const [source, setSource] = useState<Source>(fromParam ? "past" : "template");
  const [templateId, setTemplateId] = useState<string | null>(null);
  const [pastId, setPastId] = useState<string | null>(fromParam);
  const [siteId, setSiteId] = useState<string | null>(null);
  const [dayOne, setDayOne] = useState("");
  const [details, setDetails] = useState<DetailsDraft>(EMPTY_DETAILS);
  const [nameTouched, setNameTouched] = useState(false);
  const [assignments, setAssignments] = useState<Record<string, string | null>>({});
  const [overrides, setOverrides] = useState<Record<string, string | null>>({});
  const [oneOffs, setOneOffs] = useState<OneOffInput[]>([]);
  const [updateProfile, setUpdateProfile] = useState(true);
  const [prefilled, setPrefilled] = useState<Site | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [preview, setPreview] = useState<ProjectPreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dialog, setDialog] = useState<null | "oneoff" | "template" | { site: string }>(null);

  const templates = useApi(listTemplates, []);
  const past = useApi(() => listProjects({ status: "closed" }), []);
  const sites = useApi(listSites, []);
  const instructors = useApi(() => listInstructors(siteId ?? undefined), [siteId]);
  const people = useApi(() => listPeople(false), []);
  const roles = useApi(listRoles, []);

  const activeTemplates = useMemo(() => (templates.data?.templates ?? []).filter((t) => t.active), [templates.data]);

  // Pick the first template once they load.
  useEffect(() => {
    if (!templateId && activeTemplates.length) setTemplateId(activeTemplates[0].id);
  }, [activeTemplates, templateId]);

  // A past launch fills in its site.
  const pastLaunch = past.data?.projects.find((p) => p.id === pastId) ?? null;
  useEffect(() => {
    if (source === "past" && pastLaunch?.site_id && !siteId) chooseSite(pastLaunch.site_id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pastLaunch, source]);

  // Suggest a program name until the person types their own.
  const programType =
    source === "template"
      ? activeTemplates.find((t) => t.id === templateId)?.name
      : pastLaunch?.program_type;
  useEffect(() => {
    if (nameTouched || !programType) return;
    setDetails((d) => ({ ...d, name: dayOne ? `${programType} ${seasonName(dayOne)}` : programType }));
  }, [programType, dayOne, nameTouched]);

  // Refresh the task list preview whenever a choice changes.
  const chosenSource: { template_id?: string | null; from_project_id?: string | null } =
    source === "template" ? { template_id: templateId } : { from_project_id: pastId };
  const previewKey = JSON.stringify([chosenSource, dayOne, details.end_date, assignments, overrides, oneOffs]);
  useEffect(() => {
    if (!(chosenSource.template_id || chosenSource.from_project_id)) {
      setPreview(null);
      return;
    }
    let live = true;
    const timer = window.setTimeout(() => {
      previewProject({
        ...chosenSource,
        day_one: dayOne || null,
        end_date: details.end_date || null,
        assignments,
        overrides,
        one_offs: oneOffs,
      })
        .then((result) => {
          if (!live) return;
          setPreview(result);
          setPreviewError(null);
        })
        .catch((caught) => live && setPreviewError(errorText(caught)));
    }, 250);
    return () => {
      live = false;
      window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [previewKey]);

  function chooseSite(id: string | null, list: Site[] = sites.data?.sites ?? []) {
    setSiteId(id);
    const site = list.find((s) => s.id === id);
    if (!site) {
      setPrefilled(null);
      return;
    }
    setPrefilled(site);
    setDetails((d) => ({
      ...d,
      site_type: site.site_type || d.site_type,
      location: site.location || d.location,
      partner_name: site.partner_name,
      partner_email: site.partner_email,
      partner_phone: site.partner_phone,
      shipping_address: site.shipping_address,
      drive_folder: site.drive_folder || d.drive_folder,
    }));
  }

  const errors = checkDetails({ ...details, day_one: dayOne });

  async function create() {
    if (!siteId) return setFormError("Pick a site.");
    if (!dayOne) return setFormError("Pick Day 1.");
    if (!details.name.trim()) return setFormError("Give the launch a program name.");
    if (Object.keys(errors).length) return setFormError("Fix the fields marked in the form.");
    setBusy(true);
    setFormError(null);
    try {
      const created = await createProject({
        ...details,
        ...chosenSource,
        name: details.name.trim(),
        site_id: siteId,
        day_one: dayOne,
        end_date: details.end_date || null,
        drive_folder: details.drive_folder.trim(),
        assignments,
        overrides,
        one_offs: oneOffs,
        update_site_profile: updateProfile,
      });
      toast.show("Launch created. Everyone with a task gets an email.");
      navigate(`/projects/${created.id}`);
    } catch (caught) {
      setFormError(errorText(caught));
      setBusy(false);
    }
  }

  const loadError = templates.error || sites.error;
  if (loadError) return <ErrorState error={loadError} onRetry={() => void (templates.reload(), sites.reload())} />;
  if (!templates.data || !sites.data) return <LoadingState label="Loading templates and sites" />;

  const assignable = (people.data?.people ?? []).filter(
    (u) => u.active && u.access_level !== "Partner" && u.access_level !== "Viewer",
  );
  const shownTasks = preview ? (showAll ? preview.tasks : preview.tasks.slice(0, preview.first)) : [];
  const hiddenCount = preview ? preview.tasks.length - shownTasks.length : 0;
  const siteOptions = sites.data.sites.map((s) => ({
    value: s.id,
    label: s.name,
    detail: [s.site_type, s.location].filter(Boolean).join(" · "),
  }));

  return (
    <div className="page">
      <PageHeader
        back={{ to: "/dashboard", label: "Back to dashboard" }}
        title="Start a launch"
      />

      <div className="two-col two-col--even">
        <Card>
          <form
            id="new-project"
            className="form"
            onSubmit={(event) => {
              event.preventDefault();
              void create();
            }}
          >
            <SectionLabel>Start from</SectionLabel>
            <Segmented<Source>
              label="Start from"
              value={source}
              onChange={setSource}
              options={[
                { value: "template", label: "A template" },
                { value: "past", label: "A past launch" },
              ]}
            />

            {source === "template" ? (
              <fieldset className="radio-cards">
                <legend className="section-label">Program type</legend>
                {activeTemplates.length === 0 && <p className="muted">No active templates yet.</p>}
                {activeTemplates.map((t) => (
                  <label key={t.id} className={`radio-card${t.id === templateId ? " is-selected" : ""}`}>
                    <input
                      type="radio"
                      name="template"
                      value={t.id}
                      checked={t.id === templateId}
                      onChange={() => setTemplateId(t.id)}
                    />
                    <span>
                      <strong>{t.name}</strong>
                      <span className="muted small">
                        {t.task_count} tasks{t.lead_text ? `, ${t.lead_text}` : ""}
                      </span>
                    </span>
                  </label>
                ))}
                {(templates.data?.templates.length ?? 0) > 0 && (
                  <button type="button" className="text-button" onClick={() => setDialog("template")}>
                    + Add a template
                  </button>
                )}
              </fieldset>
            ) : past.error ? (
              <p className="field-error">Past launches did not load. {past.error.message}</p>
            ) : (
              <Combobox
                label="Past launch"
                placeholder="Search finished launches"
                value={pastId}
                onChange={setPastId}
                hint="Copies its tasks, owners and timing, moved to the new Day 1."
                options={(past.data?.projects ?? []).map((p) => ({
                  value: p.id,
                  label: `${p.site || p.name}`,
                  detail: [p.program_type, p.day_one ? `Day 1 ${formatDate(p.day_one)}` : null].filter(Boolean).join(" · "),
                }))}
              />
            )}

            <div className="form-grid">
              <Combobox
                label="Site"
                placeholder="Search sites"
                value={siteId}
                onChange={(id) => chooseSite(id)}
                options={siteOptions}
                extra={{ label: "Add a new site", onSelect: (typed) => setDialog({ site: typed }) }}
              />
              <DateInput label="Day 1" value={dayOne} min={todayIso()} onChange={(e) => setDayOne(e.target.value)} required />
            </div>

            {prefilled && (
              <div className="note-box note-box--done" role="status">
                <strong>Filled in from the {prefilled.name} site profile.</strong> Partner contact, shipping address
                {prefilled.last_head_coach ? ` and last season's head coach (${prefilled.last_head_coach})` : ""}. Change
                anything below.
              </div>
            )}

            <TextInput
              label="Program name"
              value={details.name}
              maxLength={200}
              onChange={(e) => {
                setNameTouched(true);
                setDetails({ ...details, name: e.target.value });
              }}
              required
            />

            <ProjectFields
              value={details}
              onChange={(change) => setDetails({ ...details, ...change })}
              siteTypes={sites.data.site_types}
              instructors={instructors.data?.instructors ?? []}
              partners={(people.data?.people ?? []).filter((u) => u.access_level === "Partner" && u.active)}
              errors={errors}
            />

            {siteId && (
              <label className="check-option">
                <input type="checkbox" checked={updateProfile} onChange={(e) => setUpdateProfile(e.target.checked)} />
                Save the partner contact and shipping address to the site profile for next time
              </label>
            )}
          </form>
        </Card>

        <Card className="sticky-card">
          <h2>Your task list</h2>
          <p className="muted small">
            Every task gets a due date from Day 1 and a default owner by role. Pick a person to assign it directly.
          </p>

          {previewError ? (
            <p className="field-error" role="alert">
              {previewError}
            </p>
          ) : !preview ? (
            source === "past" && !pastId ? (
              <EmptyState title="Pick a past launch">Its tasks show up here.</EmptyState>
            ) : (
              <LoadingState label="Building the task list" />
            )
          ) : (
            <>
              {preview.roles.length > 0 && (
                <details className="roles-block">
                  <summary>
                    Owners by role
                    {preview.needs_owner > 0 && (
                      <span className="muted small">
                        {" "}
                        · {preview.needs_owner} {preview.needs_owner === 1 ? "task needs" : "tasks need"} an owner
                      </span>
                    )}
                  </summary>
                  <div className="form">
                    {preview.roles.map((r) => (
                      <Select
                        key={r.role_id}
                        label={r.role}
                        value={r.user_id ?? ""}
                        placeholder="Nobody yet"
                        onChange={(e) => setAssignments({ ...assignments, [r.role_id]: e.target.value || null })}
                        options={(r.candidates.length ? r.candidates : assignable).map((c) => ({
                          value: c.id,
                          label: c.name,
                        }))}
                      />
                    ))}
                  </div>
                </details>
              )}

              {!dayOne && <p className="note-box small">Pick Day 1 to see each task's due date.</p>}
              <ul className="preview-list">
                {shownTasks.map((task, index) => {
                  const newGroup = index === 0 || shownTasks[index - 1].group !== task.group;
                  return (
                    <li key={task.key}>
                      {newGroup && dayOne && <SectionLabel>{task.group}</SectionLabel>}
                      <div className="preview-row">
                        <div className="row-main">
                          <span className="row-title">{task.name}</span>
                          <span className="row-sub">
                            {[
                              task.due ? task.due_text : null,
                              task.role,
                              task.after.length ? `after ${task.after.join(", ")}` : null,
                              task.one_off ? "added here" : null,
                            ]
                              .filter(Boolean)
                              .join(" · ")}
                          </span>
                        </div>
                        <label className="visually-hidden" htmlFor={`owner-${task.key}`}>
                          Owner of {task.name}
                        </label>
                        <select
                          id={`owner-${task.key}`}
                          className="input select select--pill"
                          value={task.override ?? ""}
                          onChange={(e) => setOverrides({ ...overrides, [task.key]: e.target.value || null })}
                        >
                          <option value="">
                            {task.user ? task.user : task.role ? `${task.role} (role)` : "Nobody yet"}
                          </option>
                          {assignable.map((u) => (
                            <option key={u.id} value={u.id}>
                              {u.name}
                            </option>
                          ))}
                        </select>
                      </div>
                    </li>
                  );
                })}
              </ul>
              {hiddenCount > 0 && (
                <p className="muted small">
                  and {hiddenCount} more {hiddenCount === 1 ? "task" : "tasks"}
                  {preview.last_task ? ` through ${preview.last_task.name}${dayOne ? ` on ${preview.last_task.due_text}` : ""}` : ""}.{" "}
                  <button type="button" className="text-button" onClick={() => setShowAll(true)}>
                    Show all
                  </button>
                </p>
              )}
              {oneOffs.length > 0 && (
                <p className="muted small">
                  {oneOffs.length} added {oneOffs.length === 1 ? "task" : "tasks"}.{" "}
                  <button type="button" className="text-button" onClick={() => setOneOffs([])}>
                    Remove added tasks
                  </button>
                </p>
              )}
            </>
          )}

          {formError && (
            <p className="field-error" role="alert">
              {formError}
            </p>
          )}
          <div className="card-actions card-actions--split">
            <Button variant="outline" onClick={() => setDialog("oneoff")}>
              Add task
            </Button>
            <Button type="submit" form="new-project" disabled={busy || !preview}>
              {busy ? "Creating" : "Create launch"}
            </Button>
          </div>
        </Card>
      </div>

      <OneOffDraftDialog
        open={dialog === "oneoff"}
        roles={(roles.data?.roles ?? []).filter((r) => r.active)}
        min={todayIso()}
        onClose={() => setDialog(null)}
        onAdd={(item) => {
          setOneOffs([...oneOffs, item]);
          setDialog(null);
        }}
      />
      <NewTemplateDialog
        open={dialog === "template"}
        templates={(templates.data?.templates ?? []).map((t) => ({ id: t.id, name: t.name }))}
        onClose={() => setDialog(null)}
        onCreated={async (id, name) => {
          setDialog(null);
          await templates.reload();
          setTemplateId(id);
          toast.show(`Made ${name}. Change its tasks any time on Templates.`);
        }}
      />
      <NewSiteDialog
        open={typeof dialog === "object" && dialog !== null}
        initialName={typeof dialog === "object" && dialog ? dialog.site : ""}
        siteTypes={sites.data.site_types}
        regions={sites.data.regions}
        onClose={() => setDialog(null)}
        onCreated={async (site) => {
          setDialog(null);
          const fresh = await listSites().catch(() => null);
          if (fresh) sites.setData(fresh);
          chooseSite(site.id, fresh?.sites ?? [...(sites.data?.sites ?? []), site]);
          toast.show(`Added ${site.name}.`);
        }}
      />
    </div>
  );
}

function OneOffDraftDialog({
  open,
  roles,
  min,
  onClose,
  onAdd,
}: {
  open: boolean;
  roles: { id: string; name: string }[];
  min: string;
  onClose: () => void;
  onAdd: (item: OneOffInput) => void;
}) {
  const [name, setName] = useState("");
  const [due, setDue] = useState("");
  const [roleId, setRoleId] = useState("");
  const [error, setError] = useState<string | null>(null);

  function add() {
    if (!name.trim() || !due) {
      setError("Give the task a name and a due date.");
      return;
    }
    onAdd({ name: name.trim(), due_date: due, role_id: roleId || null });
    setName("");
    setDue("");
    setRoleId("");
    setError(null);
  }

  return (
    <Dialog
      open={open}
      title="Add task"
      description="Only this launch gets it. The template stays the same."
      onClose={onClose}
      actions={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={add}>Add task</Button>
        </>
      }
    >
      <TextInput label="Task name" value={name} maxLength={200} onChange={(e) => setName(e.target.value)} />
      <DateInput label="Due date" value={due} min={min} onChange={(e) => setDue(e.target.value)} />
      <Select
        label="Role"
        value={roleId}
        placeholder="No role"
        onChange={(e) => setRoleId(e.target.value)}
        options={roles.map((r) => ({ value: r.id, label: r.name }))}
      />
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
    </Dialog>
  );
}

function NewSiteDialog({
  open,
  initialName,
  siteTypes,
  regions,
  onClose,
  onCreated,
}: {
  open: boolean;
  initialName: string;
  siteTypes: string[];
  regions: { id: string; name: string }[];
  onClose: () => void;
  onCreated: (site: Site) => void;
}) {
  const [name, setName] = useState("");
  const [siteType, setSiteType] = useState("");
  const [location, setLocation] = useState("");
  const [regionId, setRegionId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) setName(initialName);
  }, [open, initialName]);

  async function save() {
    if (!name.trim()) {
      setError("Give the site a name.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const site = await createSite({
        name: name.trim(),
        site_type: siteType || null,
        location: location.trim(),
        region_id: regionId || null,
      });
      setName("");
      setSiteType("");
      setLocation("");
      setRegionId("");
      onCreated(site);
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      title="Add a new site"
      onClose={onClose}
      actions={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => void save()} disabled={busy}>
            {busy ? "Adding" : "Add site"}
          </Button>
        </>
      }
    >
      <TextInput label="Site name" value={name} maxLength={200} onChange={(e) => setName(e.target.value)} />
      <Select
        label="Site type"
        value={siteType}
        placeholder="Choose a site type"
        onChange={(e) => setSiteType(e.target.value)}
        options={siteTypes.map((t) => ({ value: t, label: t }))}
      />
      <TextInput label="Location" placeholder="City, WA" value={location} maxLength={200} onChange={(e) => setLocation(e.target.value)} />
      {regions.length > 0 && (
        <Select
          label="Region"
          value={regionId}
          placeholder="No region"
          onChange={(e) => setRegionId(e.target.value)}
          options={regions.map((r) => ({ value: r.id, label: r.name }))}
        />
      )}
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
    </Dialog>
  );
}
