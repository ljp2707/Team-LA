import { useMemo, useState } from "react";
import { listProjects } from "../api/projects";
import { useApi } from "../hooks/useApi";
import { ProjectCard } from "./ProjectCard";
import { Chips } from "./ui/Chips";
import { StatTile } from "./ui/Bits";
import { Card } from "./ui/Card";
import { EmptyState, ErrorState, LoadingState } from "./ui/States";

type Sort = "day1" | "overdue";

/** The summary strip, sort chips, filters and project cards. Used by Dashboard and Projects. */
export function ProjectGrid({ showSummary, emptyText }: { showSummary: boolean; emptyText: string }) {
  const [sort, setSort] = useState<Sort>("day1");
  const [region, setRegion] = useState("");
  const [type, setType] = useState("");
  const list = useApi(() => listProjects({ sort, region: region || undefined }), [sort, region]);

  const projects = useMemo(
    () => (list.data?.projects ?? []).filter((p) => !type || p.program_type === type),
    [list.data, type],
  );

  if (list.error) return <ErrorState error={list.error} onRetry={list.reload} />;
  if (!list.data) return <LoadingState label="Loading launches" />;
  const { summary, regions, program_types } = list.data;

  return (
    <>
      {showSummary && (
        <Card className="stat-strip">
          <StatTile value={summary.active} label={summary.active === 1 ? "active launch" : "active launches"} />
          <StatTile
            value={summary.overdue}
            label={summary.overdue === 1 ? "task overdue" : "tasks overdue"}
            tone={summary.overdue ? "late" : undefined}
          />
          <StatTile value={summary.blocked} label={summary.blocked === 1 ? "task blocked" : "tasks blocked"} />
          {summary.needs_owner > 0 && (
            <StatTile value={summary.needs_owner} label={summary.needs_owner === 1 ? "task needs an owner" : "tasks need an owner"} />
          )}
          <StatTile
            value={summary.next_day_one ? summary.next_day_one.text : "None"}
            label={summary.next_day_one ? `next Day 1, ${summary.next_day_one.site}` : "no Day 1 coming up"}
            to={summary.next_day_one ? `/projects/${summary.next_day_one.project_id}` : undefined}
          />
        </Card>
      )}

      <div className="toolbar">
        <Chips<Sort>
          label="Sort"
          value={sort}
          onChange={setSort}
          options={[
            { value: "day1", label: "Soonest Day 1" },
            { value: "overdue", label: "Most overdue" },
          ]}
        />
        <label className="inline-select">
          <span>Program type</span>
          <select className="input select" value={type} onChange={(e) => setType(e.target.value)}>
            <option value="">All types</option>
            {program_types.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        {regions.length > 1 && (
          <label className="inline-select">
            <span>Region</span>
            <select className="input select" value={region} onChange={(e) => setRegion(e.target.value)}>
              <option value="">All regions</option>
              {regions.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {projects.length === 0 ? (
        <Card>
          <EmptyState title="No launches here">{type || region ? "Try All types or All regions." : emptyText}</EmptyState>
        </Card>
      ) : (
        <div className="card-grid" aria-busy={list.loading}>
          {projects.map((p) => (
            <ProjectCard key={p.id} project={p} />
          ))}
        </div>
      )}
    </>
  );
}
