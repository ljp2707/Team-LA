import { useAuth } from "../auth/AuthContext";
import { ProjectGrid } from "../components/ProjectGrid";
import { PageHeader } from "../components/ui/PageHeader";

export function Projects() {
  const { me } = useAuth();
  const partner = me?.view === "partner";
  return (
    <div className="page">
      <PageHeader
        title={partner ? "Your program" : "Projects"}
        description={
          partner
            ? "The launches you are part of. Open one to see its tasks."
            : "Every launch in progress. You can look at any of them, and update the tasks assigned to you."
        }
      />
      <ProjectGrid
        showSummary={false}
        emptyText={partner ? "You are not on a launch yet. Ask your NMU contact." : "No launches are in progress."}
      />
    </div>
  );
}
