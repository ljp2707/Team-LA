import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "./AuthContext";

/** Sends anyone not in admin view to My Tasks. The backend enforces this too. */
export function RequireAdmin() {
  const { isAdminView } = useAuth();
  return isAdminView ? <Outlet /> : <Navigate to="/my-tasks" replace />;
}
