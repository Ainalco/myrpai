# Preview Seed Users Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-create three known seed users on every preview environment boot so testers can log in without manual registration.

**Architecture:** Single Python script `backend/seed_preview.py`, invoked between `migrate.py` and `uvicorn` in the preview compose command. Gated by `DEPLOYMENT_MODE=preview` for safety. Idempotent — each run looks up existing rows by slug/email and skips, so the script is safe to run on every container start.

**Tech Stack:** Python 3, SQLAlchemy ORM (existing `models.py` + `database.py`), bcrypt password hashing via the existing `auth.get_password_hash` helper, PostgreSQL.

**Spec reference:** `docs/superpowers/specs/2026-04-20-preview-seed-users-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/seed_preview.py` (new) | Entry point. Gate check, DB session, org/account/user creation. Self-contained — only imports from `database`, `models`, `auth`, `system_config`. |
| `docker/docker-compose.preview.yml` (modified) | Backend service `command` runs `seed_preview.py` after `migrate.py`. |

No other files touched. No tests — the spec explicitly chose manual verification (script is small, preview-only, gated).

Note on scope: a clean split would put helpers in a separate module, but the full script is ~120 lines with 3 users. Keeping it single-file matches "one clear purpose" (seed the preview DB) and avoids importing a one-consumer helper module.

---

### Task 1: Create `seed_preview.py` skeleton with preview gate

**Files:**
- Create: `backend/seed_preview.py`

- [ ] **Step 1: Create the skeleton file**

Create `backend/seed_preview.py` with contents:

```python
#!/usr/bin/env python3
"""Seed the preview environment DB with known users.

Runs between ``migrate.py`` and ``uvicorn`` in ``docker-compose.preview.yml``.
Gated by ``DEPLOYMENT_MODE=preview`` so accidental runs in dev/prod no-op.
Idempotent: looks up orgs by slug and users by email, skipping any that exist.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="[seed_preview] %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    mode = os.getenv("DEPLOYMENT_MODE", "")
    if mode != "preview":
        logger.info("DEPLOYMENT_MODE=%r, skipping seed", mode)
        return 0

    # Imports are delayed so the gate check doesn't require DB connectivity.
    from database import SessionLocal
    import models
    from auth import get_password_hash
    from system_config import get_config_float, get_config_int

    db = SessionLocal()
    try:
        seed_all(db, models, get_password_hash, get_config_float, get_config_int)
        logger.info("Seed complete")
        return 0
    except Exception:
        logger.exception("Seed failed")
        db.rollback()
        return 1
    finally:
        db.close()


def seed_all(db, models, get_password_hash, get_config_float, get_config_int) -> None:
    # Implemented in Task 2 and Task 3.
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Verify the file imports cleanly and the gate skips**

Run from the repo root:

```bash
cd backend && DEPLOYMENT_MODE= python3 -c "import seed_preview; print(seed_preview.main())"
```

Expected output:

```
[seed_preview] INFO DEPLOYMENT_MODE='', skipping seed
0
```

If `NotImplementedError` appears, you accidentally ran with `DEPLOYMENT_MODE=preview`. Re-run without it.

- [ ] **Step 3: Commit**

```bash
git add backend/seed_preview.py
git commit -m "feat(preview): scaffold seed_preview.py with DEPLOYMENT_MODE gate"
```

---

### Task 2: Implement org + account + trial credit creation

**Files:**
- Modify: `backend/seed_preview.py` (replace the `seed_all` stub, add helpers)

- [ ] **Step 1: Add org/account/transaction helpers**

In `backend/seed_preview.py`, replace the `seed_all` function (and its stub) with:

```python
def get_or_create_org(db, models, *, slug: str, name: str, domain: str):
    """Return the org with the given slug, creating it if missing."""
    org = db.query(models.Organization).filter(models.Organization.slug == slug).first()
    if org:
        logger.info("Org %s already exists (id=%s)", slug, org.id)
        return org

    org = models.Organization(name=name, slug=slug, domain=domain)
    db.add(org)
    db.flush()
    logger.info("Created org %s (id=%s)", slug, org.id)
    return org


