import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Button } from "./Button";

export function ProgressBar({ value, label }: { value: number; label: string }) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div
      className="progress"
      role="progressbar"
      aria-label={label}
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <span style={{ width: `${clamped}%` }} />
    </div>
  );
}

export function StatTile({
  value,
  label,
  tone,
  to,
}: {
  value: ReactNode;
  label: string;
  tone?: "late";
  to?: string;
}) {
  const body = (
    <>
      <span className={`stat-value${tone === "late" ? " is-late" : ""}`}>{value}</span>
      <span className="stat-caption">{label}</span>
    </>
  );
  return to ? (
    <Link className="stat-tile stat-tile--link" to={to}>
      {body}
    </Link>
  ) : (
    <div className="stat-tile">{body}</div>
  );
}

const AVATAR_TINTS = ["blue", "green", "peach", "sand", "lilac"];

export function Avatar({ name, size = "md" }: { name: string; size?: "sm" | "md" }) {
  const letter = (name.trim()[0] || "?").toUpperCase();
  const tint = AVATAR_TINTS[letter.charCodeAt(0) % AVATAR_TINTS.length];
  return (
    <span className={`avatar avatar--${tint} avatar--${size}`} aria-hidden="true">
      {letter}
    </span>
  );
}

/** The blue banner after moving Day 1, with Undo. */
export function UndoBanner({
  message,
  onUndo,
  onDismiss,
  busy,
}: {
  message: string;
  onUndo?: () => void;
  onDismiss: () => void;
  busy?: boolean;
}) {
  const [first, ...rest] = message.split(". ");
  return (
    <div className="banner" role="status">
      <p>
        <strong>{first}.</strong> {rest.join(". ")}
      </p>
      <div className="banner-actions">
        {onUndo && (
          <Button variant="light" onClick={onUndo} disabled={busy}>
            {busy ? "Undoing" : "Undo"}
          </Button>
        )}
        <button type="button" className="text-button" onClick={onDismiss}>
          Dismiss
        </button>
      </div>
    </div>
  );
}

export function BackLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link className="back-link" to={to}>
      {children}
    </Link>
  );
}

export function SectionLabel({ children, tone }: { children: ReactNode; tone?: "late" }) {
  return <h3 className={`section-label${tone === "late" ? " is-late" : ""}`}>{children}</h3>;
}
