import { NavLink } from "react-router-dom";
import { useAuth } from "../../auth/AuthContext";
import { LogoMark } from "../ui/LogoMark";
import { ViewSwitch } from "./ViewSwitch";

interface NavItem {
  to: string;
  label: string;
  note?: string;
}

const ADMIN_NAV: NavItem[] = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/my-tasks", label: "My Tasks" },
  { to: "/templates", label: "Templates" },
  { to: "/users", label: "Users and roles" },
  { to: "/archive", label: "Archive" },
];

const STAFF_NAV: NavItem[] = [
  { to: "/my-tasks", label: "My Tasks" },
  { to: "/projects", label: "Projects", note: "view only" },
];

export function Sidebar() {
  const { me, isAdminView } = useAuth();
  if (!me) return null;

  const { first_name, last_name, email, roles } = me.user;
  const name = [first_name, last_name].filter(Boolean).join(" ") || email;
  const subtitle = [me.access_level, roles[0]].filter(Boolean).join(" · ");

  return (
    <aside className="sidebar">
      <NavLink to={me.home} className="logo">
        <LogoMark size={32} />
        <span>
          NMU
          <br />
          Launches
        </span>
      </NavLink>

      <nav className="sidebar-nav" aria-label="Main">
        {(isAdminView ? ADMIN_NAV : STAFF_NAV).map((item) => (
          <NavLink key={item.to} to={item.to} className="nav-link">
            {item.label}
            {item.note && <span className="nav-note">{item.note}</span>}
          </NavLink>
        ))}
      </nav>

      <div className="sidebar-foot">
        {me.can_switch_view && <ViewSwitch />}
        <div className="user-block">
          <span className="avatar" aria-hidden="true">
            {name[0].toUpperCase()}
          </span>
          <div>
            <div className="user-name">{name}</div>
            <div className="user-subtitle">{subtitle}</div>
          </div>
        </div>
        <a className="sign-out" href="/auth/logout">
          Sign out
        </a>
      </div>
    </aside>
  );
}
