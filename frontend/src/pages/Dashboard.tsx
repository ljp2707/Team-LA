import { ProjectGrid } from "../components/ProjectGrid";
import { Button } from "../components/ui/Button";
import { PageHeader } from "../components/ui/PageHeader";

export function Dashboard() {
  return (
    <div className="page">
      <PageHeader
        title="Active launches"
        action={<Button to="/projects/new">Start a launch</Button>}
      />
      <ProjectGrid showSummary emptyText="Start a launch to see it here." />
    </div>
  );
}
