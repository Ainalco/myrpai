"""
Shared condition evaluation module.

Used by:
1. Pipeline execution (executions.py) — evaluates conditional logic component at pipeline time
2. Email queue processor (email_service.py) — re-evaluates a single CRM condition before sending
"""

import logging
from typing import Dict, Any, Tuple, List, Optional
from sqlalchemy.orm import Session

import models

logger = logging.getLogger(__name__)


def resolve_ai_filter_model(config: Dict[str, Any], db: Optional[Session] = None) -> str:
    """Resolve which model an AI Filter execution should use.

    Precedence:
      1. SystemConfig key ``ai_filter.default_model`` — admin kill-switch. When set
         to ``"sonnet"`` or ``"haiku"`` it forces that choice across every filter,
         overriding per-component config. Used to emergency-revert a bad rollout.
      2. ``config["model"]`` — per-component opt-in, populated by the filter's
         config UI. Must be ``"sonnet"`` or ``"haiku"`` to take effect.
      3. ``"sonnet"`` — backward-compat default for filters created before the
         model field existed (whose stored config has no ``model`` key).

    Reuses the caller's ``db`` when supplied so execution paths with many AI
    filter nodes don't pay a connection-pool acquire/release per call. A fresh
    ``SessionLocal()`` is opened only as a fallback when the caller can't pass
    one (rare — most sites are inside an execution).
    """
    try:
        from system_config import get_config

        if db is not None:
            kill_switch = get_config("ai_filter.default_model", db)
        else:
            from database import SessionLocal
            session = SessionLocal()
            try:
                kill_switch = get_config("ai_filter.default_model", session)
            finally:
                session.close()
        if kill_switch in ("sonnet", "haiku"):
            return kill_switch
    except Exception as exc:
        logger.warning(f"Failed to read ai_filter.default_model kill-switch: {exc}")

    per_component = config.get("model")
    if per_component in ("sonnet", "haiku"):
        return per_component
    return "sonnet"


def evaluate_single_condition(field_value: Any, operator: str, value: str) -> bool:
    """
    Pure operator logic for a single condition.
    No DB calls, no side effects — just compares field_value against value using operator.
    """
    if operator == "equals":
        return str(field_value) == str(value)
    elif operator == "not_equals":
        return str(field_value) != str(value)
    elif operator == "contains":
        return str(value) in str(field_value)
    elif operator == "not_contains":
        return str(value) not in str(field_value)
    elif operator == "greater_than":
        try:
            return float(field_value) > float(value) if field_value and value else False
        except (ValueError, TypeError):
            return False
    elif operator == "less_than":
        try:
            return float(field_value) < float(value) if field_value and value else False
        except (ValueError, TypeError):
            return False
    elif operator == "is_empty":
        return not field_value
    elif operator == "is_not_empty":
        return bool(field_value)
    else:
        return False


async def fetch_deal_crm_data(
    db: Session,
    user_id: int,
    participant_emails: List[str]
) -> Dict[str, Any]:
    """
    Look up a Pipedrive deal by participant emails and return mapped CRM data.

    Returns dict with keys: deal_id, title, value, currency, status, stage, stage_id,
    probability, owner_name, person_name, org_name, expected_close_date, etc.

    Returns empty dict if no deal found.
    Raises on API/DB errors (caller decides how to handle).
    """
    from pipedrive_service import find_latest_deal_by_emails

    # Get user's internal domains to filter out internal emails
    user = db.query(models.User).filter(models.User.id == user_id).first()
    internal_domains = []
    if user and user.internal_domains:
        internal_domains = [d.strip().lower() for d in user.internal_domains.split(",") if d.strip()]

    # Filter to external emails only
    external_emails = []
    for email in participant_emails:
        if email:
            email_domain = email.split("@")[-1].lower() if "@" in email else ""
            if not any(domain in email_domain for domain in internal_domains):
                external_emails.append(email)

    if not external_emails:
        logger.info("fetch_deal_crm_data: No external emails after filtering")
        return {}

    logger.info(f"fetch_deal_crm_data: Looking up deal for emails: {external_emails}")
    deal_lookup_result = await find_latest_deal_by_emails(db, user_id, external_emails)

    if not deal_lookup_result.get("success") or not deal_lookup_result.get("deal_data"):
        logger.warning(f"fetch_deal_crm_data: No deal found for emails: {external_emails}")
        return {}

    deal_data = deal_lookup_result["deal_data"]

    crm_data = {
        "deal_id": deal_data.get("id"),
        "title": deal_data.get("title"),
        "value": deal_data.get("value"),
        "currency": deal_data.get("currency"),
        "status": deal_data.get("status_label") or deal_data.get("status"),
        "stage": deal_data.get("stage_name") or deal_data.get("stage_id"),
        "stage_id": deal_data.get("stage_id"),
        "probability": deal_data.get("probability"),
        "owner_name": deal_data.get("owner_name"),
        "person_name": deal_data.get("person_name"),
        "org_name": deal_data.get("org_name"),
        "expected_close_date": deal_data.get("expected_close_date"),
        "add_time": deal_data.get("add_time"),
        "update_time": deal_data.get("update_time"),
    }

    logger.info(
        f"fetch_deal_crm_data: Found deal '{crm_data.get('title')}' "
        f"(ID: {crm_data.get('deal_id')}) - Stage: {crm_data.get('stage')}, "
        f"Status: {crm_data.get('status')}"
    )
    return crm_data


