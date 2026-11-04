import { useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { ToastProvider } from "../ui/Toast";
import { Sidebar } from "./Sidebar";

export function AppShell() {
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();

  // Close the phone menu after moving to another page.
  useEffect(() => setMenuOpen(false), [location.pathname]);

  return (
    <ToastProvider>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <div className="shell">
        <Sidebar menuOpen={menuOpen} onToggleMenu={() => setMenuOpen((open) => !open)} />
        <main className="main" id="main" tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </ToastProvider>
  );
}
