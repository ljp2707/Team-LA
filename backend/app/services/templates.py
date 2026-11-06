"""Templates: drafts, publishing versions, copies, and "From past launches" insights.

How versions work:
- The live steps of a template are the Steps rows for it with no Retired In Version
  (and the older Retired checkbox not ticked).
- The first edit makes a Draft row in Template Versions (live version + 1) holding
  the whole list of steps as JSON. Later edits replace that JSON.
- Publishing applies the draft to Steps: changed steps are updated, new ones are
  created with Added In Version = N, and removed ones get Retired In Version = N
  instead of being deleted. Running projects never change, because their tasks
  hold their own copies of names, dates and roles.
"""

from __future__ import annotations

import json
import statistics
import uuid
from dataclasses import dataclass
from datetime import date

from fastapi import HTTPException, status

from app.airtable import client
from app.airtable.schema import Steps, TemplateList, TemplateVersions
from app.services import clock, history
from app.services.logic import fmt_date, short_timing
from app.services.records import (
    ProjectRec,
    StepRec,
    TaskRec,
    TemplateRec,
    VersionRec,
    live_steps,
    load_projects,
    load_roles,
    load_steps,
    load_tasks,
    load_templates,
    load_versions,
    safe,
)
from app.services.timeline import find_cycle

# "From past launches" thresholds: a pattern counts if it happened in at least
# MIN_LAUNCHES closed launches, or in at least MIN_SHARE of them.
MIN_LAUNCHES = 3
MIN_SHARE = 0.4
MIN_LAUNCHES_ADDED = 3

DRAFT = "Draft"
LIVE = "Live"
RETIRED = "Retired"


@dataclass
class DraftStep:
    key: str
    name: str
    description: str = ""
    anchor: str = "Start"
    days_before: int = 0
    role_id: str | None = None
    depends_on: list[str] | None = None

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "anchor": self.anchor,
            "days_before": self.days_before,
            "role_id": self.role_id,
            "depends_on": list(self.depends_on or []),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DraftStep":
        return cls(
            key=str(data.get("key") or f"new-{uuid.uuid4().hex[:8]}"),
            name=str(data.get("name", "")).strip(),
            description=str(data.get("description", "") or ""),
            anchor="End" if data.get("anchor") == "End" else "Start",
            days_before=int(data.get("days_before") or 0),
            role_id=data.get("role_id") or None,
            depends_on=[str(d) for d in (data.get("depends_on") or [])],
        )


def get_template(template_id: str) -> TemplateRec:
    for t in load_templates():
        if t.id == template_id:
            return t
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")


def steps_as_draft(steps: list[StepRec]) -> list[DraftStep]:
    return [
        DraftStep(
            key=s.id,
            name=s.name,
            description=s.description,
            anchor=s.anchor,
            days_before=s.days_before,
            role_id=s.role_id,
            depends_on=list(s.depends_on),
        )
        for s in steps
    ]


def get_draft(template_id: str, versions: list[VersionRec] | None = None) -> VersionRec | None:
    versions = safe(load_versions) if versions is None else versions
    drafts = [v for v in versions if v.template_id == template_id and v.status == DRAFT]
    return max(drafts, key=lambda v: v.version) if drafts else None


def parse_steps_json(text: str) -> list[DraftStep]:
    try:
        data = json.loads(text or "[]")
    except ValueError:
        return []
    return [DraftStep.from_dict(d) for d in data if isinstance(d, dict)]


def validate(steps: list[DraftStep]) -> None:
    """Refuse empty names, unknown dependencies and cycles."""
    keys = {s.key for s in steps}
    if len(keys) != len(steps):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Two tasks share an ID")
    for s in steps:
        if not s.name:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Every task needs a name")
        if s.key in (s.depends_on or []):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, f"{s.name} cannot need itself first"
            )
        s.depends_on = [d for d in (s.depends_on or []) if d in keys]
    if find_cycle({s.key: list(s.depends_on or []) for s in steps}):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Those needs first choices go in a circle. Remove one so the order has a start.",
        )


