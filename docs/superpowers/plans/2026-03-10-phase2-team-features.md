# Phase 2 — Team Features Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add multi-seat team functionality: invitation system, team management, per-user Acorn allocation modes, and audit logging.

**Architecture:** Build on the existing Org → Account → User hierarchy from Phase 1. Add an `invitations` table for token-based invites, an `audit_log` table for tracking key events, and `acorn_allocation_mode` to Account for shared pool vs. locked-per-seat modes. New `team.py` backend router handles all team CRUD. Frontend gets a Team settings page with invite/manage UI.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, PostgreSQL, React, TypeScript, Tailwind, shadcn/ui

**Spec:** Architecture doc Section 10 Phase 2 items:
1. Role system with full permission enforcement at API and UI levels
2. Invitation system with email flow, token-based accept, join org logic
3. Acorn allocation modes (shared pool + locked per seat)
4. Team settings page, Acorn management page, audit log
5. Acorn top-up purchases — **already done in Phase 1 Paddle port**

---

## File Structure

### Backend — New Files
| File | Responsibility |
|------|---------------|
| `backend/team.py` | Team management router: list members, invite, accept invite, change role, remove member, transfer ownership |
| `backend/audit_service.py` | Audit logging: `log_event()` helper + query endpoint for audit log |
| `backend/alembic/versions/021_add_invitations_audit_log.py` | Migration: invitations, audit_log tables, acorn_allocation_mode column on accounts |

### Backend — Modified Files
| File | Changes |
|------|---------|
| `backend/models.py` | Add `Invitation`, `AuditLog` models. Add `acorn_allocation_mode` to Account. Update Organization relationship. |
| `backend/main.py` | Register `team_router` and `audit_router` |
| `backend/auth.py` | Add accept-invitation register variant |
| `backend/acorn_service.py` | Add per-user allocation check, `allocate_acorns_to_user()`, `get_user_acorn_budget()` |
| `backend/workflows.py` | Add `org_id` scoping to workflow queries |
| `backend/executions.py` | Check per-user allocation before execution if locked mode |

### Frontend — New Files
| File | Responsibility |
|------|---------------|
| `frontend/src/pages/TeamSettingsPage.tsx` | Team member list, invite form, role management, remove members |
| `frontend/src/pages/AcceptInvitePage.tsx` | Streamlined signup for invited users (name + password, email pre-filled) |

### Frontend — Modified Files
| File | Changes |
|------|---------|
| `frontend/src/App.tsx` | Add `/settings/team` and `/accept-invite/:token` routes |
| `frontend/src/lib/api.ts` | Add `teamApi` endpoints (list, invite, accept, changeRole, remove, transferOwnership) |
| `frontend/src/pages/SettingsPage.tsx` | Add "Team" tab (Owner/Admin only) |
| `frontend/src/components/Layout.tsx` | Add Team nav link in settings navigation |

---

## Chunk 1: Database Schema & Models

### Task 1: Add Invitation and AuditLog Models

**Files:**
- Modify: `backend/models.py`

- [ ] **Step 1: Add InvitationStatus enum after existing enums (after line 38)**

```python
class InvitationStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    expired = "expired"
    revoked = "revoked"
```

- [ ] **Step 2: Add Invitation model after PaddleWebhookEvent (after line 115)**

```python
class Invitation(Base):
    __tablename__ = "invitations"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    invited_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    email = Column(String(255), nullable=False)
    role = Column(SAEnum(UserRole), nullable=False, default=UserRole.member)
    token = Column(String(255), unique=True, nullable=False, index=True)
    status = Column(SAEnum(InvitationStatus), nullable=False, default=InvitationStatus.pending)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    organization = relationship("Organization")
    inviter = relationship("User", foreign_keys=[invited_by])
```

- [ ] **Step 3: Add AuditLog model after Invitation**

```python
class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(100), nullable=False, index=True)  # e.g. "member.invited", "role.changed", "billing.upgraded"
    target_type = Column(String(50), nullable=True)  # "user", "invitation", "account", "workflow"
    target_id = Column(Integer, nullable=True)
    details = Column(JSON, nullable=True)  # action-specific metadata
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    organization = relationship("Organization")
    user = relationship("User")
```

- [ ] **Step 4: Add `acorn_allocation_mode` to Account model (line ~69, after `acorn_balance`)**

