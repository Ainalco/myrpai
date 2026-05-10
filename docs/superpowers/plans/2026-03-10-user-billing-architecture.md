# User System, Billing & Admin Architecture — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the single-user app into a multi-tenant SaaS with Org → Account → User hierarchy, Paddle billing, Acorn credit system, and plan-based feature gating.

**Architecture:** Wrap existing users in an Organization/Account hierarchy. Port the external PHP Paddle billing service into the Python backend. Add Acorn balance checks to the workflow execution engine. Gate features by plan tier. All DB queries scoped by org_id.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, PostgreSQL, Paddle Python SDK, React, TypeScript, Tailwind, shadcn/ui

**Spec:** `docs/superpowers/specs/2026-03-10-user-billing-architecture-design.md`

---

## File Structure

### Backend — New Files
| File | Responsibility |
|------|---------------|
| `backend/paddle_service.py` | Paddle SDK client: create checkout sessions, manage subscriptions, verify webhook signatures |
| `backend/paddle_webhooks.py` | FastAPI router for `POST /api/paddle/webhook`, event handlers for each Paddle event type |
| `backend/acorn_service.py` | Acorn balance operations: credit, debit, check balance, get transactions. All atomic DB operations. |
| `backend/plan_features.py` | Plan feature matrix dict + `check_feature_access()` helper |
| `backend/system_config.py` | CRUD for system_config table + `get_config(key)` cached helper |
| `backend/alembic/versions/020_add_organizations_accounts.py` | Migration: organizations, accounts, system_config, acorn_transactions tables + user column changes |

### Backend — Modified Files
| File | Changes |
|------|---------|
| `backend/models.py` | Add Organization, Account, AcornTransaction, SystemConfig models. Add org_id/role/is_superadmin to User. Drop username. |
| `backend/auth.py` | Email-based login, refresh tokens, updated register (creates Org+Account+User), require_role dependency, require_active_account dependency |
| `backend/main.py` | Include paddle_webhooks router and system_config router |
| `backend/executions.py` | Pre-execution acorn balance check, post-execution acorn debit |
| `backend/database.py` | No changes needed |

### Frontend — New Files
| File | Responsibility |
|------|---------------|
| `frontend/src/pages/OrganizationSettingsPage.tsx` | Org name, logo, domain settings |
| `frontend/src/pages/TreasuryPage.tsx` | Plan display, acorn balance, buy acorns, transaction history, upgrade/downgrade |
| `frontend/src/components/ui/acorn-balance.tsx` | Persistent nav bar acorn balance indicator |
| `frontend/src/components/ui/trial-banner.tsx` | Trial/past_due/suspended status banner |
| `frontend/src/components/ui/upgrade-cta.tsx` | Inline upgrade prompt component |
| `frontend/src/lib/permissions.ts` | `canAccess(feature)`, `hasRole(role)` helpers |

### Frontend — Modified Files
| File | Changes |
|------|---------|
| `frontend/src/contexts/AuthContext.tsx` | Expand to include org, acorns, role, plan_tier, refreshAcorns() |
| `frontend/src/pages/RegisterPage.tsx` | Send company_name + onboarding data to backend, drop username |
| `frontend/src/pages/LoginPage.tsx` | Remove username field, use email |
| `frontend/src/pages/SettingsPage.tsx` | Add navigation tabs for Profile/Organization/Treasury/Integrations with role guards |
| `frontend/src/lib/api.ts` | Update register payload, add acorn/billing/org API functions, add refresh token interceptor |
| `frontend/src/App.tsx` | Add routes for new settings sub-pages, add ProtectedRoute role checks |

---

## Chunk 1: Database Schema & Models

### Task 1: Create New SQLAlchemy Models

**Files:**
- Modify: `backend/models.py:1-36`

- [ ] **Step 1: Add new imports to models.py**

At line 1, update the import to include `Enum` and `Numeric`:

```python
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON, Float, Enum as SAEnum, Numeric
```

- [ ] **Step 2: Add Organization model after imports, before User**

Insert after line 4 (after `from database import Base`), before the User class:

