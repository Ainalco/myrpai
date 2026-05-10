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


if __name__ == "__main__":
    sys.exit(main())
