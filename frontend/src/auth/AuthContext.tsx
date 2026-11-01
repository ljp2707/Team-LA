import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api } from "../api/client";

export type View = "admin" | "staff";

/** The answer from GET /api/me. */
export interface Me {
  user: {
    id: string;
    email: string;
    first_name: string;
    last_name: string;
    roles: string[];
  };
  access_level: string | null;
  base_view: View;
  view: View;
  home: string;
  can_switch_view: boolean;
  dev_mode: boolean;
}

interface Auth {
  loading: boolean;
  me: Me | null;
  /** True in admin view. Only for display: the backend enforces every rule. */
  isAdminView: boolean;
  switchView: (view: View) => Promise<Me>;
}

const AuthContext = createContext<Auth | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    api<Me>("/api/me")
      .then(setMe)
      .catch(() => setMe(null))
      .finally(() => setLoading(false));
  }, []);

  const switchView = useCallback(async (view: View) => {
    const updated = await api<Me>("/api/me/view", {
      method: "POST",
      body: JSON.stringify({ view }),
    });
    setMe(updated);
    return updated;
  }, []);

  const value = useMemo(
    () => ({ loading, me, isAdminView: me?.view === "admin", switchView }),
    [loading, me, switchView],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): Auth {
  const auth = useContext(AuthContext);
  if (!auth) throw new Error("useAuth must be used inside AuthProvider");
  return auth;
}
