import { ComingSoon } from "../components/ui/ComingSoon";
import { PageHeader } from "../components/ui/PageHeader";

export function TaskDetail() {
  return (
    <>
      <PageHeader title="Task detail" description="Everything about one task." />
      <ComingSoon
        features={[
          "Status control",
          "Notes, Drive and Canva links",
          "Due date and timing rule",
          "Role and assignee (only admins can reassign)",
          "What must finish first and what is waiting on this",
          "Automatic reminders (7 days before and on the due date) and custom reminders",
        ]}
      />
    </>
  );
}
