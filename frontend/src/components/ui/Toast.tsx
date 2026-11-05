import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

interface ToastItem {
  id: number;
  text: string;
  tone: "info" | "error";
  leaving?: boolean;
}

interface ToastApi {
  show: (text: string) => void;
  error: (text: string) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

const SHOW_MS = 5000;
/** Matches the .toast.is-leaving transition in motion.css. */
const LEAVE_MS = 180;

interface Timer {
  handle: number;
  /** When the current countdown started, and how much of SHOW_MS was left then. */
  started: number;
  remaining: number;
}

/**
 * Short messages after an action, read out to screen readers.
 *
 * Toasts slide out instead of vanishing. Their timers pause while the pointer
 * is over them or the tab is hidden, so nobody misses a message they were
 * still reading.
 */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const next = useRef(1);
  const timers = useRef(new Map<number, Timer>());
  const paused = useRef(false);

  const dismiss = useCallback((id: number) => {
    const timer = timers.current.get(id);
    if (timer) window.clearTimeout(timer.handle);
    timers.current.delete(id);
    setItems((current) => current.map((t) => (t.id === id ? { ...t, leaving: true } : t)));
    window.setTimeout(() => setItems((current) => current.filter((t) => t.id !== id)), LEAVE_MS);
  }, []);

  const start = useCallback(
    (id: number, remaining: number) => {
      const handle = window.setTimeout(() => dismiss(id), remaining);
      timers.current.set(id, { handle, started: Date.now(), remaining });
    },
    [dismiss],
  );

  const pauseAll = useCallback(() => {
    if (paused.current) return;
    paused.current = true;
    for (const timer of timers.current.values()) {
      window.clearTimeout(timer.handle);
      timer.remaining = Math.max(1000, timer.remaining - (Date.now() - timer.started));
    }
  }, []);

  const resumeAll = useCallback(() => {
    if (!paused.current) return;
    paused.current = false;
    for (const [id, timer] of timers.current) start(id, timer.remaining);
  }, [start]);

  useEffect(() => {
    const onVisibility = () => (document.hidden ? pauseAll() : resumeAll());
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [pauseAll, resumeAll]);

  const push = useCallback(
    (text: string, tone: ToastItem["tone"]) => {
      const id = next.current++;
      setItems((current) => [...current, { id, text, tone }]);
      if (paused.current) {
        timers.current.set(id, { handle: 0, started: Date.now(), remaining: SHOW_MS });
      } else {
        start(id, SHOW_MS);
      }
    },
    [start],
  );

  const api = useMemo(
    () => ({ show: (text: string) => push(text, "info"), error: (text: string) => push(text, "error") }),
    [push],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toasts" role="status" aria-live="polite" onPointerEnter={pauseAll} onPointerLeave={resumeAll}>
        {items.map((item) => (
          <div key={item.id} className={`toast toast--${item.tone}${item.leaving ? " is-leaving" : ""}`}>
            {item.text}
            <button type="button" className="toast-close" aria-label="Dismiss" onClick={() => dismiss(item.id)}>
              Dismiss
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const toast = useContext(ToastContext);
  if (!toast) throw new Error("useToast must be used inside ToastProvider");
  return toast;
}
