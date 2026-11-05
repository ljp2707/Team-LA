import { get, query, send } from "./client";
import type { HandOffPreview, PeopleList, Person, RoleRow } from "./types";

export interface PersonInput {
  first_name: string;
  last_name: string;
  email: string;
  access_level: string;
  role_ids: string[];
}

export const listPeople = (inactive: boolean) =>
  get<PeopleList>(`/api/users${query({ inactive: inactive ? "true" : null })}`);

export const addPerson = (body: PersonInput) => send<Person>("POST", "/api/users", body);

export const updatePerson = (
  id: string,
  body: Partial<Omit<PersonInput, "email">> & { status?: "Active" | "Inactive" },
) => send<Person>("PATCH", `/api/users/${id}`, body);

/** For a deletion request. The person must be deactivated and have no open tasks. */
export const erasePerson = (id: string) =>
  send<{ erased: boolean; history_rows: number }>("POST", `/api/users/${id}/erase`);

export const handOff = (body: {
  from_user: string;
  to_user: string;
  replace_on_teams: boolean;
  preview: boolean;
}) => send<HandOffPreview>("POST", "/api/users/hand-off", body);

export const listRoles = () => get<{ roles: RoleRow[] }>("/api/roles");

export const addRole = (name: string) => send<{ roles: RoleRow[] }>("POST", "/api/roles", { name });

export const updateRole = (id: string, body: { name?: string; status?: string }) =>
  send<{ roles: RoleRow[] }>("PATCH", `/api/roles/${id}`, body);

export interface AirtableHealth {
  connected: boolean;
  tables: { table: string; count: number | null; error: string | null }[];
}

export interface AuthHealth {
  client_id_set: boolean;
  client_secret_set: boolean;
  callback_url: string;
  dev_login: boolean;
  allowed_email_domain: string;
  gmail_ready: boolean;
  gmail_sender: string;
  reminders_dry_run: boolean;
}

export const airtableHealth = () => get<AirtableHealth>("/api/health/airtable");
export const authHealth = () => get<AuthHealth>("/api/health/auth");

export const sendTestEmail = () =>
  send<{ sent: boolean; dry_run: boolean; error: string | null; to: string }>(
    "POST",
    "/api/admin/test-email",
  );