Add this column to the Account class:

```python
acorn_allocation_mode = Column(String(20), default="shared", nullable=False)  # "shared" or "locked"
```

- [ ] **Step 5: Add `invitations` relationship to Organization model (line ~55)**

Add to Organization's relationships:

```python
invitations = relationship("Invitation", back_populates="organization", cascade="all, delete-orphan")
```

And update the Invitation model's organization relationship to include `back_populates`:

```python
organization = relationship("Organization", back_populates="invitations")
```

- [ ] **Step 6: Fix Organization.members relationship**

The current Organization model has `members = relationship("User", back_populates="organization")`. Verify this matches User's `organization = relationship("Organization", back_populates="members")`. If User says `back_populates="members"` but Organization says `back_populates="organization"`, they should be symmetric. Check and fix if needed.

- [ ] **Step 7: Commit**

```bash
git add backend/models.py
git commit -m "feat: add Invitation, AuditLog models and acorn_allocation_mode"
```

---

### Task 2: Create Alembic Migration

**Files:**
- Create: `backend/alembic/versions/021_add_invitations_audit_log.py`

- [ ] **Step 1: Write the migration file**

```python
"""add_invitations_audit_log

Revision ID: 021_add_invitations_audit_log
Revises: 020_add_organizations_accounts
Create Date: 2026-03-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '021_add_invitations_audit_log'
down_revision = '020_add_organizations_accounts'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum type for invitation status
    op.execute("CREATE TYPE invitation_status AS ENUM ('pending', 'accepted', 'expired', 'revoked')")

    # Create invitations table
    op.create_table('invitations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('org_id', sa.Integer(), nullable=False),
        sa.Column('invited_by', sa.Integer(), nullable=True),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('role', sa.Enum('owner', 'admin', 'member', name='user_role', create_type=False), nullable=False),
        sa.Column('token', sa.String(255), nullable=False),
        sa.Column('status', sa.Enum('pending', 'accepted', 'expired', 'revoked', name='invitation_status', create_type=False), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invited_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_invitations_id'), 'invitations', ['id'], unique=False)
    op.create_index(op.f('ix_invitations_token'), 'invitations', ['token'], unique=True)

    # Create audit_log table
    op.create_table('audit_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('org_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('target_type', sa.String(50), nullable=True),
        sa.Column('target_id', sa.Integer(), nullable=True),
        sa.Column('details', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_log_id'), 'audit_log', ['id'], unique=False)
    op.create_index(op.f('ix_audit_log_org_id'), 'audit_log', ['org_id'], unique=False)
    op.create_index(op.f('ix_audit_log_action'), 'audit_log', ['action'], unique=False)
    op.create_index(op.f('ix_audit_log_created_at'), 'audit_log', ['created_at'], unique=False)

    # Add acorn_allocation_mode to accounts
    op.add_column('accounts', sa.Column('acorn_allocation_mode', sa.String(20), server_default='shared', nullable=False))


def downgrade() -> None:
    op.drop_column('accounts', 'acorn_allocation_mode')

    op.drop_index(op.f('ix_audit_log_created_at'), table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_action'), table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_org_id'), table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_id'), table_name='audit_log')
    op.drop_table('audit_log')

    op.drop_index(op.f('ix_invitations_token'), table_name='invitations')
    op.drop_index(op.f('ix_invitations_id'), table_name='invitations')
    op.drop_table('invitations')

    op.execute("DROP TYPE IF EXISTS invitation_status")
```

- [ ] **Step 2: Commit**

```bash
git add backend/alembic/versions/021_add_invitations_audit_log.py
git commit -m "feat: migration for invitations, audit_log tables and acorn_allocation_mode"
```

---

## Chunk 2: Audit Logging Service

### Task 3: Create Audit Service

**Files:**
- Create: `backend/audit_service.py`

