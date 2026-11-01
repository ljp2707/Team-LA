import { useEffect, useState } from "react";
import { api } from "../api/client";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { ComingSoon } from "../components/ui/ComingSoon";
import { PageHeader } from "../components/ui/PageHeader";
import { Tag } from "../components/ui/Tag";

interface AirtableHealth {
  connected: boolean;
  tables: { table: string; count: number | null; error: string | null }[];
}

function AirtableStatus() {
  const [health, setHealth] = useState<AirtableHealth | "loading" | "failed">("loading");

  useEffect(() => {
    api<AirtableHealth>("/api/health/airtable")
      .then(setHealth)
      .catch(() => setHealth("failed"));
  }, []);

  if (health === "loading") {
    return (
      <Card className="status-card">
        <span>Checking Airtable</span>
      </Card>
    );
  }

  if (health === "failed" || !health.connected) {
    return (
      <Card className="status-card">
        <span>Airtable not connected</span>
        <Tag tone="late">Check setup</Tag>
      </Card>
    );
  }

  const projects = health.tables.find((t) => t.table === "Session")?.count ?? 0;
  return (
    <Card className="status-card">
      <span>
        Airtable connected, {projects} {projects === 1 ? "project" : "projects"}
      </span>
      <Tag tone="done">Connected</Tag>
    </Card>
  );
}

export function Dashboard() {
  return (
    <>
      <PageHeader
        title="Active launches"
        description="Every program launch in progress, one card each."
        action={<Button to="/projects/new">Start a launch</Button>}
      />
      <AirtableStatus />
      <ComingSoon
        features={[
          "One card per active project with site, program type, Day 1, % complete, overdue count, next milestone and lead instructor",
          "A summary row: active launches, overdue, blocked, next Day 1",
          "Sort and filter",
          "Clicking a card opens the project",
        ]}
      />
    </>
  );
}
