import { useNavigate } from "react-router-dom";
import { useAuth } from "../../auth/AuthContext";
import type { View } from "../../auth/AuthContext";

const OPTIONS: { view: View; label: string }[] = [
  { view: "admin", label: "Admin view" },
  { view: "staff", label: "Staff view" },
];

/** Lets an admin see exactly what staff see. The backend changes with the view. */
export function ViewSwitch() {
  const { me, switchView } = useAuth();
  const navigate = useNavigate();

  async function choose(view: View) {
    if (view === me?.view) return;
    const updated = await switchView(view);
    navigate(updated.home);
  }

  return (
    <div className="view-switch-group">
      {me?.dev_mode && <div className="dev-label">Dev mode</div>}
      <div className="view-switch" role="group" aria-label="Switch view">
        {OPTIONS.map(({ view, label }) => (
          <button
            key={view}
            type="button"
            aria-pressed={me?.view === view}
            onClick={() => void choose(view)}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}