- [ ] **Step 1: Write audit_service.py**

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add backend/audit_service.py
git commit -m "feat: audit logging service with log_event and query helpers"
```

---

## Chunk 3: Team Management Backend

### Task 4: Create Team Router

**Files:**
- Create: `backend/team.py`

- [ ] **Step 1: Write team.py with all endpoints**

```python
"""
Team management router — invite, list, change roles, remove members, transfer ownership.

All endpoints require Owner or Admin role (except accept-invite which is public).
All queries scoped by org_id for data isolation.
"""

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

    # TODO: Send invitation email via email_service
    # For now, return the token so the frontend can construct the invite link
    org = db.query(models.Organization).filter(models.Organization.id == current_user.org_id).first()

    logger.info("Invitation created: org=%d, email=%s, role=%s", current_user.org_id, body.email, body.role)

    return {
        "id": invitation.id,
        "email": invitation.email,
        "role": body.role,
        "token": token,
        "expires_at": invitation.expires_at.isoformat(),
        "org_name": org.name if org else None,
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
        # If user exists but in a different org, they can't join (Phase 1 = single org per user)
        if existing_user.org_id and existing_user.org_id != invitation.org_id:
            raise HTTPException(
                status_code=400,
                detail="This email is already associated with another organization"
            )
        # If user exists in the same org, just activate them
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

    if account.acorn_allocation_mode != "locked":
        raise HTTPException(status_code=400, detail="Acorn allocation mode is 'shared'. Switch to 'locked' first.")

    target = db.query(models.User).filter(
        models.User.id == body.user_id,
        models.User.org_id == current_user.org_id,
    ).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found in your organization")

    # Calculate total allocated across all users
    all_members = db.query(models.User).filter(
        models.User.org_id == current_user.org_id,
        models.User.is_active == True,
        models.User.id != body.user_id,
    ).all()
    already_allocated = sum(m.locked_acorn_balance or 0 for m in all_members)

    if already_allocated + body.amount > account.acorn_balance:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot allocate {body.amount}. Total pool: {account.acorn_balance}, already allocated: {already_allocated}"
        )

    target.locked_acorn_balance = body.amount

    audit_service.log_event(
        db,
        org_id=current_user.org_id,
        user_id=current_user.id,
        action="acorns.user_allocation_set",
        target_type="user",
        target_id=body.user_id,
        details={"amount": body.amount},
        ip_address=request.client.host if request.client else None,
    )

    db.commit()
    return {"ok": True, "user_id": body.user_id, "locked_acorn_balance": body.amount}


# ---------------------------------------------------------------------------
# Audit log (read-only)
# ---------------------------------------------------------------------------

@router.get("/audit-log")
async def get_audit_log_endpoint(
    action: Optional[str] = None,
    user_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: models.User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db),
):
    """Return paginated audit log for the organization. Owner/Admin only."""
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
```

- [ ] **Step 2: Register team router in main.py**

In `backend/main.py`, add after line 25:

```python
from team import router as team_router
```

And after line 100, add:

```python
app.include_router(team_router, prefix="/team", tags=["Team"])
```

- [ ] **Step 3: Commit**

```bash
git add backend/team.py backend/main.py
git commit -m "feat: team management router with invite, roles, acorn allocation, and audit log"
```

---

## Chunk 4: Acorn Allocation in Execution Engine

### Task 5: Update Execution Engine for Per-User Allocation

**Files:**
- Modify: `backend/acorn_service.py`
- Modify: `backend/executions.py`

- [ ] **Step 1: Add per-user budget check to acorn_service.py**

Add after the existing `check_can_execute` function (around line 213):

```python
def check_user_can_execute(user: models.User, account: models.Account, db: Session) -> bool:
    """
    Check if a specific user can execute a workflow.

    In 'shared' mode: checks account-level balance (same as check_can_execute).
    In 'locked' mode: checks user's locked_acorn_balance.
    """
    min_reserve = get_config_float("min_acorn_reserve", db, default=1.0)

    if account.acorn_allocation_mode == "locked" and user.locked_acorn_balance is not None:
        return user.locked_acorn_balance >= min_reserve
    return float(account.acorn_balance) >= min_reserve
```

- [ ] **Step 2: Update execution pre-check in executions.py**

Find the existing pre-execution acorn balance check in `executions.py` and update it to use `check_user_can_execute` instead of `check_can_execute`:

```python
from acorn_service import check_user_can_execute, get_account_for_user, spend_acorns, usd_to_acorns

# Pre-execution acorn balance check
account = get_account_for_user(current_user, db)
if not account:
    raise HTTPException(status_code=403, detail="No billing account found")
if not check_user_can_execute(current_user, account, db):
    raise HTTPException(
        status_code=402,
        detail="Insufficient Acorn balance. Please top up or ask your admin to allocate more Acorns."
    )