def save_draft(template_id: str, steps: list[DraftStep], actor_id: str) -> VersionRec:
    """Create the draft on the first edit, or replace its steps."""
    template = get_template(template_id)
    validate(steps)
    payload = json.dumps([s.as_dict() for s in steps])
    draft = get_draft(template_id)
    if draft:
        client.update_record(
            TemplateVersions.TABLE, draft.id, {TemplateVersions.STEPS_JSON: payload}
        )
    else:
        version = template.version + 1
        client.create_record(
            TemplateVersions.TABLE,
            {
                TemplateVersions.NAME: f"{template.name} v{version}",
                TemplateVersions.TEMPLATE: [template_id],
                TemplateVersions.VERSION: version,
                TemplateVersions.STATUS: DRAFT,
                TemplateVersions.STEPS_JSON: payload,
            },
            typecast=True,
        )
    result = get_draft(template_id)
    assert result is not None
    return result


def discard_draft(template_id: str) -> None:
    draft = get_draft(template_id)
    if draft is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no draft to discard")
    # The draft row is the app's own scratch copy, so it is safe to remove.
    client.delete_records(TemplateVersions.TABLE, [draft.id])


def draft_notes(live: list[DraftStep], draft: list[DraftStep]) -> dict[str, str]:
    """Short notes on what a draft changed, by step key."""
    live_by_key = {s.key: s for s in live}
    names = {s.key: s.name for s in draft} | {s.key: s.name for s in live}
    notes = {}
    for s in draft:
        old = live_by_key.get(s.key)
        parts = []
        if old is None:
            parts.append("New in this draft")
        else:
            if (old.anchor, old.days_before) != (s.anchor, s.days_before):
                parts.append(f"Moved from {short_timing(old.anchor, old.days_before).lower()} in this draft")
            if old.name != s.name:
                parts.append(f"Renamed from {old.name}")
            if old.role_id != s.role_id:
                parts.append("Role changed")
            added = [d for d in (s.depends_on or []) if d not in (old.depends_on or [])]
            if added:
                parts.append("needs " + " and ".join(names.get(d, "a task") for d in added) + " first")
        if parts:
            notes[s.key] = " · ".join(parts)
    return notes


def removed_in_draft(live: list[DraftStep], draft: list[DraftStep]) -> list[str]:
    keys = {s.key for s in draft}
    return [s.name for s in live if s.key not in keys]


def _step_fields(template_id: str, s: DraftStep, order: int) -> dict:
    fields = {
        Steps.SHORT_DESCRIPTION: s.name,
        Steps.LONG_DESCRIPTION: s.description,
        Steps.DAYS_BEFORE_ANCHOR: s.days_before,
        Steps.ANCHOR: s.anchor,
        Steps.TEMPLATE: [template_id],
        Steps.ROLES: [s.role_id] if s.role_id else [],
        Steps.SORT_ORDER: order,
    }
    return fields


