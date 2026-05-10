"""
Contact organizations router — all /contact-organizations endpoints.
Serves the frontend ContactOrganizationsPage.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timezone
import logging
import csv
import io

from database import get_db
from auth import get_current_active_user
import models
from contacts_schemas import (
    OrgListItem, OrgListResponse, OrgDetailResponse, OrgPersonItem,
    OrgUpdateRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_model=OrgListResponse)
async def list_organizations(
    search: Optional[str] = Query(None),
    cursor: Optional[int] = Query(None),
    limit: int = Query(50, le=200),
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """List contact organizations with aggregated stats."""
    query = db.query(models.ContactOrganization).filter(
        models.ContactOrganization.user_id == current_user.id,
        models.ContactOrganization.deleted_at.is_(None),
    )

    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            (models.ContactOrganization.name.ilike(search_filter))
            | (models.ContactOrganization.domain.ilike(search_filter))
        )

    query = query.order_by(models.ContactOrganization.name)
    if cursor:
        query = query.filter(models.ContactOrganization.id > cursor)

    results = query.limit(limit + 1).all()
    has_more = len(results) > limit
    orgs = results[:limit]
    next_cursor = orgs[-1].id if has_more and orgs else None

    items = []
    for org in orgs:
        contact_count = db.query(func.count(models.Contact.id)).filter(
            models.Contact.contact_organization_id == org.id,
            models.Contact.deleted_at.is_(None),
        ).scalar() or 0

        open_deals = db.query(func.count(models.ContactDeal.id)).join(
            models.Contact, models.ContactDeal.contact_id == models.Contact.id
        ).filter(
            models.Contact.contact_organization_id == org.id,
            models.Contact.deleted_at.is_(None),
            models.ContactDeal.status == "open",
            models.ContactDeal.deleted_at.is_(None),
        ).scalar() or 0

        # Total value includes open + won deals (excludes lost)
        total_value = float(db.query(func.coalesce(func.sum(models.ContactDeal.value), 0)).join(
            models.Contact, models.ContactDeal.contact_id == models.Contact.id
        ).filter(
            models.Contact.contact_organization_id == org.id,
            models.Contact.deleted_at.is_(None),
            models.ContactDeal.status.in_(["open", "won"]),
            models.ContactDeal.deleted_at.is_(None),
        ).scalar() or 0)

        # has_dnc = db.query(models.Contact.id).filter(
        #     models.Contact.contact_organization_id == org.id,
        #     models.Contact.deleted_at.is_(None),
        #     models.Contact.status == "do_not_contact",
        # ).first() is not None
        has_dnc = org.dnc

        items.append(OrgListItem(
            id=org.id,
            name=org.name,
            domain=org.domain,
            contacts=contact_count,
            openDeals=open_deals,
            totalValue=total_value,
            dnc=has_dnc,
            dncProp=org.do_not_contact_propagation if org.do_not_contact_propagation is not None else True,
        ))

    return OrgListResponse(items=items, nextCursor=next_cursor, hasMore=has_more)


# IMPORTANT: /export MUST come before /{org_id} to avoid route capture
@router.get("/export")
async def export_organizations(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Export all contact organizations as CSV."""
    orgs = db.query(models.ContactOrganization).filter(
        models.ContactOrganization.user_id == current_user.id,
        models.ContactOrganization.deleted_at.is_(None),
    ).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Domain", "Contacts", "DNC", "DNC Propagation"])

    for org in orgs:
        contact_count = db.query(func.count(models.Contact.id)).filter(
            models.Contact.contact_organization_id == org.id,
            models.Contact.deleted_at.is_(None),
        ).scalar() or 0

        # has_dnc = db.query(models.Contact.id).filter(
        #     models.Contact.contact_organization_id == org.id,
        #     models.Contact.status == "do_not_contact",
        #     models.Contact.deleted_at.is_(None),
        # ).first() is not None
        has_dnc = org.dnc

        writer.writerow([
            org.name,
            org.domain or "",
            contact_count,
            "Yes" if has_dnc else "No",
            "Yes" if org.do_not_contact_propagation else "No",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=contact-organizations.csv"},
    )


@router.get("/{org_id}", response_model=OrgDetailResponse)
async def get_organization_detail(
    org_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get organization detail with persons list."""
    org = db.query(models.ContactOrganization).filter(
        models.ContactOrganization.id == org_id,
        models.ContactOrganization.user_id == current_user.id,
        models.ContactOrganization.deleted_at.is_(None),
    ).first()

    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    contacts = db.query(models.Contact).filter(
        models.Contact.contact_organization_id == org.id,
        models.Contact.deleted_at.is_(None),
    ).all()

    open_deal_count = db.query(func.count(models.ContactDeal.id)).join(
        models.Contact, models.ContactDeal.contact_id == models.Contact.id
    ).filter(
        models.Contact.contact_organization_id == org.id,
        models.Contact.deleted_at.is_(None),
        models.ContactDeal.status == "open",
        models.ContactDeal.deleted_at.is_(None),
    ).scalar() or 0

    total_deal_value = float(db.query(func.coalesce(func.sum(models.ContactDeal.value), 0)).join(
        models.Contact, models.ContactDeal.contact_id == models.Contact.id
    ).filter(
        models.Contact.contact_organization_id == org.id,
        models.Contact.deleted_at.is_(None),
        models.ContactDeal.status.in_(["open", "won"]),
        models.ContactDeal.deleted_at.is_(None),
    ).scalar() or 0)

    # has_dnc = any(c.status == "do_not_contact" for c in contacts)
    has_dnc = org.dnc

    persons = [
        OrgPersonItem(id=c.id, name=c.name, email=c.email, status=c.status or "active")
        for c in contacts
    ]

    return OrgDetailResponse(
        id=org.id,
        name=org.name,
        domain=org.domain,
        contacts=len(contacts),
        openDeals=open_deal_count,
        totalValue=total_deal_value,
        dnc=has_dnc,
        dncProp=org.do_not_contact_propagation if org.do_not_contact_propagation is not None else True,
        persons=persons,
    )


@router.put("/{org_id}", response_model=OrgDetailResponse)
async def update_organization(
    org_id: int,
    data: OrgUpdateRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Update organization name or DNC propagation setting."""
    org = db.query(models.ContactOrganization).filter(
        models.ContactOrganization.id == org_id,
        models.ContactOrganization.user_id == current_user.id,
        models.ContactOrganization.deleted_at.is_(None),
    ).first()

    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    if data.name is not None:
        org.name = data.name
    if data.do_not_contact_propagation is not None:
        org.do_not_contact_propagation = data.do_not_contact_propagation
     
    # Here is new dne code   
    if hasattr(data, "dnc") and data.dnc is not None:
        # TURN ON DNC
        if data.dnc is True and not getattr(org, "dnc", False):
            org.dnc = True
            org.dnc_set_at = datetime.now(timezone.utc)
            org.dnc_set_by = current_user.id
            org.dnc_propagation_status = "pending"
    
            db.commit()
    
            # trigger cascade
            from contacts_orgs_service import trigger_org_dnc_cascade
            trigger_org_dnc_cascade(org.id)

        # TURN OFF (NO REVERSE)
        elif data.dnc is False:
            org.dnc = False

    db.commit()
    return await get_organization_detail(org_id, current_user, db)


@router.post("/{org_id}/merge")
async def merge_organization(
    org_id: int,
    data: dict,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Merge another org into this one. Moves all contacts from merge org to keep org."""
    merge_id = data.get("merge_id")
    if not merge_id:
        raise HTTPException(status_code=400, detail="merge_id required")

    keep_org = db.query(models.ContactOrganization).filter(
        models.ContactOrganization.id == org_id,
        models.ContactOrganization.user_id == current_user.id,
        models.ContactOrganization.deleted_at.is_(None),
    ).first()
    merge_org = db.query(models.ContactOrganization).filter(
        models.ContactOrganization.id == merge_id,
        models.ContactOrganization.user_id == current_user.id,
        models.ContactOrganization.deleted_at.is_(None),
    ).first()

    if not keep_org or not merge_org:
        raise HTTPException(status_code=404, detail="Both organizations must exist")

    db.query(models.Contact).filter(
        models.Contact.contact_organization_id == merge_id,
        models.Contact.user_id == current_user.id,
        models.Contact.deleted_at.is_(None),
    ).update({"contact_organization_id": org_id})

    db.query(models.ContactDeal).filter(
        models.ContactDeal.contact_organization_id == merge_id,
        models.ContactDeal.user_id == current_user.id,
    ).update({"contact_organization_id": org_id})

    merge_org.deleted_at = datetime.now(timezone.utc)
    db.commit()

    return {"success": True, "keptId": org_id}
