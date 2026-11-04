import { get, query } from "./client";
import type { ArchiveDetail, ArchiveRow } from "./types";

export const listArchive = (params: { site?: string; from?: string; to?: string }) =>
  get<{ launches: ArchiveRow[] }>(`/api/archive${query(params)}`);

export const archiveDetail = (id: string) => get<ArchiveDetail>(`/api/archive/${id}`);

export interface SeasonStats {
  year: number;
  sites_to_launch: number;
  sites_launched: number;
  tasks_done_this_week: number;
}

export const seasonStats = () => get<SeasonStats>("/api/public/season-stats");