def get_or_create_account_with_trial(db, models, org, *, trial_acorns: float, trial_days: int):
    """Return the account for this org, creating it + the initial trial credit if missing."""
    account = db.query(models.Account).filter(models.Account.org_id == org.id).first()
    if account:
        logger.info("Account for org %s already exists (id=%s)", org.slug, account.id)
        return account

    account = models.Account(
        org_id=org.id,
        plan_tier=models.PlanTier.trialing,
        status=models.AccountStatus.trialing,
        acorn_balance=trial_acorns,
        trial_ends_at=datetime.utcnow() + timedelta(days=trial_days),
    )
    db.add(account)
    db.flush()
    logger.info("Created account for org %s (id=%s)", org.slug, account.id)

    if trial_acorns > 0:
        txn = models.AcornTransaction(
            account_id=account.id,
            type=models.AcornTransactionType.trial_credit,
            amount=trial_acorns,
            balance_after=trial_acorns,
            description="Trial acorns (seed)",
        )
        db.add(txn)
        db.flush()
        logger.info("Created trial_credit transaction for account %s", account.id)

    return account


def seed_all(db, models, get_password_hash, get_config_float, get_config_int) -> None:
    trial_acorns = get_config_float("trial_acorns", db, default=100.0)
    trial_days = get_config_int("trial_duration_days", db, default=14)

    # Admin org — sandbox so the superadmin can also exercise regular-user flows.
    admin_org = get_or_create_org(
        db, models,
        slug="scurry-preview-admin",
        name="Scurry Preview (Admin)",
        domain="scurry.ai",
    )
    get_or_create_account_with_trial(
        db, models, admin_org, trial_acorns=trial_acorns, trial_days=trial_days,
    )

    # Shared org — contains org owner and regular member.
    shared_org = get_or_create_org(
        db, models,
        slug="scurry-preview",
        name="Scurry Preview",
        domain="scurry.ai",
    )
    get_or_create_account_with_trial(
        db, models, shared_org, trial_acorns=trial_acorns, trial_days=trial_days,
    )

    # Users are added in Task 3.
    db.commit()
```

- [ ] **Step 2: Verify the file still imports cleanly**

```bash
cd backend && DEPLOYMENT_MODE= python3 -c "import seed_preview; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/seed_preview.py
git commit -m "feat(preview): add idempotent org+account+trial-credit helpers"
```

---

### Task 3: Implement user creation and wire the three seed users

**Files:**
- Modify: `backend/seed_preview.py` (add user helper, extend `seed_all`)

- [ ] **Step 1: Add the user helper and expand `seed_all`**

In `backend/seed_preview.py`, add this function below `get_or_create_account_with_trial`:

```python
def get_or_create_user(
    db, models, get_password_hash,
    *,
    email: str,
    password: str,
    full_name: str,
    org_id: int,
    role,
    is_superadmin: bool = False,
):
    """Return the user with this email, creating it if missing."""
    user = db.query(models.User).filter(models.User.email == email).first()
    if user:
        logger.info("User %s already exists (id=%s)", email, user.id)
        return user

    user = models.User(
        email=email,
        hashed_password=get_password_hash(password),
        full_name=full_name,
        is_active=True,
        is_superadmin=is_superadmin,
        org_id=org_id,
        role=role,
    )
    db.add(user)
    db.flush()
    logger.info("Created user %s (id=%s)", email, user.id)
    return user
```

Then replace the `seed_all` function in its entirety with:

```python
def seed_all(db, models, get_password_hash, get_config_float, get_config_int) -> None:
    trial_acorns = get_config_float("trial_acorns", db, default=100.0)
    trial_days = get_config_int("trial_duration_days", db, default=14)

    admin_org = get_or_create_org(
        db, models,
        slug="scurry-preview-admin",
        name="Scurry Preview (Admin)",
        domain="scurry.ai",
    )
    get_or_create_account_with_trial(
        db, models, admin_org, trial_acorns=trial_acorns, trial_days=trial_days,
    )
    get_or_create_user(
        db, models, get_password_hash,
        email="admin@scurry.ai",
        password="12345678",
        full_name="Scurry Admin",
        org_id=admin_org.id,
        role=models.UserRole.owner,
        is_superadmin=True,
    )

    shared_org = get_or_create_org(
        db, models,
        slug="scurry-preview",
        name="Scurry Preview",
        domain="scurry.ai",
    )
    get_or_create_account_with_trial(
        db, models, shared_org, trial_acorns=trial_acorns, trial_days=trial_days,
    )
    get_or_create_user(
        db, models, get_password_hash,
        email="org@scurry.ai",
        password="12345678",
        full_name="Scurry Org Owner",
        org_id=shared_org.id,
        role=models.UserRole.owner,
        is_superadmin=False,
    )
    get_or_create_user(
        db, models, get_password_hash,
        email="user@scurry.ai",
        password="12345678",
        full_name="Scurry User",
        org_id=shared_org.id,
        role=models.UserRole.member,
        is_superadmin=False,
    )

    db.commit()
