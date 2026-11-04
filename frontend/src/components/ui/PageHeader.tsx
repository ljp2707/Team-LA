import type { ReactNode } from "react";
import { BackLink } from "./Bits";

interface PageHeaderProps {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  back?: { to: string; label: string };
}

export function PageHeader({ title, description, action, back }: PageHeaderProps) {
  return (
    <header className="page-header">
      <div>
        {back && <BackLink to={back.to}>{back.label}</BackLink>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {action && <div className="page-actions">{action}</div>}
    </header>
  );
}
