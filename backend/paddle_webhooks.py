"""
Paddle webhook handlers and billing API endpoints.

Ported from the PHP Paddle microservice. Handles incoming Paddle webhook events
(subscription lifecycle, transactions, refunds) and exposes billing-related
endpoints for the frontend.
"""

from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func
from database import get_db, SessionLocal
import models
import acorn_service
import paddle_service
from auth import get_current_active_user
import logging
import json
import httpx
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

router = APIRouter()

# Valid paid plans that can be upgraded to via the API
VALID_UPGRADE_PLANS = {"oak", "redwood"}


# ---------------------------------------------------------------------------
# Role helpers
# ---------------------------------------------------------------------------

def _require_owner_or_admin(current_user: models.User = Depends(get_current_active_user)) -> models.User:
    """Dependency that ensures the user is an owner or admin."""
    if current_user.role not in (models.UserRole.owner, models.UserRole.admin):
        raise HTTPException(status_code=403, detail="Owner or admin access required")
    return current_user


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_int(value, default: int = 0) -> int:
    """Safely convert a value to int, returning default on failure."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _extract_user_id(data: dict) -> int:
    """Extract user_id from Paddle custom_data, returning 0 on failure."""
    custom_data = data.get("custom_data") or {}
    return _safe_int(custom_data.get("user_id"), 0)


def _get_account_for_user_id(user_id: int, db: Session) -> Optional[models.Account]:
    """Get account for a user by user ID."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user or not user.org_id:
        return None
    return db.query(models.Account).filter(models.Account.org_id == user.org_id).first()


def _get_price_id_from_items(data: dict) -> Optional[str]:
    """Extract the first price ID from subscription/transaction items."""
    items = data.get("items", [])
    if items and isinstance(items, list):
        price = items[0].get("price", {})
        return price.get("id") if isinstance(price, dict) else None
    return None


def _check_paddle_txn_idempotency(account_id: int, paddle_transaction_id: str, db: Session) -> bool:
    """Return True if this paddle_transaction_id has already been credited for this account."""
    if not paddle_transaction_id:
        return False
    existing = db.query(models.AcornTransaction).filter(
        models.AcornTransaction.account_id == account_id,
        models.AcornTransaction.paddle_transaction_id == paddle_transaction_id,
        models.AcornTransaction.amount > 0,
    ).first()
    return existing is not None


# ---------------------------------------------------------------------------
# Webhook event handlers
# ---------------------------------------------------------------------------

def _handle_subscription_created(data: dict, db: Session) -> None:
    """
    Handle subscription.created event.

    Uses custom_data.user_id to find the user. Sets Paddle IDs, plan tier,
    billing cycle, and subscription status. Credits trial acorns if trialing
    (once per lifetime).
    """
    user_id = _extract_user_id(data)
    if user_id <= 0:
        logger.error("subscription.created: missing or invalid custom_data.user_id")
        return

    account = _get_account_for_user_id(user_id, db)
    if not account:
        logger.error("subscription.created: no account for user_id=%d", user_id)
        return

    status = data.get("status", "none")
    price_id = _get_price_id_from_items(data)
    plan_info = paddle_service.get_plan_from_price_id(price_id) if price_id else None

    # Store Paddle IDs
    account.paddle_customer_id = data.get("customer_id")
    account.paddle_subscription_id = data.get("id")

    # Set plan and cycle
    if plan_info:
        account.plan_tier = models.PlanTier(plan_info["plan"])
        account.billing_cycle = plan_info["cycle"]

    # Set subscription status
    if status == "trialing":
        account.status = models.AccountStatus.trialing
        # Only credit trial acorns once per lifetime
        existing_trial_credit = db.query(models.AcornTransaction).filter(
            models.AcornTransaction.account_id == account.id,
            models.AcornTransaction.type == models.AcornTransactionType.trial_credit,
        ).first()
        if not existing_trial_credit:
            acorn_service.credit_acorns(
                account_id=account.id,
                amount=100,
                txn_type=models.AcornTransactionType.trial_credit,
                description="Trial started",
                db=db,
            )
        else:
            logger.info("subscription.created: skipping trial credit for user_id=%d (already received)", user_id)
    elif status == "active":
        account.status = models.AccountStatus.active

    db.flush()
    logger.info("subscription.created: user_id=%d, plan=%s, status=%s", user_id, plan_info, status)


