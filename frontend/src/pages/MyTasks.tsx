import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { myReminders, myTasks } from "../api/tasks";
import type { MyTasks as MyTasksData, MyTasksSort, TaskRow, TaskStatus } from "../api/types";
import { CalendarFeedCard } from "../components/CalendarFeedCard";
import { changeStatus, MyTaskRow } from "../components/TaskRow";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Chips } from "../components/ui/Chips";
import { SectionLabel } from "../components/ui/Bits";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/States";
import { useToast } from "../components/ui/Toast";
import { useApi } from "../hooks/useApi";

type Filter = "all" | "week" | "overdue";

const LATER_SHOWN = 5;

const GROUPS: { key: keyof MyTasksData["groups"]; label: string; tone?: "late" }[] = [
  { key: "overdue", label: "Overdue", tone: "late" },
  { key: "this_week", label: "This week" },
  { key: "later", label: "Later" },
  { key: "done_recently", label: "Done recently" },
];

const SORTS: { value: MyTasksSort; label: string }[] = [
  { value: "due", label: "Due date" },
  { value: "program", label: "Program" },
  { value: "location", label: "Location" },
];

export function MyTasks() {
  const toast = useToast();
  // Filters live in the address, so a filtered view can be refreshed or shared.
  const [params, setParams] = useSearchParams();
  const show = params.get("show");
  const filter: Filter = show === "week" || show === "overdue" ? show : "all";
  const project = params.get("project") ?? "";
  const state = params.get("state") ?? "";
  const city = params.get("city") ?? "";
  const programType = params.get("type") ?? "";
  const sortParam = params.get("sort");
  const sort: MyTasksSort = sortParam === "program" || sortParam === "location" ? sortParam : "due";
  const [showAll, setShowAll] = useState(false);
  const tasks = useApi(
    () =>
      myTasks({
        filter: filter === "all" ? undefined : filter,
        project: project || undefined,
        state: state || undefined,
        city: city || undefined,
        program_type: programType || undefined,
        sort: sort === "due" ? undefined : sort,
      }),
    [filter, project, state, city, programType, sort],
  );

  /** Change one filter in the address. Empty or default values are left out. */
  function setParam(name: string, value: string, defaultValue = "") {
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (value && value !== defaultValue) next.set(name, value);
        else next.delete(name);
        return next;
      },
      { replace: true },
    );
  }
  const filtered = filter !== "all" || Boolean(project || state || city || programType);
  const reminders = useApi(myReminders, []);

  function update(id: string, change: Partial<TaskRow> | null, saved?: TaskRow) {
    tasks.setData((current) => {
      if (!current) return current;
      const groups = Object.fromEntries(
        Object.entries(current.groups).map(([key, rows]) => [
          key,
          (rows as TaskRow[]).map((row) => (row.id === id ? (saved ?? { ...row, ...change }) : row)),
        ]),
      ) as MyTasksData["groups"];
      return { ...current, groups };
    });
  }

  function onStatus(task: TaskRow, status: TaskStatus) {
    void changeStatus(task, status, update, toast.error).then(() => {
      if (status === "Done") toast.show(`Marked ${task.name} done.`);
      void reminders.reload();
    });
  }

  const data = tasks.data;
  const total = data ? Object.values(data.groups).reduce((sum, rows) => sum + rows.length, 0) : 0;

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>My Tasks</h1>
        </div>
      </header>

      {/* Full width, above both columns, so the filters never run under the Reminders card. */}
      <div className="toolbar toolbar--wrap">
        <Chips<Filter>
          label="Show"
          value={filter}
          onChange={(value) => setParam("show", value, "all")}
          options={[
            { value: "all", label: "All" },
            { value: "week", label: "Due this week" },
            { value: "overdue", label: "Overdue" },
          ]}
        />
        <label className="inline-select">
          <span>Project</span>
          <select className="input select" value={project} onChange={(event) => setParam("project", event.target.value)}>
            <option value="">All projects</option>
            {data?.projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        {/* Each filter shows only when some of your tasks have a value for it (or it is in use). */}
        {(data?.filters.states.length || state) && (
          <label className="inline-select">
            <span>State</span>
            <select className="input select" value={state} onChange={(event) => setParam("state", event.target.value)}>
              <option value="">All states</option>
              {data?.filters.states.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
        )}
        {(data?.filters.cities.length || city) && (
          <label className="inline-select">
            <span>City</span>
            <select className="input select" value={city} onChange={(event) => setParam("city", event.target.value)}>
              <option value="">All cities</option>
              {data?.filters.cities.map((c) => (
                <option key={c.label} value={c.value}>
                  {c.label}
                </option>
              ))}
            </select>
          </label>
        )}
        {(data?.filters.program_types.length || programType) && (
          <label className="inline-select">
            <span>Program type</span>
            <select
              className="input select"
              value={programType}
              onChange={(event) => setParam("type", event.target.value)}
            >
              <option value="">All types</option>
              {data?.filters.program_types.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="inline-select">
          <span>Sort by</span>
          <select className="input select" value={sort} onChange={(event) => setParam("sort", event.target.value, "due")}>
            {SORTS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="page--aside page-columns">
        <div className="page-main">
          {tasks.error ? (
            <ErrorState error={tasks.error} onRetry={tasks.reload} />
          ) : !data ? (
            <LoadingState label="Loading your tasks" />
          ) : total === 0 ? (
            <Card>
              <EmptyState title={filtered ? "No tasks match" : "Nothing assigned to you"}>
                {filtered
                  ? "Try All, and clear the other filters, to see everything assigned to you."
                  : "When an admin gives you a task it shows up here."}
              </EmptyState>
            </Card>
          ) : (
            <Card className="task-card" aria-busy={tasks.loading}>
              {GROUPS.map(({ key, label, tone }) => {
                let rows = data.groups[key];
                if (!rows.length) return null;
                const hidden = key === "later" && !showAll ? Math.max(0, rows.length - LATER_SHOWN) : 0;
                if (hidden) rows = rows.slice(0, LATER_SHOWN);
                return (
                  <section key={key} className="task-group" aria-label={label}>
                    <SectionLabel tone={tone}>{label}</SectionLabel>
                    <ul className="rows">
                      {rows.map((task) => (
                        <MyTaskRow key={task.id} task={task} onStatus={onStatus} />
                      ))}
                    </ul>
                    {hidden > 0 && (
                      <button type="button" className="text-button" onClick={() => setShowAll(true)}>
                        Show {hidden} more
                      </button>
                    )}
                  </section>
                );
              })}
            </Card>
          )}
        </div>

        <aside className="page-aside">
          {data?.do_this_first && (
            <section className="first-card" aria-label="Do this first">
              <p className="eyebrow-light">Do this first</p>
              <h2>{data.do_this_first.name}</h2>
              <p>{data.do_this_first.reason}</p>
              <Button variant="light" to={`/tasks/${data.do_this_first.id}`}>
                Open task
              </Button>
            </section>
          )}
          <Card>
            <h2>Reminders</h2>
            {reminders.error ? (
              <p className="muted">Reminders did not load.</p>
            ) : !reminders.data ? (
              <LoadingState label="Loading reminders" />
            ) : reminders.data.reminders.length === 0 ? (
              <p className="muted">No reminders coming up.</p>
            ) : (
              <ul className="reminder-list">
                {reminders.data.reminders.slice(0, 6).map((r, index) => (
                  <li key={`${r.date}-${index}`}>
                    <strong>{r.when}</strong>
                    <span className="muted">
                      {r.task_id ? <Link to={`/tasks/${r.task_id}`}>{r.text}</Link> : r.text}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <CalendarFeedCard />
        </aside>
      </div>
    </div>
  );
}
