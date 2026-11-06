import { get, send } from "./client";
import type { Insights, TemplateDetail, TemplateSummary, TemplateVersion } from "./types";

export interface StepInput {
  key: string;
  name: string;
  description: string;
  anchor: "Start" | "End";
  days_before: number;
  role_id: string | null;
  depends_on: string[];
}

export const listTemplates = () => get<{ templates: TemplateSummary[] }>("/api/templates");

export const getTemplate = (id: string) => get<TemplateDetail>(`/api/templates/${id}`);

export const saveDraft = (id: string, steps: StepInput[]) =>
  send<TemplateDetail>("PUT", `/api/templates/${id}/draft`, { steps });

export const discardDraft = (id: string) => send<TemplateDetail>("DELETE", `/api/templates/${id}/draft`);

export const publishDraft = (id: string, changeNote: string) =>
  send<TemplateDetail & { version: number }>("POST", `/api/templates/${id}/publish`, {
    change_note: changeNote,
  });

export const templateVersions = (id: string) =>
  get<{ versions: TemplateVersion[] }>(`/api/templates/${id}/versions`);

export const templateInsights = (id: string) => get<Insights>(`/api/templates/${id}/insights`);

export const setTemplateStatus = (id: string, status: "Active" | "Inactive") =>
  send<TemplateDetail>("PATCH", `/api/templates/${id}`, { status });

export const deleteTemplate = (id: string) => send<void>("DELETE", `/api/templates/${id}`);

export const duplicateTemplate = (id: string, name?: string) =>
  send<{ id: string }>("POST", `/api/templates/${id}/duplicate`, { name: name || null });

export const newTemplate = (copyFrom: string, name: string) =>
  send<{ id: string }>("POST", "/api/templates", { copy_from: copyFrom, name });

export const templateFromProject = (projectId: string, name: string) =>
  send<{ id: string }>("POST", "/api/templates/from-project", { project_id: projectId, name });
