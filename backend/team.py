"""
Team management router — invite, list, change roles, remove members, transfer ownership.

All endpoints require Owner or Admin role (except accept-invite which is public).
All queries scoped by org_id for data isolation.
"""

import html
import os
import secrets
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_active_user, get_password_hash, require_role
import models
import audit_service
from email_service import send_email_resend

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class InviteRequest(BaseModel):
    email: EmailStr
    role: str = "member"  # "admin" or "member"


class AcceptInviteRequest(BaseModel):
    token: str
    password: str
    full_name: Optional[str] = None


class ChangeRoleRequest(BaseModel):
    role: str  # "admin" or "member"


class TransferOwnershipRequest(BaseModel):
    new_owner_user_id: int


class AllocateAcornsRequest(BaseModel):
    user_id: int
    amount: float


class AllocationModeRequest(BaseModel):
    mode: str  # "shared" or "locked"


# ---------------------------------------------------------------------------
# List members
# ---------------------------------------------------------------------------

@router.get("/members")
async def list_members(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """List all members of the current user's organization. Any role can view."""
    members = db.query(models.User).filter(
        models.User.org_id == current_user.org_id,
        models.User.is_active == True,
    ).all()

    return [
        {
            "id": m.id,
            "email": m.email,
            "full_name": m.full_name,
            "role": m.role.value if m.role else "member",
            "locked_acorn_allocation": m.locked_acorn_allocation,
            "locked_acorn_balance": m.locked_acorn_balance,
            "last_login_at": m.last_login_at.isoformat() if m.last_login_at else None,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in members
    ]


# ---------------------------------------------------------------------------
# Invite member
# ---------------------------------------------------------------------------

@router.post("/invite")
async def invite_member(
    body: InviteRequest,
    request: Request,
    current_user: models.User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db),
):
    """Send an invitation to join the organization."""
    if body.role not in ("admin", "member"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'member'")

    # Check if email already belongs to a member of this org
    existing = db.query(models.User).filter(
        models.User.email == body.email,
        models.User.org_id == current_user.org_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="User is already a member of this organization")

    # Check for pending invitation
    pending = db.query(models.Invitation).filter(
        models.Invitation.email == body.email,
        models.Invitation.org_id == current_user.org_id,
        models.Invitation.status == models.InvitationStatus.pending,
    ).first()
    if pending:
        raise HTTPException(status_code=400, detail="A pending invitation already exists for this email")

    # Create invitation
    token = secrets.token_urlsafe(32)
    invitation = models.Invitation(
        org_id=current_user.org_id,
        invited_by=current_user.id,
        email=body.email,
        role=models.UserRole(body.role),
        token=token,
        status=models.InvitationStatus.pending,
        expires_at=datetime.utcnow() + timedelta(days=7),
    )
    db.add(invitation)

    audit_service.log_event(
        db,
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="member.invited",
        target_type="invitation",
        details={"email": body.email, "role": body.role},
        ip_address=request.client.host if request.client else None,
    )

    db.commit()
    db.refresh(invitation)

    org = db.query(models.Organization).filter(models.Organization.id == current_user.org_id).first()
    org_name = org.name if org else "your organization"

    # Build invite link from request origin
    origin = request.headers.get("origin") or request.headers.get("referer", "").rstrip("/")
    if not origin:
        origin = os.getenv("APP_URL", "http://localhost:3000")
    invite_url = f"{origin}/accept-invite/{token}"
    safe_invite_url = html.escape(invite_url, quote=True)

    # Send invitation email (best-effort — if user has no email config, the link is still returned)
    try:
        safe_org = html.escape(org_name)
        safe_inviter = html.escape(current_user.full_name or current_user.email)
        safe_role = html.escape(body.role)
        invite_html = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 520px; margin: 0 auto;">
            <h2 style="color: #1a1a1a; margin-bottom: 4px;">You've been invited to {safe_org}</h2>
            <p style="color: #6b7280; font-size: 15px;">
                <strong>{safe_inviter}</strong> has invited you to join
                <strong>{safe_org}</strong> as {('an' if body.role == 'admin' else 'a')} <strong>{safe_role}</strong>.
            </p>
            <a href="{safe_invite_url}"
               style="display: inline-block; margin: 20px 0; padding: 12px 28px; background-color: #F97316;
                      color: white; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 15px;">
                Accept Invitation
            </a>
            <p style="color: #9ca3af; font-size: 13px;">
                This invitation expires in 7 days. If you didn't expect this, you can ignore this email.
            </p>
        </div>
        """
        await send_email_resend(
            recipient_email=body.email,
            subject=f"You're invited to join {org_name}",
            body=invite_html,
            from_name=safe_org,
        )
        logger.info("Invitation email sent: org=%d, email=%s", current_user.org_id, body.email)
    except Exception as e:
        # Email sending is best-effort — log but don't fail the invite creation
        logger.warning("Could not send invitation email to %s: %s", body.email, str(e))

    logger.info("Invitation created: org=%d, email=%s, role=%s", current_user.org_id, body.email, body.role)

    return {
        "id": invitation.id,
        "email": invitation.email,
        "role": body.role,
        "token": token,
        "expires_at": invitation.expires_at.isoformat(),
        "org_name": org_name,
    }


# ---------------------------------------------------------------------------
# List pending invitations
# ---------------------------------------------------------------------------

@router.get("/invitations")
async def list_invitations(
    current_user: models.User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db),
):
    """List all invitations for the organization."""
    invitations = db.query(models.Invitation).filter(
        models.Invitation.org_id == current_user.org_id,
    ).order_by(models.Invitation.created_at.desc()).all()

    return [
        {
            "id": inv.id,
            "email": inv.email,
            "role": inv.role.value if inv.role else "member",
            "status": inv.status.value if inv.status else "pending",
            "token": inv.token if inv.status == models.InvitationStatus.pending else None,
            "expires_at": inv.expires_at.isoformat() if inv.expires_at else None,
            "created_at": inv.created_at.isoformat() if inv.created_at else None,
        }
        for inv in invitations
    ]


# ---------------------------------------------------------------------------
# Revoke invitation
# ---------------------------------------------------------------------------

@router.delete("/invitations/{invitation_id}")
async def revoke_invitation(
    invitation_id: int,
    request: Request,
    current_user: models.User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db),
):
    """Revoke a pending invitation."""
    invitation = db.query(models.Invitation).filter(
        models.Invitation.id == invitation_id,
        models.Invitation.org_id == current_user.org_id,
    ).first()
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if invitation.status != models.InvitationStatus.pending:
        raise HTTPException(status_code=400, detail="Only pending invitations can be revoked")

    invitation.status = models.InvitationStatus.revoked
    db.commit()

    return {"ok": True, "message": "Invitation revoked"}


# ---------------------------------------------------------------------------
# Accept invitation (public — no auth required)
# ---------------------------------------------------------------------------

@router.get("/invite/{token}")
async def get_invitation_info(token: str, db: Session = Depends(get_db)):
    """Public endpoint to check invitation validity before showing the signup form."""
    invitation = db.query(models.Invitation).filter(
        models.Invitation.token == token,
    ).first()

    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if invitation.status != models.InvitationStatus.pending:
        raise HTTPException(status_code=400, detail=f"Invitation is {invitation.status.value}")
    if invitation.expires_at.replace(tzinfo=None) < datetime.utcnow():
        invitation.status = models.InvitationStatus.expired
        db.commit()
        raise HTTPException(status_code=400, detail="Invitation has expired")

    org = db.query(models.Organization).filter(models.Organization.id == invitation.org_id).first()

    return {
        "email": invitation.email,
        "role": invitation.role.value,
        "org_name": org.name if org else None,
        "expires_at": invitation.expires_at.isoformat(),
    }


@router.post("/invite/{token}/accept")
async def accept_invitation(
    token: str,
    body: AcceptInviteRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Accept an invitation and create the user account. Public endpoint."""
    invitation = db.query(models.Invitation).filter(
        models.Invitation.token == token,
    ).first()

    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if invitation.status != models.InvitationStatus.pending:
        raise HTTPException(status_code=400, detail=f"Invitation is {invitation.status.value}")
    if invitation.expires_at.replace(tzinfo=None) < datetime.utcnow():
        invitation.status = models.InvitationStatus.expired
        db.commit()
        raise HTTPException(status_code=400, detail="Invitation has expired")

    # Check if user already exists with this email
    existing_user = db.query(models.User).filter(models.User.email == invitation.email).first()

    if existing_user:
        if existing_user.org_id and existing_user.org_id != invitation.org_id:
            raise HTTPException(
                status_code=400,
                detail="This email is already associated with another organization"
            )
        if existing_user.org_id == invitation.org_id:
            raise HTTPException(status_code=400, detail="User is already a member of this organization")

    # Create new user
    hashed = get_password_hash(body.password)
    user = models.User(
        org_id=invitation.org_id,
        email=invitation.email,
        full_name=body.full_name,
        hashed_password=hashed,
        role=invitation.role,
        is_active=True,
    )
    db.add(user)

    # Mark invitation as accepted
    invitation.status = models.InvitationStatus.accepted
    invitation.accepted_at = datetime.utcnow()

    audit_service.log_event(
        db,
        org_id=invitation.org_id,
        action="member.accepted",
        target_type="user",
        details={"email": invitation.email, "role": invitation.role.value},
        ip_address=request.client.host if request.client else None,
    )

    db.commit()
    db.refresh(user)

    logger.info("Invitation accepted: org=%d, email=%s", invitation.org_id, invitation.email)

    return {
        "id": user.id,
        "email": user.email,
        "role": user.role.value,
        "message": "Welcome to the team!",
    }


# ---------------------------------------------------------------------------
# Change member role
# ---------------------------------------------------------------------------

@router.put("/members/{user_id}/role")
async def change_member_role(
    user_id: int,
    body: ChangeRoleRequest,
    request: Request,
    current_user: models.User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db),
):
    """Change a member's role. Only Owner can promote to Admin. Cannot change Owner role."""
    if body.role not in ("admin", "member"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'member'")

    target = db.query(models.User).filter(
        models.User.id == user_id,
        models.User.org_id == current_user.org_id,
    ).first()
    if not target:
        raise HTTPException(status_code=404, detail="Member not found")

    if target.role == models.UserRole.owner:
        raise HTTPException(status_code=400, detail="Cannot change the Owner's role. Use ownership transfer instead.")

    if target.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot change your own role")

    # Only Owner can promote someone to Admin
    if body.role == "admin" and current_user.role != models.UserRole.owner:
        raise HTTPException(status_code=403, detail="Only the Owner can promote members to Admin")

    old_role = target.role.value
    target.role = models.UserRole(body.role)

    audit_service.log_event(
        db,
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="member.role_changed",
        target_type="user",
        target_id=user_id,
        details={"old_role": old_role, "new_role": body.role},
        ip_address=request.client.host if request.client else None,
    )

    db.commit()
    return {"ok": True, "user_id": user_id, "new_role": body.role}


# ---------------------------------------------------------------------------
# Remove member
# ---------------------------------------------------------------------------

@router.delete("/members/{user_id}")
async def remove_member(
    user_id: int,
    request: Request,
    current_user: models.User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db),
):
    """Remove a member from the organization. Cannot remove the Owner."""
    target = db.query(models.User).filter(
        models.User.id == user_id,
        models.User.org_id == current_user.org_id,
    ).first()
    if not target:
        raise HTTPException(status_code=404, detail="Member not found")

    if target.role == models.UserRole.owner:
        raise HTTPException(status_code=400, detail="Cannot remove the Owner")

    if target.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")

    # Admins can only remove Members, not other Admins
    if current_user.role == models.UserRole.admin and target.role == models.UserRole.admin:
        raise HTTPException(status_code=403, detail="Admins cannot remove other Admins")

    # Deactivate rather than delete — preserves audit trail and data
    target.is_active = False
    target.org_id = None

    audit_service.log_event(
        db,
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="member.removed",
        target_type="user",
        target_id=user_id,
        details={"email": target.email, "role": target.role.value},
        ip_address=request.client.host if request.client else None,
    )

    db.commit()
    return {"ok": True, "message": f"Member {target.email} has been removed"}


# ---------------------------------------------------------------------------
# Transfer ownership
# ---------------------------------------------------------------------------

@router.post("/transfer-ownership")
async def transfer_ownership(
    body: TransferOwnershipRequest,
    request: Request,
    current_user: models.User = Depends(require_role("owner")),
    db: Session = Depends(get_db),
):
    """Transfer ownership to another member. Current owner becomes Admin. Owner only."""
    new_owner = db.query(models.User).filter(
        models.User.id == body.new_owner_user_id,
        models.User.org_id == current_user.org_id,
        models.User.is_active == True,
    ).first()
    if not new_owner:
        raise HTTPException(status_code=404, detail="Target user not found in your organization")

    if new_owner.id == current_user.id:
        raise HTTPException(status_code=400, detail="You are already the owner")

    # Transfer: new owner becomes Owner, old owner becomes Admin
    new_owner.role = models.UserRole.owner
    current_user.role = models.UserRole.admin

    audit_service.log_event(
        db,
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="member.ownership_transferred",
        target_type="user",
        target_id=new_owner.id,
        details={"from_user": current_user.email, "to_user": new_owner.email},
        ip_address=request.client.host if request.client else None,
    )

    db.commit()
    return {"ok": True, "message": f"Ownership transferred to {new_owner.email}"}


# ---------------------------------------------------------------------------
# Delete organization
# ---------------------------------------------------------------------------

@router.delete("/organization")
async def delete_organization(
    request: Request,
    current_user: models.User = Depends(require_role("owner")),
    db: Session = Depends(get_db),
):
    """
    Permanently delete the organization and all associated data. Owner only.
    Deactivates all members and removes their org association.
    """
    org_id = current_user.org_id
    org = db.query(models.Organization).filter(models.Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Collect all member IDs for cascade cleanup
    member_ids = [m.id for m in db.query(models.User.id).filter(models.User.org_id == org_id).all()]

    if member_ids:
        workflow_ids = [w.id for w in db.query(models.Workflow.id).filter(
            models.Workflow.owner_id.in_(member_ids)
        ).all()]

        exec_ids = []
        component_ids = []
        email_queue_ids = []
        contact_ids = []
        seq_config_ids = []

        if workflow_ids:
            exec_ids = [e.id for e in db.query(models.Execution.id).filter(
                models.Execution.workflow_id.in_(workflow_ids)
            ).all()]
            component_ids = [c.id for c in db.query(models.Component.id).filter(
                models.Component.workflow_id.in_(workflow_ids)
            ).all()]
            seq_config_ids = [s.id for s in db.query(models.EmailSequenceConfig.id).filter(
                models.EmailSequenceConfig.workflow_id.in_(workflow_ids)
            ).all()]

        email_queue_ids = [eq.id for eq in db.query(models.EmailQueue.id).filter(
            models.EmailQueue.user_id.in_(member_ids)
        ).all()]
        contact_ids = [c.id for c in db.query(models.Contact.id).filter(
            models.Contact.user_id.in_(member_ids)
        ).all()]

        # ── Deletion order: leaf tables first, then parents ──
        # Topologically sorted to respect FK constraints (all FKs default to RESTRICT).

        # 1. ScheduledSequenceEmail → refs executions, email_queue, sequence_emails, sequence_configs
        if seq_config_ids:
            db.query(models.ScheduledSequenceEmail).filter(
                models.ScheduledSequenceEmail.sequence_config_id.in_(seq_config_ids)
            ).delete(synchronize_session=False)

        # 2. ContactActivity → refs contacts, email_queue
        if contact_ids:
            db.query(models.ContactActivity).filter(
                models.ContactActivity.contact_id.in_(contact_ids)
            ).delete(synchronize_session=False)

        # 3. AiUsageLog → refs users, executions, components
        db.query(models.AiUsageLog).filter(
            models.AiUsageLog.user_id.in_(member_ids)
        ).delete(synchronize_session=False)

        # 4. EmailQueue → refs workflows, executions, components, contacts, sequence_configs
        if email_queue_ids:
            db.query(models.EmailQueue).filter(
                models.EmailQueue.id.in_(email_queue_ids)
            ).delete(synchronize_session=False)

        # 5. ComponentExecution → refs executions, components
        if exec_ids:
            db.query(models.ComponentExecution).filter(
                models.ComponentExecution.execution_id.in_(exec_ids)
            ).delete(synchronize_session=False)

        # 6. ExtractedVariable → refs workflows, executions
        if workflow_ids:
            db.query(models.ExtractedVariable).filter(
                models.ExtractedVariable.workflow_id.in_(workflow_ids)
            ).delete(synchronize_session=False)

        # 7. Executions → refs workflows
        if exec_ids:
            db.query(models.Execution).filter(
                models.Execution.id.in_(exec_ids)
            ).delete(synchronize_session=False)

        # 8. SequenceEmail → refs sequence_configs
        if seq_config_ids:
            db.query(models.SequenceEmail).filter(
                models.SequenceEmail.sequence_config_id.in_(seq_config_ids)
            ).delete(synchronize_session=False)

        # 9. EmailSequenceConfig → refs workflows
        if seq_config_ids:
            db.query(models.EmailSequenceConfig).filter(
                models.EmailSequenceConfig.id.in_(seq_config_ids)
            ).delete(synchronize_session=False)

        # 10. Connections → refs components
        if component_ids:
            db.query(models.Connection).filter(
                (models.Connection.from_component_id.in_(component_ids)) |
                (models.Connection.to_component_id.in_(component_ids))
            ).delete(synchronize_session=False)

        # 11. Webhooks → refs workflows, components
        if workflow_ids:
            db.query(models.Webhook).filter(
                models.Webhook.workflow_id.in_(workflow_ids)
            ).delete(synchronize_session=False)

        # 12. Components → refs workflows
        if component_ids:
            db.query(models.Component).filter(
                models.Component.id.in_(component_ids)
            ).delete(synchronize_session=False)

        # 13. Workflows
        if workflow_ids:
            db.query(models.Workflow).filter(
                models.Workflow.id.in_(workflow_ids)
            ).delete(synchronize_session=False)

        # 14. Contacts → refs users
        if contact_ids:
            db.query(models.Contact).filter(
                models.Contact.id.in_(contact_ids)
            ).delete(synchronize_session=False)

        # 15. ApiKeys → refs users
        db.query(models.ApiKey).filter(
            models.ApiKey.user_id.in_(member_ids)
        ).delete(synchronize_session=False)

    # Deactivate all members (set org_id=None, is_active=False)
    members = db.query(models.User).filter(models.User.org_id == org_id).all()
    for m in members:
        m.org_id = None
        m.is_active = False

    # Flush user deactivation before deleting org — User.org_id is SET NULL,
    # so we need org_id=None committed to avoid the FK referencing a deleted org.
    db.flush()

    # Delete the organization (cascades to account, acorn_transactions, invitations, audit_log)
    db.delete(org)

    db.commit()

    logger.info("Organization deleted: id=%d, name=%s, by user=%d", org_id, org.name, current_user.id)

    return {"ok": True, "message": "Organization has been permanently deleted"}


# ---------------------------------------------------------------------------
# Acorn allocation mode
# ---------------------------------------------------------------------------

@router.get("/acorn-allocation")
async def get_allocation_mode(
    current_user: models.User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db),
):
    """Get current acorn allocation mode and per-user allocations."""
    account = db.query(models.Account).filter(models.Account.org_id == current_user.org_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="No account found")

    members = db.query(models.User).filter(
        models.User.org_id == current_user.org_id,
        models.User.is_active == True,
    ).all()

    return {
        "mode": account.acorn_allocation_mode,
        "total_balance": float(account.acorn_balance),
        "members": [
            {
                "user_id": m.id,
                "email": m.email,
                "full_name": m.full_name,
                "locked_acorn_allocation": m.locked_acorn_allocation,
                "locked_acorn_balance": m.locked_acorn_balance,
            }
            for m in members
        ],
    }


@router.put("/acorn-allocation/mode")
async def set_allocation_mode(
    body: AllocationModeRequest,
    request: Request,
    current_user: models.User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db),
):
    """Toggle between 'shared' pool and 'locked' per-seat allocation."""
    if body.mode not in ("shared", "locked"):
        raise HTTPException(status_code=400, detail="Mode must be 'shared' or 'locked'")

    account = db.query(models.Account).filter(models.Account.org_id == current_user.org_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="No account found")

    old_mode = account.acorn_allocation_mode
    account.acorn_allocation_mode = body.mode

    # If switching to shared, clear all per-user allocations
    if body.mode == "shared":
        members = db.query(models.User).filter(models.User.org_id == current_user.org_id).all()
        for m in members:
            m.locked_acorn_allocation = None
            m.locked_acorn_balance = None

    audit_service.log_event(
        db,
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="acorns.allocation_mode_changed",
        details={"old_mode": old_mode, "new_mode": body.mode},
        ip_address=request.client.host if request.client else None,
    )

    db.commit()
    return {"ok": True, "mode": body.mode}


