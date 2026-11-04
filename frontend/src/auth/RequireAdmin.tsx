import { Outlet } from "react-router-dom";
import { ApiError } from "../api/client";
import { ErrorState } from "../components/ui/States";
import { useAuth } from "./AuthContext";

/** Admin pages show a friendly "no access" message outside admin view. The backend enforces this too. */
export function RequireAdmin() {
  const { isAdminView } = useAuth();
  return isAdminView ? <Outlet /> : <ErrorState error={new ApiError(403, "")} />;
}
