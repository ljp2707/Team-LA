import { ProjectGrid } from "../components/ProjectGrid";
import { Button } from "../components/ui/Button";
import { PageHeader } from "../components/ui/PageHeader";

export function Dashboard() {
  return (
    <div className="page">
      <PageHeader
        title="Active programs"
        action={<Button to="/projects/new">Start a program</Button>}
      />
      <ProjectGrid showSummary emptyText="Start a program to see it here." />
    </div>
  );
}
