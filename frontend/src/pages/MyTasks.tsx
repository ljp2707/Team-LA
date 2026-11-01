import { ComingSoon } from "../components/ui/ComingSoon";
import { PageHeader } from "../components/ui/PageHeader";

export function MyTasks() {
  return (
    <>
      <PageHeader title="My Tasks" description="Only tasks assigned to you, across every project." />
      <ComingSoon
        features={[
          "Your tasks across every project, sorted by due date with overdue on top",
          "One-click status: Not Started, In Progress, Blocked, Done",
          'Blocked tasks show "Waiting on [task]"',
          "Filters for this week and by project",
          'A "Do this first" card and upcoming reminders',
        ]}
      />
    </>
  );
}
