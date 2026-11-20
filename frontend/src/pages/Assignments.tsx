import { Link } from "react-router-dom";
import { listPeople } from "../api/users";
import { Avatar } from "../components/ui/Bits";
import { Card } from "../components/ui/Card";
import { PageHeader } from "../components/ui/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/States";
import { useApi } from "../hooks/useApi";

/** Admins only: everyone who is active, busiest first. A name opens that person's launches and tasks. */
export function Assignments() {
  const people = useApi(() => listPeople(false), []);

  if (people.error) return <ErrorState error={people.error} onRetry={people.reload} />;
  if (!people.data) return <LoadingState label="Loading people" />;

  const active = people.data.people
    .filter((p) => p.active)
    .sort((a, b) => b.open_tasks - a.open_tasks || a.name.localeCompare(b.name));
  const total = active.reduce((sum, p) => sum + p.open_tasks, 0);

  return (
    <div className="page">
      <PageHeader title="Assignments" description="What each person is assigned to. Choose a name to see their programs and open tasks." />

      <Card>
        <div className="split">
          <h2>People</h2>
          <span className="muted small">
            {active.length} {active.length === 1 ? "person" : "people"} · {total} open {total === 1 ? "task" : "tasks"}
          </span>
        </div>
        {active.length === 0 ? (
          <EmptyState title="Nobody here yet">People added on Users and roles show here.</EmptyState>
        ) : (
          <ul className="people-list people-list--work">
            {active.map((person) => (
              <li key={person.id}>
                <Avatar name={person.name} />
                <div className="row-main">
                  <Link to={`/assignments/${person.id}`} className="row-title">
                    {person.name}
                  </Link>
                  <span className="pill-row">
                    {person.roles.length === 0 ? (
                      <span className="muted small">No role yet</span>
                    ) : (
                      person.roles.map((r) => (
                        <span key={r.id} className="pill">
                          {r.name}
                        </span>
                      ))
                    )}
                  </span>
                </div>
                <span className={`small nowrap${person.open_tasks === 0 ? " muted" : ""}`}>
                  {person.open_tasks === 0
                    ? "No open tasks"
                    : `${person.open_tasks} open ${person.open_tasks === 1 ? "task" : "tasks"}`}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