def publish(template_id: str, change_note: str, actor_id: str) -> int:
    """Apply the draft to Steps and make it the live version. Returns N."""
    template = get_template(template_id)
    draft = get_draft(template_id)
    if draft is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "There is no draft to publish")
    steps = parse_steps_json(draft.steps_json)
    validate(steps)
    version = draft.version
    live = live_steps(template_id)
    live_by_id = {s.id: s for s in live}

    updates, new_rows, new_keys = [], [], []
    for order, s in enumerate(steps):
        if s.key in live_by_id:
            old = live_by_id[s.key]
            if (
                old.name != s.name
                or old.description != s.description
                or old.days_before != s.days_before
                or old.anchor != s.anchor
                or old.role_id != s.role_id
                or old.sort_order != float(order)
            ):
                fields = _step_fields(template_id, s, order)
                updates.append({"id": s.key, "fields": fields})
        else:
            fields = _step_fields(template_id, s, order)
            fields[Steps.ADDED_IN_VERSION] = version
            new_rows.append(fields)
            new_keys.append(s.key)
    client.update_records(Steps.TABLE, updates, typecast=True)
    created = client.create_records(Steps.TABLE, new_rows, typecast=True)
    key_to_id = {s.key: s.key for s in steps if s.key in live_by_id}
    key_to_id.update({k: rec["id"] for k, rec in zip(new_keys, created)})

    keys = {s.key for s in steps}
    retired = [s for s in live if s.id not in keys]
    client.update_records(
        Steps.TABLE,
        [{"id": s.id, "fields": {Steps.RETIRED_IN_VERSION: version}} for s in retired],
    )

    dep_updates = []
    for s in steps:
        new_deps = [key_to_id[d] for d in (s.depends_on or []) if d in key_to_id]
        old = live_by_id.get(s.key)
        if old is None or sorted(old.depends_on) != sorted(new_deps):
            dep_updates.append({"id": key_to_id[s.key], "fields": {Steps.DEPENDS_ON: new_deps}})
    client.update_records(Steps.TABLE, dep_updates)

    final = [
        DraftStep(
            key=key_to_id[s.key],
            name=s.name,
            description=s.description,
            anchor=s.anchor,
            days_before=s.days_before,
            role_id=s.role_id,
            depends_on=[key_to_id[d] for d in (s.depends_on or []) if d in key_to_id],
        ).as_dict()
        for s in steps
    ]
    versions = safe(load_versions)
    old_live = [v for v in versions if v.template_id == template_id and v.status == LIVE]
    if old_live:
        client.update_records(
            TemplateVersions.TABLE,
            [{"id": v.id, "fields": {TemplateVersions.STATUS: RETIRED}} for v in old_live],
        )
    else:
        # Templates from before versions existed: keep a copy of what was live.
        client.create_record(
            TemplateVersions.TABLE,
            {
                TemplateVersions.NAME: f"{template.name} v{template.version}",
                TemplateVersions.TEMPLATE: [template_id],
                TemplateVersions.VERSION: template.version,
                TemplateVersions.STATUS: RETIRED,
                TemplateVersions.STEPS_JSON: json.dumps([s.as_dict() for s in steps_as_draft(live)]),
                TemplateVersions.CHANGE_NOTE: "The steps before versions were tracked",
            },
            typecast=True,
        )
    client.update_record(
        TemplateVersions.TABLE,
        draft.id,
        {
            TemplateVersions.STATUS: LIVE,
            TemplateVersions.STEPS_JSON: json.dumps(final),
            TemplateVersions.CHANGE_NOTE: change_note,
            TemplateVersions.PUBLISHED_AT: clock.utc_now_iso(),
            TemplateVersions.PUBLISHED_BY: [actor_id],
        },
        typecast=True,
    )
    client.update_record(TemplateList.TABLE, template_id, {TemplateList.LIVE_VERSION: version})
    history.log_event(
        None,
        None,
        actor_id,
        "System",
        f"published {template.name} v{version}"
        + (f": {change_note}" if change_note else "")
        + f" ({len(updates)} changed, {len(new_rows)} added, {len(retired)} retired)",
    )
    return version


def create_template(name: str, steps: list[DraftStep], actor_id: str, note: str) -> str:
    """A new template at v1 with these steps. Returns its ID."""
    name = name.strip()
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Give the template a name")
    if any(t.name.strip().lower() == name.lower() for t in load_templates()):
        raise HTTPException(status.HTTP_409_CONFLICT, "A template with that name already exists")
    validate(steps)
    template = client.create_record(
        TemplateList.TABLE,
        {TemplateList.NAME: name, TemplateList.STATUS: "Active", TemplateList.LIVE_VERSION: 1},
        typecast=True,
    )
    tid = template["id"]
    rows = []
    for order, s in enumerate(steps):
        fields = _step_fields(tid, s, order)
        fields[Steps.ADDED_IN_VERSION] = 1
        rows.append(fields)
    created = client.create_records(Steps.TABLE, rows, typecast=True)
    key_to_id = {s.key: rec["id"] for s, rec in zip(steps, created)}
    client.update_records(
        Steps.TABLE,
        [
            {"id": key_to_id[s.key], "fields": {Steps.DEPENDS_ON: [key_to_id[d] for d in s.depends_on or [] if d in key_to_id]}}
            for s in steps
            if s.depends_on
        ],
    )
    snapshot = [
        DraftStep(
            key=key_to_id[s.key],
            name=s.name,
            description=s.description,
            anchor=s.anchor,
            days_before=s.days_before,
            role_id=s.role_id,
            depends_on=[key_to_id[d] for d in s.depends_on or [] if d in key_to_id],
        ).as_dict()
        for s in steps
    ]
    client.create_record(
        TemplateVersions.TABLE,
        {
            TemplateVersions.NAME: f"{name} v1",
            TemplateVersions.TEMPLATE: [tid],
            TemplateVersions.VERSION: 1,
            TemplateVersions.STATUS: LIVE,
            TemplateVersions.STEPS_JSON: json.dumps(snapshot),
            TemplateVersions.CHANGE_NOTE: note,
            TemplateVersions.PUBLISHED_AT: clock.utc_now_iso(),
            TemplateVersions.PUBLISHED_BY: [actor_id],
        },
        typecast=True,
    )
    history.log_event(None, None, actor_id, "System", f"created the template {name}: {note}")
    return tid


