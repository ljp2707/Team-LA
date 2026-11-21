import { useState } from "react";
import { listAudit } from "../api/audit";
import { Card } from "../components/ui/Card";
import { Select } from "../components/ui/Field";
import { PageHeader } from "../components/ui/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/States";
import { useApi } from "../hooks/useApi";

const PERIODS = [
  { value: "7", label: "Last 7 days" },
  { value: "30", label: "Last 30 days" },
  { value: "90", label: "Last 90 days" },
  { value: "365", label: "Last year" },
  { value: "3650", label: "Everything" },
];

const WHEN = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

/** Every admin action, newest first. Read only: nobody can change or delete these. */
export function Audit() {
  const [days, setDays] = useState("30");
  const [actor, setActor] = useState("");
  const list = useApi(() => listAudit({ days, actor }), [days, actor]);
  const entries = list.data?.entries ?? [];

  return (
    <div className="page">
      <PageHeader
        title="Audit"
        description="Every change made with admin access: who did it, what it was and when. Nobody can edit or delete these entries."
      />

      <div className="filter-grid filter-grid--audit">
        <Select label="Admin" value={actor} onChange={(e) => setActor(e.target.value)} placeholder="Everyone"
          options={(list.data?.actors ?? []).map((a) => ({ value: a.id, label: a.name }))} />
        <Select label="When" value={days} onChange={(e) => setDays(e.target.value)} options={PERIODS} />
      </div>

      {list.error ? (
        <ErrorState error={list.error} onRetry={list.reload} />
      ) : !list.data ? (
        <LoadingState label="Loading the audit trail" />
      ) : entries.length === 0 ? (
        <Card>
          <EmptyState title="No admin changes in this period">Try a longer period or another admin.</EmptyState>
        </Card>
      ) : (
        <Card className="table-card">
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">When</th>
                  <th scope="col">Who</th>
                  <th scope="col">What</th>
                  <th scope="col">Which</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <tr key={`${entry.when}-${entry.request_id}`}>
                    <td className="nowrap">{WHEN.format(new Date(entry.when))}</td>
                    <td>{entry.actor_name}</td>
                    <td title={`${entry.action} (request ${entry.request_id})`}>{entry.label}</td>
                    <td>{entry.target || "None"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {list.data.more && <p className="muted small">Showing the newest 500. Choose a shorter period or one admin to see the rest.</p>}
        </Card>
      )}
    </div>
  );
}
