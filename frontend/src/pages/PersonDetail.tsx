import { Link, useParams } from "react-router-dom";
import type { PersonWork, TaskRow, TaskStatus } from "../api/types";
import { personWork } from "../api/users";
import { changeStatus, MyTaskRow } from "../components/TaskRow";
import { Card } from "../components/ui/Card";
import { PageHeader } from "../components/ui/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/States";
import { Tag } from "../components/ui/Tag";
import { useToast } from "../components/ui/Toast";
import { useApi } from "../hooks/useApi";
import { formatDate } from "../lib/dates";

/** Admins only: one person's active launches, with their open tasks under each. */
export function PersonDetail() {
  const { id = "" } = useParams();
  const toast = useToast();
  const work = useApi(() => personWork(id), [id]);

  if (work.error) return <ErrorState error={work.error} onRetry={work.reload} />;
  if (!work.data) return <LoadingState label="Loading their work" />;
  const { person, launches } = work.data;

  function update(taskId: string, change: Partial<TaskRow> | null, saved?: TaskRow) {
    work.setData((current: PersonWork | null) =>
      current
        ? {
            ...current,
            launches: current.launches.map((launch) => ({
              ...launch,
              tasks: launch.tasks.map((t) => (t.id === taskId ? (saved ?? { ...t, ...change }) : t)),
            })),
          }
        : current,
    );
  }

  function onStatus(task: TaskRow, status: TaskStatus) {
    void changeStatus(task, status, update, toast.error).then(() => {
      if (status === "Done") toast.show(`Marked ${task.name} done.`);
      void work.reload();
    });
  }

  const openCount = launches.reduce((sum, launch) => sum + launch.tasks.length, 0);
  const firstName = person.first_name || person.name;

  return (
    <div className="page">
      <PageHeader
        back={{ to: "/users", label: "Users and roles" }}
        title={person.name}
        description={
          <span className="person-summary">
            <span className="tag tag--idle">{person.access_level ?? "No level"}</span>
            {!person.active && <Tag tone="idle">Inactive</Tag>}
            {person.roles.length > 0 && <span>{person.roles.map((r) => r.name).join(", ")}</span>}
            <span className="muted">{person.email}</span>
          </span>
        }
      />

      {launches.length === 0 ? (
        <Card>
          <EmptyState title={`${firstName} is not on any active launches`}>
            Launches show here when they are on the team or have a task. Closed launches are in the archive.
          </EmptyState>
        </Card>
      ) : (
        <>
          <p className="muted">
            {launches.length === 1 ? "1 active launch" : `${launches.length} active launches`} ·{" "}
            {openCount === 1 ? "1 open task" : `${openCount} open tasks`}
          </p>
          {launches.map((launch) => (
            <Card key={launch.id} className="task-card" aria-busy={work.loading}>
              <div className="person-launch-head">
                <h2>
                  <Link to={`/projects/${launch.id}`} className="row-title">
                    {launch.site || launch.name}
                  </Link>
                </h2>
                <span className="muted small">
                  {[
                    launch.program_type,
                    launch.day_one ? `Day 1 ${formatDate(launch.day_one)}` : "Day 1 not set",
                    launch.roles.length > 0 ? `on the team as ${launch.roles.join(", ")}` : null,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
              </div>
              {launch.tasks.length === 0 ? (
                <p className="muted person-launch-empty">
                  {launch.done > 0
                    ? `No open tasks. ${firstName} has finished all ${launch.done === 1 ? "1 task" : `${launch.done} tasks`} on this launch.`
                    : `No tasks assigned to ${firstName} on this launch.`}
                </p>
              ) : (
                <>
                  <ul className="rows">
                    {launch.tasks.map((task) => (
                      <MyTaskRow key={task.id} task={task} onStatus={onStatus} showProject={false} />
                    ))}
                  </ul>
                  {launch.done > 0 && (
                    <p className="muted small person-launch-empty">
                      {launch.done === 1 ? "1 more task is" : `${launch.done} more tasks are`} done or skipped.
                    </p>
                  )}
                </>
              )}
            </Card>
          ))}
        </>
      )}
    </div>
  );
}
