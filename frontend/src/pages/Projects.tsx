import { ComingSoon } from "../components/ui/ComingSoon";
import { PageHeader } from "../components/ui/PageHeader";

export function Projects() {
  return (
    <>
      <PageHeader title="Projects" description="Every active launch, view only." />
      <ComingSoon features={["The same project cards as the dashboard, read only"]} />
    </>
  );
}
