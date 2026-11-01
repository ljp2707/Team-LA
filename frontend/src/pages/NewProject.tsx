import { ComingSoon } from "../components/ui/ComingSoon";
import { PageHeader } from "../components/ui/PageHeader";

export function NewProject() {
  return (
    <>
      <PageHeader
        title="Start a launch"
        description="One project is one program launch at one site."
      />
      <ComingSoon
        features={[
          "Start from a template or a past launch",
          "Program type, site, site type, program name, Day 1, program hours, location, lead instructors, partner contact, Google Drive folder link",
          "Site profile pre-fills",
          "Preview of the generated task list with default owner by role and an optional person per task",
          "Add a one-off task",
          "Create the project",
        ]}
      />
    </>
  );
}