def _handle_subscription_activated(data: dict, db: Session) -> None:
    """Handle subscription.activated — set status to active."""
    user_id = _extract_user_id(data)
    if user_id <= 0:
        return
    account = _get_account_for_user_id(user_id, db)
    if account:
        account.status = models.AccountStatus.active
        db.flush()
        logger.info("subscription.activated: user_id=%d", user_id)


def _handle_subscription_canceled(data: dict, db: Session) -> None:
    """
    Handle subscription.canceled.

    Paddle cancellation is scheduled — the user keeps their paid plan until
    current_period_ends_at. We record the end date and mark status as
    cancelled. The actual downgrade to seedling happens when the period
    expires (checked in require_active_account).
    """
    user_id = _extract_user_id(data)
    if user_id <= 0:
        return
    account = _get_account_for_user_id(user_id, db)
    if not account:
        return

    # Record when the paid period actually ends
    # Paddle may put this in scheduled_change.effective_at or current_billing_period.ends_at
    ends_at = (
        (data.get("scheduled_change") or {}).get("effective_at")
        or (data.get("current_billing_period") or {}).get("ends_at")
    )
    if ends_at:
        try:
            account.current_period_ends_at = datetime.fromisoformat(ends_at.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            pass
    logger.info("subscription.canceled: ends_at=%s, scheduled_change=%s, current_billing_period=%s",
                ends_at, data.get("scheduled_change"), data.get("current_billing_period"))

    # Mark as cancelled — they keep the paid plan until period ends
    account.status = models.AccountStatus.cancelled
    account.paddle_subscription_id = None
    db.flush()
    logger.info("subscription.canceled: user_id=%d, access until=%s", user_id, ends_at)


def _handle_subscription_past_due(data: dict, db: Session) -> None:
    """Handle subscription.past_due — set status to past_due."""
    user_id = _extract_user_id(data)
    if user_id <= 0:
        return
    account = _get_account_for_user_id(user_id, db)
    if account:
        account.status = models.AccountStatus.past_due
        db.flush()
        logger.info("subscription.past_due: user_id=%d", user_id)


def _handle_subscription_updated(data: dict, db: Session) -> None:
    """Handle subscription.updated — update plan/cycle if changed."""
    user_id = _extract_user_id(data)
    if user_id <= 0:
        return
    account = _get_account_for_user_id(user_id, db)
    if not account:
        return

    price_id = _get_price_id_from_items(data)
    plan_info = paddle_service.get_plan_from_price_id(price_id) if price_id else None
    status = data.get("status")

    if plan_info:
        account.plan_tier = models.PlanTier(plan_info["plan"])
        account.billing_cycle = plan_info["cycle"]

    # Map Paddle status to our enum safely
    if status:
        PADDLE_STATUS_MAP = {
            "active": models.AccountStatus.active,
            "trialing": models.AccountStatus.trialing,
            "past_due": models.AccountStatus.past_due,
            "paused": models.AccountStatus.suspended,
            "canceled": models.AccountStatus.cancelled,  # Paddle uses American spelling
            "cancelled": models.AccountStatus.cancelled,
        }
        mapped = PADDLE_STATUS_MAP.get(status)
        if mapped:
            account.status = mapped
        else:
            logger.warning("subscription.updated: unknown status '%s' for user_id=%d", status, user_id)

    db.flush()
    logger.info("subscription.updated: user_id=%d, plan=%s", user_id, plan_info)


def _handle_transaction_completed(data: dict, db: Session) -> None:
    """
    Handle transaction.completed event.

    Credits acorns for top-up purchases or subscription renewals.
    Double-checks paddle_transaction_id to prevent duplicate credits
    even if the webhook event-level idempotency is bypassed.
    """
    user_id = _extract_user_id(data)
    if user_id <= 0:
        return

    account = _get_account_for_user_id(user_id, db)
    if not account:
        logger.error("transaction.completed: no account for user_id=%d", user_id)
        return

    txn_id = data.get("id")
    items = data.get("items") or []
    if not isinstance(items, list):
        items = []

    # Transaction-level idempotency check (FIX #4)
    if txn_id and _check_paddle_txn_idempotency(account.id, txn_id, db):
        logger.info("transaction.completed: already credited txn=%s, skipping", txn_id)
        return

    for item in items:
        price_id = (item.get("price") or {}).get("id")
        qty = _safe_int(item.get("quantity", 1), 1)
        if not price_id or qty < 1:
            continue

        # Top-up purchase
        if paddle_service.is_topup_price_id(price_id):
            acorns = paddle_service.get_topup_acorns(price_id) * qty
            if acorns > 0:
                acorn_service.credit_acorns(
                    account_id=account.id,
                    amount=acorns,
                    txn_type=models.AcornTransactionType.purchase,
                    description=f"Top-up: {acorns} acorns",
                    db=db,
                    paddle_transaction_id=txn_id,
                )
            continue

        # Subscription payment
        plan_info = paddle_service.get_plan_from_price_id(price_id)
        if plan_info:
            plan_name = plan_info["plan"]
            acorns = paddle_service.plan_acorns(plan_name) * qty
            if acorns > 0:
                acorn_service.credit_acorns(
                    account_id=account.id,
                    amount=acorns,
                    txn_type=models.AcornTransactionType.subscription_credit,
                    description=f"Subscription: {plan_name} plan",
                    db=db,
                    paddle_transaction_id=txn_id,
                )

                # In locked allocation mode, reset each user's balance to their allocation
                if account.acorn_allocation_mode == "locked":
                    org_members = db.query(models.User).filter(
                        models.User.org_id == account.org_id,
                        models.User.is_active == True,
                        models.User.locked_acorn_allocation.isnot(None),
                    ).all()
                    for member in org_members:
                        member.locked_acorn_balance = member.locked_acorn_allocation
                    logger.info(
                        "Billing cycle renewed: reset %d user allocations for org_id=%d",
                        len(org_members), account.org_id,
                    )

    db.flush()
    logger.info("transaction.completed: user_id=%d, txn=%s", user_id, txn_id)


def _handle_transaction_refunded(data: dict, db: Session) -> None:
    """
    Handle transaction.refunded event.

    Finds previously credited acorns for this transaction and reverses them.
    """
    user_id = _extract_user_id(data)
    if user_id <= 0:
        return

    account = _get_account_for_user_id(user_id, db)
    if not account:
        return

    txn_id = data.get("id")

    # Find how much was credited for this transaction
    credited = db.query(sa_func.sum(models.AcornTransaction.amount)).filter(
        models.AcornTransaction.paddle_transaction_id == txn_id,
        models.AcornTransaction.account_id == account.id,
        models.AcornTransaction.amount > 0,
    ).scalar() or 0

    if credited > 0:
        # Cap refund at current balance to avoid going negative (FIX #11)
        refund_amount = min(credited, float(account.acorn_balance))
        if refund_amount > 0:
            acorn_service.refund_acorns(
                account_id=account.id,
                amount=refund_amount,
                description=f"Refund for transaction {txn_id}",
                db=db,
                paddle_transaction_id=txn_id,
            )
        db.flush()
        logger.info("transaction.refunded: user_id=%d, amount=%d", user_id, refund_amount)


# ---------------------------------------------------------------------------
# Event handler dispatch
# ---------------------------------------------------------------------------

EVENT_HANDLERS = {
    "subscription.created": _handle_subscription_created,
    "subscription.activated": _handle_subscription_activated,
    "subscription.canceled": _handle_subscription_canceled,
    "subscription.past_due": _handle_subscription_past_due,
    "subscription.updated": _handle_subscription_updated,
    "transaction.completed": _handle_transaction_completed,
    "transaction.refunded": _handle_transaction_refunded,
}


# ---------------------------------------------------------------------------
# Webhook endpoint
# ---------------------------------------------------------------------------

@router.post("/paddle/webhook")
async def paddle_webhook(request: Request):
    """
    Receive and process Paddle webhook events.

    Verifies signature, checks idempotency via paddle_webhook_events table,
    then routes to the appropriate handler.
    """
    raw_body = await request.body()

    # Verify webhook signature
    signature = request.headers.get("paddle-signature", "")
    if not paddle_service.verify_webhook_signature(raw_body, signature):
        logger.warning("Paddle webhook: invalid signature")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # Parse payload
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_id = payload.get("event_id")
    event_type = payload.get("event_type")
    data = payload.get("data")

    if not event_id or not event_type or not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Bad payload structure")

    logger.info("Paddle webhook received: event_id=%s, event_type=%s", event_id, event_type)

    db = SessionLocal()
    try:
        db.begin()

        # Idempotency check
        existing = db.query(models.PaddleWebhookEvent).filter(
            models.PaddleWebhookEvent.event_id == event_id
        ).first()
        if existing:
            db.rollback()
            logger.info("Paddle webhook already processed: event_id=%s", event_id)
            return {"ok": True, "skipped": True}

        # Log the event for idempotency
        webhook_event = models.PaddleWebhookEvent(
            event_id=event_id,
            event_type=event_type,
            raw_payload=raw_body.decode("utf-8", errors="replace"),
        )
        db.add(webhook_event)
        db.flush()

        # Dispatch to handler
        handler = EVENT_HANDLERS.get(event_type)
        if handler:
            handler(data, db)
        else:
            logger.info("Paddle webhook: unhandled event_type=%s", event_type)

        db.commit()
        return {"ok": True, "event_id": event_id}

    except Exception as e:
        db.rollback()
        logger.exception("Paddle webhook error: event_id=%s, error=%s", event_id, str(e))
        raise HTTPException(status_code=500, detail="Server error")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Billing API endpoints (for frontend)
# ---------------------------------------------------------------------------

@router.get("/billing/prices")
async def get_billing_prices(
    _current_user: models.User = Depends(get_current_active_user),
):
    """Return Paddle price configuration for the frontend. Requires auth (FIX #5)."""
    return paddle_service.get_price_ids()


@router.get("/billing/status")
async def get_billing_status(
    current_user: models.User = Depends(_require_owner_or_admin),
    db: Session = Depends(get_db),
):
    """Return billing status for the current user's organization. Owner/Admin only."""
    account = acorn_service.get_account_for_user(current_user, db)
    if not account:
        raise HTTPException(status_code=404, detail="No billing account found")

    return {
        "plan_tier": account.plan_tier.value if account.plan_tier else None,
        "billing_cycle": account.billing_cycle,
        "status": account.status.value if account.status else None,
        "acorn_balance": float(account.acorn_balance),
        "trial_ends_at": account.trial_ends_at.isoformat() if account.trial_ends_at else None,
        "current_period_ends_at": account.current_period_ends_at.isoformat() if account.current_period_ends_at else None,
        # Removed paddle_customer_id and paddle_subscription_id (FIX #16)
    }


@router.get("/billing/transactions")
async def get_billing_transactions(
    limit: int = 20,
    offset: int = 0,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Return paginated acorn transaction history. Members see only their own usage."""
    account = acorn_service.get_account_for_user(current_user, db)
    if not account:
        raise HTTPException(status_code=404, detail="No billing account found")

    # Clamp limit to prevent abuse
    limit = min(limit, 100)

    # Members can only see their own transactions
    txn_user_id = None
    if current_user.role == models.UserRole.member:
        txn_user_id = current_user.id

    result = acorn_service.get_transactions(account.id, db, limit=limit, offset=offset, user_id=txn_user_id)

    # Batch-fetch user names for the transactions
    user_ids = {t.user_id for t in result["transactions"] if t.user_id}
    users_map = {}
    if user_ids:
        users = db.query(models.User).filter(models.User.id.in_(user_ids)).all()
        users_map = {u.id: u.full_name or u.email for u in users}

    return {
        "transactions": [
            {
                "id": t.id,
                "type": t.type.value,
                "amount": t.amount,
                "balance_after": t.balance_after,
                "description": t.description,
                "user_name": users_map.get(t.user_id) if t.user_id else None,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in result["transactions"]
        ],
        "total": result["total"],
        "limit": result["limit"],
        "offset": result["offset"],
        "has_more": result["has_more"],
    }


@router.get("/billing/acorns")
async def get_acorn_balance(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Return acorn balance. Any authenticated user."""
    account = acorn_service.get_account_for_user(current_user, db)
    if not account:
        raise HTTPException(status_code=404, detail="No billing account found")
    return {
        "acorn_balance": float(account.acorn_balance),
        "acorn_allocation_mode": account.acorn_allocation_mode,
        "locked_acorn_allocation": current_user.locked_acorn_allocation,
        "locked_acorn_balance": current_user.locked_acorn_balance,
        "plan_tier": account.plan_tier.value if account.plan_tier else None,
    }


class UpgradeRequest(BaseModel):
    plan: str  # "oak" or "redwood"
    cycle: str = "monthly"  # "monthly" or "annual"


class SpendRequest(BaseModel):
    cost: float
    description: str


@router.post("/billing/spend")
async def spend_acorns_endpoint(
    body: SpendRequest,
    current_user: models.User = Depends(_require_owner_or_admin),  # FIX #1: was get_current_active_user
    db: Session = Depends(get_db),
):
    """
    Deduct acorns from the account balance. Owner/Admin only.

    Returns 402 if insufficient balance.
    """
    account = acorn_service.get_account_for_user(current_user, db)
    if not account:
        raise HTTPException(status_code=404, detail="No billing account found")

    # Check account is active or trialing
    if account.status not in (models.AccountStatus.active, models.AccountStatus.trialing):
        raise HTTPException(status_code=403, detail="Account is not active")

    if account.acorn_balance < body.cost:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Insufficient acorns",
                "required": body.cost,
                "available": float(account.acorn_balance),
            },
        )

    try:
        acorn_service.spend_acorns(
            account_id=account.id,
            user_id=current_user.id,
            amount=body.cost,
            description=body.description,
            db=db,
        )
        db.commit()
    except ValueError as e:
        raise HTTPException(status_code=402, detail=str(e))

    return {
        "ok": True,
        "spent": body.cost,
        "new_balance": float(account.acorn_balance),
        "description": body.description,
    }


