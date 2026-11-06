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
      />
      <ProjectGrid
        showSummary={false}
        emptyText={partner ? "You are not on a launch yet. Ask your NMU contact." : "No launches are in progress."}
      />
    </div>
  );
}
