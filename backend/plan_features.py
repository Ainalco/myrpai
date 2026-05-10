from typing import Optional

import models


PLAN_FEATURES = {
    "trialing":       {"max_emails_per_sequence": 15,   "ai_filter": True,  "ai_send_timing": True,  "api_access": True,  "max_resource_links": 10, "max_resource_files": 5},
    "seedling":       {"max_emails_per_sequence": 3,    "ai_filter": False, "ai_send_timing": False, "api_access": False, "max_resource_links": 2,  "max_resource_files": 0},
    "oak":            {"max_emails_per_sequence": 7,    "ai_filter": True,  "ai_send_timing": True,  "api_access": False, "max_resource_links": 10, "max_resource_files": 5},
    "redwood":        {"max_emails_per_sequence": 15,   "ai_filter": True,  "ai_send_timing": True,  "api_access": True,  "max_resource_links": 25, "max_resource_files": 15},
    "ancient_forest": {"max_emails_per_sequence": None, "ai_filter": True,  "ai_send_timing": True,  "api_access": True,  "max_resource_links": None, "max_resource_files": None},
}

PLAN_DISPLAY_INFO = {
    "seedling": {
        "name": "Seedling",
        "price_monthly": 0,
        "price_annual": 0,
        "emoji": "\U0001f331",  # 🌱
    },
    "oak": {
        "name": "Oak",
        "price_monthly": 99,
        "price_annual": 79,
        "emoji": "\U0001f333",  # 🌳
    },
    "redwood": {
        "name": "Redwood",
        "price_monthly": 249,
        "price_annual": 199,
        "emoji": "\U0001f332",  # 🌲
    },
    "ancient_forest": {
        "name": "Ancient Forest",
        "price_monthly": None,
        "price_annual": None,
        "emoji": "\U0001f3d4\ufe0f",  # 🏔️
    },
}


def get_plan_features(plan_tier: str) -> dict:
    """Return the feature dict for a given plan tier, defaulting to trialing."""
    return PLAN_FEATURES.get(plan_tier, PLAN_FEATURES["trialing"])


def check_feature_access(account: models.Account, feature: str) -> bool:
    """Check if a feature is accessible for the account's plan.

    For boolean features, returns the boolean value directly.
    For non-boolean features (e.g. max_emails_per_sequence), returns True
    to indicate the feature is accessible (with a limit).
    """
    features = get_plan_features(account.plan_tier.value if hasattr(account.plan_tier, "value") else account.plan_tier)
    value = features.get(feature)
    if isinstance(value, bool):
        return value
    # Non-bool features (int or None) are always accessible — they just have limits
    return True


def get_feature_limit(account: models.Account, feature: str) -> Optional[int]:
    """Return the numeric limit for a feature, or None if unlimited."""
    features = get_plan_features(account.plan_tier.value if hasattr(account.plan_tier, "value") else account.plan_tier)
    return features.get(feature)


def get_plan_display_info() -> dict:
    """Return plan display info (name, price_monthly, price_annual, emoji) for frontend."""
    return PLAN_DISPLAY_INFO
