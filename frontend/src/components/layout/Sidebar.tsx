import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { myTasks } from "../../api/tasks";
import { useAuth } from "../../auth/AuthContext";
import { Avatar } from "../ui/Bits";
import { LogoMark } from "../ui/LogoMark";
import { ViewSwitch } from "./ViewSwitch";

interface NavItem {
  to: string;
  label: string;
  note?: string;
  badge?: boolean;
}

const ADMIN_NAV: NavItem[] = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/my-tasks", label: "My Tasks", badge: true },
  { to: "/templates", label: "Templates" },
  { to: "/users", label: "Users and roles" },
  { to: "/archive", label: "Archive" },
];

const STAFF_NAV: NavItem[] = [
  { to: "/my-tasks", label: "My Tasks", badge: true },
  { to: "/projects", label: "Projects", note: "view only" },
];

const PARTNER_NAV: NavItem[] = [
  { to: "/my-tasks", label: "My Tasks", badge: true },
  { to: "/projects", label: "Your program" },
];

/** Open tasks for the badge. Reloads when the page changes so it stays close to right. */
function useOpenCount(): number | null {
  const [count, setCount] = useState<number | null>(null);
  const location = useLocation();
  useEffect(() => {
    let live = true;
    myTasks()
      .then((data) => live && setCount(data.counts.open))
      .catch(() => live && setCount(null));
    return () => {
      live = false;
    };
  }, [location.pathname]);
  return count;
}

export function Sidebar({ menuOpen, onToggleMenu }: { menuOpen: boolean; onToggleMenu: () => void }) {
  const { me } = useAuth();
  const openCount = useOpenCount();
  if (!me) return null;

  const { first_name, last_name, email, roles } = me.user;
  const name = [first_name, last_name].filter(Boolean).join(" ") || email;
  const subtitle = [me.access_level, roles[0]].filter(Boolean).join(" · ");
  const nav = me.view === "admin" ? ADMIN_NAV : me.view === "partner" ? PARTNER_NAV : STAFF_NAV;

  return (
    <aside className={`sidebar${menuOpen ? " is-open" : ""}`}>
      <div className="sidebar-top">
        <NavLink to={me.home} className="logo">
          <LogoMark size={32} />
          <span>
            NMU
            <br />
            Launches
          </span>
        </NavLink>
        <button
          type="button"
          className="menu-button"
          aria-expanded={menuOpen}
          aria-controls="sidebar-menu"
          onClick={onToggleMenu}
        >
          <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
            {menuOpen ? (
              <path d="M4 4l10 10M14 4 4 14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            ) : (
              <path d="M2 4h14M2 9h14M2 14h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            )}
          </svg>
          Menu
        </button>
      </div>

      <div className="sidebar-menu" id="sidebar-menu">
        <nav className="sidebar-nav" aria-label="Main">
          {nav.map((item) => (
            <NavLink key={item.to} to={item.to} className="nav-link" end={item.to === "/projects" ? false : undefined}>
              {item.label}
              {item.note && <span className="nav-note">{item.note}</span>}
              {item.badge && openCount !== null && openCount > 0 && (
                <span className="nav-badge" aria-label={`${openCount} open`}>
                  {openCount}
                </span>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-foot">
          {me.can_switch_view && <ViewSwitch />}
          <div className="user-block">
            <Avatar name={name} />
            <div>
              <div className="user-name">{name}</div>
              <div className="user-subtitle">{subtitle}</div>
            </div>
          </div>
          <a className="sign-out" href="/auth/logout">
            Sign out
          </a>
        </div>
      </div>
    </aside>
  );
}
