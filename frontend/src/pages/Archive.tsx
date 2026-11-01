import { ComingSoon } from "../components/ui/ComingSoon";
import { PageHeader } from "../components/ui/PageHeader";

export function Archive() {
  return (
    <>
      <PageHeader
        title="Archive"
        description="Every finished launch, kept for good. Only admins can see this page."
      />
      <ComingSoon
        features={[
          "Finished projects, searchable by site and date",
          "Planned vs actual dates per task, with late, skipped and added markers",
          "Start a new launch from a past one",
        ]}
      />
    </>
  );
}
