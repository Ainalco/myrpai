from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
import os
from dotenv import load_dotenv

from database import get_db
import models
import audit_service

load_dotenv()

router = APIRouter()
security = HTTPBearer()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# Pydantic models
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    company_name: Optional[str] = None
    team_size: Optional[str] = None
    current_crm: Optional[str] = None
    meeting_tool: Optional[str] = None
    meetings_per_week: Optional[str] = None
    deal_cycle: Optional[str] = None
    challenge: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class RefreshRequest(BaseModel):
    refresh_token: str

class TokenData(BaseModel):
    user_id: Optional[str] = None

class User(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    is_active: bool
    is_superadmin: bool = False
    enable_advanced_components: bool = False
    internal_domains: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_use_tls: Optional[bool] = None
    smtp_from_email: Optional[str] = None
    smtp_from_name: Optional[str] = None
    email_signature: Optional[str] = None
    email_signature_enabled: Optional[bool] = None
    created_at: datetime

    class Config:
        from_attributes = True

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def get_user_by_email(db: Session, email: str) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.email == email).first()

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=24))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(user_id: int):
    expire = datetime.utcnow() + timedelta(days=7)
    data = {"sub": str(user_id), "type": "refresh", "exp": expire}
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            raise credentials_exception
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    if user is None:
        raise credentials_exception
    return user

SEEDLING_ACORN_CAP = 300

def _enforce_seedling_acorn_cap(account: models.Account, db: Session) -> None:
    """Cap acorns at SEEDLING_ACORN_CAP when downgrading to the free plan."""
    balance = float(account.acorn_balance)
    if balance > SEEDLING_ACORN_CAP:
        excess = balance - SEEDLING_ACORN_CAP
        account.acorn_balance = SEEDLING_ACORN_CAP
        # Record the adjustment
        txn = models.AcornTransaction(
            account_id=account.id,
            type=models.AcornTransactionType.adjustment,
            amount=-excess,
            balance_after=SEEDLING_ACORN_CAP,
            description=f"Seedling plan acorn cap ({SEEDLING_ACORN_CAP} max) — {int(excess)} acorns released",
        )
        db.add(txn)
        db.flush()

