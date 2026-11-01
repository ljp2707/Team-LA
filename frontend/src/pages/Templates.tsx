import { ComingSoon } from "../components/ui/ComingSoon";
import { PageHeader } from "../components/ui/PageHeader";

export function Templates() {
  return (
    <>
      <PageHeader
        title="Templates"
        description="One template per kind of launch. Changes only apply to new projects."
      />
      <ComingSoon
        features={[
          "One template per program type, with a list of steps showing timing, default role and dependencies",
          "Duplicate a template, or save a project as a template",
          "Version drafts that do not affect running projects",
          'A "From past launches" panel showing steps often late, skipped or added',
        ]}
      />
    </>
  );
}
