import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

interface ToastItem {
  id: number;
  text: string;
  tone: "info" | "error";
}

interface ToastApi {
  show: (text: string) => void;
  error: (text: string) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

const SHOW_MS = 5000;

/** Short messages after an action, read out to screen readers. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const next = useRef(1);

  const push = useCallback((text: string, tone: ToastItem["tone"]) => {
    const id = next.current++;
    setItems((current) => [...current, { id, text, tone }]);
    window.setTimeout(() => setItems((current) => current.filter((t) => t.id !== id)), SHOW_MS);
  }, []);

  const api = useMemo(
    () => ({ show: (text: string) => push(text, "info"), error: (text: string) => push(text, "error") }),
    [push],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {items.map((item) => (
          <div key={item.id} className={`toast toast--${item.tone}`}>
            {item.text}
            <button
              type="button"
              className="toast-close"
              aria-label="Dismiss"
              onClick={() => setItems((current) => current.filter((t) => t.id !== item.id))}
            >
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
