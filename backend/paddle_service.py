"""
Paddle billing service for subscription and top-up management.

Handles webhook verification, price ID mapping, and plan resolution
for Paddle payment integration.
"""

import hashlib
import hmac
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Environment variables
# ---------------------------------------------------------------------------
PADDLE_API_KEY = os.getenv("PADDLE_API_KEY", "")
PADDLE_ENVIRONMENT = os.getenv("PADDLE_ENVIRONMENT", "sandbox")
PADDLE_WEBHOOK_SECRET = os.getenv("PADDLE_WEBHOOK_SECRET", "")
PADDLE_CLIENT_TOKEN = os.getenv("PADDLE_CLIENT_TOKEN", "")

# Price IDs per plan / cycle (seedling is free — no Paddle product)
PADDLE_PRICE_OAK_MONTHLY = os.getenv("PADDLE_PRICE_OAK_MONTHLY", "")
PADDLE_PRICE_OAK_ANNUAL = os.getenv("PADDLE_PRICE_OAK_ANNUAL", "")
PADDLE_PRICE_REDWOOD_MONTHLY = os.getenv("PADDLE_PRICE_REDWOOD_MONTHLY", "")
PADDLE_PRICE_REDWOOD_ANNUAL = os.getenv("PADDLE_PRICE_REDWOOD_ANNUAL", "")

# Top-up acorn price IDs
PADDLE_PRICE_ACORNS_500 = os.getenv("PADDLE_PRICE_ACORNS_500", "")
PADDLE_PRICE_ACORNS_1750 = os.getenv("PADDLE_PRICE_ACORNS_1750", "")
PADDLE_PRICE_ACORNS_4000 = os.getenv("PADDLE_PRICE_ACORNS_4000", "")

# Maximum age of a webhook signature (5 minutes)
WEBHOOK_SIGNATURE_MAX_AGE_SECONDS = 300

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PADDLE_API_BASE = (
    "https://api.paddle.com"
    if PADDLE_ENVIRONMENT == "production"
    else "https://sandbox-api.paddle.com"
)

# Mapping of plan names to their Paddle price IDs (no seedling — it's free)
PRICE_IDS: dict[str, str] = {
    "oak_monthly": PADDLE_PRICE_OAK_MONTHLY,
    "oak_annual": PADDLE_PRICE_OAK_ANNUAL,
    "redwood_monthly": PADDLE_PRICE_REDWOOD_MONTHLY,
    "redwood_annual": PADDLE_PRICE_REDWOOD_ANNUAL,
}

# Mapping of top-up price IDs to the number of acorns granted
TOPUP_ACORN_AMOUNTS: dict[str, int] = {
    PADDLE_PRICE_ACORNS_500: 500,
    PADDLE_PRICE_ACORNS_1750: 1750,
    PADDLE_PRICE_ACORNS_4000: 4000,
}

# Mapping of price IDs to plan metadata
PLAN_FROM_PRICE: dict[str, dict[str, str]] = {
    PADDLE_PRICE_OAK_MONTHLY: {"plan": "oak", "cycle": "monthly"},
    PADDLE_PRICE_OAK_ANNUAL: {"plan": "oak", "cycle": "annual"},
    PADDLE_PRICE_REDWOOD_MONTHLY: {"plan": "redwood", "cycle": "monthly"},
    PADDLE_PRICE_REDWOOD_ANNUAL: {"plan": "redwood", "cycle": "annual"},
}


# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------

def verify_webhook_signature(raw_body: bytes, signature_header: str) -> bool:
    """Verify a Paddle webhook signature using HMAC SHA256.

    Paddle sends signatures in the format: ts=<timestamp>;h1=<hash>
    The signed payload is: <timestamp>:<raw_body>

    Also checks timestamp freshness to prevent replay attacks (FIX #7).
    """
    if not PADDLE_WEBHOOK_SECRET:
        logger.warning(
            "PADDLE_WEBHOOK_SECRET is not set — skipping webhook signature verification"
        )
        return True

    if not signature_header:
        return False

    # Parse ts=...;h1=... format
    parts = {}
    for pair in signature_header.split(";"):
        pair = pair.strip()
        if "=" not in pair:
            continue
        key, value = pair.split("=", 1)
        parts[key] = value

    ts = parts.get("ts")
    h1 = parts.get("h1")
    if not ts or not h1:
        return False

    # Check timestamp freshness (FIX #7)
    try:
        ts_int = int(ts)
        age = abs(time.time() - ts_int)
        if age > WEBHOOK_SIGNATURE_MAX_AGE_SECONDS:
            logger.warning("Paddle webhook signature too old: age=%.0fs", age)
            return False
    except (ValueError, TypeError):
        return False

    # Compute expected signature: HMAC-SHA256(secret, "ts:body")
    signed_payload = f"{ts}:".encode("utf-8") + raw_body
    expected = hmac.new(
        PADDLE_WEBHOOK_SECRET.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, h1)


def get_price_ids() -> dict:
    """Return Paddle configuration needed by the frontend."""
    return {
        "environment": PADDLE_ENVIRONMENT,
        "client_token": PADDLE_CLIENT_TOKEN,
        "plans": {
            name: price_id
            for name, price_id in PRICE_IDS.items()
            if price_id  # only include configured prices
        },
        "topups": {
            price_id: acorns
            for price_id, acorns in TOPUP_ACORN_AMOUNTS.items()
            if price_id  # only include configured prices
        },
    }


def get_plan_from_price_id(price_id: str) -> Optional[dict]:
    """Resolve a Paddle price ID to plan metadata."""
    return PLAN_FROM_PRICE.get(price_id)


def get_topup_acorns(price_id: str) -> Optional[int]:
    """Return the number of acorns granted by a top-up price ID."""
    return TOPUP_ACORN_AMOUNTS.get(price_id)


def is_topup_price_id(price_id: str) -> bool:
    """Check whether a price ID is a top-up (vs subscription)."""
    return price_id in TOPUP_ACORN_AMOUNTS and bool(price_id)


def plan_acorns(plan: str) -> int:
    """Return the monthly acorn grant for a plan tier."""
    return {"seedling": 100, "oak": 375, "redwood": 800}.get(plan, 0)