```

- [ ] **Step 2: Verify the file still imports cleanly**

```bash
cd backend && DEPLOYMENT_MODE= python3 -c "import seed_preview; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/seed_preview.py
git commit -m "feat(preview): create three seed users across two orgs"
```

---

### Task 4: Wire seed_preview.py into the preview compose command

**Files:**
- Modify: `docker/docker-compose.preview.yml` (backend service `command`)

- [ ] **Step 1: Update the backend command**

Open `docker/docker-compose.preview.yml` and find the backend service's `command` line:

```yaml
    command: sh -c "python migrate.py && uvicorn main:socket_app --host 0.0.0.0 --port 9000"
```

Replace it with:

```yaml
    command: sh -c "python migrate.py && python seed_preview.py && uvicorn main:socket_app --host 0.0.0.0 --port 9000"
```

No other changes in this file. Leave `docker-compose.yml` and `docker-compose.prod.yml` alone.

- [ ] **Step 2: Verify the compose file is still valid YAML**

```bash
docker compose -f docker/docker-compose.preview.yml config > /dev/null && echo "compose valid"
```

Expected: `compose valid`

If this command isn't available locally, skip and rely on the preview deploy to validate.

- [ ] **Step 3: Commit**

```bash
git add docker/docker-compose.preview.yml
git commit -m "feat(preview): run seed_preview.py on backend start"
```

---

### Task 5: End-to-end verification on a preview environment

No code changes in this task — just the manual verification steps from the spec. This is what proves the feature works.

- [ ] **Step 1: Open a draft PR against `develop` to trigger a preview deploy**

Push the `feat/preview-seed-users` branch and open a PR. Wait for the preview-deploy workflow to post the "Preview Environment Ready" comment with a Tailscale IP.

- [ ] **Step 2: Inspect backend logs for seed output**

```bash
ssh ubuntu@<tailscale-ip> "cd ~/app && docker compose -f docker/docker-compose.preview.yml logs backend | grep seed_preview"
```

Expected: nine "Created" lines (2 orgs, 2 accounts, 2 trial_credit transactions, 3 users = 9) and a final "Seed complete".

- [ ] **Step 3: Log in as each seed user via the frontend**

Visit `http://<tailscale-ip>:3000` and log in with each of:
- `admin@scurry.ai` / `12345678` — confirm superadmin UI is visible
- `org@scurry.ai` / `12345678` — confirm normal user UI works; confirm the org is "Scurry Preview"
- `user@scurry.ai` / `12345678` — confirm normal user UI works; confirm same org as `org@scurry.ai`

- [ ] **Step 4: Verify idempotency by restarting the backend container**

```bash
ssh ubuntu@<tailscale-ip> "cd ~/app && docker compose -f docker/docker-compose.preview.yml restart backend"
sleep 15
ssh ubuntu@<tailscale-ip> "cd ~/app && docker compose -f docker/docker-compose.preview.yml logs --tail=50 backend | grep seed_preview"
```

Expected: "already exists" lines for all orgs/accounts/users; no duplicate rows. Log in again to confirm nothing broke.

- [ ] **Step 5: Verify the safety gate by running locally without `DEPLOYMENT_MODE=preview`**

From your local dev environment:

```bash
cd backend && DEPLOYMENT_MODE= python3 seed_preview.py
```

Expected: one line — `[seed_preview] INFO DEPLOYMENT_MODE='', skipping seed` — exit 0. No DB writes.

Also verify with an explicit non-preview mode:

```bash
cd backend && DEPLOYMENT_MODE=development python3 seed_preview.py
```

Expected: `[seed_preview] INFO DEPLOYMENT_MODE='development', skipping seed` — exit 0.

- [ ] **Step 6: If all verifications pass, mark the PR ready for review**

No additional commit in this task.