@router.post("/billing/upgrade")
async def upgrade_plan(
    body: UpgradeRequest,
    current_user: models.User = Depends(_require_owner_or_admin),
    db: Session = Depends(get_db),
):
    """
    Upgrade/downgrade subscription via Paddle API.

    For users with an existing active Paddle subscription, updates the
    subscription items to the new plan's price ID. For users without a
    subscription, returns the price ID so the frontend can open a checkout.
    """
    # FIX #2: Validate plan is a valid paid plan
    if body.plan not in VALID_UPGRADE_PLANS:
        raise HTTPException(status_code=400, detail="Invalid plan. Choose 'oak' or 'redwood'.")

    if body.cycle not in ("monthly", "annual"):
        raise HTTPException(status_code=400, detail="Invalid cycle. Choose 'monthly' or 'annual'.")

    price_key = f"{body.plan}_{body.cycle}"
    price_id = paddle_service.PRICE_IDS.get(price_key)
    if not price_id:
        raise HTTPException(status_code=400, detail=f"Plan {price_key} is not configured.")

    account = acorn_service.get_account_for_user(current_user, db)
    if not account:
        raise HTTPException(status_code=404, detail="No billing account found")

    # If no existing subscription, or cancelled/suspended — open fresh checkout
    if not account.paddle_subscription_id or account.status in (
        models.AccountStatus.cancelled,
        models.AccountStatus.suspended,
    ):
        return {
            "action": "checkout",
            "price_id": price_id,
            "message": "No active subscription. Use Paddle checkout to subscribe.",
        }

    # Call Paddle API to update the existing subscription
    if not paddle_service.PADDLE_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="Paddle API key not configured on the server.",
        )

    paddle_url = (
        f"{paddle_service.PADDLE_API_BASE}"
        f"/subscriptions/{account.paddle_subscription_id}"
    )

    try:
        async with httpx.AsyncClient() as client:
            response = await client.patch(
                paddle_url,
                headers={
                    "Authorization": f"Bearer {paddle_service.PADDLE_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "items": [{"price_id": price_id, "quantity": 1}],
                    "proration_billing_mode": "prorated_immediately",
                },
                timeout=30.0,
            )

        if response.status_code in (200, 201):
            return {
                "action": "upgraded",
                "plan": body.plan,
                "cycle": body.cycle,
                "message": f"Subscription updated to {body.plan} ({body.cycle}).",
            }
        else:
            error_detail = response.text
            logger.error(
                "Paddle subscription update failed: status=%d body=%s",
                response.status_code,
                error_detail,
            )
            raise HTTPException(
                status_code=502,
                detail=f"Paddle API error: {response.status_code}",
            )
    except httpx.RequestError as e:
        logger.exception("Paddle API request error: %s", str(e))
        raise HTTPException(status_code=502, detail="Failed to reach Paddle API")


