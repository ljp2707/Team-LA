import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { archiveDetail, listArchive } from "../api/archive";
import { StatTile } from "../components/ui/Bits";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { TextInput } from "../components/ui/Field";
import { PageHeader } from "../components/ui/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/States";
import { Tag } from "../components/ui/Tag";
import { useApi } from "../hooks/useApi";

const TASKS_SHOWN = 8;

/** Wait until typing stops before searching. */
function useDebounced<T>(value: T, ms = 300): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setSettled(value), ms);
    return () => window.clearTimeout(timer);
  }, [value, ms]);
  return settled;
}

export function Archive() {
  const [site, setSite] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const search = useDebounced(site);
  const list = useApi(() => listArchive({ site: search.trim(), from, to }), [search, from, to]);
  const launches = list.data?.launches ?? [];
  const current = selected && launches.some((l) => l.id === selected) ? selected : launches[0]?.id ?? null;
  const detail = useApi(() => (current ? archiveDetail(current) : Promise.resolve(null)), [current]);

  return (
    <div className="page">
      <PageHeader title="Archive" />

      <div className="filter-grid">
        <TextInput label="Site" type="search" placeholder="Search by site name" value={site} onChange={(e) => setSite(e.target.value)} maxLength={100} />
        <TextInput label="From" type="month" value={from} onChange={(e) => setFrom(e.target.value)} />
        <TextInput label="To" type="month" value={to} onChange={(e) => setTo(e.target.value)} />
      </div>

      {list.error ? (
        <ErrorState error={list.error} onRetry={list.reload} />
      ) : !list.data ? (
        <LoadingState label="Loading the archive" />
      ) : launches.length === 0 ? (
        <Card>
          <EmptyState title={site || from || to ? "No launches match" : "No finished launches yet"}>
            {site || from || to ? "Try a wider date range or another site name." : "Closed launches show up here."}
          </EmptyState>
        </Card>
      ) : (
        <div className="two-col two-col--even">
          <Card className="archive-list">
            <div className="split list-head" aria-hidden="true">
              <span>Launch</span>
              <span>On time</span>
            </div>
            <ul>
              {launches.map((l) => (
                <li key={l.id}>
                  <button
                    type="button"
                    className={`archive-item${l.id === current ? " is-selected" : ""}`}
                    aria-current={l.id === current ? "true" : undefined}
                    onClick={() => setSelected(l.id)}
                  >
                    <span className="row-main">
                      <span className="row-title">{l.site || l.name}</span>
                      <span className="row-sub">
                        {l.program_type} · {l.day_one ? `Day 1 ${l.day_one_text}` : "No Day 1"}
                      </span>
                    </span>
                    <span className={`archive-score${l.on_time !== null && l.on_time < 70 ? " is-late" : ""}`}>
                      {l.on_time === null ? "None" : `${l.on_time}%`}
                      <span className="visually-hidden"> on time</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </Card>

          <Card aria-live="polite">
            {detail.error ? (
              <ErrorState error={detail.error} onRetry={detail.reload} />
            ) : !detail.data ? (
              <LoadingState />
            ) : (
              <>
                <h2 className="archive-title">{detail.data.site || detail.data.name}</h2>
                <p className="muted">{detail.data.subtitle}</p>
                <div className="card-actions">
                  <Button to={`/projects/new?from=${detail.data.id}`}>Start a new launch from this</Button>
                </div>
                <div className="stat-row-plain">
                  <StatTile value={detail.data.counts.tasks} label="tasks" />
                  <StatTile value={detail.data.counts.late} label="finished late" />
                  <StatTile value={detail.data.counts.skipped} label="skipped" />
                  <StatTile value={detail.data.counts.added} label="added" />
                </div>
                <div className="table-scroll">
                  <table className="table table--archive">
                    <thead>
                      <tr>
                        <th scope="col">Task</th>
                        <th scope="col">
                          <span className="visually-hidden">Outcome</span>
                        </th>
                        <th scope="col">Planned</th>
                        <th scope="col">Actual</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.data.tasks.slice(0, TASKS_SHOWN).map((t) => (
                        <tr key={t.id}>
                          <th scope="row">
                            {t.name}
                            {t.done_by && <span className="row-sub">Done by {t.done_by}</span>}
                          </th>
                          <td>
                            <Tag tone={t.tone}>{t.label}</Tag>
                          </td>
                          <td>{t.planned}</td>
                          <td className={t.actual_late ? "is-late" : undefined}>{t.actual}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <Link className="strong-link" to={`/projects/${detail.data.id}`}>
                  See all {detail.data.counts.tasks} tasks and the full history log
                </Link>
              </>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
