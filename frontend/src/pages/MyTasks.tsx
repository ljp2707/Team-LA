import { useState } from "react";
import { Link } from "react-router-dom";
import { myReminders, myTasks } from "../api/tasks";
import type { MyTasks as MyTasksData, TaskRow, TaskStatus } from "../api/types";
import { useAuth } from "../auth/AuthContext";
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

export function MyTasks() {
  const { me } = useAuth();
  const toast = useToast();
  const [filter, setFilter] = useState<Filter>("all");
  const [project, setProject] = useState("");
  const [showAll, setShowAll] = useState(false);
  const tasks = useApi(
    () => myTasks({ filter: filter === "all" ? undefined : filter, project: project || undefined }),
    [filter, project],
  );
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
    <div className="page page--aside">
      <div className="page-main">
        <header className="page-header">
          <div>
            <h1>My Tasks</h1>
            <p>
              Only tasks assigned to you, across every {me?.view === "partner" ? "program you work on" : "project"}.{" "}
              {data && (
                <>
                  {data.counts.overdue > 0 && <strong className="is-late">{data.counts.overdue} overdue</strong>}
                  {data.counts.overdue > 0 && ", "}
                  {data.counts.this_week} due this week.
                </>
              )}
            </p>
          </div>
        </header>

        <div className="toolbar">
          <Chips<Filter>
            label="Show"
            value={filter}
            onChange={setFilter}
            options={[
              { value: "all", label: "All" },
              { value: "week", label: "Due this week" },
              { value: "overdue", label: "Overdue" },
            ]}
          />
          <label className="inline-select">
            <span>Project</span>
            <select className="input select" value={project} onChange={(event) => setProject(event.target.value)}>
              <option value="">All projects</option>
              {data?.projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        {tasks.error ? (
          <ErrorState error={tasks.error} onRetry={tasks.reload} />
        ) : !data ? (
          <LoadingState label="Loading your tasks" />
        ) : total === 0 ? (
          <Card>
            <EmptyState title={filter === "all" && !project ? "Nothing assigned to you" : "No tasks match"}>
              {filter === "all" && !project
                ? "When an admin gives you a task it shows up here."
                : "Try All to see everything assigned to you."}
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
      </aside>
    </div>
  );
}