@router.post("/billing/cancel")
async def cancel_subscription(
    current_user: models.User = Depends(_require_owner_or_admin),
    db: Session = Depends(get_db),
):
    """
    Cancel the current Paddle subscription.

    The user keeps their paid plan until the end of the current billing period.
    After that, they're automatically downgraded to seedling (free).
    """
    account = acorn_service.get_account_for_user(current_user, db)
    if not account:
        raise HTTPException(status_code=404, detail="No billing account found")

    if not account.paddle_subscription_id:
        raise HTTPException(status_code=400, detail="No active subscription to cancel.")

    if account.status not in (models.AccountStatus.active, models.AccountStatus.past_due):
        raise HTTPException(status_code=400, detail="Subscription is not active.")

    if not paddle_service.PADDLE_API_KEY:
        raise HTTPException(status_code=500, detail="Paddle API key not configured.")

    paddle_url = (
        f"{paddle_service.PADDLE_API_BASE}"
        f"/subscriptions/{account.paddle_subscription_id}/cancel"
    )

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                paddle_url,
                headers={
                    "Authorization": f"Bearer {paddle_service.PADDLE_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={"effective_from": "next_billing_period"},
                timeout=30.0,
            )

        if response.status_code in (200, 201):
            return {
                "ok": True,
                "message": "Subscription cancelled. You'll keep access until the end of your billing period.",
            }
        else:
            error_body = response.text
            logger.error(
                "Paddle cancel failed: status=%d body=%s",
                response.status_code,
                error_body,
            )
            # Handle specific Paddle errors with user-friendly messages
            try:
                error_data = response.json()
                error_code = error_data.get("error", {}).get("code", "")
            except Exception:
                error_code = ""

            if error_code == "subscription_locked_pending_changes":
                raise HTTPException(
                    status_code=409,
                    detail="Your subscription has a pending change (e.g. a recent upgrade). Please wait a minute and try again.",
                )
            raise HTTPException(
                status_code=502,
                detail=f"Paddle API error: {response.status_code}",
            )
    except httpx.RequestError as e:
        logger.exception("Paddle cancel request error: %s", str(e))
        raise HTTPException(status_code=502, detail="Failed to reach Paddle API")
