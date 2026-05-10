# User System, Billing & Admin Architecture — Phase 1 Design Spec

**Date:** 2026-03-10
**Scope:** Phase 1 (MVP/Beta) — Single-user orgs, Paddle billing, Acorn credits, feature gating, settings UI
**Out of scope:** Setup Squirrel onboarding wizard (separate dev), Phase 2 multi-seat, Phase 3 enterprise

---

## 1. Database Schema Changes

### New Tables

**`organizations`**
| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | Auto-increment |
| name | String(255) | Company name from signup Step 2 |
| slug | String(255) | URL-safe, unique, derived from name |
| domain | String(255) | Nullable, extracted from owner email |
| logo_url | String(500) | Nullable |
| settings | JSON | Stores team_size, current_crm, meeting_tool, and other onboarding data |
| created_at | DateTime | Default now |

**`accounts`**
| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | Auto-increment |
| org_id | Integer FK → organizations | Unique (1:1) |
| paddle_customer_id | String(255) | Nullable, set when Paddle subscription created |
| paddle_subscription_id | String(255) | Nullable |
| plan_tier | Enum | trialing / sapling / oak / redwood / ancient_forest |
| billing_cycle | Enum | monthly / annual, nullable for trial |
| acorn_balance | Float | Default 0. Single source of truth for balance |
| status | Enum | trialing / active / past_due / suspended / cancelled |
| trial_ends_at | DateTime | Nullable, set on signup |
| current_period_ends_at | DateTime | Nullable, set by Paddle webhook |
| created_at | DateTime | Default now |

**`acorn_transactions`**
| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | Auto-increment |
| account_id | Integer FK → accounts | |
| user_id | Integer FK → users | Nullable (system credits have no user) |
| type | Enum | trial_credit / subscription_credit / purchase / usage / adjustment / refund |
| amount | Float | Positive for credits, negative for debits |
| balance_after | Float | Snapshot of balance after this transaction |
| description | String(500) | Human-readable description |
| paddle_transaction_id | String(255) | Nullable, links to Paddle transaction |
| metadata | JSON | Nullable, extra context (execution_id, component_id, etc.) |
| created_at | DateTime | Default now |

**`system_config`**
| Column | Type | Notes |
|--------|------|-------|
| key | String(100) PK | Unique config key |
| value | Text | String value, parsed by application |
| description | String(500) | Human-readable description |
| updated_at | DateTime | Last modified |

Initial config values:
- `acorn_cost_rate_usd` = "0.01"
- `trial_acorns` = "250" (TBD, adjustable)
- `trial_duration_days` = "14"
- `min_acorn_reserve` = "1"
- `plan_acorns_sapling` = "500" (TBD)
- `plan_acorns_oak` = "1750" (TBD)
- `plan_acorns_redwood` = "4000" (TBD)
- `payment_grace_days` = "7"
- `suspension_days` = "90"
- `data_export_days` = "30"

### Modified Tables

**`users`** — add columns:
- `org_id` Integer FK → organizations (NOT NULL after migration)
- `role` Enum: owner / admin / member (default: owner)
- `locked_acorn_balance` Float nullable (Phase 2, add column now)
- `is_superadmin` Boolean default False (replaces `is_admin` — platform-level flag)

**`users`** — drop columns:
- `username` (switch to email-based auth)
- `is_admin` (replaced by `is_superadmin`)

### Migration Strategy

1. Create new tables (organizations, accounts, acorn_transactions, system_config)
2. Add new columns to users (org_id nullable initially, role, is_superadmin, locked_acorn_balance)
3. Data migration: for each existing user, create an Organization (name from email domain or "User's Org") and Account (status=active, plan_tier=trialing). Set user.org_id and user.role='owner'. Copy is_admin to is_superadmin.
4. Make org_id NOT NULL
5. Drop username column, drop is_admin column
6. Seed system_config with default values

---

## 2. Auth & Permission System

### JWT Changes

**Access token (24hr):**
```json
{ "sub": "<user_id>", "org_id": "<org_id>", "role": "owner", "type": "access", "exp": "..." }
```

**Refresh token (7 days):**
```json
{ "sub": "<user_id>", "type": "refresh", "exp": "..." }
```

Refresh token rotation: each use issues a new refresh token, invalidates the old one.

### Login

- Switch from username-based to email-based login
- Return both access_token and refresh_token
- Add `POST /auth/refresh` endpoint

