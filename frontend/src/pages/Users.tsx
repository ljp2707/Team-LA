import { useEffect, useState } from "react";
import type { HandOffPreview, PeopleList, Person, RoleRow } from "../api/types";
import {
  addPerson,
  addRole,
  airtableHealth,
  authHealth,
  erasePerson,
  handOff,
  listPeople,
  listRoles,
  sendTestEmail,
  updatePerson,
  updateRole,
} from "../api/users";
import type { PersonInput } from "../api/users";
import { useAuth } from "../auth/AuthContext";
import { Avatar } from "../components/ui/Bits";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Dialog } from "../components/ui/Dialog";
import { Select, TextInput } from "../components/ui/Field";
import { PageHeader } from "../components/ui/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/States";
import { Tag } from "../components/ui/Tag";
import { useToast } from "../components/ui/Toast";
import { useApi } from "../hooks/useApi";
import { PERMISSION_TABLE } from "../permissionsTable";

function errorText(caught: unknown) {
  return caught instanceof Error ? caught.message : "That did not work. Please try again.";
}

type Open = null | "add" | "roles" | { edit: Person };

export function Users() {
  const toast = useToast();
  const [showInactive, setShowInactive] = useState(false);
  const people = useApi(() => listPeople(showInactive), [showInactive]);
  const [open, setOpen] = useState<Open>(null);
  const close = () => setOpen(null);

  return (
    <div className="page">
      <PageHeader
        title="Users and roles"
        action={<Button onClick={() => setOpen("add")}>Add a person</Button>}
      />

      {people.error ? (
        <ErrorState error={people.error} onRetry={people.reload} />
      ) : !people.data ? (
        <LoadingState label="Loading people" />
      ) : (
        <div className="two-col">
          <Card>
            <div className="split">
              <h2>People</h2>
              <span className="muted small">
                {people.data.counts.people} people · {people.data.counts.roles} roles
              </span>
            </div>
            {people.data.people.length === 0 ? (
              <EmptyState title="Nobody here yet">Add a person to get started.</EmptyState>
            ) : (
              <ul className="people-list">
                {people.data.people.map((person) => (
                  <li key={person.id} className={person.active ? undefined : "is-inactive"}>
                    <Avatar name={person.name} />
                    <div className="row-main">
                      <span className="row-title">
                        {person.name}
                        {!person.active && (
                          <>
                            {" "}
                            <Tag tone="idle">Inactive</Tag>
                          </>
                        )}
                      </span>
                      <span className="pill-row">
                        {person.roles.length === 0 ? (
                          <span className="muted small">No role yet</span>
                        ) : (
                          person.roles.map((r) => (
                            <span key={r.id} className="pill">
                              {r.name}
                            </span>
                          ))
                        )}
                      </span>
                    </div>
                    <span className="muted small nowrap">
                      {person.open_tasks} open {person.open_tasks === 1 ? "task" : "tasks"}
                    </span>
                    <span className="tag tag--idle">{person.access_level ?? "No level"}</span>
                    <Button variant="outline" size="sm" onClick={() => setOpen({ edit: person })} aria-label={`Edit ${person.name}`}>
                      Edit
                    </Button>
                  </li>
                ))}
              </ul>
            )}
            <div className="card-actions">
              <Button variant="outline" onClick={() => setOpen("roles")}>
                Manage roles
              </Button>
              <label className="check-option">
                <input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} />
                Show inactive people
              </label>
            </div>
          </Card>

          <HandOffCard
            people={people.data.people.filter((p) => p.active)}
            onDone={(moved, to) => {
              toast.show(`Moved ${moved} ${moved === 1 ? "task" : "tasks"} to ${to}.`);
              void people.reload();
            }}
          />
        </div>
      )}

      <Card className="table-card">
        <h2>What each level can do</h2>
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Action</th>
                <th scope="col">Admin</th>
                <th scope="col">Staff</th>
                <th scope="col">Partner</th>
              </tr>
            </thead>
            <tbody>
              {PERMISSION_TABLE.map((row) => (
                <tr key={row.action}>
                  <th scope="row">{row.action}</th>
                  {[row.admin, row.staff, row.partner].map((cell, i) => (
                    <td key={i} className={row.action !== "Who" && cell !== "No" && cell !== "Notes only" ? "is-yes" : undefined}>
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted small">
          Viewers can see everything staff can, but cannot change anything. Project Leads work like staff.
        </p>
      </Card>

      <SystemCard />

      {people.data && (
        <>
          <PersonDialog
            open={open === "add" || (typeof open === "object" && open !== null)}
            person={typeof open === "object" && open ? open.edit : null}
            data={people.data}
            onClose={close}
            onSaved={(text) => {
              close();
              toast.show(text);
              void people.reload();
            }}
          />
          <RolesDialog open={open === "roles"} onClose={close} onChanged={() => void people.reload()} />
        </>
      )}
    </div>
  );
}

function HandOffCard({ people, onDone }: { people: Person[]; onDone: (moved: number, to: string) => void }) {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [replace, setReplace] = useState(true);
  const [preview, setPreview] = useState<HandOffPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setPreview(null);
    setError(null);
    if (!from || !to) return;
    if (from === to) {
      setError("Pick two different people.");
      return;
    }
    let live = true;
    handOff({ from_user: from, to_user: to, replace_on_teams: replace, preview: true })
      .then((result) => live && setPreview(result))
      .catch((caught) => live && setError(errorText(caught)));
    return () => {
      live = false;
    };
  }, [from, to, replace]);

  async function move() {
    setBusy(true);
    setError(null);
    try {
      const result = await handOff({ from_user: from, to_user: to, replace_on_teams: replace, preview: false });
      onDone(result.moved ?? result.count, people.find((p) => p.id === to)?.first_name ?? "them");
      setFrom("");
      setTo("");
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <h2>Hand off tasks</h2>
      <p className="muted small">When someone leaves or goes on leave, move all their open tasks at once.</p>
      <div className="form">
        <Select
          label="From"
          value={from}
          placeholder="Pick a person"
          onChange={(e) => setFrom(e.target.value)}
          options={people.map((p) => ({ value: p.id, label: `${p.name}, ${p.open_tasks} open` }))}
        />
        <Select
          label="To"
          value={to}
          placeholder="Pick a person"
          onChange={(e) => setTo(e.target.value)}
          options={people
            .filter((p) => p.id !== from && p.access_level !== "Viewer")
            .map((p) => ({ value: p.id, label: p.name }))}
        />
        <label className="check-option">
          <input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} />
          Also put them on those launch teams
        </label>
        {preview && (
          <div className="small" role="status">
            {preview.count === 0 ? (
              <p className="muted">{preview.preview}</p>
            ) : (
              <ul className="plain-list">
                {preview.tasks.slice(0, 3).map((name, i) => (
                  <li key={`${name}-${i}`}>{name}</li>
                ))}
                {preview.count > 3 && <li className="muted">and {preview.count - 3} more</li>}
              </ul>
            )}
          </div>
        )}
        {error && (
          <p className="field-error" role="alert">
            {error}
          </p>
        )}
        <Button onClick={() => void move()} disabled={!preview || preview.count === 0 || busy}>
          {busy ? "Moving" : preview?.button ?? "Move tasks"}
        </Button>
      </div>
    </Card>
  );
}

function PersonDialog({
  open,
  person,
  data,
  onClose,
  onSaved,
}: {
  open: boolean;
  person: Person | null;
  data: PeopleList;
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const { me } = useAuth();
  const [form, setForm] = useState<PersonInput>({ first_name: "", last_name: "", email: "", access_level: "Staff", role_ids: [] });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setForm(
      person
        ? {
            first_name: person.first_name,
            last_name: person.last_name,
            email: person.email,
            access_level: person.access_level ?? "Staff",
            role_ids: person.roles.map((r) => r.id),
          }
        : { first_name: "", last_name: "", email: "", access_level: "Staff", role_ids: [] },
    );
  }, [open, person]);

  async function save() {
    if (!form.first_name.trim() || (!person && !form.email.trim())) {
      setError("Add a first name and an email.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (person) {
        await updatePerson(person.id, {
          first_name: form.first_name.trim(),
          last_name: form.last_name.trim(),
          access_level: form.access_level,
          role_ids: form.role_ids,
        });
        onSaved(`Saved ${form.first_name.trim()}.`);
      } else {
        await addPerson({ ...form, first_name: form.first_name.trim(), last_name: form.last_name.trim(), email: form.email.trim() });
        onSaved(`Added ${form.first_name.trim()}. They get a welcome email.`);
      }
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setBusy(false);
    }
  }

  async function setActive(active: boolean) {
    if (!person) return;
    if (!active && person.open_tasks > 0 && !window.confirm(`${person.first_name} has ${person.open_tasks} open tasks. Hand them off first, or they stay assigned. Deactivate anyway?`)) return;
    setBusy(true);
    try {
      await updatePerson(person.id, { status: active ? "Active" : "Inactive" });
      onSaved(active ? `${person.first_name} can sign in again.` : `${person.first_name} can no longer sign in.`);
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setBusy(false);
    }
  }

  async function erase() {
    if (!person) return;
    const ok = window.confirm(
      `Remove ${person.name}'s personal details? Their name and email are replaced with "Former team member" everywhere, ` +
        "including the history, and their reminders stop. Their finished work stays. This cannot be undone.",
    );
    if (!ok) return;
    setBusy(true);
    try {
      await erasePerson(person.id);
      onSaved("Their personal details are removed.");
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setBusy(false);
    }
  }

  const activeRoles = data.roles;
  const isSelf = person?.id === me?.user.id;

  return (
    <Dialog
      open={open}
      title={person ? `Edit ${person.name}` : "Add a person"}
      description={
        person
          ? person.email
          : "They can sign in with Google once you add them. They get one welcome email, and NMU Launches keeps their name and email so their team can see who does what."
      }
      onClose={onClose}
      wide
      actions={
        <>
          {person && !isSelf && (
            <Button variant={person.active ? "danger" : "outline"} className="push-left" disabled={busy} onClick={() => void setActive(!person.active)}>
              {person.active ? "Deactivate" : "Reactivate"}
            </Button>
          )}
          {person && !isSelf && !person.active && person.first_name !== "Former" && (
            <Button variant="danger" disabled={busy} onClick={() => void erase()}>
              Remove personal details
            </Button>
          )}
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="person-form" disabled={busy}>
            {busy ? "Saving" : person ? "Save" : "Add person"}
          </Button>
        </>
      }
    >
      <form
        id="person-form"
        className="form"
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}
      >
        <div className="form-grid">
          <TextInput label="First name" value={form.first_name} maxLength={100} required onChange={(e) => setForm({ ...form, first_name: e.target.value })} />
          <TextInput label="Last name" value={form.last_name} maxLength={100} onChange={(e) => setForm({ ...form, last_name: e.target.value })} />
        </div>
        {!person && (
          <TextInput
            label="Google account email"
            type="email"
            value={form.email}
            maxLength={200}
            required
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
        )}
        <Select
          label="Access level"
          value={form.access_level}
          hint={isSelf ? "You cannot remove your own admin access." : undefined}
          onChange={(e) => setForm({ ...form, access_level: e.target.value })}
          options={data.access_levels.map((level) => ({ value: level, label: level }))}
        />
        <fieldset className="check-group">
          <legend>Roles</legend>
          {activeRoles.map((role) => (
            <label key={role.id} className="check-option">
              <input
                type="checkbox"
                checked={form.role_ids.includes(role.id)}
                onChange={() =>
                  setForm({
                    ...form,
                    role_ids: form.role_ids.includes(role.id)
                      ? form.role_ids.filter((r) => r !== role.id)
                      : [...form.role_ids, role.id],
                  })
                }
              />
              {role.name}
            </label>
          ))}
        </fieldset>
        {error && (
          <p className="field-error" role="alert">
            {error}
          </p>
        )}
      </form>
    </Dialog>
  );
}

function RolesDialog({ open, onClose, onChanged }: { open: boolean; onClose: () => void; onChanged: () => void }) {
  const roles = useApi(() => (open ? listRoles() : Promise.resolve(null)), [open]);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ id: string; name: string } | null>(null);

  async function run(action: () => Promise<{ roles: RoleRow[] }>) {
    setError(null);
    try {
      roles.setData(await action());
      onChanged();
    } catch (caught) {
      setError(errorText(caught));
    }
  }

  return (
    <Dialog open={open} title="Manage roles" description="Steps and launch teams point at roles. A role in use cannot be removed, only made inactive." onClose={onClose} wide>
      {roles.error ? (
        <ErrorState error={roles.error} onRetry={roles.reload} />
      ) : !roles.data ? (
        <LoadingState />
      ) : (
        <ul className="role-list">
          {roles.data.roles.map((role) => (
            <li key={role.id} className={role.active ? undefined : "is-inactive"}>
              {editing?.id === role.id ? (
                <form
                  className="inline-form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void run(() => updateRole(role.id, { name: editing.name.trim() })).then(() => setEditing(null));
                  }}
                >
                  <label className="visually-hidden" htmlFor={`role-name-${role.id}`}>
                    Role name
                  </label>
                  <input
                    id={`role-name-${role.id}`}
                    className="input"
                    value={editing.name}
                    maxLength={100}
                    onChange={(e) => setEditing({ id: role.id, name: e.target.value })}
                  />
                  <Button type="submit" size="sm">
                    Save
                  </Button>
                  <button type="button" className="text-button" onClick={() => setEditing(null)}>
                    Cancel
                  </button>
                </form>
              ) : (
                <>
                  <div className="row-main">
                    <span className="row-title">
                      {role.name} {!role.active && <Tag tone="idle">{role.status}</Tag>}
                    </span>
                    <span className="muted small">
                      {role.people} {role.people === 1 ? "person" : "people"} · {role.steps} template {role.steps === 1 ? "task" : "tasks"}
                    </span>
                  </div>
                  <div className="inline-actions">
                    <button type="button" className="text-button" onClick={() => setEditing({ id: role.id, name: role.name })}>
                      Rename<span className="visually-hidden"> {role.name}</span>
                    </button>
                    <button
                      type="button"
                      className="text-button"
                      onClick={() => void run(() => updateRole(role.id, { status: role.active ? "In Active" : "Active" }))}
                    >
                      {role.active ? "Make inactive" : "Make active"}
                      <span className="visually-hidden"> {role.name}</span>
                    </button>
                  </div>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
      <form
        className="inline-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (!name.trim()) return;
          void run(() => addRole(name.trim())).then(() => setName(""));
        }}
      >
        <TextInput label="New role" value={name} maxLength={100} onChange={(e) => setName(e.target.value)} />
        <Button type="submit" variant="outline">
          Add role
        </Button>
      </form>
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
    </Dialog>
  );
}

function SystemCard() {
  const toast = useToast();
  const airtable = useApi(airtableHealth, []);
  const auth = useApi(authHealth, []);
  const [sending, setSending] = useState(false);

  async function test() {
    setSending(true);
    try {
      const result = await sendTestEmail();
      if (result.error) toast.error(result.error);
      else if (result.dry_run) toast.show(`Dry run is on, so nothing was sent. It would have gone to ${result.to}.`);
      else toast.show(`Test email sent to ${result.to}.`);
    } catch (caught) {
      toast.error(errorText(caught));
    } finally {
      setSending(false);
    }
  }

  const yes = (ok: boolean, good: string, bad: string) => (
    <Tag tone={ok ? "done" : "late"}>{ok ? good : bad}</Tag>
  );

  return (
    <Card>
      <h2>System</h2>
      <dl className="facts facts--rows">
        <div>
          <dt>Airtable</dt>
          <dd>
            {airtable.error
              ? yes(false, "", "Not connected")
              : !airtable.data
                ? "Checking"
                : yes(airtable.data.connected, "Connected", "Not connected")}
          </dd>
        </div>
        {auth.data && (
          <>
            <div>
              <dt>Google sign in</dt>
              <dd>
                {yes(auth.data.client_id_set && auth.data.client_secret_set, "Set up", "Missing client ID or secret")}
                {auth.data.dev_login && <span className="muted small"> Dev login is on</span>}
              </dd>
            </div>
            <div>
              <dt>Redirect URI</dt>
              <dd className="code small">{auth.data.callback_url}</dd>
            </div>
            {auth.data.allowed_email_domain && (
              <div>
                <dt>Allowed domain</dt>
                <dd>{auth.data.allowed_email_domain}</dd>
              </div>
            )}
            <div>
              <dt>Email</dt>
              <dd>
                {yes(auth.data.gmail_ready, `Sends as ${auth.data.gmail_sender}`, "Not set up")}
                {auth.data.reminders_dry_run && <span className="muted small"> Dry run is on</span>}
              </dd>
            </div>
          </>
        )}
      </dl>
      {airtable.data && !airtable.data.connected && (
        <ul className="plain-list small">
          {airtable.data.tables
            .filter((t) => t.error)
            .map((t) => (
              <li key={t.table}>
                {t.table}: {t.error}
              </li>
            ))}
        </ul>
      )}
      <div className="card-actions">
        <Button variant="outline" onClick={() => void test()} disabled={sending}>
          {sending ? "Sending" : "Send me a test email"}
        </Button>
      </div>
    </Card>
  );
}
