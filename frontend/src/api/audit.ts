import { get, query } from "./client";

/** One admin action from the audit trail (findings F34, F35). Read only. */
export interface AuditEntry {
  when: string;
  action: string;
  label: string;
  actor_id: string;
  actor_name: string;
  target: string;
  status: number | null;
  request_id: string;
}

export interface AuditList {
  entries: AuditEntry[];
  more: boolean;
  actors: { id: string; name: string }[];
}

export const listAudit = (params: { days?: string; actor?: string }) => get<AuditList>(`/api/audit${query(params)}`);