def duplicate(template_id: str, actor_id: str, name: str | None = None) -> str:
    source = get_template(template_id)
    steps = steps_as_draft(live_steps(template_id))
    return create_template(
        name or f"{source.name} copy", steps, actor_id, f"Copied from {source.name} v{source.version}"
    )


def steps_from_project(project: ProjectRec, tasks: list[TaskRec]) -> list[DraftStep]:
    """Each task's offset from Day 1, its role and its dependencies, one-offs included."""
    mine = [t for t in tasks if t.session_id == project.id]
    ids = {t.id for t in mine}
    mine.sort(key=lambda t: (t.due or date.max, t.sort_order or 0))
    out = []
    for t in mine:
        if t.anchor == "End" and t.days_before is not None:
            anchor, days = "End", t.days_before
        elif project.start and t.due:
            anchor, days = "Start", (project.start - t.due).days
        else:
            anchor, days = "Start", t.days_before or 0
        out.append(
            DraftStep(
                key=t.id,
                name=t.name,
                description=t.description,
                anchor=anchor,
                days_before=days,
                role_id=t.role_id,
                depends_on=[d for d in t.depends_on if d in ids],
            )
        )
    return out


def from_project(project_id: str, name: str, actor_id: str) -> str:
    project = next((p for p in load_projects() if p.id == project_id), None)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    steps = steps_from_project(project, load_tasks())
    if not steps:
        raise HTTPException(status.HTTP_409_CONFLICT, "That project has no tasks to copy")
    return create_template(name, steps, actor_id, f"Saved from the project {project.name}")


def delete_template(template_id: str, actor_id: str) -> None:
    """Delete a template with its steps and versions.

    Only allowed while no launch, running or archived, was made from it: their tasks
    still point at its steps for descriptions and insights. Those templates can be
    made inactive instead.
    """
    template = get_template(template_id)
    steps = [s for s in load_steps() if s.template_id == template_id]
    step_ids = {s.id for s in steps}
    in_use = any(p.template_id == template_id for p in load_projects()) or any(
        t.step_id in step_ids for t in load_tasks(steps)
    )
    if in_use:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Launches were made from this template, so it cannot be deleted. Make it inactive instead.",
        )
    versions = [v.id for v in safe(load_versions) if v.template_id == template_id]
    client.delete_records(Steps.TABLE, sorted(step_ids))
    client.delete_records(TemplateVersions.TABLE, versions)
    client.delete_records(TemplateList.TABLE, [template_id])
    history.log_event(None, None, actor_id, "System", f"deleted the template {template.name}")


def set_status(template_id: str, active: bool, actor_id: str) -> None:
    template = get_template(template_id)
    client.update_record(
        TemplateList.TABLE,
        template_id,
        {TemplateList.STATUS: "Active" if active else "Inactive"},
        typecast=True,
    )
    history.log_event(
        None,
        None,
        actor_id,
        "System",
        f"set the template {template.name} to {'Active' if active else 'Inactive'}",
    )


# --- From past launches --------------------------------------------------------


