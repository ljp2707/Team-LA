import { useEffect, useId, useRef, useState } from "react";
import type { TaskStatus } from "../../api/types";
import { STATUS_LABELS, STATUS_TONES, StatusTag } from "./StatusTag";

const CHOICES: TaskStatus[] = ["Not Started", "In Progress", "Blocked", "Done"];

interface StatusMenuProps {
  status: TaskStatus;
  taskName: string;
  canEdit: boolean;
  canSkip?: boolean;
  onChange: (status: TaskStatus) => void;
}

/** One-click status: the tag opens a small menu. Read only people just see the tag. */
export function StatusMenu({ status, taskName, canEdit, canSkip = false, onChange }: StatusMenuProps) {
  const [open, setOpen] = useState(false);
  const wrapper = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    function close(event: MouseEvent | KeyboardEvent) {
      if (event instanceof KeyboardEvent) {
        if (event.key === "Escape") {
          setOpen(false);
          button.current?.focus();
        }
        return;
      }
      if (!wrapper.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    wrapper.current?.querySelector<HTMLButtonElement>("[role=menuitemradio]")?.focus();
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  if (!canEdit) return <StatusTag status={status} />;

  const choices = canSkip ? [...CHOICES, "Skipped" as TaskStatus] : CHOICES;

  function onMenuKey(event: React.KeyboardEvent) {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    event.preventDefault();
    const items = Array.from(wrapper.current?.querySelectorAll<HTMLButtonElement>("[role=menuitemradio]") ?? []);
    const index = items.indexOf(document.activeElement as HTMLButtonElement);
    const next = event.key === "ArrowDown" ? (index + 1) % items.length : (index - 1 + items.length) % items.length;
    items[next]?.focus();
  }

  return (
    <div className="status-menu" ref={wrapper}>
      <button
        ref={button}
        type="button"
        className={`status-button tag tag--${STATUS_TONES[status]}`}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label={`Status of ${taskName}: ${STATUS_LABELS[status]}. Change status`}
        onClick={() => setOpen((value) => !value)}
      >
        {STATUS_LABELS[status]}
        <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
          <path d="M2 3.5 5 6.5 8 3.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      </button>
      {open && (
        <div className="status-popover" role="menu" id={menuId} aria-label={`Status for ${taskName}`} onKeyDown={onMenuKey}>
          {choices.map((choice) => (
            <button
              key={choice}
              type="button"
              role="menuitemradio"
              aria-checked={choice === status}
              onClick={() => {
                setOpen(false);
                button.current?.focus();
                if (choice !== status) onChange(choice);
              }}
            >
              {STATUS_LABELS[choice]}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