```

- [ ] **Step 3: Commit**

```bash
git add backend/acorn_service.py backend/executions.py
git commit -m "feat: per-user acorn allocation check in execution engine"
```

---

## Chunk 5: Permission Enforcement Audit

### Task 6: Add org_id Scoping to Workflow & Component Queries

**Files:**
- Modify: `backend/workflows.py`
- Modify: `backend/components.py`

- [ ] **Step 1: Scope workflow queries by org_id**

In `backend/workflows.py`, find the list workflows endpoint and ensure all queries filter by the current user's org_id:

```python
# Example: list workflows should only show workflows belonging to users in the same org
workflows = db.query(models.Workflow).join(models.User).filter(
    models.User.org_id == current_user.org_id
).all()
```

For individual workflow fetches, add an ownership/org check:

```python
workflow = db.query(models.Workflow).filter(models.Workflow.id == workflow_id).first()
if not workflow:
    raise HTTPException(status_code=404)
# Verify org ownership
owner = db.query(models.User).filter(models.User.id == workflow.owner_id).first()
if not owner or owner.org_id != current_user.org_id:
    raise HTTPException(status_code=404, detail="Workflow not found")
```

Review every endpoint in workflows.py and add this scoping where missing.

- [ ] **Step 2: Similarly scope component and execution queries**

Review `backend/components.py` and `backend/executions.py` — ensure any query that returns user data also joins through the workflow's owner to verify org_id matches.

- [ ] **Step 3: Commit**

```bash
git add backend/workflows.py backend/components.py backend/executions.py
git commit -m "feat: enforce org_id scoping on all workflow, component, and execution queries"
```

---

## Chunk 6: Frontend — Team Management UI

### Task 7: Add Team API Functions

**Files:**
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Add teamApi object after billingApi (around line 1041)**

```typescript
export const teamApi = {
  listMembers: () => api.get('/team/members'),
  invite: (data: { email: string; role: string }) => api.post('/team/invite', data),
  listInvitations: () => api.get('/team/invitations'),
  revokeInvitation: (id: number) => api.delete(`/team/invitations/${id}`),
  getInviteInfo: (token: string) => api.get(`/team/invite/${token}`),
  acceptInvite: (token: string, data: { token: string; password: string; full_name?: string }) =>
    api.post(`/team/invite/${token}/accept`, data),
  changeRole: (userId: number, role: string) => api.put(`/team/members/${userId}/role`, { role }),
  removeMember: (userId: number) => api.delete(`/team/members/${userId}`),
  transferOwnership: (userId: number) => api.post('/team/transfer-ownership', { new_owner_user_id: userId }),
  getAllocationMode: () => api.get('/team/acorn-allocation'),
  setAllocationMode: (mode: string) => api.put('/team/acorn-allocation/mode', { mode }),
  allocateAcorns: (userId: number, amount: number) => api.put('/team/acorn-allocation/user', { user_id: userId, amount }),
  getAuditLog: (params?: { action?: string; user_id?: number; limit?: number; offset?: number }) =>
    api.get('/team/audit-log', { params }),
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat: add teamApi functions for members, invitations, roles, and allocation"
```

---

### Task 8: Create Team Settings Page

**Files:**
- Create: `frontend/src/pages/TeamSettingsPage.tsx`

- [ ] **Step 1: Write TeamSettingsPage.tsx**

Build a page with three sections:

**Section 1 — Team Members Table:**
- Columns: Name, Email, Role (badge), Last Login, Actions
- Actions dropdown: Change Role, Remove Member (with confirmation)
- Owner transfer button (only visible to Owner, with confirmation dialog)

**Section 2 — Invite Member:**
- Email input + Role select (Admin/Member) + "Send Invitation" button
- Below: pending invitations list with Revoke buttons

**Section 3 — Acorn Allocation (Owner/Admin only):**
- Toggle: Shared Pool / Locked Per Seat
- If locked: per-user allocation inputs with remaining balance display

Use React Query with `useQuery` and `useMutation` from `@tanstack/react-query`. Use existing shadcn/ui components: `Card`, `Button`, `Input`, `Badge`, `Select`, `Dialog`, `Alert`.

```typescript
import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { teamApi } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/components/ui/use-toast'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Users, UserPlus, Shield, Crown, Loader2, Trash2, Mail } from 'lucide-react'

export default function TeamSettingsPage() {
  const { user } = useAuth()
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteRole, setInviteRole] = useState('member')

  const isOwner = user?.role === 'owner'
  const isOwnerOrAdmin = user?.role === 'owner' || user?.role === 'admin'

  // Queries
  const { data: members, isLoading: membersLoading } = useQuery({
    queryKey: ['team-members'],
    queryFn: () => teamApi.listMembers().then(r => r.data),
  })

  const { data: invitations } = useQuery({
    queryKey: ['team-invitations'],
    queryFn: () => teamApi.listInvitations().then(r => r.data),
    enabled: isOwnerOrAdmin,
  })

  // Mutations
  const inviteMutation = useMutation({
    mutationFn: (data: { email: string; role: string }) => teamApi.invite(data),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['team-invitations'] })
      setInviteEmail('')
      toast({ title: 'Invitation sent', description: `Invited ${res.data.email} as ${res.data.role}` })
    },
    onError: (err: any) => {
      toast({ title: 'Error', description: err.response?.data?.detail || 'Failed to send invitation', variant: 'destructive' })
    },
  })

  const changeRoleMutation = useMutation({
    mutationFn: ({ userId, role }: { userId: number; role: string }) => teamApi.changeRole(userId, role),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['team-members'] })
      toast({ title: 'Role updated' })
    },
  })

  const removeMutation = useMutation({
    mutationFn: (userId: number) => teamApi.removeMember(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['team-members'] })
      toast({ title: 'Member removed' })
    },
  })

  const revokeMutation = useMutation({
    mutationFn: (id: number) => teamApi.revokeInvitation(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['team-invitations'] })
      toast({ title: 'Invitation revoked' })
    },
  })

  const roleBadge = (role: string) => {
    const colors: Record<string, string> = {
      owner: 'bg-orange-100 text-orange-700',
      admin: 'bg-purple-100 text-purple-700',
      member: 'bg-gray-100 text-gray-700',
    }
    const icons: Record<string, string> = { owner: '👑', admin: '⚙️', member: '🐿️' }
    return (
      <Badge className={colors[role] || colors.member}>
        {icons[role]} {role.charAt(0).toUpperCase() + role.slice(1)}
      </Badge>
    )
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold">Team Management</h1>
        <p className="text-muted-foreground">Manage your organization's team members and invitations.</p>
      </div>

      {/* Members List */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Users className="h-5 w-5" /> Team Members</CardTitle>
          <CardDescription>{members?.length || 0} member{(members?.length || 0) !== 1 ? 's' : ''}</CardDescription>
        </CardHeader>
        <CardContent>
          {membersLoading ? (
            <div className="flex justify-center py-8"><Loader2 className="h-6 w-6 animate-spin" /></div>
          ) : (
            <div className="divide-y">
              {members?.map((m: any) => (
                <div key={m.id} className="flex items-center justify-between py-3">
                  <div>
                    <div className="font-medium">{m.full_name || m.email}</div>
                    <div className="text-sm text-muted-foreground">{m.email}</div>
                  </div>
                  <div className="flex items-center gap-3">
                    {roleBadge(m.role)}
                    {isOwnerOrAdmin && m.role !== 'owner' && m.id !== user?.id && (
                      <div className="flex gap-1">
                        {isOwner && m.role === 'member' && (
                          <Button size="sm" variant="ghost" onClick={() => changeRoleMutation.mutate({ userId: m.id, role: 'admin' })}>
                            Promote
                          </Button>
                        )}
                        {isOwner && m.role === 'admin' && (
                          <Button size="sm" variant="ghost" onClick={() => changeRoleMutation.mutate({ userId: m.id, role: 'member' })}>
                            Demote
                          </Button>
                        )}
                        <Button size="sm" variant="ghost" className="text-red-600" onClick={() => {
                          if (confirm(`Remove ${m.email} from the team?`)) removeMutation.mutate(m.id)
                        }}>
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Invite Section */}
      {isOwnerOrAdmin && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><UserPlus className="h-5 w-5" /> Invite Member</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex gap-3">
              <Input
                type="email"
                placeholder="colleague@company.com"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                className="flex-1"
              />
              <select
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value)}
                className="border rounded px-3 py-2 text-sm"
              >
                <option value="member">Member</option>
                <option value="admin">Admin</option>
              </select>
              <Button
                onClick={() => inviteMutation.mutate({ email: inviteEmail, role: inviteRole })}
                disabled={!inviteEmail || inviteMutation.isPending}
              >
                {inviteMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mail className="h-4 w-4 mr-1" />}
                Invite
              </Button>
            </div>

            {/* Pending invitations */}
            {invitations && invitations.filter((i: any) => i.status === 'pending').length > 0 && (
              <div className="mt-4">
                <h4 className="text-sm font-medium text-muted-foreground mb-2">Pending Invitations</h4>
                <div className="divide-y">
                  {invitations.filter((i: any) => i.status === 'pending').map((inv: any) => (
                    <div key={inv.id} className="flex items-center justify-between py-2">
                      <div className="text-sm">
                        <span className="font-medium">{inv.email}</span>
                        <span className="text-muted-foreground ml-2">as {inv.role}</span>
                      </div>
                      <Button size="sm" variant="ghost" className="text-red-600" onClick={() => revokeMutation.mutate(inv.id)}>
                        Revoke
                      </Button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/TeamSettingsPage.tsx
git commit -m "feat: Team settings page with members list, invite, and role management"
```

---

### Task 9: Create Accept Invitation Page

**Files:**
- Create: `frontend/src/pages/AcceptInvitePage.tsx`

- [ ] **Step 1: Write AcceptInvitePage.tsx**

A streamlined signup form: email (pre-filled, read-only), full name, password. Shows org name and role. On submit, calls `teamApi.acceptInvite()` then redirects to `/login`.

```typescript
import React, { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { teamApi } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Loader2, CheckCircle } from 'lucide-react'

export default function AcceptInvitePage() {
  const { token } = useParams<{ token: string }>()
  const navigate = useNavigate()
  const [fullName, setFullName] = useState('')
  const [password, setPassword] = useState('')
  const [success, setSuccess] = useState(false)

  const { data: invite, isLoading, error } = useQuery({
    queryKey: ['invitation', token],
    queryFn: () => teamApi.getInviteInfo(token!).then(r => r.data),
    enabled: !!token,
  })

  const acceptMutation = useMutation({
    mutationFn: () => teamApi.acceptInvite(token!, { token: token!, password, full_name: fullName }),
    onSuccess: () => {
      setSuccess(true)
      setTimeout(() => navigate('/login'), 3000)
    },
  })

  if (isLoading) return <div className="flex justify-center items-center h-screen"><Loader2 className="h-8 w-8 animate-spin" /></div>
  if (error) return (
    <div className="flex justify-center items-center h-screen">
      <Card className="w-full max-w-md">
        <CardContent className="pt-6 text-center text-red-600">
          This invitation is invalid or has expired.
        </CardContent>
      </Card>
    </div>
  )

  if (success) return (
    <div className="flex justify-center items-center h-screen">
      <Card className="w-full max-w-md">
        <CardContent className="pt-6 text-center space-y-3">
          <CheckCircle className="h-12 w-12 text-green-500 mx-auto" />
          <h2 className="text-xl font-bold">Welcome to the team!</h2>
          <p className="text-muted-foreground">Redirecting to login...</p>
        </CardContent>
      </Card>
    </div>
  )

  return (
    <div className="flex justify-center items-center min-h-screen bg-gray-50 p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <div className="text-3xl mb-2">🐿️</div>
          <CardTitle>Join {invite?.org_name}</CardTitle>
          <CardDescription>You've been invited as {invite?.role}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="text-sm font-medium">Email</label>
            <Input value={invite?.email || ''} disabled className="bg-gray-50" />
          </div>
          <div>
            <label className="text-sm font-medium">Full Name</label>
            <Input value={fullName} onChange={e => setFullName(e.target.value)} placeholder="Your name" />
          </div>
          <div>
            <label className="text-sm font-medium">Password</label>
            <Input type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="Create a password" />
          </div>
          <Button
            className="w-full"
            onClick={() => acceptMutation.mutate()}
            disabled={!password || acceptMutation.isPending}
          >
            {acceptMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
            Join Team
          </Button>
          {acceptMutation.error && (
            <p className="text-sm text-red-600 text-center">
              {(acceptMutation.error as any).response?.data?.detail || 'Failed to accept invitation'}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/AcceptInvitePage.tsx
git commit -m "feat: accept invitation page with streamlined signup flow"
```

---

### Task 10: Add Routes and Navigation

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/SettingsPage.tsx`

- [ ] **Step 1: Add routes to App.tsx**

Add imports at top of App.tsx:

```typescript
import TeamSettingsPage from '@/pages/TeamSettingsPage'
import AcceptInvitePage from '@/pages/AcceptInvitePage'
```

Add after the `/settings/organization` route (after line 205):

```typescript
<Route
  path="/settings/team"
  element={
    <ProtectedRoute>
      <Layout>
        <TeamSettingsPage />
      </Layout>
    </ProtectedRoute>
  }
/>
```

Add the accept-invite route as a **public** route (near the login/register routes, around line 135):

```typescript
<Route path="/accept-invite/:token" element={<AcceptInvitePage />} />
```

- [ ] **Step 2: Add "Team" tab to SettingsPage navigation**

In `frontend/src/pages/SettingsPage.tsx`, find the settings tab navigation section. Add a "Team" tab that links to `/settings/team`, visible only to Owner/Admin:

```typescript
{(user?.role === 'owner' || user?.role === 'admin') && (
  <Link to="/settings/team" className={tabClass('/settings/team')}>
    <Users className="h-4 w-4" /> Team
  </Link>
)}
```

Add `Users` to the lucide-react imports.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.tsx frontend/src/pages/SettingsPage.tsx
git commit -m "feat: add team settings route and navigation tab"
```

---

## Chunk 7: Integration & Verification

### Task 11: Add Audit Logging to Existing Actions

**Files:**
- Modify: `backend/auth.py`
- Modify: `backend/paddle_webhooks.py`

- [ ] **Step 1: Add audit logging to login**

In `backend/auth.py` login endpoint (line 214), after updating `last_login_at` and before commit:

```python
import audit_service

# Inside login(), after line 222:
if user.org_id:
    audit_service.log_event(
        db, org_id=user.org_id, user_id=user.id, action="auth.login",
    )
```

- [ ] **Step 2: Add audit logging to registration**

In `backend/auth.py` register endpoint (line 152), after creating user and before commit:

```python
audit_service.log_event(
    db, org_id=org.id, user_id=user.id, action="auth.register",
    details={"email": user.email},
)
```

Note: Since `user.id` may not be set yet before commit, add this after `db.flush()` on the user add (add a `db.flush()` after `db.add(user)` and before the audit call, then keep `db.commit()` at the end).

- [ ] **Step 3: Add audit logging to billing events in paddle_webhooks.py**

In subscription created/updated/cancelled handlers, add audit log entries. Example for `_handle_subscription_created`:

```python
if account and user_id > 0:
    audit_service.log_event(
        db, org_id=account.org_id, action="billing.plan_changed",
        details={"plan": plan_info, "status": status},
    )
```

- [ ] **Step 4: Commit**

```bash
git add backend/auth.py backend/paddle_webhooks.py
git commit -m "feat: add audit logging to auth and billing events"
```

---

### Task 12: Verification Checklist

- [ ] **Step 1: Verify Python syntax on all new/modified backend files**

```bash
cd /home/tauhid/code/aibot2/backend && python3 -c "
import ast
files = ['models.py', 'team.py', 'audit_service.py', 'acorn_service.py', 'auth.py', 'main.py', 'paddle_webhooks.py', 'alembic/versions/021_add_invitations_audit_log.py']
for f in files:
    try:
        ast.parse(open(f).read())
        print(f'OK: {f}')
    except SyntaxError as e:
        print(f'SYNTAX ERROR in {f}: {e}')
"
```

- [ ] **Step 2: Verify frontend TypeScript compiles**

```bash
cd /home/tauhid/code/aibot2/frontend && npx tsc --noEmit 2>&1 | head -30
```

- [ ] **Step 3: Verify all imports resolve**

Check that all new imports (`team.py`, `audit_service.py`) exist and are importable. Check that frontend imports for new pages resolve.

- [ ] **Step 4: Fix any issues found and commit**

```bash
git add -A
git commit -m "fix: resolve any syntax or import issues from Phase 2 implementation"
```
