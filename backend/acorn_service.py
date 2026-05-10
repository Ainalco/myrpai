"""
Acorn (credit) service – atomic balance operations and helpers.
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import desc, func

import models
from system_config import get_config_float

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

def get_balance(account_id: int, db: Session) -> float:
    """Return the current acorn balance for an account."""
    account = db.query(models.Account).filter(models.Account.id == account_id).first()
    if account is None:
        raise ValueError(f"Account {account_id} not found")
    return float(account.acorn_balance)


def get_account_for_user(user: models.User, db: Session) -> Optional[models.Account]:
    """Return the Account linked to the user's organisation, or None."""
    if user.org_id is None:
        return None
    account = (
        db.query(models.Account)
        .filter(models.Account.org_id == user.org_id)
        .first()
    )
    return account


# ---------------------------------------------------------------------------
# Credit / Spend (atomic)
# ---------------------------------------------------------------------------

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
    """
    Credit acorns to an account.

    Uses SELECT … FOR UPDATE to ensure the balance update is atomic.
    Stores a **positive** amount in the transaction record.
    """
    if amount <= 0:
        raise ValueError("Credit amount must be positive")

    # Lock the account row for the duration of the transaction
    account = (
        db.query(models.Account)
        .filter(models.Account.id == account_id)
        .with_for_update()
        .first()
    )
    if account is None:
        raise ValueError(f"Account {account_id} not found")

    account.acorn_balance = float(account.acorn_balance) + amount
    new_balance = float(account.acorn_balance)

    txn = models.AcornTransaction(
        account_id=account_id,
        user_id=user_id,
        type=txn_type,
        amount=amount,
        balance_after=new_balance,
        description=description,
        paddle_transaction_id=paddle_transaction_id,
        metadata_json=metadata,
    )
    db.add(txn)
    db.flush()

    logger.info(
        "Credited %.2f acorns to account %d (type=%s, balance_after=%.2f)",
        amount, account_id, txn_type.value, new_balance,
    )
    return txn


def spend_acorns(
    account_id: int,
    user_id: int,
    amount: float,
    description: str,
    db: Session,
    metadata: Optional[dict] = None,
    allow_overdraft: bool = False,
) -> models.AcornTransaction:
    """
    Spend acorns from an account.

    Uses SELECT … FOR UPDATE to ensure the balance update is atomic.
    Stores a **negative** amount in the transaction record.

    If ``allow_overdraft`` is True, the balance can go negative (used when
    the cost is only known after execution, e.g. AI token usage).

    In 'locked' allocation mode, also deducts from the user's personal
    ``locked_acorn_balance`` so their budget cap decreases.

    Raises ValueError if the account (or user in locked mode) has
    insufficient balance.
    """
    if amount <= 0:
        raise ValueError("Spend amount must be positive")

    # Lock the account row for the duration of the transaction
    account = (
        db.query(models.Account)
        .filter(models.Account.id == account_id)
        .with_for_update()
        .first()
    )
    if account is None:
        raise ValueError(f"Account {account_id} not found")

    current_balance = float(account.acorn_balance)
    if current_balance < amount and not allow_overdraft:
        raise ValueError(
            f"Insufficient acorn balance: have {current_balance:.2f}, need {amount:.2f}"
        )

    # In locked mode, also deduct from the user's personal allocation
    if account.acorn_allocation_mode == "locked" and user_id:
        user = (
            db.query(models.User)
            .filter(models.User.id == user_id)
            .with_for_update()
            .first()
        )
        if user and user.locked_acorn_balance is not None:
            user_balance = float(user.locked_acorn_balance)
            if user_balance < amount and not allow_overdraft:
                raise ValueError(
                    f"Insufficient personal acorn allocation: have {user_balance:.2f}, need {amount:.2f}"
                )
            user.locked_acorn_balance = user_balance - amount
            logger.info(
                "Deducted %.2f from user %d locked balance (remaining=%.2f)",
                amount, user_id, user.locked_acorn_balance,
            )

    account.acorn_balance = current_balance - amount
    new_balance = float(account.acorn_balance)

    txn = models.AcornTransaction(
        account_id=account_id,
        user_id=user_id,
        type=models.AcornTransactionType.usage,
        amount=-amount,
        balance_after=new_balance,
        description=description,
        metadata_json=metadata,
    )
    db.add(txn)
    db.flush()

    logger.info(
        "Spent %.2f acorns from account %d (balance_after=%.2f)",
        amount, account_id, new_balance,
    )
    return txn


def refund_acorns(
    account_id: int,
    amount: float,
    description: str,
    db: Session,
    paddle_transaction_id: Optional[str] = None,
) -> models.AcornTransaction:
    """
    Deduct acorns from an account as a refund reversal.

    Unlike spend_acorns, this does NOT check for sufficient balance —
    refunds can bring the balance negative (the customer got their money back).
    """
    if amount <= 0:
        raise ValueError("Refund amount must be positive")

    account = (
        db.query(models.Account)
        .filter(models.Account.id == account_id)
        .with_for_update()
        .first()
    )
    if account is None:
        raise ValueError(f"Account {account_id} not found")

    account.acorn_balance = float(account.acorn_balance) - amount
    new_balance = float(account.acorn_balance)

    txn = models.AcornTransaction(
        account_id=account_id,
        type=models.AcornTransactionType.refund,
        amount=-amount,
        balance_after=new_balance,
        description=description,
        paddle_transaction_id=paddle_transaction_id,
    )
    db.add(txn)
    db.flush()

    logger.info(
        "Refunded %.2f acorns from account %d (balance_after=%.2f)",
        amount, account_id, new_balance,
    )
    return txn


# ---------------------------------------------------------------------------
# Execution guard
# ---------------------------------------------------------------------------

def check_can_execute(account_id: int, db: Session) -> bool:
    """
    Return True if the account's acorn balance is at or above the
    minimum reserve required to execute a workflow.

    The minimum is read from system_config key ``min_acorn_reserve``
    (defaults to 1.0 if not set).
    """
    balance = get_balance(account_id, db)
    min_reserve = get_config_float("min_acorn_reserve", db, default=1.0)
    return balance >= min_reserve


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


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------

def usd_to_acorns(usd_cost: float, db: Session) -> float:
    """
    Convert a USD cost to acorns using the ``acorn_cost_rate_usd`` system
    config value (i.e. how many USD one acorn is worth).

    Formula: acorns = usd_cost / rate
    """
    rate = get_config_float("acorn_cost_rate_usd", db, default=0.01)
    if rate <= 0:
        raise ValueError("acorn_cost_rate_usd must be positive")
    return usd_cost / rate


# ---------------------------------------------------------------------------
# Transaction history
# ---------------------------------------------------------------------------

def get_transactions(
    account_id: int,
    db: Session,
    limit: int = 20,
    offset: int = 0,
    user_id: Optional[int] = None,
) -> dict:
    """
    Return a paginated dict of acorn transactions for an account.

    If ``user_id`` is provided, only returns transactions for that user.

    Keys: transactions, total, limit, offset, has_more
    """
    query = (
        db.query(models.AcornTransaction)
        .filter(models.AcornTransaction.account_id == account_id)
    )
    if user_id is not None:
        query = query.filter(models.AcornTransaction.user_id == user_id)

    total = query.count()

    transactions = (
        query
        .order_by(desc(models.AcornTransaction.created_at))
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "transactions": transactions,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total,
    }