async def evaluate_pre_send_ai_filter(
    ai_filter_config: dict,
    input_data: dict,
    db: Optional[Session] = None,
) -> Tuple[bool, str]:
    """
    Evaluate an AI filter as part of the pre-send check.

    Reuses the same evaluation logic as the standalone AI Filter pipeline component
    (executions.py:execute_ai_filter), but returns (passed, reason) for pre-send use.

    Args:
        ai_filter_config: {
            "ai_prompt": str,
            "condition_operator": str,  # contains, equals, starts_with, etc.
            "condition_value": str,
            "case_sensitive": bool
        }
        input_data: The execution context data (transcript, participants, etc.)

    Returns:
        (True, reason) if AI filter passes (email should send)
        (False, reason) if AI filter fails (email should be cancelled)

    Raises:
        Exception on AI service errors — caller decides whether to send anyway.
    """
    import re
    from ai_service import analyze_with_ai, analyze_with_haiku

    ai_prompt = ai_filter_config.get("ai_prompt", "")
    condition_operator = ai_filter_config.get("condition_operator", "contains")
    condition_value = ai_filter_config.get("condition_value", "")
    case_sensitive = ai_filter_config.get("case_sensitive", False)

    if not ai_prompt:
        return (True, "AI filter prompt not configured, skipping")

    # RAG Phase 6: run a Haiku sufficiency check before the filter evaluates.
    # If the context appears insufficient, pull a single compensating retrieval.
    # Reuse caller's db session; only open a short-lived one if none was passed.
    try:
        from rag_service import check_context_sufficiency, retrieve_context
        context_str = ""
        for key in ("summary", "extracted_information", "transcript"):
            val = input_data.get(key)
            if isinstance(val, str):
                context_str += f"\n{key}: {val[:1000]}"
            elif isinstance(val, (dict, list)):
                context_str += f"\n{key}: {str(val)[:1000]}"
        if context_str:
            verdict, gap = await check_context_sufficiency(context_str, ai_prompt, db=db)
            if verdict == "MISSING" and gap and input_data.get("__account_id__"):
                _owns = False
                _s = db
                if _s is None:
                    from database import SessionLocal
                    _s = SessionLocal()
                    _owns = True
                try:
                    extra = await retrieve_context(
                        db=_s,
                        query_text=gap,
                        account_id=input_data["__account_id__"],
                        source_types=["resource", "text_gen_output", "transcript_chunk", "generated_email", "activity"],
                        contact_id=input_data.get("__contact_id__"),
                        org_id=input_data.get("__org_id__"),
                        limit=3,
                    )
                    if extra:
                        input_data = {**input_data, "__rag_gap_fill__": [r["chunk_text"] for r in extra[:3]]}
                finally:
                    if _owns:
                        _s.close()
    except Exception as _e:
        logger.debug(f"Sufficiency gate skipped: {_e}")

    model_choice = resolve_ai_filter_model(ai_filter_config, db=db)
    logger.info(
        f"Running pre-send AI filter with operator={condition_operator} model={model_choice}"
    )
    if model_choice == "haiku":
        ai_response = await analyze_with_haiku(ai_prompt, input_data)
    else:
        ai_response = await analyze_with_ai(ai_prompt, input_data)

    # Evaluate the condition (same logic as execute_ai_filter)
    passes_filter = False
    response_val = ai_response if case_sensitive else ai_response.lower()
    check_val = condition_value if case_sensitive else condition_value.lower()

    if condition_operator == "contains":
        passes_filter = check_val in response_val
    elif condition_operator == "not_contains":
        passes_filter = check_val not in response_val
    elif condition_operator == "equals":
        passes_filter = response_val == check_val
    elif condition_operator == "not_equals":
        passes_filter = response_val != check_val
    elif condition_operator == "starts_with":
        passes_filter = response_val.startswith(check_val)
    elif condition_operator == "ends_with":
        passes_filter = response_val.endswith(check_val)
    elif condition_operator == "greater_than":
        try:
            numbers = re.findall(r'-?\d+\.?\d*', ai_response)
            if numbers:
                passes_filter = float(numbers[0]) > float(condition_value)
        except (ValueError, TypeError):
            pass
    elif condition_operator == "less_than":
        try:
            numbers = re.findall(r'-?\d+\.?\d*', ai_response)
            if numbers:
                passes_filter = float(numbers[0]) < float(condition_value)
        except (ValueError, TypeError):
            pass
    elif condition_operator == "matches_regex":
        try:
            passes_filter = bool(re.compile(condition_value).search(ai_response))
        except re.error:
            pass
    elif condition_operator == "positive_sentiment":
        positive_keywords = ["positive", "good", "excellent", "great", "satisfied", "happy", "excited"]
        passes_filter = any(kw in response_val for kw in positive_keywords)
    elif condition_operator == "negative_sentiment":
        negative_keywords = ["negative", "bad", "poor", "unsatisfied", "unhappy", "concerned", "worried"]
        passes_filter = any(kw in response_val for kw in negative_keywords)
    elif condition_operator == "neutral_sentiment":
        neutral_keywords = ["neutral", "okay", "fine", "moderate", "average"]
        passes_filter = any(kw in response_val for kw in neutral_keywords)

    reason = (
        f"Pre-send AI filter: operator={condition_operator}, "
        f"value='{condition_value}', AI response='{ai_response[:200]}' "
        f"→ {'PASSED' if passes_filter else 'FAILED'}"
    )
    logger.info(reason)

    return (passes_filter, reason)


