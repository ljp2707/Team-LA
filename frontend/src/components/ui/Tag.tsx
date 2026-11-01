import type { ReactNode } from "react";

export type TagTone = "progress" | "late" | "done" | "idle";

export function Tag({ tone = "idle", children }: { tone?: TagTone; children: ReactNode }) {
  return <span className={`tag tag--${tone}`}>{children}</span>;
}
