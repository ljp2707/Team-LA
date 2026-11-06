"""Templates, /templates (admin): steps, drafts, versions, copies and insights."""

from fastapi import APIRouter, Depends, status

from app.auth.deps import require_admin
from app.models.template import (
    DraftIn,
    DuplicateIn,
    FromProjectIn,
    NewTemplateIn,
    PublishIn,
    TemplateStatusIn,
)
from app.models.user import CurrentUser
from app.services import logic
from app.services import templates as svc
from app.services.records import live_steps, load_versions, safe
from app.services.views import World

router = APIRouter(
    prefix="/api/templates", tags=["templates"], dependencies=[Depends(require_admin)]
)


def _step_dict(step: svc.DraftStep, names: dict[str, str], roles: dict[str, str], note: str | None = None) -> dict:
    return {
        **step.as_dict(),
        "when": logic.short_timing(step.anchor, step.days_before),
        "timing": logic.timing_label(step.anchor, step.days_before),
        "role": roles.get(step.role_id or ""),
        "needs_first": [names[d] for d in (step.depends_on or []) if d in names],
        "note": note,
    }


@router.get("")
def list_templates():
    world = World()
    versions = safe(load_versions)
    out = []
    for t in sorted(world.templates.values(), key=lambda t: t.name):
        steps = live_steps(t.id, world.steps)
        out.append(
            {
                "id": t.id,
                "name": t.name,
                "status": t.status or "Active",
                "active": t.active,
                "live_version": t.version,
                "description": t.description,
                "task_count": len(steps),
                "lead_text": logic.lead_time_text([s.days_before for s in steps if s.anchor != "End"]),
                "has_draft": svc.get_draft(t.id, versions) is not None,
            }
        )
    return {"templates": out}


@router.post("", status_code=status.HTTP_201_CREATED)
def new_template(body: NewTemplateIn, user: CurrentUser = Depends(require_admin)):
    """New templates start from a copy of an existing one."""
    return {"id": svc.duplicate(body.copy_from, user.id, body.name)}


@router.get("/{template_id}")
def get_template(template_id: str):
    world = World()
    template = svc.get_template(template_id)
    roles = {r.id: r.name for r in world.roles.values()}
    live = svc.steps_as_draft(live_steps(template_id, world.steps))
    live_names = {s.key: s.name for s in live}
    draft_rec = svc.get_draft(template_id)
    draft = None
    if draft_rec:
        steps = svc.parse_steps_json(draft_rec.steps_json)
        names = {s.key: s.name for s in steps}
        notes = svc.draft_notes(live, steps)
        draft = {
            "id": draft_rec.id,
            "version": draft_rec.version,
            "steps": [_step_dict(s, names, roles, notes.get(s.key)) for s in steps],
            "removed": svc.removed_in_draft(live, steps),
        }
    on_live = [
        {"id": p.id, "site": world.site_name(p), "name": p.name}
        for p in world.projects.values()
        if p.template_id == template_id
        and not p.closed
        and (p.template_version or 1) == template.version
    ]
    return {
        "id": template.id,
        "name": template.name,
        "status": template.status or "Active",
        "active": template.active,
        "description": template.description,
        "live_version": template.version,
        "steps": [_step_dict(s, live_names, roles) for s in live],
        "draft": draft,
        "projects_on_live": on_live,
        "roles": sorted(
            ({"id": r.id, "name": r.name} for r in world.roles.values() if r.active),
            key=lambda r: r["name"],
        ),
    }


@router.put("/{template_id}/draft")
def save_draft(template_id: str, body: DraftIn, user: CurrentUser = Depends(require_admin)):
    steps = [svc.DraftStep.from_dict(s.model_dump()) for s in body.steps]
    svc.save_draft(template_id, steps, user.id)
    return get_template(template_id)


@router.delete("/{template_id}/draft")
def discard_draft(template_id: str):
    svc.discard_draft(template_id)
    return get_template(template_id)


@router.post("/{template_id}/publish")
def publish(template_id: str, body: PublishIn, user: CurrentUser = Depends(require_admin)):
    version = svc.publish(template_id, body.change_note.strip(), user.id)
    return {"version": version, **get_template(template_id)}


@router.get("/{template_id}/versions")
def versions(template_id: str):
    world = World()
    roles = {r.id: r.name for r in world.roles.values()}
    out = []
    for v in svc.version_list(template_id, world.today):
        steps = [svc.DraftStep.from_dict(s) for s in v["steps"]]
        names = {s.key: s.name for s in steps}
        out.append({**v, "steps": [_step_dict(s, names, roles) for s in steps]})
    return {"versions": out}


@router.get("/{template_id}/insights")
def insights(template_id: str):
    svc.get_template(template_id)
    return svc.insights(template_id)


@router.patch("/{template_id}")
def set_status(template_id: str, body: TemplateStatusIn, user: CurrentUser = Depends(require_admin)):
    svc.set_status(template_id, body.status == "Active", user.id)
    return get_template(template_id)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(template_id: str, user: CurrentUser = Depends(require_admin)):
    svc.delete_template(template_id, user.id)


@router.post("/{template_id}/duplicate", status_code=status.HTTP_201_CREATED)
def duplicate(template_id: str, body: DuplicateIn, user: CurrentUser = Depends(require_admin)):
    return {"id": svc.duplicate(template_id, user.id, body.name)}


@router.post("/from-project", status_code=status.HTTP_201_CREATED)
def from_project(body: FromProjectIn, user: CurrentUser = Depends(require_admin)):
    return {"id": svc.from_project(body.project_id, body.name, user.id)}