@router.put("/acorn-allocation/user")
async def allocate_acorns_to_user(
    body: AllocateAcornsRequest,
    request: Request,
    current_user: models.User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db),
):
    """Set a user's locked Acorn allocation (only in 'locked' mode)."""
    account = db.query(models.Account).filter(models.Account.org_id == current_user.org_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="No account found")

    if body.amount < 0:
        raise HTTPException(status_code=400, detail="Allocation amount cannot be negative")

    if account.acorn_allocation_mode != "locked":
        raise HTTPException(status_code=400, detail="Acorn allocation mode is 'shared'. Switch to 'locked' first.")

    target = db.query(models.User).filter(
        models.User.id == body.user_id,
        models.User.org_id == current_user.org_id,
    ).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found in your organization")

    # Calculate total allocated across all users (use allocation, not balance)
    all_members = db.query(models.User).filter(
        models.User.org_id == current_user.org_id,
        models.User.is_active == True,
        models.User.id != body.user_id,
    ).all()
    already_allocated = sum(m.locked_acorn_allocation or 0 for m in all_members)

    if already_allocated + body.amount > account.acorn_balance:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot allocate {body.amount}. Total pool: {account.acorn_balance}, already allocated: {already_allocated}"
        )

    old_allocation = target.locked_acorn_allocation or 0
    old_balance = target.locked_acorn_balance or 0

    target.locked_acorn_allocation = body.amount

    if old_allocation > 0:
        # Preserve spend history: adjust balance by the allocation difference
        # e.g., had 500 allocation, spent 200 (balance=300), new allocation=600 → balance=400
        spent = old_allocation - old_balance
        target.locked_acorn_balance = max(body.amount - spent, 0)
    else:
        # First-time allocation — start full
        target.locked_acorn_balance = body.amount

    audit_service.log_event(
        db,
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="acorns.user_allocation_set",
        target_type="user",
        target_id=body.user_id,
        details={"allocation": body.amount},
        ip_address=request.client.host if request.client else None,
    )

    db.commit()
    return {
        "ok": True,
        "user_id": body.user_id,
        "locked_acorn_allocation": body.amount,
        "locked_acorn_balance": body.amount,
    }


# ---------------------------------------------------------------------------
# Audit log (read-only)
# ---------------------------------------------------------------------------

@router.get("/audit-log")
async def get_audit_log_endpoint(
    action: Optional[str] = None,
    user_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Return paginated audit log. Members see only their own entries."""
    # Members can only see their own audit entries
    if current_user.role == models.UserRole.member:
        user_id = current_user.id

    result = audit_service.get_audit_log(
        org_id=current_user.org_id,
        db=db,
        action=action,
        user_id=user_id,
        limit=limit,
        offset=offset,
    )

    # Fetch user emails for display
    user_ids = {e.user_id for e in result["entries"] if e.user_id}
    users_map = {}
    if user_ids:
        users = db.query(models.User).filter(models.User.id.in_(user_ids)).all()
        users_map = {u.id: u.email for u in users}

    return {
        "entries": [
            {
                "id": e.id,
                "action": e.action,
                "action_label": audit_service.ACTIONS.get(e.action, e.action),
                "user_id": e.user_id,
                "user_email": users_map.get(e.user_id),
                "target_type": e.target_type,
                "target_id": e.target_id,
                "details": e.details,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in result["entries"]
        ],
        "total": result["total"],
        "has_more": result["has_more"],
    }
