"""Sites and instructors, for the New Project form. Admin only."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.airtable import client
from app.airtable.schema import SITE_TYPES, Site
from app.auth.deps import require_admin
from app.models.people import SiteIn
from app.services.records import SiteRec, load_instructors, load_regions, load_sites

router = APIRouter(prefix="/api", tags=["sites"], dependencies=[Depends(require_admin)])


def site_dict(site: SiteRec, regions: dict[str, str]) -> dict:
    return {
        "id": site.id,
        "name": site.name,
        "site_type": site.site_type,
        "location": site.location,
        "region": regions.get(site.region_id or ""),
        "region_id": site.region_id,
        "partner_name": site.partner_name,
        "partner_email": site.partner_email,
        "partner_phone": site.partner_phone,
        "shipping_address": site.shipping_address,
        "last_head_coach": site.last_head_coach,
        "drive_folder": site.drive_folder,
    }


def _regions() -> dict[str, str]:
    return {r.id: r.name for r in load_regions()}


@router.get("/sites")
def list_sites():
    regions = _regions()
    return {
        "sites": sorted((site_dict(s, regions) for s in load_sites()), key=lambda s: s["name"]),
        "site_types": SITE_TYPES,
        "regions": [{"id": k, "name": v} for k, v in sorted(regions.items(), key=lambda r: r[1])],
    }


@router.post("/sites", status_code=status.HTTP_201_CREATED)
def create_site(body: SiteIn):
    name = body.name.strip()
    if any(s.name.strip().lower() == name.lower() for s in load_sites()):
        raise HTTPException(status.HTTP_409_CONFLICT, "A site with that name already exists")
    fields = {
        Site.PROGRAM_NAME: name,
        Site.SITE_TYPE: body.site_type,
        Site.PROGRAM_LOCATION: body.location.strip(),
        Site.REGION: [body.region_id] if body.region_id else [],
        Site.PARTNER_CONTACT_NAME: body.partner_name.strip(),
        Site.PARTNER_CONTACT_EMAIL: body.partner_email.strip() or None,
        Site.PARTNER_CONTACT_PHONE: body.partner_phone.strip() or None,
        Site.SHIPPING_ADDRESS: body.shipping_address.strip(),
    }
    created = client.create_record(
        Site.TABLE, {k: v for k, v in fields.items() if v not in (None, "", [])}, typecast=True
    )
    site = next(s for s in load_sites() if s.id == created["id"])
    return site_dict(site, _regions())


@router.get("/sites/{site_id}")
def get_site(site_id: str):
    site = next((s for s in load_sites() if s.id == site_id), None)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")
    return site_dict(site, _regions())


@router.get("/instructors")
def list_instructors(site: str | None = None):
    rows = load_instructors()
    if site:
        rows = [i for i in rows if site in i.site_ids]
    return {"instructors": sorted(({"id": i.id, "name": i.name} for i in rows), key=lambda i: i["name"])}