### Registration

Backend `POST /auth/register` accepts:
```json
{
  "email": "string",
  "password": "string",
  "full_name": "string",
  "company_name": "string",
  "team_size": "string (optional)",
  "current_crm": "string (optional)",
  "meeting_tool": "string (optional)"
}
```

Creates: Organization → Account (trialing, trial_ends_at=now+14d, acorn_balance=trial_acorns from config) → User (role=owner). Inserts trial_credit acorn_transaction.

### Permission Middleware

FastAPI dependency:
```python
def require_role(*roles: str):
    # Extracts user from JWT, checks user.role in roles
    # Returns 403 if insufficient
    # Also injects org_id for DB query scoping

def require_active_account():
    # Checks account.status in ('trialing', 'active')
    # Returns 403 with descriptive message for other states
```

All data-access queries scoped by org_id from JWT.

### Permission Matrix (Phase 1 — Owner only, but enforced for future)

| Permission | Owner | Admin | Member |
|-----------|-------|-------|--------|
| Billing & subscription | Yes | Yes | No |
| Purchase Acorns | Yes | Yes | No |
| View invoices | Yes | Yes | No |
| Configure integrations | Yes | Yes | No |
| Create/edit workflows | Yes | Yes | Yes |
| Generate sequences (uses Acorns) | Yes | Yes | Yes |
| Email queue | Yes | Yes | Yes |
| View own Acorn usage | Yes | Yes | Yes |
| Manage own profile | Yes | Yes | Yes |
| Transfer ownership | Yes | No | No |
| Delete organization | Yes | No | No |

---

## 3. Paddle Integration (In-Repo)

### New Backend Files

**`backend/paddle_service.py`** — Paddle API client:
- Initialize Paddle SDK with API key and environment (sandbox/production)
- Create checkout sessions for subscription and top-up purchases
- Fetch subscription details, cancel subscription
- Verify webhook signatures

**`backend/paddle_webhooks.py`** — Webhook endpoint and handlers:

| Event | Handler |
|-------|---------|
| `subscription.created` | Set account status=active, store paddle IDs, credit plan acorns |
| `subscription.activated` | Update status to active |
| `subscription.updated` | Handle plan changes (upgrade immediate, downgrade at period end) |
| `subscription.payment_succeeded` | Credit monthly acorn allotment |
| `subscription.payment_failed` | Set status=past_due |
| `subscription.cancelled` | Set status=cancelled at period end |
| `subscription.past_due` | Set status=past_due |
| `transaction.completed` | Credit acorns (subscription renewal or one-time top-up) |
| `adjustment.created` | Handle refunds — deduct credited acorns |

Webhook endpoint: `POST /api/paddle/webhook` — verifies Paddle signature, routes to handler.

Idempotency: store `paddle_transaction_id` in `acorn_transactions`, skip if already processed.

### Environment Variables

```
PADDLE_API_KEY=...
PADDLE_ENVIRONMENT=sandbox|production
PADDLE_WEBHOOK_SECRET=...
PADDLE_CLIENT_TOKEN=...  # For frontend checkout
PADDLE_PRICE_SAPLING_MONTHLY=pri_xxx
PADDLE_PRICE_SAPLING_ANNUAL=pri_xxx
PADDLE_PRICE_OAK_MONTHLY=pri_xxx
PADDLE_PRICE_OAK_ANNUAL=pri_xxx
PADDLE_PRICE_REDWOOD_MONTHLY=pri_xxx
PADDLE_PRICE_REDWOOD_ANNUAL=pri_xxx
PADDLE_PRICE_ACORNS_500=pri_xxx
PADDLE_PRICE_ACORNS_1750=pri_xxx
PADDLE_PRICE_ACORNS_4000=pri_xxx
```

---

## 4. Acorn Credit System

### New File: `backend/acorn_service.py`

Core functions (all direct DB operations, no HTTP):

```python
async def get_balance(account_id: int) -> float
async def credit_acorns(account_id: int, amount: float, type: str, description: str, ...) -> AcornTransaction
async def spend_acorns(account_id: int, user_id: int, amount: float, description: str, ...) -> AcornTransaction
async def check_can_execute(account_id: int) -> bool  # balance >= min_acorn_reserve
async def get_transactions(account_id: int, limit=20, offset=0) -> list[AcornTransaction]
async def refund_acorns(account_id: int, original_transaction_id: int, amount: float) -> AcornTransaction
```