def insights(template_id: str, projects=None, tasks=None, steps=None) -> dict:
    """What happened to this template's tasks across its closed launches."""
    projects = load_projects() if projects is None else projects
    tasks = load_tasks() if tasks is None else tasks
    steps = load_steps() if steps is None else steps
    closed = [p for p in projects if p.template_id == template_id and p.closed]
    total = len(closed)
    step_names = {s.id: s.name for s in steps}
    late: dict[str, list[int]] = {}
    skipped: dict[str, int] = {}
    added: dict[str, list[int]] = {}
    added_names: dict[str, str] = {}
    labels: dict[str, str] = {}
    for project in closed:
        seen_late, seen_skip, seen_added = set(), set(), set()
        for t in (t for t in tasks if t.session_id == project.id):
            if t.one_off or not t.step_id:
                key = "name:" + t.name.strip().lower()
                if key not in seen_added and project.start and t.due:
                    seen_added.add(key)
                    added.setdefault(key, []).append((project.start - t.due).days)
                    added_names.setdefault(key, t.name.strip())
                continue
            key = t.step_id
            labels[key] = step_names.get(key, t.name)
            if t.status == "Done" and t.completed and t.due and t.completed > t.due and key not in seen_late:
                seen_late.add(key)
                late.setdefault(key, []).append((t.completed - t.due).days)
            if t.status == "Skipped" and key not in seen_skip:
                seen_skip.add(key)
                skipped[key] = skipped.get(key, 0) + 1

    def counts(n: int) -> bool:
        return total > 0 and (n >= MIN_LAUNCHES or n / total >= MIN_SHARE)

    often_late = [
        {
            "step_id": key,
            "name": labels[key],
            "count": len(days),
            "text": f"Late in {len(days)} of {total}, by {round(sum(days) / len(days))} days on average",
        }
        for key, days in late.items()
        if counts(len(days))
    ]
    often_skipped = [
        {"step_id": key, "name": labels[key], "count": n, "text": f"Skipped in {n} of {total}"}
        for key, n in skipped.items()
        if counts(n)
    ]
    live_names = {s.name.strip().lower() for s in steps if s.template_id == template_id and s.live}
    often_added = [
        {
            "name": added_names[key],
            "count": len(offsets),
            "days_before": int(statistics.median(offsets)),
            "text": f"Added by hand in {len(offsets)} of {total}",
            "in_template": added_names[key].lower() in live_names,
        }
        for key, offsets in added.items()
        if len(offsets) >= MIN_LAUNCHES_ADDED
    ]
    for group in (often_late, often_skipped, often_added):
        group.sort(key=lambda g: -g["count"])
    return {
        "launches": total,
        "often_late": often_late,
        "often_skipped": often_skipped,
        "often_added": often_added,
    }


def version_list(template_id: str, today: date) -> list[dict]:
    template = get_template(template_id)
    from app.services.records import load_users

    names = {u.id: u.name for u in load_users()}
    versions = [v for v in safe(load_versions) if v.template_id == template_id]
    out = []
    for v in sorted(versions, key=lambda v: -v.version):
        steps = parse_steps_json(v.steps_json)
        published = clock.parse_date(v.published_at)
        out.append(
            {
                "id": v.id,
                "version": v.version,
                "status": v.status,
                "published_at": published.isoformat() if published else None,
                "published_text": fmt_date(published, today) if published else None,
                "published_by": names.get(v.published_by or "", None),
                "change_note": v.change_note,
                "task_count": len(steps),
                "steps": [s.as_dict() for s in steps],
            }
        )
    if not any(v["version"] == template.version for v in out):
        live = steps_as_draft(live_steps(template_id))
        out.append(
            {
                "id": None,
                "version": template.version,
                "status": LIVE,
                "published_at": None,
                "published_text": None,
                "published_by": None,
                "change_note": "Made before versions were tracked",
                "task_count": len(live),
                "steps": [s.as_dict() for s in live],
            }
        )
        out.sort(key=lambda v: -v["version"])
    return out


def role_names() -> dict[str, str]:
    return {r.id: r.name for r in load_roles()}
