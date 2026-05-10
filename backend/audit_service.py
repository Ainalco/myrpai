"""
Audit logging service — records key events for compliance and admin visibility.

Usage:
    from audit_service import log_event
    log_event(db, org_id=1, user_id=2, action="member.invited", target_type="invitation", target_id=5, details={"email": "new@co.com", "role": "member"})
"""

import logging
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc
import models

logger = logging.getLogger(__name__)

# Standard action constants
ACTIONS = {
    # Team
    "member.invited": "Team member invited",
    "member.accepted": "Invitation accepted",
    "member.removed": "Team member removed",
    "member.role_changed": "Member role changed",
    "member.ownership_transferred": "Ownership transferred",
    # Auth
    "auth.login": "User logged in",
    "auth.register": "User registered",
    # Billing
    "billing.plan_changed": "Plan changed",
    "billing.acorns_purchased": "Acorns purchased",
    "billing.subscription_cancelled": "Subscription cancelled",
    # Acorn allocation
    "acorns.allocation_mode_changed": "Acorn allocation mode changed",
    "acorns.user_allocation_set": "User acorn allocation set",
    # Integrations
    "integration.connected": "Integration connected",
    "integration.disconnected": "Integration disconnected",
    # Workflows
    "workflow.created": "Workflow created",
    "workflow.deleted": "Workflow deleted",
}


def log_event(
    db: Session,
    org_id: int,
    action: str,
    user_id: Optional[int] = None,
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
    details: Optional[dict] = None,
    ip_address: Optional[str] = None,
) -> models.AuditLog:
    """Record an audit event. Does NOT commit — caller manages the transaction."""
    entry = models.AuditLog(
        org_id=org_id,
        user_id=user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details,
        ip_address=ip_address,
    )
    db.add(entry)
    db.flush()
    return entry


def get_audit_log(
    org_id: int,
    db: Session,
    action: Optional[str] = None,
    user_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Return paginated audit log entries for an organization."""
    query = db.query(models.AuditLog).filter(models.AuditLog.org_id == org_id)

    if action:
        query = query.filter(models.AuditLog.action == action)
    if user_id:
        query = query.filter(models.AuditLog.user_id == user_id)

    total = query.count()
    entries = query.order_by(desc(models.AuditLog.created_at)).offset(offset).limit(limit).all()

    return {
        "entries": entries,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total,
    }
