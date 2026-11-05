import { useMemo, useState } from "react";
import { listProjects } from "../api/projects";
import { useApi } from "../hooks/useApi";
import { ProjectCard } from "./ProjectCard";
import { Chips } from "./ui/Chips";
import { StatTile } from "./ui/Bits";
import { Card } from "./ui/Card";
import { EmptyState, ErrorState, LoadingState } from "./ui/States";
import type { ProjectCard as Project } from "../api/types";

type Sort = "day1" | "overdue";

/** True when every word typed appears somewhere in the launch's name, site, type, region or lead. */
function matchesSearch(project: Project, search: string): boolean {
  const words = search.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return true;
  const text = [
    project.site,
    project.name,
    project.program_type,
    project.site_type,
    project.region,
    project.lead_instructor,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return words.every((word) => text.includes(word));
}

/** The summary strip, sort chips, filters and project cards. Used by Dashboard and Projects. */
export function ProjectGrid({ showSummary, emptyText }: { showSummary: boolean; emptyText: string }) {
  const [sort, setSort] = useState<Sort>("day1");
  const [region, setRegion] = useState("");
  const [type, setType] = useState("");
  const [search, setSearch] = useState("");
  const list = useApi(() => listProjects({ sort, region: region || undefined }), [sort, region]);

  const projects = useMemo(
    () => (list.data?.projects ?? []).filter((p) => (!type || p.program_type === type) && matchesSearch(p, search)),
    [list.data, type, search],
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
        <label className="search-field">
          <span className="visually-hidden">Search launches</span>
          <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
            <circle cx="7" cy="7" r="5" fill="none" stroke="currentColor" strokeWidth="1.8" />
            <path d="m11 11 3.5 3.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
          <input
            type="search"
            className="input"
            placeholder="Search launches"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === "Escape" && setSearch("")}
          />
        </label>
        <div className="toolbar-filters">
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
      </div>

      {projects.length === 0 ? (
        <Card>
          {search.trim() ? (
            <EmptyState title={`No launches match "${search.trim()}"`}>
              Check the spelling, or{" "}
              <button type="button" className="link-button" onClick={() => setSearch("")}>
                clear the search
              </button>
              .
            </EmptyState>
          ) : (
            <EmptyState title="No launches here">{type || region ? "Try All types or All regions." : emptyText}</EmptyState>
          )}
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
