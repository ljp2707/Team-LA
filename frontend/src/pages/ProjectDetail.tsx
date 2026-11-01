import { ComingSoon } from "../components/ui/ComingSoon";
import { PageHeader } from "../components/ui/PageHeader";

export function ProjectDetail() {
  return (
    <>
      <PageHeader title="Project timeline" description="One launch, from first task to last." />
      <ComingSoon
        features={[
          "Summary: Day 1, % complete, overdue, hours, lead instructor",
          "Move Day 1, which shifts open due dates and reminders and keeps finished tasks' dates, with an undo notice",
          "Tasks grouped before, during and after the program",
          "Late tasks show how many tasks depend on them",
          "One-off tasks",
          "Partner contact and Drive link",
          "History log",
        ]}
      />
    </>
  );
}
