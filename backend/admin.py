from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Date
from datetime import datetime, timedelta, timezone
import logging

from database import get_db
from auth import get_current_active_user
import models

logger = logging.getLogger(__name__)

router = APIRouter()


async def get_current_admin_user(
    current_user: models.User = Depends(get_current_active_user),
) -> models.User:
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


def _get_model_pricing(db: Session) -> dict:
    """Load all model pricing as {model_id: (input_cost, output_cost)}."""
    all_models = db.query(models.AiModel).all()
    pricing = {}
    active_pricing = (3.0, 15.0)  # fallback
    for m in all_models:
        pricing[m.model_id] = (m.input_cost_per_million, m.output_cost_per_million)
        if m.is_active:
            active_pricing = (m.input_cost_per_million, m.output_cost_per_million)
    pricing["__default__"] = active_pricing
    return pricing


def _calculate_cost(prompt_tokens: int, completion_tokens: int, model_id: str, pricing: dict) -> float:
    """Calculate baseline cost in dollars (no cache discounts) using model-specific pricing.

    Used as a fallback for rows lacking stored cost columns; matches `billable_cost`
    semantics since aggregated prompt_tokens already include cache creation/read tokens.
    """
    costs = pricing.get(model_id, pricing.get("__default__", (3.0, 15.0)))
    return (prompt_tokens * costs[0] / 1_000_000) + (completion_tokens * costs[1] / 1_000_000)


def _resolve_costs(
    stored_cost: float,
    stored_billable: float,
    prompt_tokens: int,
    completion_tokens: int,
    model_id: str,
    pricing: dict,
) -> tuple[float, float]:
    """Return (actual_cost, billable_cost) for an aggregated row.

    - actual_cost: what we paid Anthropic (with cache tier pricing). Stored in `ai_usage_log.cost`.
    - billable_cost: what we charge users (baseline, cache-agnostic). Stored in `ai_usage_log.billable_cost`.

    Falls back to a recomputed baseline for pre-migration rows where the stored
    column is 0/NULL. This fallback equals billable semantics, so actual may be
    underestimated for legacy rows that predate migration 032.
    """
    actual_missing = not stored_cost or stored_cost <= 0
    billable_missing = not stored_billable or stored_billable <= 0
    fallback = _calculate_cost(prompt_tokens, completion_tokens, model_id, pricing) if (actual_missing or billable_missing) else 0.0
    return (
        fallback if actual_missing else stored_cost,
        fallback if billable_missing else stored_billable,
    )
    

def _setting_value(settings: dict, *keys: str):
    """Return the first non-empty setting value from possible keys."""
    for key in keys:
        value = settings.get(key)
        if value is None:
            continue

        if isinstance(value, str):
            value = value.strip()
            if value:
                return value
        else:
            return str(value)

    return None


def _get_onboarding_info(org: models.Organization | None) -> dict:
    """Typed admin-safe onboarding fields captured during signup."""
    settings = org.settings if org and isinstance(org.settings, dict) else {}

    return {
        "company_name": (
            _setting_value(settings, "company_name", "company", "companyName")
            or (org.name if org else None)
        ),
        "team_size": _setting_value(settings, "team_size", "teamSize"),
        "current_crm": _setting_value(settings, "current_crm", "currentCRM", "currentCrm"),
        "meeting_tool": _setting_value(settings, "meeting_tool", "meetingTool"),
        "meetings_per_week": _setting_value(settings, "meetings_per_week", "meetingsPerWeek"),
        "deal_cycle": _setting_value(settings, "deal_cycle", "dealCycle"),
        "challenge": _setting_value(settings, "challenge"),
    }

