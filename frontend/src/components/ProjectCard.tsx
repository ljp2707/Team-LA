import { Link } from "react-router-dom";
import type { ProjectCard as Card } from "../api/types";
import { formatDate } from "../lib/dates";
import { ProgressBar } from "./ui/Bits";
import { Tag } from "./ui/Tag";

/** One launch on the dashboard or the Projects page. The whole card is a link. */
export function ProjectCard({ project }: { project: Card }) {
  const health =
    project.overdue > 0 ? (
      <Tag tone="late">{project.overdue} overdue</Tag>
    ) : project.complete >= 100 ? (
      <Tag tone="done">Done</Tag>
    ) : (
      <Tag tone="done">On track</Tag>
    );
  const subtitle = [project.program_type, project.site_type].filter(Boolean).join(" · ");
  return (
    <Link to={`/projects/${project.id}`} className="project-card">
      <div className="project-card-head">
        <h2>{project.site || project.name}</h2>
        {health}
      </div>
      <p className="muted small">{subtitle}</p>
      <div className="project-card-day">
        <span className="eyebrow">Day 1</span>
        <span className="project-card-date">
          {project.day_one ? formatDate(project.day_one, { weekday: true }) : "Not set"}
        </span>
      </div>
      <div className="project-card-progress">
        <div className="split small">
          <span>Complete</span>
          <strong>{project.complete}%</strong>
        </div>
        <ProgressBar value={project.complete} label={`${project.site || project.name} complete`} />
      </div>
      <dl className="project-card-facts">
        <div>
          <dt>Next milestone</dt>
          <dd>{project.next_milestone ? `${project.next_milestone.name}, ${project.next_milestone.due_text}` : "None left"}</dd>
        </div>
        <div>
          <dt>Lead instructor</dt>
          <dd>{project.lead_instructor || "Not set"}</dd>
        </div>
        {project.needs_owner > 0 && (
          <div>
            <dt>Needs an owner</dt>
            <dd>
              {project.needs_owner} {project.needs_owner === 1 ? "task" : "tasks"}
            </dd>
          </div>
        )}
      </dl>
    </Link>
  );
}
