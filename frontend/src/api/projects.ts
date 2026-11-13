import { get, query, send, upload } from "./client";
import type {
  DayOneResult,
  HistoryEntry,
  ProjectDetail,
  ProjectEdit,
  ProjectList,
  ProjectPreview,
  Site,
} from "./types";

export interface OneOffInput {
  name: string;
  due_date: string;
  role_id?: string | null;
  user_id?: string | null;
  user_ids?: string[];
  needs_first?: string[];
  comes_before?: string[];
}

export interface PreviewInput {
  template_id?: string | null;
  from_project_id?: string | null;
  day_one?: string | null;
  end_date?: string | null;
  assignments?: Record<string, string | null>;
  overrides?: Record<string, string | null>;
  one_offs?: OneOffInput[];
}

export type ProjectInput = PreviewInput &
  Partial<Omit<ProjectEdit, "day_one" | "end_date">> & {
    name: string;
    site_id: string;
    day_one: string;
    update_site_profile?: boolean;
  };

export const listProjects = (params: { status?: string; sort?: string; region?: string } = {}) =>
  get<ProjectList>(`/api/projects${query(params)}`);

export const getProject = (id: string) => get<ProjectDetail>(`/api/projects/${id}`);

export const previewProject = (body: PreviewInput) =>
  send<ProjectPreview>("POST", "/api/projects/preview", body);

export const createProject = (body: ProjectInput) =>
  send<{ id: string }>("POST", "/api/projects", body);

export const updateProject = (id: string, body: Partial<ProjectEdit>) =>
  send<ProjectDetail>("PATCH", `/api/projects/${id}`, body);

export const moveDayOne = (id: string, newDayOne: string, preview: boolean) =>
  send<DayOneResult>("POST", `/api/projects/${id}/move-day-one`, {
    new_day_one: newDayOne,
    preview,
  });

export const undoDayOne = (id: string, batch: string) =>
  send<{ message: string }>("POST", `/api/projects/${id}/move-day-one/undo`, { batch });

export const addOneOff = (id: string, body: OneOffInput) =>
  send<{ id: string; warnings: string[] }>("POST", `/api/projects/${id}/tasks`, body);

export const closeProject = (id: string, skipOpen: boolean) =>
  send<{ closed: boolean }>("POST", `/api/projects/${id}/close`, { skip_open: skipOpen });

export const reopenProject = (id: string) => send<{ reopened: boolean }>("POST", `/api/projects/${id}/reopen`);

export const projectHistory = (id: string, page: number) =>
  get<{ entries: HistoryEntry[]; page: number; pages: number; total: number }>(
    `/api/projects/${id}/history?page=${page}`,
  );

export const addProjectLink = (id: string, title: string, url: string) =>
  send<{ id: string }>("POST", `/api/projects/${id}/links`, { title, url });

export const addProjectFile = (id: string, file: File, title: string) =>
  upload<{ id: string; kind: string }>(`/api/projects/${id}/files`, file, { title });

export const removeLink = (id: string) => send<{ removed: boolean }>("DELETE", `/api/links/${id}`);

export interface SiteList {
  sites: Site[];
  site_types: string[];
  regions: { id: string; name: string }[];
}

export const listSites = () => get<SiteList>("/api/sites");

export const createSite = (body: Partial<Site> & { name: string }) => send<Site>("POST", "/api/sites", body);

export const listInstructors = (siteId?: string) =>
  get<{ instructors: { id: string; name: string }[] }>(`/api/instructors${query({ site: siteId })}`);