All balance mutations are atomic: update `accounts.acorn_balance` and insert `acorn_transactions` in a single DB transaction.

### Execution Engine Integration

Changes to `backend/executions.py`:

1. **Pre-execution:** `check_can_execute()` — reject with 402 if balance < min_acorn_reserve
2. **Execute:** Run workflow as today. AiUsageLog tracks token counts.
3. **Post-execution:** Calculate total USD cost from execution's AI usage → convert to acorns via `acorn_cost_rate_usd` config → call `spend_acorns()`
4. **Failure:** Only debit for tokens actually consumed. If spend call fails, log for manual reconciliation.

### Cost Conversion

```python
acorn_cost = usd_cost / float(get_config("acorn_cost_rate_usd"))
# e.g., $0.075 API cost / $0.01 per acorn = 7.5 acorns debited
```

Never round before storing. Store exact decimal. Round only for display.

---

## 5. Account Lifecycle

### States and Access Rules

| State | Login | Execute | View Data | Export |
|-------|-------|---------|-----------|--------|
| trialing | Yes | Yes | Yes | Yes |
| active | Yes | Yes | Yes | Yes |
| past_due | Yes | No | Read-only | Yes |
| suspended | Yes | No | No | Yes |
| cancelled | Yes | No | No | 30-day window |

### Trial Expiry

Local check: if `status == 'trialing'` and `trial_ends_at < now()`, treat as expired. Block execution, show upgrade prompt.

### Enforcement

`require_active_account()` dependency on all workflow/execution/generation endpoints.

---

## 6. Feature Gating

### Plan Feature Matrix (in code)

```python
PLAN_FEATURES = {
    "trialing":       {"max_emails_per_sequence": 3, "ai_filter": False, "ai_send_timing": False, "api_access": False},
    "sapling":        {"max_emails_per_sequence": 3, "ai_filter": False, "ai_send_timing": False, "api_access": False},
    "oak":            {"max_emails_per_sequence": 7, "ai_filter": True,  "ai_send_timing": True,  "api_access": False},
    "redwood":        {"max_emails_per_sequence": 15, "ai_filter": True, "ai_send_timing": True,  "api_access": True},
    "ancient_forest": {"max_emails_per_sequence": None, "ai_filter": True, "ai_send_timing": True, "api_access": True},
}
```

### Backend Enforcement

`check_feature_access(account, feature)` called before gated operations.

### Frontend Pattern

- Don't render gated features at all (no grayed-out UI)
- Inline upgrade CTAs when limits are hit: "Need more emails? Upgrade to Oak →"
- `canAccess(feature)` helper reads plan_tier from AuthContext

---

## 7. Frontend Changes

### AuthContext Expansion

```typescript
interface AuthState {
  user: { id, email, name, role, avatar_url }
  org: { id, name, slug, plan_tier, status }
  acorns: { balance }
  login(), logout(), refreshAcorns()
}
```

### Registration Page Changes

- Send existing Step 2 fields (company_name, team_size, current_crm, meeting_tool) to backend
- Drop username — derive from email or remove entirely
- Backend creates Org + Account + User on registration

### New Settings Pages

| Page | Access | Content |
|------|--------|---------|
| Profile | All | Existing + minor cleanup |
| Organization | Owner/Admin | Company name, logo, domain, internal domains |
| The Treasury | Owner/Admin | Plan display, upgrade/downgrade (Paddle checkout), acorn balance, buy more acorns, transaction history |
| Integrations | Owner/Admin | Existing, add role gate |

### Acorn Balance Display

Persistent indicator in top nav. Warning color when low. Clicks to Treasury.

### Trial Banner

Non-dismissible banner when trialing: "X days remaining. [Choose a plan →]"
Urgent banner for past_due/suspended states.

### Paddle Checkout Integration

Frontend loads Paddle.js, opens checkout overlay for:
- Subscription selection (plan + billing cycle)
- Acorn top-up packs

Passes `org_id` / `account_id` as custom data so webhooks can link back.

---

## 8. Security

- JWT: 24hr access + 7-day refresh with rotation. Claims include org_id and role.
- All DB queries scoped by org_id. No cross-org data leaks.
- Paddle webhooks verified via signature.
- Acorn balance mutations atomic (single DB transaction).
- Rate limiting: login 5/15min per email, API 100/min per user.
- Sensitive fields encrypted at rest (existing encryption_service.py).