@router.get("/stats/overview")
async def get_admin_overview(
    current_user: models.User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Get platform overview stats and per-user breakdown.
    Token counts come from ai_usage_log (captures all AI calls including tests, email edits, etc.)."""
    pricing = _get_model_pricing(db)

    total_users = db.query(func.count(models.User.id)).scalar()
    total_workflows = db.query(func.count(models.Workflow.id)).scalar()
    total_executions = db.query(func.count(models.Execution.id)).scalar()

    # Token totals from ai_usage_log (captures ALL AI usage, not just executions)
    token_result = db.query(
        func.coalesce(func.sum(models.AiUsageLog.total_tokens), 0),
        func.coalesce(func.sum(models.AiUsageLog.prompt_tokens), 0),
        func.coalesce(func.sum(models.AiUsageLog.completion_tokens), 0),
    ).first()

    # Fall back to execution-based totals if ai_usage_log is empty (for historical data)
    if token_result[0] == 0:
        token_result = db.query(
            func.coalesce(func.sum(models.Execution.total_tokens), 0),
            func.coalesce(func.sum(models.Execution.total_prompt_tokens), 0),
            func.coalesce(func.sum(models.Execution.total_completion_tokens), 0),
        ).first()

    total_tokens = token_result[0]
    total_prompt_tokens = token_result[1]
    total_completion_tokens = token_result[2]

    # Cost by model for all users (pull stored cost columns + tokens for fallback)
    model_usage = (
        db.query(
            models.AiUsageLog.user_id,
            models.AiUsageLog.ai_model,
            func.coalesce(func.sum(models.AiUsageLog.prompt_tokens), 0).label("prompt"),
            func.coalesce(func.sum(models.AiUsageLog.completion_tokens), 0).label("completion"),
            func.coalesce(func.sum(models.AiUsageLog.cost), 0).label("stored_cost"),
            func.coalesce(func.sum(models.AiUsageLog.billable_cost), 0).label("stored_billable"),
        )
        .group_by(models.AiUsageLog.user_id, models.AiUsageLog.ai_model)
        .all()
    )

    user_billable_map = {}
    user_actual_map = {}
    total_billable_cost = 0.0
    total_actual_cost = 0.0
    for row in model_usage:
        actual, billable = _resolve_costs(
            row.stored_cost, row.stored_billable,
            row.prompt, row.completion, row.ai_model or "", pricing,
        )
        user_billable_map[row.user_id] = user_billable_map.get(row.user_id, 0.0) + billable
        user_actual_map[row.user_id] = user_actual_map.get(row.user_id, 0.0) + actual
        total_billable_cost += billable
        total_actual_cost += actual

    # Per-user stats
    users = db.query(models.User).all()

    # Prefetch orgs/accounts once to avoid per-user N+1 queries
    org_ids = list({user.org_id for user in users if user.org_id})

    org_map = {
        org.id: org
        for org in db.query(models.Organization).filter(models.Organization.id.in_(org_ids)).all()
    } if org_ids else {}

    account_map = {
        account.org_id: account
        for account in db.query(models.Account).filter(models.Account.org_id.in_(org_ids)).all()
    } if org_ids else {}

    user_stats = []
    for user in users:
        workflow_count = (
            db.query(func.count(models.Workflow.id))
            .filter(models.Workflow.owner_id == user.id)
            .scalar()
        )

        # Execution count and last active from executions table
        user_executions = (
            db.query(
                func.count(models.Execution.id),
                func.max(models.Execution.started_at),
            )
            .join(models.Workflow, models.Execution.workflow_id == models.Workflow.id)
            .filter(models.Workflow.owner_id == user.id)
            .first()
        )

        # Token totals from ai_usage_log (all AI calls)
        user_tokens = (
            db.query(
                func.coalesce(func.sum(models.AiUsageLog.total_tokens), 0),
                func.coalesce(func.sum(models.AiUsageLog.prompt_tokens), 0),
                func.coalesce(func.sum(models.AiUsageLog.completion_tokens), 0),
            )
            .filter(models.AiUsageLog.user_id == user.id)
            .first()
        )

        # Fall back to execution-based tokens if usage log is empty for this user
        u_total_tokens = user_tokens[0] if user_tokens else 0
        u_prompt_tokens = user_tokens[1] if user_tokens else 0
        u_completion_tokens = user_tokens[2] if user_tokens else 0
        if u_total_tokens == 0:
            exec_tokens = (
                db.query(
                    func.coalesce(func.sum(models.Execution.total_tokens), 0),
                    func.coalesce(func.sum(models.Execution.total_prompt_tokens), 0),
                    func.coalesce(func.sum(models.Execution.total_completion_tokens), 0),
                )
                .join(models.Workflow, models.Execution.workflow_id == models.Workflow.id)
                .filter(models.Workflow.owner_id == user.id)
                .first()
            )
            if exec_tokens:
                u_total_tokens = exec_tokens[0]
                u_prompt_tokens = exec_tokens[1]
                u_completion_tokens = exec_tokens[2]

        # Get acorn balance for this user's account
        user_acorn_balance = 0.0
        user_plan = "none"

        org = org_map.get(user.org_id) if user.org_id else None
        user_account = account_map.get(user.org_id) if user.org_id else None

        if user_account:
            user_acorn_balance = float(user_account.acorn_balance)
            user_plan = user_account.plan_tier.value if user_account.plan_tier else "none"

        org_name = org.name if org else None
        onboarding = _get_onboarding_info(org)

        user_billable = round(user_billable_map.get(user.id, 0.0), 6)
        user_actual = round(user_actual_map.get(user.id, 0.0), 6)
        user_stats.append({
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "is_active": user.is_active,
            "is_superadmin": user.is_superadmin,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "org_id": user.org_id,
            "org_name": org_name,
            "onboarding": onboarding,
            "workflow_count": workflow_count,
            "execution_count": user_executions[0] if user_executions else 0,
            "total_tokens": u_total_tokens,
            "total_prompt_tokens": u_prompt_tokens,
            "total_completion_tokens": u_completion_tokens,
            "cost": user_billable,          # Cost shown to/charged the user (cache-agnostic baseline)
            "actual_cost": user_actual,     # Actual Anthropic cost (with cache tier pricing)
            "acorns_spent": round(user_billable / 0.01, 2) if user_billable > 0 else 0,
            "acorn_balance": round(user_acorn_balance, 2),
            "plan": user_plan,
            "last_active": user_executions[1].isoformat() if user_executions and user_executions[1] else None,
        })
       

    return {
        "total_users": total_users,
        "total_workflows": total_workflows,
        "total_executions": total_executions,
        "total_tokens": total_tokens,
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "total_cost": round(total_billable_cost, 6),       # Billable to users
        "total_actual_cost": round(total_actual_cost, 6),  # What we paid Anthropic
        "total_acorns_spent": round(total_billable_cost / 0.01, 2) if total_billable_cost > 0 else 0,
        "users": user_stats,
    }


@router.get("/stats/usage-over-time")
async def get_usage_over_time(
    days: int = Query(default=30, ge=1, le=365),
    current_user: models.User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Get daily aggregated token usage and execution counts.
    Token data comes from ai_usage_log for comprehensive tracking."""
    pricing = _get_model_pricing(db)
    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    # Token usage from ai_usage_log (all AI calls)
    usage_rows = (
        db.query(
            cast(models.AiUsageLog.created_at, Date).label("date"),
            models.User.email,
            func.coalesce(func.sum(models.AiUsageLog.total_tokens), 0).label("tokens"),
            func.coalesce(func.sum(models.AiUsageLog.prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(func.sum(models.AiUsageLog.completion_tokens), 0).label("completion_tokens"),
            func.coalesce(func.sum(models.AiUsageLog.cost), 0).label("stored_cost"),
            func.coalesce(func.sum(models.AiUsageLog.billable_cost), 0).label("stored_billable"),
            models.AiUsageLog.ai_model,
        )
        .join(models.User, models.AiUsageLog.user_id == models.User.id)
        .filter(models.AiUsageLog.created_at >= start_date)
        .group_by(cast(models.AiUsageLog.created_at, Date), models.User.email, models.AiUsageLog.ai_model)
        .order_by(cast(models.AiUsageLog.created_at, Date))
        .all()
    )

    # Execution counts from executions table
    exec_rows = (
        db.query(
            cast(models.Execution.started_at, Date).label("date"),
            models.User.email,
            func.count(models.Execution.id).label("executions"),
        )
        .join(models.Workflow, models.Execution.workflow_id == models.Workflow.id)
        .join(models.User, models.Workflow.owner_id == models.User.id)
        .filter(models.Execution.started_at >= start_date)
        .group_by(cast(models.Execution.started_at, Date), models.User.email)
        .order_by(cast(models.Execution.started_at, Date))
        .all()
    )

    # Fallback: execution-based token data for days not covered by ai_usage_log
    fallback_rows = (
        db.query(
            cast(models.Execution.started_at, Date).label("date"),
            models.User.email,
            func.coalesce(func.sum(models.Execution.total_tokens), 0).label("tokens"),
            func.coalesce(func.sum(models.Execution.total_prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(func.sum(models.Execution.total_completion_tokens), 0).label("completion_tokens"),
        )
        .join(models.Workflow, models.Execution.workflow_id == models.Workflow.id)
        .join(models.User, models.Workflow.owner_id == models.User.id)
        .filter(models.Execution.started_at >= start_date)
        .group_by(cast(models.Execution.started_at, Date), models.User.email)
        .order_by(cast(models.Execution.started_at, Date))
        .all()
    )

    # Build daily map
    daily_map = {}

    def _empty_day(date_str):
        return {
            "date": date_str, "tokens": 0, "prompt_tokens": 0, "completion_tokens": 0,
            "cost": 0.0, "actual_cost": 0.0, "executions": 0, "by_user": {},
        }

    def _empty_user():
        return {
            "tokens": 0, "prompt_tokens": 0, "completion_tokens": 0,
            "cost": 0.0, "actual_cost": 0.0, "executions": 0,
        }

    # Process primary ai_usage_log data
    for row in usage_rows:
        date_str = row.date.isoformat() if row.date else None
        if date_str not in daily_map:
            daily_map[date_str] = _empty_day(date_str)
        daily_map[date_str]["tokens"] += row.tokens
        daily_map[date_str]["prompt_tokens"] += row.prompt_tokens
        daily_map[date_str]["completion_tokens"] += row.completion_tokens
        if row.email not in daily_map[date_str]["by_user"]:
            daily_map[date_str]["by_user"][row.email] = _empty_user()
        daily_map[date_str]["by_user"][row.email]["tokens"] += row.tokens
        daily_map[date_str]["by_user"][row.email]["prompt_tokens"] += row.prompt_tokens
        daily_map[date_str]["by_user"][row.email]["completion_tokens"] += row.completion_tokens
        actual, billable = _resolve_costs(
            row.stored_cost, row.stored_billable,
            row.prompt_tokens, row.completion_tokens, row.ai_model or "", pricing,
        )
        daily_map[date_str]["cost"] += billable
        daily_map[date_str]["actual_cost"] += actual
        daily_map[date_str]["by_user"][row.email]["cost"] += billable
        daily_map[date_str]["by_user"][row.email]["actual_cost"] += actual

    # Track which dates are covered by ai_usage_log (primary source)
    dates_with_ai_log = set(daily_map.keys())

    # Fill in cost/token data for days not covered by ai_usage_log (historical data fallback)
    for row in fallback_rows:
        date_str = row.date.isoformat() if row.date else None
        if date_str in dates_with_ai_log:
            continue  # ai_usage_log already covers this date
        if date_str not in daily_map:
            daily_map[date_str] = _empty_day(date_str)
        daily_map[date_str]["tokens"] += row.tokens
        daily_map[date_str]["prompt_tokens"] += row.prompt_tokens
        daily_map[date_str]["completion_tokens"] += row.completion_tokens
        if row.email not in daily_map[date_str]["by_user"]:
            daily_map[date_str]["by_user"][row.email] = _empty_user()
        daily_map[date_str]["by_user"][row.email]["tokens"] += row.tokens
        daily_map[date_str]["by_user"][row.email]["prompt_tokens"] += row.prompt_tokens
        daily_map[date_str]["by_user"][row.email]["completion_tokens"] += row.completion_tokens
        # Legacy fallback: no cache info available, treat baseline == actual
        cost = _calculate_cost(row.prompt_tokens, row.completion_tokens, "", pricing)
        daily_map[date_str]["cost"] += cost
        daily_map[date_str]["actual_cost"] += cost
        daily_map[date_str]["by_user"][row.email]["cost"] += cost
        daily_map[date_str]["by_user"][row.email]["actual_cost"] += cost

    for row in exec_rows:
        date_str = row.date.isoformat() if row.date else None
        if date_str not in daily_map:
            daily_map[date_str] = _empty_day(date_str)
        daily_map[date_str]["executions"] += row.executions
        if row.email not in daily_map[date_str]["by_user"]:
            daily_map[date_str]["by_user"][row.email] = _empty_user()
        daily_map[date_str]["by_user"][row.email]["executions"] += row.executions

    # Sort by date
    sorted_stats = sorted(daily_map.values(), key=lambda x: x["date"] or "")

    return {
        "days": days,
        "daily_stats": sorted_stats,
    }


@router.get("/stats/user/{user_id}")
async def get_user_stats(
    user_id: int,
    days: int = Query(default=0, ge=0, le=365),
    start_date: str = Query(default=None),
    end_date: str = Query(default=None),
    current_user: models.User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Get detailed stats for a specific user. Supports days preset or custom start_date/end_date (YYYY-MM-DD)."""
    pricing = _get_model_pricing(db)
    date_filter = None
    date_end = None
    if start_date:
        date_filter = datetime.strptime(start_date, "%Y-%m-%d")
    elif days > 0:
        date_filter = datetime.now(timezone.utc) - timedelta(days=days)
    if end_date:
        date_end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)  # inclusive
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    workflows = (
        db.query(models.Workflow)
        .filter(models.Workflow.owner_id == user_id)
        .all()
    )

    # Get per-workflow cost from ai_usage_log via executions
    workflow_ids = [wf.id for wf in workflows]
    workflow_billable_map = {}
    workflow_actual_map = {}
    if workflow_ids:
        wf_cost_rows = (
            db.query(
                models.Execution.workflow_id,
                models.AiUsageLog.ai_model,
                func.coalesce(func.sum(models.AiUsageLog.prompt_tokens), 0).label("prompt"),
                func.coalesce(func.sum(models.AiUsageLog.completion_tokens), 0).label("completion"),
                func.coalesce(func.sum(models.AiUsageLog.cost), 0).label("stored_cost"),
                func.coalesce(func.sum(models.AiUsageLog.billable_cost), 0).label("stored_billable"),
            )
            .join(models.Execution, models.AiUsageLog.execution_id == models.Execution.id)
            .filter(models.Execution.workflow_id.in_(workflow_ids))
            .group_by(models.Execution.workflow_id, models.AiUsageLog.ai_model)
            .all()
        )
        for row in wf_cost_rows:
            actual, billable = _resolve_costs(
                row.stored_cost, row.stored_billable,
                row.prompt, row.completion, row.ai_model or "", pricing,
            )
            workflow_billable_map[row.workflow_id] = workflow_billable_map.get(row.workflow_id, 0.0) + billable
            workflow_actual_map[row.workflow_id] = workflow_actual_map.get(row.workflow_id, 0.0) + actual

    workflow_stats = []
    for wf in workflows:
        exec_stats = (
            db.query(
                func.count(models.Execution.id),
                func.coalesce(func.sum(models.Execution.total_tokens), 0),
                func.max(models.Execution.started_at),
            )
            .filter(models.Execution.workflow_id == wf.id)
            .first()
        )
        workflow_stats.append({
            "id": wf.id,
            "name": wf.name,
            "is_active": wf.is_active,
            "created_at": wf.created_at.isoformat() if wf.created_at else None,
            "execution_count": exec_stats[0] if exec_stats else 0,
            "total_tokens": exec_stats[1] if exec_stats else 0,
            "cost": round(workflow_billable_map.get(wf.id, 0.0), 6),
            "actual_cost": round(workflow_actual_map.get(wf.id, 0.0), 6),
            "last_executed": exec_stats[2].isoformat() if exec_stats and exec_stats[2] else None,
        })

    # Usage breakdown by source from ai_usage_log
    source_q = (
        db.query(
            models.AiUsageLog.source,
            func.count(models.AiUsageLog.id).label("call_count"),
            func.coalesce(func.sum(models.AiUsageLog.total_tokens), 0).label("tokens"),
        )
        .filter(models.AiUsageLog.user_id == user_id)
    )
    if date_filter:
        source_q = source_q.filter(models.AiUsageLog.created_at >= date_filter)
    if date_end:
        source_q = source_q.filter(models.AiUsageLog.created_at < date_end)
    source_breakdown = source_q.group_by(models.AiUsageLog.source).all()

    # Total token usage from ai_usage_log
    token_q = (
        db.query(
            func.coalesce(func.sum(models.AiUsageLog.total_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(models.AiUsageLog.prompt_tokens), 0).label("total_prompt_tokens"),
            func.coalesce(func.sum(models.AiUsageLog.completion_tokens), 0).label("total_completion_tokens"),
        )
        .filter(models.AiUsageLog.user_id == user_id)
    )
    if date_filter:
        token_q = token_q.filter(models.AiUsageLog.created_at >= date_filter)
    if date_end:
        token_q = token_q.filter(models.AiUsageLog.created_at < date_end)
    token_totals = token_q.first()

    model_q = (
        db.query(
            models.AiUsageLog.ai_model,
            func.coalesce(func.sum(models.AiUsageLog.prompt_tokens), 0).label("prompt"),
            func.coalesce(func.sum(models.AiUsageLog.completion_tokens), 0).label("completion"),
            func.coalesce(func.sum(models.AiUsageLog.cost), 0).label("stored_cost"),
            func.coalesce(func.sum(models.AiUsageLog.billable_cost), 0).label("stored_billable"),
        )
        .filter(models.AiUsageLog.user_id == user_id)
    )
    if date_filter:
        model_q = model_q.filter(models.AiUsageLog.created_at >= date_filter)
    if date_end:
        model_q = model_q.filter(models.AiUsageLog.created_at < date_end)
    user_model_usage = model_q.group_by(models.AiUsageLog.ai_model).all()
    user_total_cost = 0.0
    user_total_actual_cost = 0.0
    for r in user_model_usage:
        actual, billable = _resolve_costs(
            r.stored_cost, r.stored_billable, r.prompt, r.completion, r.ai_model or "", pricing,
        )
        user_total_cost += billable
        user_total_actual_cost += actual

    # Full pipeline executions
    exec_q = (
        db.query(models.Execution)
        .join(models.Workflow, models.Execution.workflow_id == models.Workflow.id)
        .filter(models.Workflow.owner_id == user_id)
    )
    if date_filter:
        exec_q = exec_q.filter(models.Execution.started_at >= date_filter)
    if date_end:
        exec_q = exec_q.filter(models.Execution.started_at < date_end)
    recent_executions = exec_q.order_by(models.Execution.started_at.desc()).all()

    # Component tests from ai_usage_log — individual rows, not aggregated
    ct_q = (
        db.query(
            models.AiUsageLog.id,
            models.AiUsageLog.component_id,
            models.Component.name.label("component_name"),
            models.Workflow.name.label("workflow_name"),
            models.AiUsageLog.ai_model,
            models.AiUsageLog.total_tokens,
            models.AiUsageLog.prompt_tokens,
            models.AiUsageLog.completion_tokens,
            models.AiUsageLog.cost,
            models.AiUsageLog.billable_cost,
            models.AiUsageLog.task,
            models.AiUsageLog.created_at,
        )
        .join(models.Component, models.AiUsageLog.component_id == models.Component.id)
        .join(models.Workflow, models.Component.workflow_id == models.Workflow.id)
        .filter(
            models.AiUsageLog.user_id == user_id,
            models.AiUsageLog.source == "component_test",
        )
    )
    if date_filter:
        ct_q = ct_q.filter(models.AiUsageLog.created_at >= date_filter)
    if date_end:
        ct_q = ct_q.filter(models.AiUsageLog.created_at < date_end)
    component_tests = (
        ct_q.order_by(models.AiUsageLog.created_at.desc())
        .all()
    )

    # Get model display names for activity
    model_display = {m.model_id: m.display_name for m in db.query(models.AiModel).all()}

    # Get per-execution cost from ai_usage_log
    exec_ids = [ex.id for ex in recent_executions]
    exec_model_usage = {}
    if exec_ids:
        exec_usage_rows = (
            db.query(
                models.AiUsageLog.execution_id,
                models.AiUsageLog.ai_model,
                func.coalesce(func.sum(models.AiUsageLog.prompt_tokens), 0).label("prompt"),
                func.coalesce(func.sum(models.AiUsageLog.completion_tokens), 0).label("completion"),
                func.coalesce(func.sum(models.AiUsageLog.cost), 0).label("stored_cost"),
                func.coalesce(func.sum(models.AiUsageLog.billable_cost), 0).label("stored_billable"),
            )
            .filter(models.AiUsageLog.execution_id.in_(exec_ids))
            .group_by(models.AiUsageLog.execution_id, models.AiUsageLog.ai_model)
            .all()
        )
        for row in exec_usage_rows:
            if row.execution_id not in exec_model_usage:
                exec_model_usage[row.execution_id] = {"cost": 0.0, "actual_cost": 0.0, "model": row.ai_model}
            actual, billable = _resolve_costs(
                row.stored_cost, row.stored_billable,
                row.prompt, row.completion, row.ai_model or "", pricing,
            )
            exec_model_usage[row.execution_id]["cost"] += billable
            exec_model_usage[row.execution_id]["actual_cost"] += actual
            exec_model_usage[row.execution_id]["model"] = row.ai_model

    # Build unified activity list
    activity = []
    for ex in recent_executions:
        eu = exec_model_usage.get(ex.id, {})
        model_id = eu.get("model", "")
        activity.append({
            "type": "pipeline",
            "label": "Full Pipeline",
            "workflow_name": ex.workflow.name,
            "status": ex.status,
            "started_at": ex.started_at.isoformat() if ex.started_at else None,
            "total_tokens": ex.total_tokens or 0,
            "total_prompt_tokens": ex.total_prompt_tokens or 0,
            "total_completion_tokens": ex.total_completion_tokens or 0,
            "cost": round(eu.get("cost", 0.0), 6),
            "actual_cost": round(eu.get("actual_cost", 0.0), 6),
            "model": model_display.get(model_id, model_id) if model_id else "",
        })
    for ct in component_tests:
        fallback = _calculate_cost(ct.prompt_tokens or 0, ct.completion_tokens or 0, ct.ai_model or "", pricing)
        ct_billable = ct.billable_cost if ct.billable_cost else (ct.cost or fallback)
        ct_actual = ct.cost if ct.cost else fallback
        model_id = ct.ai_model or ""
        label = ct.component_name or "Component Test"
        if ct.task:
            label = f"{label} — {ct.task}"
        activity.append({
            "type": "component_test",
            "label": label,
            "workflow_name": ct.workflow_name or "Unknown",
            "status": "completed",
            "started_at": ct.created_at.isoformat() if ct.created_at else None,
            "total_tokens": ct.total_tokens or 0,
            "total_prompt_tokens": ct.prompt_tokens or 0,
            "total_completion_tokens": ct.completion_tokens or 0,
            "cost": round(ct_billable, 6),
            "actual_cost": round(ct_actual, 6),
            "model": model_display.get(model_id, model_id) if model_id else "",
        })

    # Sort by started_at descending
    activity.sort(key=lambda x: x["started_at"] or "", reverse=True)

    org = None
    if user.org_id:
        org = db.query(models.Organization).filter(models.Organization.id == user.org_id).first()

    onboarding = _get_onboarding_info(org)
    
    # Acorn data for this user
    user_acorn_balance = 0.0
    user_plan = "none"
    user_acorns_spent = 0.0
    if user.org_id:
        user_account = db.query(models.Account).filter(models.Account.org_id == user.org_id).first()
        if user_account:
            user_acorn_balance = float(user_account.acorn_balance)
            user_plan = user_account.plan_tier.value if user_account.plan_tier else "none"
            # Sum all spend transactions
            spent = db.query(func.coalesce(func.sum(models.AcornTransaction.amount), 0)).filter(
                models.AcornTransaction.account_id == user_account.id,
                models.AcornTransaction.amount < 0,
            ).scalar()
            user_acorns_spent = abs(float(spent)) if spent else 0.0

    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "is_active": user.is_active,
            "is_superadmin": user.is_superadmin,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "org_id": user.org_id,
            "org_name": org.name if org else None,
            "plan": user_plan,
            "acorn_balance": round(user_acorn_balance, 2),
            "onboarding": onboarding,
        },
        "total_tokens": token_totals.total_tokens if token_totals else 0,
        "total_prompt_tokens": token_totals.total_prompt_tokens if token_totals else 0,
        "total_completion_tokens": token_totals.total_completion_tokens if token_totals else 0,
        "total_cost": round(user_total_cost, 6),              # Billable to user
        "total_actual_cost": round(user_total_actual_cost, 6), # Actual Anthropic cost
        "total_acorns_spent": round(user_acorns_spent, 2),
        "workflows": workflow_stats,
        "usage_by_source": [
            {"source": row.source, "call_count": row.call_count, "tokens": row.tokens}
            for row in source_breakdown
        ],
        "recent_activity": activity,
    }


@router.get("/stats/org/{org_id}")
async def get_org_stats(
    org_id: int,
    current_user: models.User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Get stats for a specific organization including all members and their usage."""
    org = db.query(models.Organization).filter(models.Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    account = db.query(models.Account).filter(models.Account.org_id == org_id).first()

    pricing = _get_model_pricing(db)

    # Cost map for all users in this org
    members = db.query(models.User).filter(models.User.org_id == org_id).all()
    member_ids = [u.id for u in members]

    model_usage = (
        db.query(
            models.AiUsageLog.user_id,
            models.AiUsageLog.ai_model,
            func.coalesce(func.sum(models.AiUsageLog.prompt_tokens), 0).label("prompt"),
            func.coalesce(func.sum(models.AiUsageLog.completion_tokens), 0).label("completion"),
            func.coalesce(func.sum(models.AiUsageLog.cost), 0).label("stored_cost"),
            func.coalesce(func.sum(models.AiUsageLog.billable_cost), 0).label("stored_billable"),
        )
        .filter(models.AiUsageLog.user_id.in_(member_ids))
        .group_by(models.AiUsageLog.user_id, models.AiUsageLog.ai_model)
        .all()
    ) if member_ids else []

    user_billable_map = {}
    user_actual_map = {}
    total_cost = 0.0
    total_actual_cost = 0.0
    for row in model_usage:
        actual, billable = _resolve_costs(
            row.stored_cost, row.stored_billable,
            row.prompt, row.completion, row.ai_model or "", pricing,
        )
        user_billable_map[row.user_id] = user_billable_map.get(row.user_id, 0.0) + billable
        user_actual_map[row.user_id] = user_actual_map.get(row.user_id, 0.0) + actual
        total_cost += billable
        total_actual_cost += actual

    member_stats = []
    for user in members:
        workflow_count = (
            db.query(func.count(models.Workflow.id))
            .filter(models.Workflow.owner_id == user.id)
            .scalar()
        )
        user_executions = (
            db.query(
                func.count(models.Execution.id),
                func.max(models.Execution.started_at),
            )
            .join(models.Workflow, models.Execution.workflow_id == models.Workflow.id)
            .filter(models.Workflow.owner_id == user.id)
            .first()
        )
        user_tokens = (
            db.query(
                func.coalesce(func.sum(models.AiUsageLog.total_tokens), 0),
                func.coalesce(func.sum(models.AiUsageLog.prompt_tokens), 0),
                func.coalesce(func.sum(models.AiUsageLog.completion_tokens), 0),
            )
            .filter(models.AiUsageLog.user_id == user.id)
            .first()
        )
        u_total_tokens = user_tokens[0] if user_tokens else 0
        u_prompt_tokens = user_tokens[1] if user_tokens else 0
        u_completion_tokens = user_tokens[2] if user_tokens else 0

        user_usd_cost = round(user_billable_map.get(user.id, 0.0), 6)
        user_usd_actual = round(user_actual_map.get(user.id, 0.0), 6)

        # Per-user acorn balance
        user_acorn_balance = 0.0
        if account:
            if account.acorn_allocation_mode == "locked" and user.locked_acorn_balance is not None:
                user_acorn_balance = float(user.locked_acorn_balance)
            else:
                user_acorn_balance = float(account.acorn_balance)

        member_stats.append({
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "is_active": user.is_active,
            "is_superadmin": user.is_superadmin,
            "role": user.role.value if user.role else "member",
            "workflow_count": workflow_count,
            "execution_count": user_executions[0] if user_executions else 0,
            "total_tokens": u_total_tokens,
            "total_prompt_tokens": u_prompt_tokens,
            "total_completion_tokens": u_completion_tokens,
            "cost": user_usd_cost,
            "actual_cost": user_usd_actual,
            "acorns_spent": round(user_usd_cost / 0.01, 2) if user_usd_cost > 0 else 0,
            "acorn_balance": round(user_acorn_balance, 2),
            "last_active": user_executions[1].isoformat() if user_executions and user_executions[1] else None,
        })

    plan = account.plan_tier.value if account and account.plan_tier else "none"
    allocation_mode = account.acorn_allocation_mode if account else "shared"
    org_acorn_balance = float(account.acorn_balance) if account else 0.0

    return {
        "org": {
            "id": org.id,
            "name": org.name,
            "slug": org.slug,
            "domain": org.domain,
            "created_at": org.created_at.isoformat() if org.created_at else None,
        },
        "plan": plan,
        "allocation_mode": allocation_mode,
        "acorn_balance": round(org_acorn_balance, 2),
        "total_cost": round(total_cost, 6),                 # Billable to users
        "total_actual_cost": round(total_actual_cost, 6),   # Actual Anthropic cost
        "total_acorns_spent": round(total_cost / 0.01, 2) if total_cost > 0 else 0,
        "total_tokens": sum(u["total_tokens"] for u in member_stats),
        "members": member_stats,
    }


@router.delete("/stats/user/{user_id}/reset-usage")
async def reset_user_usage(
    user_id: int,
    current_user: models.User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Reset all token usage data for a specific user."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Delete ai_usage_log entries
    deleted_logs = db.query(models.AiUsageLog).filter(models.AiUsageLog.user_id == user_id).delete()

    # Reset execution token counters
    user_workflow_ids = [w.id for w in db.query(models.Workflow.id).filter(models.Workflow.owner_id == user_id).all()]
    deleted_exec_tokens = 0
    if user_workflow_ids:
        deleted_exec_tokens = (
            db.query(models.Execution)
            .filter(models.Execution.workflow_id.in_(user_workflow_ids))
            .update({
                models.Execution.total_tokens: 0,
                models.Execution.total_prompt_tokens: 0,
                models.Execution.total_completion_tokens: 0,
            }, synchronize_session='fetch')
        )

    db.commit()
    logger.info(f"Admin {current_user.email} reset usage for user {user_id}: {deleted_logs} log entries, {deleted_exec_tokens} executions zeroed")
    return {"message": f"Usage reset for {user.email}", "deleted_logs": deleted_logs, "executions_reset": deleted_exec_tokens}


# --- Model Management ---

@router.get("/models")
async def list_models(
    current_user: models.User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """List all AI models."""
    all_models = db.query(models.AiModel).order_by(models.AiModel.created_at.desc()).all()
    return [
        {
            "id": m.id,
            "model_id": m.model_id,
            "display_name": m.display_name,
            "input_cost_per_million": m.input_cost_per_million,
            "output_cost_per_million": m.output_cost_per_million,
            "is_active": m.is_active,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in all_models
    ]


@router.post("/models", status_code=201)
async def create_model(
    body: dict,
    current_user: models.User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Add a new AI model."""
    existing = db.query(models.AiModel).filter(models.AiModel.model_id == body["model_id"]).first()
    if existing:
        raise HTTPException(status_code=400, detail="Model ID already exists")

    model = models.AiModel(
        model_id=body["model_id"],
        display_name=body["display_name"],
        input_cost_per_million=body["input_cost_per_million"],
        output_cost_per_million=body["output_cost_per_million"],
        is_active=False,
    )
    db.add(model)
    db.commit()
    db.refresh(model)
    return {
        "id": model.id,
        "model_id": model.model_id,
        "display_name": model.display_name,
        "input_cost_per_million": model.input_cost_per_million,
        "output_cost_per_million": model.output_cost_per_million,
        "is_active": model.is_active,
        "created_at": model.created_at.isoformat() if model.created_at else None,
    }


@router.put("/models/{model_db_id}")
async def update_model(
    model_db_id: int,
    body: dict,
    current_user: models.User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Update a model's display name or pricing."""
    model = db.query(models.AiModel).filter(models.AiModel.id == model_db_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    if "display_name" in body:
        model.display_name = body["display_name"]
    if "input_cost_per_million" in body:
        model.input_cost_per_million = body["input_cost_per_million"]
    if "output_cost_per_million" in body:
        model.output_cost_per_million = body["output_cost_per_million"]

    db.commit()
    db.refresh(model)
    return {
        "id": model.id,
        "model_id": model.model_id,
        "display_name": model.display_name,
        "input_cost_per_million": model.input_cost_per_million,
        "output_cost_per_million": model.output_cost_per_million,
        "is_active": model.is_active,
        "created_at": model.created_at.isoformat() if model.created_at else None,
    }


@router.put("/models/{model_db_id}/activate")
async def activate_model(
    model_db_id: int,
    current_user: models.User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Set a model as the active model. Deactivates all others."""
    model = db.query(models.AiModel).filter(models.AiModel.id == model_db_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    # Deactivate all models
    db.query(models.AiModel).update({"is_active": False})
    # Activate the selected one
    model.is_active = True
    db.commit()

    # Clear the cached model in ai_service
    from ai_service import clear_model_cache
    clear_model_cache()

    return {"message": f"Model '{model.display_name}' is now active", "model_id": model.model_id}


@router.delete("/models/{model_db_id}")
async def delete_model(
    model_db_id: int,
    current_user: models.User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Delete a model. Cannot delete the active model."""
    model = db.query(models.AiModel).filter(models.AiModel.id == model_db_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    if model.is_active:
        raise HTTPException(status_code=400, detail="Cannot delete the active model")

    db.delete(model)
    db.commit()
    return {"message": "Model deleted"}


# ── RAG Observability Dashboard (Issue #96) ────────────────────────

@router.get("/rag/metrics")
async def get_rag_metrics(
    current_user: models.User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Aggregated RAG metrics for the observability dashboard. Cached in Redis for 60s."""
    from cache_service import cache_get, cache_set

    cache_key = "admin:rag:metrics"

    cached = cache_get(cache_key)
    if cached:
        return cached

    # 1. Total embeddings stored
    total_embeddings = db.query(func.count(models.ContentEmbedding.id)).scalar() or 0

    # 2. Embeddings by source_type
    source_type_rows = (
        db.query(models.ContentEmbedding.source_type, func.count(models.ContentEmbedding.id))
        .group_by(models.ContentEmbedding.source_type)
        .all()
    )
    embeddings_by_source = {row[0]: row[1] for row in source_type_rows}

    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)

    # 3. Anthropic prompt cache hit rate — from ai_usage_log
    total_ai_calls = (
        db.query(func.count(models.AiUsageLog.id))
        .filter(models.AiUsageLog.created_at >= seven_days_ago)
        .scalar()
    ) or 0

    cache_hits = (
        db.query(func.count(models.AiUsageLog.id))
        .filter(
            models.AiUsageLog.created_at >= seven_days_ago,
            models.AiUsageLog.cache_read_input_tokens > 0,
        )
        .scalar()
    ) or 0

    cache_hit_rate = round((cache_hits / total_ai_calls * 100), 1) if total_ai_calls > 0 else 0.0

    # 4. Avg retrieval latency — mean of rag_retrieval_log.latency_ms over the last 7 days
    avg_latency = (
        db.query(func.avg(models.RagRetrievalLog.latency_ms))
        .filter(models.RagRetrievalLog.created_at >= seven_days_ago)
        .scalar()
    )
    avg_retrieval_latency_ms = round(float(avg_latency), 1) if avg_latency is not None else None

    # 5. Anthropic Batch API health — surfaces stuck batches so operators can
    #    act before the customer-visible retry path does. "Stuck" is any row
    #    still in batch_stage="submitted" past Anthropic's 24h SLA. The
    #    threshold is the same rag.batch_stuck_threshold_hours the batch
    #    worker uses to fail rows out — keeping them in sync means the admin
    #    dashboard shows exactly what the worker is about to act on.
    from system_config import get_config_int
    # tz-aware throughout — batch_submitted_at is Postgres timestamptz and
    # comes back aware via psycopg2. datetime.utcnow() would be naive and
    # raise TypeError on comparison/subtraction; it's also deprecated in 3.12.
    now = datetime.now(timezone.utc)
    batch_submitted_count = (
        db.query(func.count(models.EmailQueue.id))
        .filter(models.EmailQueue.batch_stage == "submitted")
        .scalar()
    ) or 0
    stuck_threshold_hours = get_config_int("rag.batch_stuck_threshold_hours", db, default=24)
    stuck_cutoff = now - timedelta(hours=stuck_threshold_hours)
    batch_stuck_count = (
        db.query(func.count(models.EmailQueue.id))
        .filter(models.EmailQueue.batch_stage == "submitted")
        .filter(models.EmailQueue.batch_submitted_at.isnot(None))
        .filter(models.EmailQueue.batch_submitted_at < stuck_cutoff)
        .scalar()
    ) or 0
    oldest_submitted_at = (
        db.query(func.min(models.EmailQueue.batch_submitted_at))
        .filter(models.EmailQueue.batch_stage == "submitted")
        .scalar()
    )
    if oldest_submitted_at is not None:
        # Defensive: if some psycopg2 version returned a naive datetime for
        # the timestamptz column, attach UTC so subtraction with `now` (aware)
        # stays well-defined. The DB stores UTC, so this is the true tz.
        ts = oldest_submitted_at
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age_hours = round((now - ts).total_seconds() / 3600.0, 1)
    else:
        age_hours = None

    metrics = {
        "total_embeddings": total_embeddings,
        "embeddings_by_source": embeddings_by_source,
        "cache_hit_rate_pct": cache_hit_rate,
        "total_ai_calls_7d": total_ai_calls,
        "cache_hits_7d": cache_hits,
        "avg_retrieval_latency_ms": avg_retrieval_latency_ms,
        "batch_submitted_count": batch_submitted_count,
        "batch_stuck_count": batch_stuck_count,
        "batch_oldest_submitted_age_hours": age_hours,
    }

    cache_set(cache_key, metrics, ttl=60)
    return metrics