```python
import enum

class PlanTier(str, enum.Enum):
    trialing = "trialing"
    sapling = "sapling"
    oak = "oak"
    redwood = "redwood"
    ancient_forest = "ancient_forest"

class AccountStatus(str, enum.Enum):
    trialing = "trialing"
    active = "active"
    past_due = "past_due"
    suspended = "suspended"
    cancelled = "cancelled"

class UserRole(str, enum.Enum):
    owner = "owner"
    admin = "admin"
    member = "member"

class AcornTransactionType(str, enum.Enum):
    trial_credit = "trial_credit"
    subscription_credit = "subscription_credit"
    purchase = "purchase"
    usage = "usage"
    adjustment = "adjustment"
    refund = "refund"

class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, nullable=False, index=True)
    domain = Column(String(255), nullable=True)
    logo_url = Column(String(500), nullable=True)
    settings = Column(JSON, nullable=True)  # team_size, current_crm, meeting_tool, etc.
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    account = relationship("Account", back_populates="organization", uselist=False, cascade="all, delete-orphan")
    users = relationship("User", back_populates="organization")

class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), unique=True, nullable=False)
    paddle_customer_id = Column(String(255), nullable=True)
    paddle_subscription_id = Column(String(255), nullable=True)
    plan_tier = Column(SAEnum(PlanTier), default=PlanTier.trialing, nullable=False)
    billing_cycle = Column(String(20), nullable=True)  # "monthly" or "annual"
    acorn_balance = Column(Float, default=0, nullable=False)
    status = Column(SAEnum(AccountStatus), default=AccountStatus.trialing, nullable=False)
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)
    current_period_ends_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    organization = relationship("Organization", back_populates="account")
    acorn_transactions = relationship("AcornTransaction", back_populates="account", cascade="all, delete-orphan")

class AcornTransaction(Base):
    __tablename__ = "acorn_transactions"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    type = Column(SAEnum(AcornTransactionType), nullable=False)
    amount = Column(Float, nullable=False)  # positive=credit, negative=debit
    balance_after = Column(Float, nullable=False)
    description = Column(String(500), nullable=False)
    paddle_transaction_id = Column(String(255), nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    account = relationship("Account", back_populates="acorn_transactions")
    user = relationship("User")

class SystemConfig(Base):
    __tablename__ = "system_config"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=False)
    description = Column(String(500), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

- [ ] **Step 3: Modify User model — add new columns, drop username**

Update the User class (currently lines 6-36) to add `org_id`, `role`, `is_superadmin`, `locked_acorn_balance`. Remove `username`. Rename `is_admin` to `is_superadmin`:

```python
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)  # nullable initially for migration
    email = Column(String, unique=True, index=True)
    full_name = Column(String, nullable=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    is_superadmin = Column(Boolean, default=False)  # platform-level admin (was is_admin)
    role = Column(SAEnum(UserRole), default=UserRole.owner, nullable=False)
    locked_acorn_balance = Column(Float, nullable=True)  # Phase 2
    enable_advanced_components = Column(Boolean, default=False)
    # SMTP fields remain unchanged
    smtp_host = Column(String, nullable=True)
    smtp_port = Column(Integer, nullable=True)
    smtp_username = Column(String, nullable=True)
    smtp_password = Column(String, nullable=True)
    smtp_use_tls = Column(Boolean, nullable=True)
    smtp_from_email = Column(String, nullable=True)
    smtp_from_name = Column(String, nullable=True)
    internal_domains = Column(Text, nullable=True)
    email_signature = Column(Text, nullable=True)
    email_signature_enabled = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    organization = relationship("Organization", back_populates="users")
    workflows = relationship("Workflow", back_populates="owner")
    contacts = relationship("Contact", back_populates="user", cascade="all, delete-orphan")
```

- [ ] **Step 4: Commit models**

```bash
git add backend/models.py
git commit -m "feat: add Organization, Account, AcornTransaction, SystemConfig models and update User model"
```

---

### Task 2: Create Alembic Migration

**Files:**
- Create: `backend/alembic/versions/020_add_organizations_accounts.py`

- [ ] **Step 1: Generate migration skeleton**

```bash
cd /home/tauhid/code/aibot2/backend && alembic revision -m "add organizations accounts and acorn system"
```

- [ ] **Step 2: Edit the migration file**

The migration must:
1. Create `organizations` table
2. Create `accounts` table
3. Create `acorn_transactions` table
4. Create `system_config` table
5. Add `org_id`, `role`, `is_superadmin`, `locked_acorn_balance`, `last_login_at` to `users`
6. Data migration: for each existing user, create Organization + Account, set org_id
7. Make `org_id` NOT NULL after data migration
8. Rename `is_admin` → `is_superadmin` (copy values)
9. Drop `username` column from `users`
10. Seed `system_config` with default values

Write the full migration with upgrade() and downgrade() functions. Use `op.execute()` for the data migration SQL.

Key data migration SQL:
```sql
-- For each user, create org and account
INSERT INTO organizations (name, slug, domain, created_at)
SELECT
    COALESCE(full_name, split_part(email, '@', 1)) || '''s Organization',
    'org-' || id,
    split_part(email, '@', 2),
    created_at
FROM users;

-- Create accounts for each org
INSERT INTO accounts (org_id, plan_tier, status, acorn_balance, trial_ends_at, created_at)
SELECT o.id, 'trialing', 'active', 0, NOW() + INTERVAL '14 days', o.created_at
FROM organizations o;

-- Link users to their orgs
UPDATE users u SET org_id = o.id
FROM organizations o WHERE o.slug = 'org-' || u.id;

-- Copy is_admin to is_superadmin
UPDATE users SET is_superadmin = is_admin;
```

- [ ] **Step 3: Run migration**

```bash
cd /home/tauhid/code/aibot2/backend && python migrate.py
```

- [ ] **Step 4: Verify migration**

```bash
docker compose exec postgres psql -U workflow_user -d workflow_platform -c "\dt" | grep -E "organizations|accounts|acorn_transactions|system_config"
docker compose exec postgres psql -U workflow_user -d workflow_platform -c "SELECT id, org_id, role, is_superadmin FROM users LIMIT 5;"
```

- [ ] **Step 5: Commit migration**

```bash
git add backend/alembic/versions/020_*.py
git commit -m "feat: migration for organizations, accounts, acorn_transactions, system_config"
```

---

### Task 3: Create SystemConfig Service

**Files:**
- Create: `backend/system_config.py`

- [ ] **Step 1: Write system_config.py**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from auth import get_current_active_user
import models
from typing import Optional
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory cache (refreshed on update)
_config_cache: dict[str, str] = {}
_cache_loaded = False


def _load_cache(db: Session):
    global _config_cache, _cache_loaded
    configs = db.query(models.SystemConfig).all()
    _config_cache = {c.key: c.value for c in configs}
    _cache_loaded = True


def get_config(key: str, db: Session, default: Optional[str] = None) -> str:
    global _cache_loaded
    if not _cache_loaded:
        _load_cache(db)
    return _config_cache.get(key, default)


def get_config_float(key: str, db: Session, default: float = 0.0) -> float:
    val = get_config(key, db)
    if val is None:
        return default
    return float(val)


def get_config_int(key: str, db: Session, default: int = 0) -> int:
    val = get_config(key, db)
    if val is None:
        return default
    return int(val)


def invalidate_cache():
    global _cache_loaded
    _cache_loaded = False


@router.get("/system-config")
async def list_config(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin required")
    configs = db.query(models.SystemConfig).all()
    return [{"key": c.key, "value": c.value, "description": c.description} for c in configs]


@router.put("/system-config/{key}")
async def update_config(
    key: str,
    body: dict,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin required")
    config = db.query(models.SystemConfig).filter(models.SystemConfig.key == key).first()
    if not config:
        raise HTTPException(status_code=404, detail="Config key not found")
    config.value = str(body["value"])
    db.commit()
    invalidate_cache()
    return {"key": config.key, "value": config.value}
```

- [ ] **Step 2: Register router in main.py**

In `backend/main.py`, add import and include at line ~96:

```python
from system_config import router as system_config_router
# ...
app.include_router(system_config_router, prefix="/system-config", tags=["System Config"])
```

- [ ] **Step 3: Commit**

```bash
git add backend/system_config.py backend/main.py
git commit -m "feat: add system_config service with cached reads and superadmin CRUD"
```

---

## Chunk 2: Auth System Overhaul

### Task 4: Update Auth — Email Login, Refresh Tokens, Role Middleware

**Files:**
- Modify: `backend/auth.py:1-361`

- [ ] **Step 1: Update Pydantic models**

Replace `UserCreate` (lines 26-30) and add new models:

```python
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    company_name: Optional[str] = None
    team_size: Optional[str] = None
    current_crm: Optional[str] = None
    meeting_tool: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr  # was username
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class RefreshRequest(BaseModel):
    refresh_token: str
```

- [ ] **Step 2: Update create_access_token to include org_id and role**

Replace JWT creation function (lines 83-91):

```python
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=1440))  # 24 hours
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(user_id: int):
    expire = datetime.utcnow() + timedelta(days=7)
    data = {"sub": str(user_id), "type": "refresh", "exp": expire}
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)
```

- [ ] **Step 3: Update get_current_user to use email and validate token type**

Replace the `get_current_user` function:

```python
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            raise credentials_exception
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    if user is None:
        raise credentials_exception
    return user
```

- [ ] **Step 4: Add role-checking and account-status dependencies**

Add after `get_current_active_user`:

```python
def require_role(*allowed_roles: str):
    async def dependency(current_user: models.User = Depends(get_current_active_user)):
        if current_user.role.value not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user
    return dependency

async def require_active_account(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    account = db.query(models.Account).filter(
        models.Account.org_id == current_user.org_id
    ).first()
    if not account:
        raise HTTPException(status_code=403, detail="No account found")
    # Check trial expiry
    if account.status == models.AccountStatus.trialing and account.trial_ends_at:
        from datetime import datetime, timezone
        if account.trial_ends_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=402, detail="Trial expired. Please subscribe to continue.")
    if account.status.value not in ("trialing", "active"):
        raise HTTPException(
            status_code=403,
            detail=f"Account is {account.status.value}. Please update your subscription."
        )
    return current_user
```

- [ ] **Step 5: Update register endpoint to create Org + Account + User**

Replace the register function (lines 123-171):

```python
@router.post("/register", response_model=dict, status_code=201)
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    # Check email uniqueness
    if db.query(models.User).filter(models.User.email == user_data.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    # Create Organization
    slug = user_data.company_name.lower().replace(" ", "-") if user_data.company_name else f"org-{user_data.email.split('@')[0]}"
    # Ensure unique slug
    base_slug = slug
    counter = 1
    while db.query(models.Organization).filter(models.Organization.slug == slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1

    org = models.Organization(
        name=user_data.company_name or f"{user_data.full_name}'s Organization",
        slug=slug,
        domain=user_data.email.split("@")[1] if user_data.email else None,
        settings={
            "team_size": user_data.team_size,
            "current_crm": user_data.current_crm,
            "meeting_tool": user_data.meeting_tool,
        },
    )
    db.add(org)
    db.flush()  # get org.id

    # Create Account with trial
    from system_config import get_config_int, get_config_float
    trial_days = get_config_int("trial_duration_days", db, default=14)
    trial_acorns = get_config_float("trial_acorns", db, default=250)

    account = models.Account(
        org_id=org.id,
        plan_tier=models.PlanTier.trialing,
        status=models.AccountStatus.trialing,
        acorn_balance=trial_acorns,
        trial_ends_at=datetime.utcnow() + timedelta(days=trial_days),
    )
    db.add(account)
    db.flush()

    # Create trial credit transaction
    if trial_acorns > 0:
        txn = models.AcornTransaction(
            account_id=account.id,
            type=models.AcornTransactionType.trial_credit,
            amount=trial_acorns,
            balance_after=trial_acorns,
            description="Trial started",
        )
        db.add(txn)

    # Create User as Owner
    hashed = get_password_hash(user_data.password)
    user = models.User(
        org_id=org.id,
        email=user_data.email,
        full_name=user_data.full_name,
        hashed_password=hashed,
        role=models.UserRole.owner,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return {"id": user.id, "email": user.email, "message": "Registration successful"}
```

- [ ] **Step 6: Update login endpoint to use email**

Replace login function (lines 173-207):

```python
@router.post("/login", response_model=TokenResponse)
async def login(user_data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == user_data.email).first()
    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    # Update last login
    user.last_login_at = datetime.utcnow()
    db.commit()

    access_token = create_access_token(
        data={"sub": str(user.id), "org_id": user.org_id, "role": user.role.value}
    )
    refresh_token = create_refresh_token(user.id)

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)
```

- [ ] **Step 7: Add refresh token endpoint**

```python
@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(body: RefreshRequest, db: Session = Depends(get_db)):
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

    access_token = create_access_token(
        data={"sub": str(user.id), "org_id": user.org_id, "role": user.role.value}
    )
    new_refresh = create_refresh_token(user.id)

    return TokenResponse(access_token=access_token, refresh_token=new_refresh)
```

- [ ] **Step 8: Add /auth/me endpoint to return org and account info**

Update the existing `/me` endpoint to include org/account data:

```python
@router.get("/me")
async def get_me(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    account = db.query(models.Account).filter(
        models.Account.org_id == current_user.org_id
    ).first()
    org = db.query(models.Organization).filter(
        models.Organization.id == current_user.org_id
    ).first()

    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role.value,
        "is_superadmin": current_user.is_superadmin,
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
        "org": {
            "id": org.id,
            "name": org.name,
            "slug": org.slug,
            "domain": org.domain,
        } if org else None,
        "account": {
            "plan_tier": account.plan_tier.value,
            "status": account.status.value,
            "acorn_balance": account.acorn_balance,
            "billing_cycle": account.billing_cycle,
            "trial_ends_at": account.trial_ends_at.isoformat() if account.trial_ends_at else None,
            "current_period_ends_at": account.current_period_ends_at.isoformat() if account.current_period_ends_at else None,
        } if account else None,
    }
```

- [ ] **Step 9: Update all references from `username` to `email` across auth.py**

Search for any remaining references to `username` in auth.py and update them. The `UserLogin` model should use `email`, and any query filters using `models.User.username` should use `models.User.email`.

- [ ] **Step 10: Update admin user check**

Replace `get_current_admin_user` (used in `backend/admin.py`) to use `is_superadmin`:

```python
async def get_current_admin_user(
    current_user: models.User = Depends(get_current_active_user),
) -> models.User:
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user
```

- [ ] **Step 11: Commit**

```bash
git add backend/auth.py
git commit -m "feat: email-based auth, refresh tokens, org/account creation on register, role middleware"
```

---

## Chunk 3: Acorn Credit System & Plan Features

### Task 5: Create Acorn Service

**Files:**
- Create: `backend/acorn_service.py`

- [ ] **Step 1: Write acorn_service.py**

```python
from sqlalchemy.orm import Session
from sqlalchemy import desc
import models
from system_config import get_config_float
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def get_balance(account_id: int, db: Session) -> float:
    account = db.query(models.Account).filter(models.Account.id == account_id).first()
    if not account:
        return 0.0
    return account.acorn_balance


def credit_acorns(
    account_id: int,
    amount: float,
    txn_type: models.AcornTransactionType,
    description: str,
    db: Session,
    user_id: Optional[int] = None,
    paddle_transaction_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> models.AcornTransaction:
    account = db.query(models.Account).with_for_update().filter(
        models.Account.id == account_id
    ).first()
    if not account:
        raise ValueError(f"Account {account_id} not found")

    account.acorn_balance += amount
    txn = models.AcornTransaction(
        account_id=account_id,
        user_id=user_id,
        type=txn_type,
        amount=amount,
        balance_after=account.acorn_balance,
        description=description,
        paddle_transaction_id=paddle_transaction_id,
        metadata_json=metadata,
    )
    db.add(txn)
    db.flush()
    return txn


def spend_acorns(
    account_id: int,
    user_id: int,
    amount: float,
    description: str,
    db: Session,
    metadata: Optional[dict] = None,
) -> models.AcornTransaction:
    if amount <= 0:
        raise ValueError("Spend amount must be positive")

    account = db.query(models.Account).with_for_update().filter(
        models.Account.id == account_id
    ).first()
    if not account:
        raise ValueError(f"Account {account_id} not found")

    if account.acorn_balance < amount:
        raise ValueError(
            f"Insufficient acorns. Required: {amount}, available: {account.acorn_balance}"
        )

    account.acorn_balance -= amount
    txn = models.AcornTransaction(
        account_id=account_id,
        user_id=user_id,
        type=models.AcornTransactionType.usage,
        amount=-amount,
        balance_after=account.acorn_balance,
        description=description,
        metadata_json=metadata,
    )
    db.add(txn)
    db.flush()
    return txn


def check_can_execute(account_id: int, db: Session) -> bool:
    min_reserve = get_config_float("min_acorn_reserve", db, default=1.0)
    balance = get_balance(account_id, db)
    return balance >= min_reserve


def get_account_for_user(user: models.User, db: Session) -> Optional[models.Account]:
    return db.query(models.Account).filter(
        models.Account.org_id == user.org_id
    ).first()


def usd_to_acorns(usd_cost: float, db: Session) -> float:
    rate = get_config_float("acorn_cost_rate_usd", db, default=0.01)
    if rate <= 0:
        return 0.0
    return usd_cost / rate


def get_transactions(
    account_id: int,
    db: Session,
    limit: int = 20,
    offset: int = 0,
):
    query = db.query(models.AcornTransaction).filter(
        models.AcornTransaction.account_id == account_id
    ).order_by(desc(models.AcornTransaction.created_at))
    total = query.count()
    transactions = query.offset(offset).limit(limit).all()
    return {
        "transactions": transactions,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total,
    }
```

- [ ] **Step 2: Commit**

```bash
git add backend/acorn_service.py
git commit -m "feat: acorn_service with credit, debit, balance check, USD conversion"
```

---

### Task 6: Create Plan Features Service

**Files:**
- Create: `backend/plan_features.py`

- [ ] **Step 1: Write plan_features.py**

```python
import models
from sqlalchemy.orm import Session
from typing import Optional


PLAN_FEATURES = {
    "trialing": {
        "max_emails_per_sequence": 3,
        "ai_filter": False,
        "ai_send_timing": False,
        "api_access": False,
    },
    "sapling": {
        "max_emails_per_sequence": 3,
        "ai_filter": False,
        "ai_send_timing": False,
        "api_access": False,
    },
    "oak": {
        "max_emails_per_sequence": 7,
        "ai_filter": True,
        "ai_send_timing": True,
        "api_access": False,
    },
    "redwood": {
        "max_emails_per_sequence": 15,
        "ai_filter": True,
        "ai_send_timing": True,
        "api_access": True,
    },
    "ancient_forest": {
        "max_emails_per_sequence": None,  # unlimited
        "ai_filter": True,
        "ai_send_timing": True,
        "api_access": True,
    },
}


def get_plan_features(plan_tier: str) -> dict:
    return PLAN_FEATURES.get(plan_tier, PLAN_FEATURES["trialing"])


def check_feature_access(account: models.Account, feature: str) -> bool:
    features = get_plan_features(account.plan_tier.value)
    value = features.get(feature)
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    return True  # non-bool means it has a limit, but is accessible


def get_feature_limit(account: models.Account, feature: str) -> Optional[int]:
    features = get_plan_features(account.plan_tier.value)
    return features.get(feature)


def get_plan_display_info():
    """Returns plan info for frontend display (pricing page, upgrade CTAs)."""
    return {
        "sapling": {"name": "Sapling", "price_monthly": 99, "price_annual": 79, "emoji": "🌱"},
        "oak": {"name": "Oak", "price_monthly": 199, "price_annual": 159, "emoji": "🌳"},
        "redwood": {"name": "Redwood", "price_monthly": 349, "price_annual": 279, "emoji": "🌲"},
        "ancient_forest": {"name": "Ancient Forest", "price_monthly": None, "price_annual": None, "emoji": "🏔️"},
    }
```

- [ ] **Step 2: Commit**

```bash
git add backend/plan_features.py
git commit -m "feat: plan feature matrix with access checks and limit queries"
```

---

### Task 7: Integrate Acorn Checks into Execution Engine

**Files:**
- Modify: `backend/executions.py:1781+` (execute_workflow function)

- [ ] **Step 1: Add pre-execution balance check**

At the start of the `execute_workflow` function (after loading the workflow, before executing components), add:

```python
from acorn_service import check_can_execute, get_account_for_user, spend_acorns, usd_to_acorns

# Pre-execution acorn balance check
account = get_account_for_user(current_user, db)
if not account:
    raise HTTPException(status_code=403, detail="No billing account found")
if not check_can_execute(account.id, db):
    raise HTTPException(
        status_code=402,
        detail="Insufficient Acorn balance. Please top up or upgrade your plan."
    )
```

- [ ] **Step 2: Add post-execution acorn debit**

After the execution completes successfully and `flush_usage_log(db)` is called, add cost deduction:

```python
# Calculate total cost from this execution's AI usage
total_cost_usd = 0.0
usage_logs = db.query(models.AiUsageLog).filter(
    models.AiUsageLog.execution_id == execution.id
).all()
for log in usage_logs:
    total_cost_usd += log.cost if hasattr(log, 'cost') and log.cost else 0.0

if total_cost_usd > 0:
    acorn_cost = usd_to_acorns(total_cost_usd, db)
    try:
        spend_acorns(
            account_id=account.id,
            user_id=current_user.id,
            amount=acorn_cost,
            description=f"Workflow execution: {workflow.name}",
            db=db,
            metadata={"execution_id": execution.id, "workflow_id": workflow.id},
        )
    except ValueError as e:
        logger.warning(f"Acorn debit failed for execution {execution.id}: {e}")
        # Don't fail the execution — log for manual reconciliation
```

- [ ] **Step 3: Commit**

```bash
git add backend/executions.py
git commit -m "feat: pre-execution acorn balance check and post-execution debit"
```

---

## Chunk 4: Paddle Integration (In-Repo)

### Task 8: Create Paddle Service

**Files:**
- Create: `backend/paddle_service.py`

- [ ] **Step 1: Write paddle_service.py**

```python
import os
import hmac
import hashlib
import json
import logging
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

PADDLE_API_KEY = os.getenv("PADDLE_API_KEY", "")
PADDLE_ENVIRONMENT = os.getenv("PADDLE_ENVIRONMENT", "sandbox")
PADDLE_WEBHOOK_SECRET = os.getenv("PADDLE_WEBHOOK_SECRET", "")
PADDLE_CLIENT_TOKEN = os.getenv("PADDLE_CLIENT_TOKEN", "")

# Paddle API base URLs
PADDLE_API_BASE = (
    "https://api.paddle.com"
    if PADDLE_ENVIRONMENT == "production"
    else "https://sandbox-api.paddle.com"
)

# Price IDs from environment
PRICE_IDS = {
    "sapling_monthly": os.getenv("PADDLE_PRICE_SAPLING_MONTHLY", ""),
    "sapling_annual": os.getenv("PADDLE_PRICE_SAPLING_ANNUAL", ""),
    "oak_monthly": os.getenv("PADDLE_PRICE_OAK_MONTHLY", ""),
    "oak_annual": os.getenv("PADDLE_PRICE_OAK_ANNUAL", ""),
    "redwood_monthly": os.getenv("PADDLE_PRICE_REDWOOD_MONTHLY", ""),
    "redwood_annual": os.getenv("PADDLE_PRICE_REDWOOD_ANNUAL", ""),
    "acorns_500": os.getenv("PADDLE_PRICE_ACORNS_500", ""),
    "acorns_1750": os.getenv("PADDLE_PRICE_ACORNS_1750", ""),
    "acorns_4000": os.getenv("PADDLE_PRICE_ACORNS_4000", ""),
}

# Acorn amounts for top-up packs
TOPUP_ACORN_AMOUNTS = {
    os.getenv("PADDLE_PRICE_ACORNS_500", ""): 500,
    os.getenv("PADDLE_PRICE_ACORNS_1750", ""): 1750,
    os.getenv("PADDLE_PRICE_ACORNS_4000", ""): 4000,
}

# Plan mapping from price IDs
PLAN_FROM_PRICE = {}
for plan in ["sapling", "oak", "redwood"]:
    for cycle in ["monthly", "annual"]:
        price_id = PRICE_IDS.get(f"{plan}_{cycle}", "")
        if price_id:
            PLAN_FROM_PRICE[price_id] = {"plan": plan, "cycle": cycle}


def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
    """Verify Paddle webhook signature."""
    if not PADDLE_WEBHOOK_SECRET:
        logger.warning("PADDLE_WEBHOOK_SECRET not set, skipping verification")
        return True
    expected = hmac.new(
        PADDLE_WEBHOOK_SECRET.encode(),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def get_price_ids():
    """Return all Paddle price IDs for frontend checkout."""
    return {
        "environment": PADDLE_ENVIRONMENT,
        "client_token": PADDLE_CLIENT_TOKEN,
        "plans": {
            k: v for k, v in PRICE_IDS.items()
            if k.startswith(("sapling", "oak", "redwood")) and v
        },
        "topups": {
            k: v for k, v in PRICE_IDS.items()
            if k.startswith("acorns") and v
        },
    }


def get_plan_from_price_id(price_id: str) -> Optional[dict]:
    """Returns {"plan": "oak", "cycle": "monthly"} or None."""
    return PLAN_FROM_PRICE.get(price_id)


def get_topup_acorns(price_id: str) -> Optional[int]:
    """Returns acorn amount for a top-up price ID, or None."""
    return TOPUP_ACORN_AMOUNTS.get(price_id)
```

- [ ] **Step 2: Commit**

```bash
git add backend/paddle_service.py
git commit -m "feat: paddle_service with config, price mapping, and webhook verification"
```

---

### Task 9: Create Paddle Webhook Handlers

**Files:**
- Create: `backend/paddle_webhooks.py`

- [ ] **Step 1: Write paddle_webhooks.py**

```python
from fastapi import APIRouter, Request, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
import models
import acorn_service
import paddle_service
from system_config import get_config_float
import logging
import json

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_account_by_paddle_customer(customer_id: str, db: Session):
    return db.query(models.Account).filter(
        models.Account.paddle_customer_id == customer_id
    ).first()


def _handle_subscription_created(data: dict, db: Session):
    customer_id = data.get("customer_id", "")
    subscription_id = data.get("id", "")
    status = data.get("status", "")

    account = _get_account_by_paddle_customer(customer_id, db)
    if not account:
        logger.error(f"No account for paddle customer {customer_id}")
        return

    account.paddle_subscription_id = subscription_id

    # Determine plan from price
    items = data.get("items", [])
    if items:
        price_id = items[0].get("price", {}).get("id", "")
        plan_info = paddle_service.get_plan_from_price_id(price_id)
        if plan_info:
            account.plan_tier = models.PlanTier(plan_info["plan"])
            account.billing_cycle = plan_info["cycle"]

    if status == "active":
        account.status = models.AccountStatus.active
        # Credit plan acorns
        plan_key = f"plan_acorns_{account.plan_tier.value}"
        acorn_amount = get_config_float(plan_key, db, default=0)
        if acorn_amount > 0:
            acorn_service.credit_acorns(
                account_id=account.id,
                amount=acorn_amount,
                txn_type=models.AcornTransactionType.subscription_credit,
                description=f"Subscription started: {account.plan_tier.value} plan",
                db=db,
                paddle_transaction_id=subscription_id,
            )
    elif status == "trialing":
        account.status = models.AccountStatus.trialing

    db.commit()
    logger.info(f"Subscription created for account {account.id}: {account.plan_tier.value}")


def _handle_subscription_updated(data: dict, db: Session):
    customer_id = data.get("customer_id", "")
    account = _get_account_by_paddle_customer(customer_id, db)
    if not account:
        return

    items = data.get("items", [])
    if items:
        price_id = items[0].get("price", {}).get("id", "")
        plan_info = paddle_service.get_plan_from_price_id(price_id)
        if plan_info:
            account.plan_tier = models.PlanTier(plan_info["plan"])
            account.billing_cycle = plan_info["cycle"]

    scheduled_change = data.get("scheduled_change")
    if scheduled_change:
        logger.info(f"Account {account.id} has scheduled change: {scheduled_change}")

    db.commit()


def _handle_subscription_canceled(data: dict, db: Session):
    customer_id = data.get("customer_id", "")
    account = _get_account_by_paddle_customer(customer_id, db)
    if not account:
        return
    # Access continues until period end
    effective_at = data.get("current_billing_period", {}).get("ends_at")
    if effective_at:
        from datetime import datetime
        account.current_period_ends_at = datetime.fromisoformat(effective_at.replace("Z", "+00:00"))
    account.status = models.AccountStatus.cancelled
    db.commit()
    logger.info(f"Subscription cancelled for account {account.id}")


def _handle_subscription_past_due(data: dict, db: Session):
    customer_id = data.get("customer_id", "")
    account = _get_account_by_paddle_customer(customer_id, db)
    if not account:
        return
    account.status = models.AccountStatus.past_due
    db.commit()
    logger.info(f"Account {account.id} is now past_due")


def _handle_transaction_completed(data: dict, db: Session):
    customer_id = data.get("customer_id", "")
    transaction_id = data.get("id", "")

    account = _get_account_by_paddle_customer(customer_id, db)
    if not account:
        logger.error(f"No account for paddle customer {customer_id}")
        return

    # Idempotency check
    existing = db.query(models.AcornTransaction).filter(
        models.AcornTransaction.paddle_transaction_id == transaction_id
    ).first()
    if existing:
        logger.info(f"Transaction {transaction_id} already processed, skipping")
        return

    items = data.get("items", [])
    for item in items:
        price_id = item.get("price", {}).get("id", "")

        # Check if top-up
        topup_amount = paddle_service.get_topup_acorns(price_id)
        if topup_amount:
            acorn_service.credit_acorns(
                account_id=account.id,
                amount=topup_amount,
                txn_type=models.AcornTransactionType.purchase,
                description=f"Acorn top-up: {topup_amount} acorns",
                db=db,
                paddle_transaction_id=transaction_id,
            )
            db.commit()
            logger.info(f"Top-up: {topup_amount} acorns credited to account {account.id}")
            return

        # Check if subscription renewal
        plan_info = paddle_service.get_plan_from_price_id(price_id)
        if plan_info:
            plan_key = f"plan_acorns_{plan_info['plan']}"
            acorn_amount = get_config_float(plan_key, db, default=0)
            if acorn_amount > 0:
                acorn_service.credit_acorns(
                    account_id=account.id,
                    amount=acorn_amount,
                    txn_type=models.AcornTransactionType.subscription_credit,
                    description=f"Monthly renewal: {plan_info['plan']} plan",
                    db=db,
                    paddle_transaction_id=transaction_id,
                )
            account.status = models.AccountStatus.active
            db.commit()
            logger.info(f"Renewal: {acorn_amount} acorns credited to account {account.id}")
            return


def _handle_adjustment_created(data: dict, db: Session):
    """Handle refunds."""
    transaction_id = data.get("transaction_id", "")
    customer_id = data.get("customer_id", "")

    account = _get_account_by_paddle_customer(customer_id, db)
    if not account:
        return

    # Find original credit transaction
    original = db.query(models.AcornTransaction).filter(
        models.AcornTransaction.paddle_transaction_id == transaction_id
    ).first()
    if original and original.amount > 0:
        acorn_service.credit_acorns(
            account_id=account.id,
            amount=-original.amount,  # negative = debit
            txn_type=models.AcornTransactionType.refund,
            description=f"Refund for transaction {transaction_id}",
            db=db,
            paddle_transaction_id=f"refund-{transaction_id}",
        )
        db.commit()
        logger.info(f"Refund: {original.amount} acorns deducted from account {account.id}")


EVENT_HANDLERS = {
    "subscription.created": _handle_subscription_created,
    "subscription.updated": _handle_subscription_updated,
    "subscription.canceled": _handle_subscription_canceled,
    "subscription.past_due": _handle_subscription_past_due,
    "subscription.activated": lambda data, db: None,  # handled by subscription.created
    "transaction.completed": _handle_transaction_completed,
    "adjustment.created": _handle_adjustment_created,
}


@router.post("/paddle/webhook")
async def paddle_webhook(request: Request):
    raw_body = await request.body()

    # Verify signature
    signature = request.headers.get("Paddle-Signature", "")
    if not paddle_service.verify_webhook_signature(raw_body, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    body = json.loads(raw_body)
    event_type = body.get("event_type", "")
    data = body.get("data", {})

    handler = EVENT_HANDLERS.get(event_type)
    if not handler:
        logger.warning(f"Unhandled Paddle event: {event_type}")
        return {"status": "ignored"}

    db = SessionLocal()
    try:
        handler(data, db)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Paddle webhook error for {event_type}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Webhook processing failed")
    finally:
        db.close()
```

- [ ] **Step 2: Add billing API endpoints for frontend**

Add to `paddle_webhooks.py`:

```python
from auth import get_current_active_user, require_role
from database import get_db

@router.get("/billing/prices")
async def get_prices():
    """Public endpoint — returns Paddle price IDs for checkout."""
    return paddle_service.get_price_ids()

@router.get("/billing/status")
async def get_billing_status(
    current_user: models.User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db),
):
    account = acorn_service.get_account_for_user(current_user, db)
    if not account:
        raise HTTPException(status_code=404, detail="No account found")
    return {
        "plan_tier": account.plan_tier.value,
        "status": account.status.value,
        "billing_cycle": account.billing_cycle,
        "acorn_balance": account.acorn_balance,
        "trial_ends_at": account.trial_ends_at.isoformat() if account.trial_ends_at else None,
        "current_period_ends_at": account.current_period_ends_at.isoformat() if account.current_period_ends_at else None,
        "paddle_customer_id": account.paddle_customer_id,
    }

@router.get("/billing/transactions")
async def get_billing_transactions(
    limit: int = 20,
    offset: int = 0,
    current_user: models.User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db),
):
    account = acorn_service.get_account_for_user(current_user, db)
    if not account:
        raise HTTPException(status_code=404, detail="No account found")
    result = acorn_service.get_transactions(account.id, db, limit, offset)
    return {
        "transactions": [
            {
                "id": t.id,
                "type": t.type.value,
                "amount": t.amount,
                "balance_after": t.balance_after,
                "description": t.description,
                "created_at": t.created_at.isoformat(),
            }
            for t in result["transactions"]
        ],
        "total": result["total"],
        "has_more": result["has_more"],
    }

@router.get("/billing/acorns")
async def get_acorn_balance(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Any role can check acorn balance."""
    account = acorn_service.get_account_for_user(current_user, db)
    if not account:
        raise HTTPException(status_code=404, detail="No account found")
    return {"balance": account.acorn_balance}
```

- [ ] **Step 3: Register router in main.py**

In `backend/main.py`, add:

```python
from paddle_webhooks import router as paddle_router
# ...
app.include_router(paddle_router, prefix="/api", tags=["Billing"])
```

- [ ] **Step 4: Commit**

```bash
git add backend/paddle_webhooks.py backend/paddle_service.py backend/main.py
git commit -m "feat: Paddle webhook handlers, billing API endpoints, and acorn top-up processing"
```

---

## Chunk 5: Frontend — Auth & Context Updates

### Task 10: Update AuthContext

**Files:**
- Modify: `frontend/src/contexts/AuthContext.tsx`

- [ ] **Step 1: Expand AuthContext types and state**

Update the context to include org, account, and acorn data:

```typescript
interface OrgInfo {
  id: number
  name: string
  slug: string
  domain: string | null
}

interface AccountInfo {
  plan_tier: string
  status: string
  acorn_balance: number
  billing_cycle: string | null
  trial_ends_at: string | null
  current_period_ends_at: string | null
}

interface AuthUser {
  id: number
  email: string
  full_name: string | null
  role: 'owner' | 'admin' | 'member'
  is_superadmin: boolean
  is_active: boolean
  email_signature: string | null
  email_signature_enabled: boolean | null
  internal_domains: string | null
  smtp_host: string | null
  smtp_port: number | null
  smtp_username: string | null
  smtp_use_tls: boolean | null
  smtp_from_email: string | null
  smtp_from_name: string | null
  created_at: string | null
  org: OrgInfo | null
  account: AccountInfo | null
}

interface AuthContextType {
  user: AuthUser | null
  isLoading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  register: (data: RegisterData) => Promise<void>
  refreshUser: () => Promise<void>
  refreshAcorns: () => Promise<void>
}

interface RegisterData {
  email: string
  password: string
  full_name?: string
  company_name?: string
  team_size?: string
  current_crm?: string
  meeting_tool?: string
}
```

- [ ] **Step 2: Update login to store refresh token and use email**

```typescript
const login = async (email: string, password: string) => {
  const response = await authApi.login({ email, password })
  localStorage.setItem('access_token', response.access_token)
  localStorage.setItem('refresh_token', response.refresh_token)
  await fetchUser()
}
```

- [ ] **Step 3: Add refreshAcorns function**

```typescript
const refreshAcorns = async () => {
  try {
    const response = await api.get('/billing/acorns')
    setUser(prev => prev ? {
      ...prev,
      account: prev.account ? { ...prev.account, acorn_balance: response.data.balance } : null
    } : null)
  } catch (err) {
    console.error('Failed to refresh acorn balance:', err)
  }
}
```

- [ ] **Step 4: Update register function to send new fields**

```typescript
const register = async (data: RegisterData) => {
  await authApi.register(data)
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/contexts/AuthContext.tsx
git commit -m "feat: expand AuthContext with org, account, acorns, role, and refresh token support"
```

---

### Task 11: Update API Client

**Files:**
- Modify: `frontend/src/lib/api.ts:19-25, 284-289`

- [ ] **Step 1: Add refresh token interceptor**

After the existing request interceptor (line 25), add a response interceptor:

```typescript
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true
      const refreshToken = localStorage.getItem('refresh_token')
      if (refreshToken) {
        try {
          const response = await api.post('/auth/refresh', { refresh_token: refreshToken })
          localStorage.setItem('access_token', response.data.access_token)
          localStorage.setItem('refresh_token', response.data.refresh_token)
          originalRequest.headers.Authorization = `Bearer ${response.data.access_token}`
          return api(originalRequest)
        } catch {
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
          window.location.href = '/login'
        }
      }
    }
    return Promise.reject(error)
  }
)
```

- [ ] **Step 2: Update register function signature**

Replace the register function (lines 284-289):

```typescript
register: (data: {
  email: string
  password: string
  full_name?: string
  company_name?: string
  team_size?: string
  current_crm?: string
  meeting_tool?: string
}) => api.post('/auth/register', data),
```

- [ ] **Step 3: Add billing API functions**

```typescript
export const billingApi = {
  getStatus: () => api.get('/billing/status'),
  getPrices: () => api.get('/billing/prices'),
  getTransactions: (limit = 20, offset = 0) =>
    api.get(`/billing/transactions?limit=${limit}&offset=${offset}`),
  getAcornBalance: () => api.get('/billing/acorns'),
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat: refresh token interceptor, updated register payload, billing API functions"
```

---

### Task 12: Update Registration Page

**Files:**
- Modify: `frontend/src/pages/RegisterPage.tsx:146-174`

- [ ] **Step 1: Update form submit handler to send all fields**

Replace the handleSubmit function:

```typescript
const handleSubmit = async (e: React.FormEvent) => {
  e.preventDefault()
  if (!validateStep(3)) return
  setIsLoading(true)
  try {
    const fullName = `${formData.firstName} ${formData.lastName}`.trim()

    await registerUser({
      email: formData.email,
      password: formData.password,
      full_name: fullName,
      company_name: formData.companyName,
      team_size: formData.teamSize,
      current_crm: formData.currentCRM,
      meeting_tool: formData.meetingTool,
    })

    setIsLoading(false)
    setIsSuccess(true)
    setTimeout(() => navigate('/login'), 3000)
  } catch (err: any) {
    setIsLoading(false)
    setErrors({ submit: err.message || 'Registration failed. Please try again.' })
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/RegisterPage.tsx
git commit -m "feat: send company and onboarding data to backend on registration"
```

---

### Task 13: Update Login Page

**Files:**
- Modify: `frontend/src/pages/LoginPage.tsx`

- [ ] **Step 1: Change login form from username to email**

Update the login form to use email field instead of username. Update the form state, input field label/placeholder, and the login call to use email.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/LoginPage.tsx
git commit -m "feat: switch login form from username to email"
```

---

### Task 14: Create Permissions Helper

**Files:**
- Create: `frontend/src/lib/permissions.ts`

- [ ] **Step 1: Write permissions.ts**

```typescript
type Role = 'owner' | 'admin' | 'member'
type PlanTier = 'trialing' | 'sapling' | 'oak' | 'redwood' | 'ancient_forest'

const PLAN_FEATURES: Record<PlanTier, Record<string, boolean | number | null>> = {
  trialing: { max_emails_per_sequence: 3, ai_filter: false, ai_send_timing: false, api_access: false },
  sapling: { max_emails_per_sequence: 3, ai_filter: false, ai_send_timing: false, api_access: false },
  oak: { max_emails_per_sequence: 7, ai_filter: true, ai_send_timing: true, api_access: false },
  redwood: { max_emails_per_sequence: 15, ai_filter: true, ai_send_timing: true, api_access: true },
  ancient_forest: { max_emails_per_sequence: null, ai_filter: true, ai_send_timing: true, api_access: true },
}

const ROLE_HIERARCHY: Record<Role, number> = { owner: 3, admin: 2, member: 1 }

export function hasRole(userRole: Role, requiredRole: Role): boolean {
  return ROLE_HIERARCHY[userRole] >= ROLE_HIERARCHY[requiredRole]
}

export function canAccess(planTier: PlanTier, feature: string): boolean {
  const features = PLAN_FEATURES[planTier] || PLAN_FEATURES.trialing
  const value = features[feature]
  if (typeof value === 'boolean') return value
  if (value === null) return true // unlimited
  if (typeof value === 'number') return true // has limit but accessible
  return false
}

export function getFeatureLimit(planTier: PlanTier, feature: string): number | null {
  const features = PLAN_FEATURES[planTier] || PLAN_FEATURES.trialing
  const value = features[feature]
  if (typeof value === 'number') return value
  return null // unlimited or not applicable
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/lib/permissions.ts
git commit -m "feat: frontend permissions and feature gating helpers"
```

---

## Chunk 6: Frontend — New Pages & UI Components

### Task 15: Create Acorn Balance Component

**Files:**
- Create: `frontend/src/components/ui/acorn-balance.tsx`

- [ ] **Step 1: Write the acorn balance indicator**

A small component for the top nav bar showing current acorn balance. Shows warning color when low (< 50 acorns). Clicking navigates to Treasury.

```typescript
import { useAuth } from '@/contexts/AuthContext'
import { useNavigate } from 'react-router-dom'

export function AcornBalance() {
  const { user } = useAuth()
  const navigate = useNavigate()

  if (!user?.account) return null

  const balance = user.account.acorn_balance
  const isLow = balance < 50

  return (
    <button
      onClick={() => navigate('/settings/treasury')}
      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
        isLow
          ? 'bg-red-100 text-red-700 hover:bg-red-200'
          : 'bg-amber-100 text-amber-700 hover:bg-amber-200'
      }`}
    >
      <span>🌰</span>
      <span>{Math.round(balance).toLocaleString()}</span>
    </button>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/ui/acorn-balance.tsx
git commit -m "feat: acorn balance nav indicator component"
```

---

### Task 16: Create Trial Banner Component

**Files:**
- Create: `frontend/src/components/ui/trial-banner.tsx`

- [ ] **Step 1: Write trial-banner.tsx**

Shows status-appropriate banner based on account state. Non-dismissible.

```typescript
import { useAuth } from '@/contexts/AuthContext'
import { useNavigate } from 'react-router-dom'

export function TrialBanner() {
  const { user } = useAuth()
  const navigate = useNavigate()

  if (!user?.account) return null

  const { status, trial_ends_at } = user.account

  if (status === 'active') return null

  let message = ''
  let bgClass = ''

  if (status === 'trialing' && trial_ends_at) {
    const daysLeft = Math.ceil(
      (new Date(trial_ends_at).getTime() - Date.now()) / (1000 * 60 * 60 * 24)
    )
    if (daysLeft <= 0) {
      message = 'Your free trial has expired.'
      bgClass = 'bg-red-600'
    } else {
      message = `You're on a free trial. ${daysLeft} day${daysLeft !== 1 ? 's' : ''} remaining.`
      bgClass = 'bg-amber-600'
    }
  } else if (status === 'past_due') {
    message = 'Payment failed. Please update your payment method to continue using Scurry.'
    bgClass = 'bg-red-600'
  } else if (status === 'suspended') {
    message = 'Your account is suspended. Please reactivate your subscription.'
    bgClass = 'bg-red-700'
  } else if (status === 'cancelled') {
    message = 'Your subscription has been cancelled. Export your data before access ends.'
    bgClass = 'bg-gray-700'
  }

  if (!message) return null

  return (
    <div className={`${bgClass} text-white text-sm text-center py-2 px-4`}>
      {message}{' '}
      <button
        onClick={() => navigate('/settings/treasury')}
        className="underline font-medium hover:no-underline"
      >
        {status === 'cancelled' ? 'Export data →' : 'Choose a plan →'}
      </button>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/ui/trial-banner.tsx
git commit -m "feat: trial/status banner component for account lifecycle states"
```

---

### Task 17: Create Treasury Page

**Files:**
- Create: `frontend/src/pages/TreasuryPage.tsx`

- [ ] **Step 1: Write TreasuryPage.tsx**

The Treasury page shows: current plan with upgrade/downgrade options, acorn balance with "Buy More" button, transaction history. Uses Paddle.js overlay for checkout.

Build this page with:
- Plan tier display card showing current plan, status, billing cycle
- Acorn balance display with top-up pack buttons (500/1750/4000)
- Transaction history table with pagination (uses `billingApi.getTransactions`)
- Paddle checkout integration: load Paddle.js, call `Paddle.Checkout.open()` with price IDs and custom data `{ account_id }`

Use existing shadcn/ui components: `Card`, `Button`, `Badge` from `components/ui/`.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/TreasuryPage.tsx
git commit -m "feat: Treasury page with plan management, acorn balance, and transaction history"
```

---

### Task 18: Create Organization Settings Page

**Files:**
- Create: `frontend/src/pages/OrganizationSettingsPage.tsx`

- [ ] **Step 1: Write OrganizationSettingsPage.tsx**

Simple form page: org name, domain, logo URL. Saves via `PUT /api/organizations/{org_id}`. Only accessible to Owner/Admin.

- [ ] **Step 2: Add backend endpoint for org update**

Add to `backend/auth.py` or create a new `backend/organizations.py`:

```python
@router.put("/organizations/{org_id}")
async def update_organization(
    org_id: int,
    body: dict,
    current_user: models.User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db),
):
    if current_user.org_id != org_id:
        raise HTTPException(status_code=403, detail="Not your organization")
    org = db.query(models.Organization).filter(models.Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404)
    if "name" in body:
        org.name = body["name"]
    if "domain" in body:
        org.domain = body["domain"]
    if "logo_url" in body:
        org.logo_url = body["logo_url"]
    db.commit()
    return {"id": org.id, "name": org.name, "domain": org.domain, "logo_url": org.logo_url}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/OrganizationSettingsPage.tsx backend/auth.py
git commit -m "feat: organization settings page and API endpoint"
```

---

### Task 19: Update Settings Page with Tab Navigation

**Files:**
- Modify: `frontend/src/pages/SettingsPage.tsx`

- [ ] **Step 1: Add tabbed navigation to settings**

Update the existing SettingsPage to act as a layout with tabs: Profile, Organization (Owner/Admin), The Treasury (Owner/Admin), Integrations (Owner/Admin). Use role checks from `permissions.ts` to conditionally show tabs.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/SettingsPage.tsx
git commit -m "feat: settings page with role-gated tab navigation"
```

---

### Task 20: Update App Routes

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Add new routes**

Add routes for the new pages:

```typescript
<Route path="/settings/treasury" element={<TreasuryPage />} />
<Route path="/settings/organization" element={<OrganizationSettingsPage />} />
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: add routes for Treasury and Organization settings pages"
```

---

### Task 21: Add Acorn Balance and Trial Banner to Layout

**Files:**
- Modify: whichever layout component wraps all authenticated pages (likely in `App.tsx` or a layout component)

- [ ] **Step 1: Add AcornBalance to the top navigation bar**

Import and render `<AcornBalance />` in the header/nav area next to the user menu.

- [ ] **Step 2: Add TrialBanner above the main content area**

Import and render `<TrialBanner />` at the top of the authenticated layout, above the page content.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/
git commit -m "feat: add acorn balance indicator and trial banner to app layout"
```

---

## Chunk 7: Backend Cleanup & Integration

### Task 22: Update All Backend References from username to email

**Files:**
- Modify: `backend/auth.py`, `backend/admin.py`, and any other files referencing `User.username`

- [ ] **Step 1: Search for all username references**

```bash
cd /home/tauhid/code/aibot2/backend && grep -rn "username" --include="*.py" | grep -v __pycache__ | grep -v alembic
```

- [ ] **Step 2: Update each reference**

Replace `user.username` with `user.email` or `user.full_name` as appropriate in admin.py stats/queries, any WebSocket identity, any logging, etc.

- [ ] **Step 3: Commit**

```bash
git add backend/
git commit -m "refactor: replace all username references with email across backend"
```

---

### Task 23: Add require_active_account to Execution Endpoints

**Files:**
- Modify: `backend/executions.py`

- [ ] **Step 1: Add the dependency to workflow execution routes**

Add `require_active_account` as a dependency on the execution creation endpoint and any other endpoints that trigger AI usage (component test, etc.):

```python
from auth import require_active_account

@router.post("/")
async def create_execution(
    ...,
    active_user: models.User = Depends(require_active_account),
):
```

- [ ] **Step 2: Commit**

```bash
git add backend/executions.py
git commit -m "feat: enforce active account status on execution endpoints"
```

---

### Task 24: Update Frontend References from username to email

**Files:**
- Modify: `frontend/src/pages/LoginPage.tsx`, `frontend/src/lib/api.ts`, and any other files referencing username

- [ ] **Step 1: Search for all username references in frontend**

```bash
cd /home/tauhid/code/aibot2/frontend && grep -rn "username" --include="*.ts" --include="*.tsx" src/ | grep -v node_modules
```

- [ ] **Step 2: Update each reference**

- LoginPage: change form field from username to email
- api.ts: update login function to send email instead of username
- AuthContext: update login call

- [ ] **Step 3: Commit**

```bash
git add frontend/src/
git commit -m "refactor: replace all username references with email across frontend"
```

---

### Task 25: End-to-End Smoke Test

- [ ] **Step 1: Run database migration**

```bash
cd /home/tauhid/code/aibot2/backend && python migrate.py
```

- [ ] **Step 2: Test registration flow**

```bash
curl -X POST http://localhost:9000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"Test1234","full_name":"Test User","company_name":"Test Corp"}'
```

Expected: 201 with user ID, org/account created.

- [ ] **Step 3: Test login flow**

```bash
curl -X POST http://localhost:9000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"Test1234"}'
```

Expected: 200 with access_token and refresh_token.

- [ ] **Step 4: Test /auth/me returns org and account data**

```bash
curl http://localhost:9000/auth/me -H "Authorization: Bearer <token>"
```

Expected: user object with `org` and `account` nested objects.

- [ ] **Step 5: Test acorn balance endpoint**

```bash
curl http://localhost:9000/api/billing/acorns -H "Authorization: Bearer <token>"
```

Expected: `{"balance": 250}` (trial acorns).

- [ ] **Step 6: Test frontend loads and displays correctly**

Open `http://localhost:3000`, register a new user, verify:
- Registration creates org + account
- Login works with email
- Acorn balance shows in nav
- Trial banner displays
- Treasury page loads with balance and empty transaction history

- [ ] **Step 7: Commit any fixes**

```bash
git add .
git commit -m "fix: end-to-end smoke test fixes"
```
