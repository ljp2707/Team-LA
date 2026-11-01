import { Route, Routes } from "react-router-dom";
import { RequireAdmin } from "./auth/RequireAdmin";
import { RequireAuth } from "./auth/RequireAuth";
import { AppShell } from "./components/layout/AppShell";
import { Archive } from "./pages/Archive";
import { Dashboard } from "./pages/Dashboard";
import { Home } from "./pages/Home";
import { MyTasks } from "./pages/MyTasks";
import { NewProject } from "./pages/NewProject";
import { NotAuthorized } from "./pages/NotAuthorized";
import { NotFound } from "./pages/NotFound";
import { ProjectDetail } from "./pages/ProjectDetail";
import { Projects } from "./pages/Projects";
import { TaskDetail } from "./pages/TaskDetail";
import { Templates } from "./pages/Templates";
import { Users } from "./pages/Users";

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/not-authorized" element={<NotAuthorized />} />

      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route path="/my-tasks" element={<MyTasks />} />
          <Route path="/projects" element={<Projects />} />
          <Route path="/projects/:id" element={<ProjectDetail />} />
          <Route path="/tasks/:id" element={<TaskDetail />} />

          <Route element={<RequireAdmin />}>
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/projects/new" element={<NewProject />} />
            <Route path="/templates" element={<Templates />} />
            <Route path="/users" element={<Users />} />
            <Route path="/archive" element={<Archive />} />
          </Route>
        </Route>
      </Route>

      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