async def evaluate_pre_send_check(
    db: Session,
    user_id: int,
    check_field: str,
    check_operator: str,
    check_value: str,
    context: Dict[str, Any]
) -> Tuple[bool, str]:
    """
    Main entry point for the email queue processor's pre-send check.

    Fetches fresh CRM data, evaluates a single condition, returns (passed, reason).

    Args:
        db: Database session
        user_id: Owner of the workflow
        check_field: CRM field name (e.g. "status", "stage")
        check_operator: Operator (e.g. "equals", "not_equals")
        check_value: Expected value
        context: Must contain "participant_emails" list

    Returns:
        (True, reason) if check passes (email should send)
        (False, reason) if check fails (email should be cancelled)

    Raises:
        Exception on infrastructure errors (Pipedrive API down, etc.)
        — caller should catch and decide whether to send anyway.
    """
    participant_emails = context.get("participant_emails", [])
    if not participant_emails:
        return (True, "No participant emails in context, skipping pre-send check")

    crm_data = await fetch_deal_crm_data(db, user_id, participant_emails)
    if not crm_data:
        return (True, "No deal found for participants, skipping pre-send check")

    # Resolve field value (special handling for stage field)
    field_value = crm_data.get(check_field)
    if check_field == "stage":
        if check_value and check_value.isdigit():
            field_value = crm_data.get("stage_id")
        else:
            field_value = crm_data.get("stage")

    passed = evaluate_single_condition(field_value, check_operator, check_value)

    reason = (
        f"Pre-send check: {check_field} ({field_value}) {check_operator} {check_value} "
        f"→ {'PASSED' if passed else 'FAILED'}"
    )
    logger.info(reason)

    return (passed, reason)


async def evaluate_pre_send_check_groups(
    db: Session,
    user_id: int,
    config: Dict[str, Any],
) -> Tuple[bool, str]:
    """
    Multi-group pre-send check evaluation.

    Config format:
    {
        "condition_groups": [
            {"id": "1", "logic": "AND", "conditions": [{"field": "stage", "operator": "equals", "value": "3"}]},
            ...
        ],
        "group_logic": "AND" | "OR",
        "data_source": "pipedrive",
        "context": {"participant_emails": [...]}
    }

    Returns:
        (True, reason) if check passes (email should send)
        (False, reason) if check fails (email should be cancelled)

    Raises:
        Exception on infrastructure errors — caller decides whether to send anyway.
    """
    context = config.get("context", {})
    participant_emails = context.get("participant_emails", [])
    condition_groups = config.get("condition_groups", [])
    group_logic = config.get("group_logic", "AND")

    if not condition_groups:
        return (True, "No condition groups configured, skipping pre-send check")

    if not participant_emails:
        return (True, "No participant emails in context, skipping pre-send check")

    crm_data = await fetch_deal_crm_data(db, user_id, participant_emails)
    if not crm_data:
        return (True, "No deal found for participants, skipping pre-send check")

    group_results = []
    group_reasons = []

    for group in condition_groups:
        conditions = group.get("conditions", [])
        logic = group.get("logic", "AND")

        if not conditions:
            group_results.append(True)
            group_reasons.append("empty group → pass")
            continue

        condition_results = []
        for cond in conditions:
            check_field = cond.get("field", "")
            check_operator = cond.get("operator", "equals")
            check_value = cond.get("value", "")

            if not check_field:
                condition_results.append(True)
                continue

            # Resolve field value (special handling for stage field)
            field_value = crm_data.get(check_field)
            if check_field == "stage":
                if check_value and str(check_value).isdigit():
                    field_value = crm_data.get("stage_id")
                else:
                    field_value = crm_data.get("stage")

            passed = evaluate_single_condition(field_value, check_operator, check_value)
            condition_results.append(passed)

        if logic == "AND":
            group_passed = all(condition_results)
        else:
            group_passed = any(condition_results)

        group_results.append(group_passed)
        group_reasons.append(
            f"Group {group.get('id', '?')} ({logic}): {'PASSED' if group_passed else 'FAILED'}"
        )

    if group_logic == "AND":
        overall_passed = all(group_results)
    else:
        overall_passed = any(group_results)

    reason = (
        f"Pre-send check ({group_logic} across {len(group_results)} group(s)): "
        f"{'PASSED' if overall_passed else 'FAILED'} — {'; '.join(group_reasons)}"
    )
    logger.info(reason)

    return (overall_passed, reason)
