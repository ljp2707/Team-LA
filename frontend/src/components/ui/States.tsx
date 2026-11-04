import type { ReactNode } from "react";
import type { ApiError } from "../../api/client";
import { Button } from "./Button";
import { Card } from "./Card";

export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div className="state" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      {label}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="state state--empty">
      <p className="state-title">{title}</p>
      {children && <div className="muted">{children}</div>}
    </div>
  );
}

/** Errors from the API. A 403 gets the friendly "no access" view. */
export function ErrorState({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  if (error.status === 403) {
    return (
      <Card className="state state--card">
        <h2>You do not have access to this page</h2>
        <p className="muted">Ask an admin if you think you should.</p>
        <Button to="/my-tasks" variant="dark">
          Go to My Tasks
        </Button>
      </Card>
    );
  }
  if (error.status === 404) {
    return (
      <Card className="state state--card">
        <h2>Not found</h2>
        <p className="muted">{error.message}</p>
        <Button to="/my-tasks" variant="dark">
          Go to My Tasks
        </Button>
      </Card>
    );
  }
  return (
    <Card className="state state--card" >
      <h2>That did not load</h2>
      <p className="muted" role="alert">
        {error.message}
      </p>
      {onRetry && (
        <Button onClick={onRetry} variant="dark">
          Try again
        </Button>
      )}
    </Card>
  );
}