async def get_current_active_user(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> models.User:
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    # Auto-downgrade expired trials and cancelled subscriptions (FIX #8)
    if current_user.org_id:
        account = db.query(models.Account).filter(
            models.Account.org_id == current_user.org_id
        ).first()
        if account:
            now = datetime.utcnow()
            changed = False

            if account.status == models.AccountStatus.trialing and account.trial_ends_at:
                if account.trial_ends_at.replace(tzinfo=None) < now:
                    account.status = models.AccountStatus.active
                    account.plan_tier = models.PlanTier.seedling
                    _enforce_seedling_acorn_cap(account, db)
                    changed = True

            if account.status == models.AccountStatus.cancelled and account.current_period_ends_at:
                if account.current_period_ends_at.replace(tzinfo=None) < now:
                    account.status = models.AccountStatus.active
                    account.plan_tier = models.PlanTier.seedling
                    account.current_period_ends_at = None
                    _enforce_seedling_acorn_cap(account, db)
                    changed = True

            if changed:
                db.commit()

    return current_user

def verify_workflow_access(workflow_id: int, current_user: models.User, db: Session) -> models.Workflow:
    """
    Verify the current user can access a workflow. Returns the workflow.

    - Owner/Admin: can access any workflow in their organization
    - Member: can only access workflows they own

    Raises HTTPException 404 if not found or not authorized.
    """
    workflow = db.query(models.Workflow).filter(models.Workflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    if current_user.role in (models.UserRole.owner, models.UserRole.admin):
        owner = db.query(models.User).filter(models.User.id == workflow.owner_id).first()
        if not owner or owner.org_id != current_user.org_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    elif workflow.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    return workflow


def require_role(*allowed_roles: str):
    async def dependency(current_user: models.User = Depends(get_current_active_user)):
        if current_user.role.value not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user
    return dependency

async def require_active_account(current_user=Depends(get_current_active_user), db=Depends(get_db)):
    """
    Ensures the user's account is in a usable state.
    Handles auto-downgrade for expired trials and cancelled subscriptions.
    """
    account = db.query(models.Account).filter(models.Account.org_id == current_user.org_id).first()
    if not account:
        raise HTTPException(status_code=403, detail="No account found")

    now = datetime.utcnow()
    changed = False

    # Trial expired — downgrade to seedling (free)
    if account.status == models.AccountStatus.trialing and account.trial_ends_at:
        if account.trial_ends_at.replace(tzinfo=None) < now:
            account.status = models.AccountStatus.active
            account.plan_tier = models.PlanTier.seedling
            _enforce_seedling_acorn_cap(account, db)
            changed = True

    # Cancelled subscription past its paid period — downgrade to seedling (FIX #3)
    if account.status == models.AccountStatus.cancelled and account.current_period_ends_at:
        if account.current_period_ends_at.replace(tzinfo=None) < now:
            account.status = models.AccountStatus.active
            account.plan_tier = models.PlanTier.seedling
            account.current_period_ends_at = None
            _enforce_seedling_acorn_cap(account, db)
            changed = True

    if changed:
        db.commit()

    # past_due users can still access (give them time to fix payment)
    if account.status.value not in ("trialing", "active", "cancelled", "past_due"):
        raise HTTPException(status_code=403, detail=f"Account is {account.status.value}. Please contact support.")
    return current_user

async def get_current_admin_user(
    current_user: models.User = Depends(get_current_active_user)
) -> models.User:
    if not getattr(current_user, 'is_superadmin', False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

@router.post("/register", status_code=201)
async def register(user_data: UserCreate, db=Depends(get_db)):
    if db.query(models.User).filter(models.User.email == user_data.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    # Create Organization
    slug = user_data.company_name.lower().replace(" ", "-").replace("'", "") if user_data.company_name else f"org-{user_data.email.split('@')[0]}"
    import re
    slug = re.sub(r'[^a-z0-9-]', '', slug)
    base_slug = slug
    counter = 1
    while db.query(models.Organization).filter(models.Organization.slug == slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1

    org = models.Organization(
        name=user_data.company_name or f"{user_data.full_name or 'My'}'s Organization",
        slug=slug,
        domain=user_data.email.split("@")[1],
        settings={
            "company_name": user_data.company_name,
            "team_size": user_data.team_size,
            "current_crm": user_data.current_crm,
            "meeting_tool": user_data.meeting_tool,
            "meetings_per_week": user_data.meetings_per_week,
            "deal_cycle": user_data.deal_cycle,
            "challenge": user_data.challenge,
        },
    )
    db.add(org)
    db.flush()

    from system_config import get_config_int, get_config_float
    trial_days = get_config_int("trial_duration_days", db, default=14)
    trial_acorns = get_config_float("trial_acorns", db, default=100)

    account = models.Account(
        org_id=org.id,
        plan_tier=models.PlanTier.trialing,
        status=models.AccountStatus.trialing,
        acorn_balance=trial_acorns,
        trial_ends_at=datetime.utcnow() + timedelta(days=trial_days),
    )
    db.add(account)
    db.flush()

    if trial_acorns > 0:
        txn = models.AcornTransaction(
            account_id=account.id,
            type=models.AcornTransactionType.trial_credit,
            amount=trial_acorns,
            balance_after=trial_acorns,
            description="Trial started",
        )
        db.add(txn)

    hashed = get_password_hash(user_data.password)
    user = models.User(
        org_id=org.id,
        email=user_data.email,
        full_name=user_data.full_name,
        hashed_password=hashed,
        role=models.UserRole.owner,
    )
    db.add(user)
    db.flush()
    audit_service.log_event(
        db, org_id=org.id, user_id=user.id, action="auth.register",
        details={"email": user.email},
    )
    db.commit()
    db.refresh(user)

    return {"id": user.id, "email": user.email, "message": "Registration successful"}

@router.post("/login")
async def login(user_data: UserLogin, db=Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == user_data.email).first()
    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    user.last_login_at = datetime.utcnow()
    if user.org_id:
        audit_service.log_event(db, org_id=user.org_id, user_id=user.id, action="auth.login")
    db.commit()

    access_token = create_access_token(data={"sub": str(user.id), "org_id": user.org_id, "role": user.role.value})
    refresh_token = create_refresh_token(user.id)

    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}

@router.post("/refresh")
async def refresh_token(body: RefreshRequest, db=Depends(get_db)):
    try:
        payload = jwt.decode(body.refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        user_id = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or disabled")

    access_token = create_access_token(data={"sub": str(user.id), "org_id": user.org_id, "role": user.role.value})
    new_refresh = create_refresh_token(user.id)

    return {"access_token": access_token, "refresh_token": new_refresh, "token_type": "bearer"}

@router.get("/me")
async def get_me(current_user=Depends(get_current_active_user), db=Depends(get_db)):
    account = db.query(models.Account).filter(models.Account.org_id == current_user.org_id).first()
    org = db.query(models.Organization).filter(models.Organization.id == current_user.org_id).first()

    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role.value if current_user.role else "owner",
        "is_superadmin": current_user.is_superadmin if hasattr(current_user, 'is_superadmin') else False,
        "is_active": current_user.is_active,
        "email_signature": current_user.email_signature,
        "email_signature_enabled": current_user.email_signature_enabled,
        "internal_domains": current_user.internal_domains,
        "smtp_host": current_user.smtp_host,
        "smtp_port": current_user.smtp_port,
        "smtp_username": current_user.smtp_username,
        "smtp_use_tls": current_user.smtp_use_tls,
        "smtp_from_email": current_user.smtp_from_email,
        "smtp_from_name": current_user.smtp_from_name,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
        "org": {"id": org.id, "name": org.name, "slug": org.slug, "domain": org.domain} if org else None,
        "locked_acorn_allocation": current_user.locked_acorn_allocation,
        "locked_acorn_balance": current_user.locked_acorn_balance,
        "account": {
            "plan_tier": "redwood" if account.status == models.AccountStatus.trialing else account.plan_tier.value,
            "status": account.status.value,
            "acorn_balance": account.acorn_balance,
            "acorn_allocation_mode": account.acorn_allocation_mode,
            "billing_cycle": account.billing_cycle,
            "trial_ends_at": account.trial_ends_at.isoformat() if account.trial_ends_at else None,
            "current_period_ends_at": account.current_period_ends_at.isoformat() if account.current_period_ends_at else None,
        } if account else None,
    }

class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None

@router.put("/profile")
async def update_profile(
    profile_data: ProfileUpdate,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update user profile (name)"""
    if profile_data.full_name is not None:
        current_user.full_name = profile_data.full_name

    db.commit()
    db.refresh(current_user)

    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
    }

@router.patch("/me/settings")
async def update_user_settings(
    internal_domains: Optional[str] = None,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update user settings like internal domains"""
    if internal_domains is not None:
        current_user.internal_domains = internal_domains

    db.commit()
    db.refresh(current_user)

    return {
        "success": True,
        "message": "Settings updated successfully",
        "internal_domains": current_user.internal_domains
    }

class SMTPSettings(BaseModel):
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_use_tls: bool = True
    smtp_from_email: str
    smtp_from_name: Optional[str] = None

@router.post("/me/smtp")
async def update_smtp_settings(
    smtp_settings: SMTPSettings,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update user SMTP settings for sending emails"""
    from encryption_service import encrypt_api_key

    # Encrypt the SMTP password before storing
    encrypted_password = encrypt_api_key(smtp_settings.smtp_password)

    # Update user SMTP settings
    current_user.smtp_host = smtp_settings.smtp_host
    current_user.smtp_port = smtp_settings.smtp_port
    current_user.smtp_username = smtp_settings.smtp_username
    current_user.smtp_password = encrypted_password
    current_user.smtp_use_tls = smtp_settings.smtp_use_tls
    current_user.smtp_from_email = smtp_settings.smtp_from_email
    current_user.smtp_from_name = smtp_settings.smtp_from_name

    db.commit()
    db.refresh(current_user)

    return {
        "success": True,
        "message": "SMTP settings saved successfully"
    }

class EmailSignatureUpdate(BaseModel):
    email_signature: Optional[str] = None
    email_signature_enabled: Optional[bool] = None

@router.put("/me/email-signature")
async def update_email_signature(
    data: EmailSignatureUpdate,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update user email signature settings"""
    if data.email_signature is not None:
        current_user.email_signature = data.email_signature
    if data.email_signature_enabled is not None:
        current_user.email_signature_enabled = data.email_signature_enabled

    db.commit()
    db.refresh(current_user)

    return {
        "success": True,
        "message": "Email signature updated successfully"
    }

@router.post("/me/smtp/test")
async def test_smtp_connection(
    smtp_settings: SMTPSettings,
    current_user: models.User = Depends(get_current_active_user)
):
    """Test SMTP connection with provided settings"""
    import smtplib
    from email.mime.text import MIMEText
    import logging

    logger = logging.getLogger(__name__)

    try:
        # Create SMTP connection
        if smtp_settings.smtp_use_tls:
            server = smtplib.SMTP(smtp_settings.smtp_host, smtp_settings.smtp_port, timeout=10)
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(smtp_settings.smtp_host, smtp_settings.smtp_port, timeout=10)

        # Login to SMTP server
        server.login(smtp_settings.smtp_username, smtp_settings.smtp_password)

        # If we got here, connection and authentication succeeded
        server.quit()

        logger.info(f"SMTP connection test successful for user {current_user.email}")

        return {
            "success": True,
            "message": f"Successfully connected to {smtp_settings.smtp_host}:{smtp_settings.smtp_port}"
        }

    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"SMTP authentication failed for user {current_user.email}: {str(e)}")
        return {
            "success": False,
            "message": "Authentication failed. Please check your username and password."
        }
    except smtplib.SMTPConnectError as e:
        logger.error(f"SMTP connection failed for user {current_user.email}: {str(e)}")
        return {
            "success": False,
            "message": f"Could not connect to {smtp_settings.smtp_host}:{smtp_settings.smtp_port}. Please check your host and port."
        }
    except Exception as e:
        logger.error(f"SMTP test failed for user {current_user.email}: {str(e)}")
        return {
            "success": False,
            "message": f"Connection failed: {str(e)}"
        }


# --- Organization endpoints ---

class OrganizationUpdate(BaseModel):
    name: Optional[str] = None
    domain: Optional[str] = None
    logo_url: Optional[str] = None


@router.get("/organization")
async def get_organization(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    org = db.query(models.Organization).filter(
        models.Organization.id == current_user.org_id
    ).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return {
        "id": org.id,
        "name": org.name,
        "slug": org.slug,
        "domain": org.domain,
        "logo_url": org.logo_url,
        "settings": org.settings,
    }


@router.put("/organization")
async def update_organization(
    body: OrganizationUpdate,
    current_user: models.User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db),
):
    org = db.query(models.Organization).filter(
        models.Organization.id == current_user.org_id
    ).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    if body.name is not None:
        org.name = body.name
    if body.domain is not None:
        org.domain = body.domain
    if body.logo_url is not None:
        org.logo_url = body.logo_url
    db.commit()
    db.refresh(org)
    return {
        "id": org.id,
        "name": org.name,
        "slug": org.slug,
        "domain": org.domain,
        "logo_url": org.logo_url,
    }
