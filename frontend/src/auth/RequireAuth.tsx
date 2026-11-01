import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "./AuthContext";

/** Sends anyone not signed in to the home page. */
export function RequireAuth() {
  const { loading, me } = useAuth();
  if (loading) {
    return (
      <div className="standalone" role="status">
        Loading
      </div>
    );
  }
  return me ? <Outlet /> : <Navigate to="/" replace />;
}
