import { ComingSoon } from "../components/ui/ComingSoon";
import { PageHeader } from "../components/ui/PageHeader";

export function Users() {
  return (
    <>
      <PageHeader
        title="Users and roles"
        description="Tasks belong to roles, not names. One person can hold several roles."
      />
      <ComingSoon
        features={[
          "People with their roles (a person can hold several) and access level",
          "Hand off all of one person's open tasks to someone else",
          "A permissions table for Admin, Staff and Partner (phase 2)",
        ]}
      />
    </>
  );
}
