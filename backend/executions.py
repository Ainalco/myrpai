from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel
from datetime import datetime
import asyncio
import time
import json
import logging

from database import get_db
from auth import get_current_active_user, require_active_account
from websocket_manager import WebSocketManager
from acorn_service import check_can_execute, check_user_can_execute, get_account_for_user, spend_acorns, usd_to_acorns
from tracing import record_skip
import models

logger = logging.getLogger(__name__)

router = APIRouter()


def _compute_acorns_used(execution_id: int, db: Session) -> Optional[float]:
    """Compute acorn cost for an execution from its AI usage logs.

    Uses billable_cost (baseline, no cache discounts) so users pay consistently
    regardless of whether Anthropic happened to hit its prompt cache.
    """
    usage_logs = db.query(models.AiUsageLog).filter(
        models.AiUsageLog.execution_id == execution_id
    ).all()
    total_cost_usd = sum((log.billable_cost or log.cost or 0) for log in usage_logs)
    if total_cost_usd > 0:
        return round(usd_to_acorns(total_cost_usd, db), 2)
    return None

# Pydantic models
class ExecutionCreate(BaseModel):
    workflow_id: int
    test_mode: bool = False
    fireflies_transcript_id: Optional[str] = None

class ComponentExecutionResult(BaseModel):
    id: int
    component_id: int
    component_name: str = ""
    component_type: str = ""
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    execution_time: Optional[int] = None
    input_data: Optional[dict] = None
    output_data: Optional[dict] = None
    error_message: Optional[str] = None

    @classmethod
    def from_orm(cls, obj):
        # Get component details from the relationship
        component_name = obj.component.name if obj.component else ""
        component_type = obj.component.type if obj.component else ""

        return cls(
            id=obj.id,
            component_id=obj.component_id,
            component_name=component_name,
            component_type=component_type,
            status=obj.status,
            started_at=obj.started_at,
            completed_at=obj.completed_at,
            execution_time=obj.execution_time,
            input_data=obj.input_data,
            output_data=obj.output_data,
            error_message=obj.error_message
        )

    class Config:
        from_attributes = True

class Execution(BaseModel):
    id: int
    workflow_id: int
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    total_execution_time: Optional[int] = None
    input_data: Optional[dict] = None
    results: Optional[dict] = None
    error_message: Optional[str] = None
    generation_reason: Optional[str] = None
    total_prompt_tokens: Optional[int] = None
    total_completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    acorns_used: Optional[float] = None
    rag_trace: Optional[List[dict]] = None
    component_executions: List[ComponentExecutionResult] = []

    class Config:
        from_attributes = True

class ExecutionStats(BaseModel):
    total_executions: int
    successful_executions: int
    failed_executions: int
    running_executions: int
    avg_execution_time: Optional[float] = None


class ExecutionSummaryResponse(BaseModel):
    """Response model for execution summary endpoint"""
    execution_id: int
    workflow_id: int
    status: str
    has_summary: bool
    summary: Optional[str] = None
    extracted_information: Optional[Dict[str, Any]] = None
    component_name: Optional[str] = None
    executed_at: Optional[datetime] = None
    fireflies_meeting_id: Optional[str] = None
    meeting_title: Optional[str] = None
    message: str

# Mock execution engine for different component types
class ComponentExecutor:
    @staticmethod
    async def execute_input_sources(config: dict, input_data: dict = None, db: Session = None) -> dict:
        """Execute input sources component - handles webhook data from multiple integrations"""
        await asyncio.sleep(0.125)  # Simulate 125ms execution
        
        # Check if we have webhook input data from any integration
        if input_data and input_data.get("source") == "fireflies_webhook":
            # Fireflies webhook data
            return {
                "status": "success",
                "data": {
                    "transcript": input_data.get("transcript", ""),
                    "participants": input_data.get("participants", []),
                    "meeting_title": input_data.get("meeting_title", ""),
                    "meeting_url": input_data.get("meeting_url", ""),
                    "meeting_date": input_data.get("meeting_date", ""),
                    "duration": input_data.get("duration", 0),
                    "summary": input_data.get("summary", ""),
                    "action_items": input_data.get("action_items", []),
                    "keywords": input_data.get("keywords", []),
                    "sentiment": input_data.get("sentiment", {}),
                    "source": "fireflies_webhook",
                    "integration": "fireflies"
                }
            }
        
        # Check if any integrations are enabled in config
        integrations = config.get("integrations", {})
        enabled_integrations = [k for k, v in integrations.items() if v.get("enabled")]
        
        if "fireflies" in enabled_integrations and integrations["fireflies"].get("auto_process"):
            # Configuration indicates Fireflies is enabled and should auto-process
            # In production, this might wait for webhook data or fetch from API
            pass
        
        # Default mock data for testing
        return {
            "status": "success",
            "data": {
                "transcript": "Sample call transcript about CRM implementation...",
                "participants": ["John Doe", "Jane Smith"],
                "call_duration": 1800,
                "source": "mock",
                "enabled_integrations": enabled_integrations
            }
        }
    
    @staticmethod
    async def execute_ai_filter(config: dict, input_data: dict, db: Session = None) -> dict:
        """Execute AI filter component with AI analysis and condition evaluation.

        Model selection is resolved via ``conditional_logic.resolve_ai_filter_model``:
        per-component ``config["model"]`` with a SystemConfig kill-switch override,
        defaulting to ``"sonnet"`` for filters that predate the model field.
        """
        try:
            from ai_service import analyze_with_ai, analyze_with_haiku
            from conditional_logic import resolve_ai_filter_model
            import re

            # Get configuration
            ai_prompt = config.get("ai_prompt", "")
            condition_operator = config.get("condition_operator", "contains")
            condition_value = config.get("condition_value", "")
            case_sensitive = config.get("case_sensitive", False)

            if not ai_prompt:
                return {
                    "status": "error",
                    "error": "AI prompt is not configured. Please configure the AI Filter by setting the AI Analysis Prompt and Proceed Condition, then save the configuration before testing."
                }

            # Substitute variables in AI prompt using unified substitution function
            from variable_substitution import substitute_variables

            component_outputs = input_data.get("__component_outputs__", {})
            ai_prompt_processed = substitute_variables(
                ai_prompt,
                input_data,
                component_outputs,
                component_name="AI Filter"
            )

            model_choice = resolve_ai_filter_model(config, db=db)
            logger.info(
                f"Running AI filter analysis with operator={condition_operator} model={model_choice}"
            )
            if model_choice == "haiku":
                ai_response = await analyze_with_haiku(ai_prompt_processed, input_data)
            else:
                ai_response = await analyze_with_ai(ai_prompt_processed, input_data)

            # Evaluate the condition based on operator
            passes_filter = False

            # Prepare values for comparison
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
                    # Try to extract number from AI response
                    numbers = re.findall(r'-?\d+\.?\d*', ai_response)
                    if numbers:
                        ai_num = float(numbers[0])
                        check_num = float(condition_value)
                        passes_filter = ai_num > check_num
                except ValueError:
                    passes_filter = False
            elif condition_operator == "less_than":
                try:
                    numbers = re.findall(r'-?\d+\.?\d*', ai_response)
                    if numbers:
                        ai_num = float(numbers[0])
                        check_num = float(condition_value)
                        passes_filter = ai_num < check_num
                except ValueError:
                    passes_filter = False
            elif condition_operator == "matches_regex":
                try:
                    pattern = re.compile(condition_value)
                    passes_filter = bool(pattern.search(ai_response))
                except re.error:
                    passes_filter = False
            elif condition_operator == "positive_sentiment":
                positive_keywords = ["positive", "good", "excellent", "great", "satisfied", "happy", "excited"]
                passes_filter = any(keyword in response_val for keyword in positive_keywords)
            elif condition_operator == "negative_sentiment":
                negative_keywords = ["negative", "bad", "poor", "unsatisfied", "unhappy", "concerned", "worried"]
                passes_filter = any(keyword in response_val for keyword in negative_keywords)
            elif condition_operator == "neutral_sentiment":
                neutral_keywords = ["neutral", "okay", "fine", "moderate", "average"]
                passes_filter = any(keyword in response_val for keyword in neutral_keywords)

            logger.info(f"AI Filter result: passes_filter={passes_filter} model={model_choice}")

            return {
                "status": "success",
                "data": {
                    "ai_response": ai_response,
                    "condition_operator": condition_operator,
                    "condition_value": condition_value,
                    "case_sensitive": case_sensitive,
                    "passes_filter": passes_filter,
                    "evaluation_result": "PASS" if passes_filter else "FAIL",
                    "model_used": model_choice,
                }
            }

        except Exception as e:
            logger.error(f"AI filter execution error: {str(e)}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    @staticmethod
    async def execute_text_generation(config: dict, input_data: dict, db: Session = None) -> dict:
        """Execute text generation component with AI-powered extraction and summary in a single API call"""
        try:
            from ai_service import extract_and_summarize, DEFAULT_EXTRACTION_POINTS

            transcript = input_data.get("transcript", "")
            participants = input_data.get("participants", [])
            workflow_id = input_data.get("workflow_id")

            if not transcript:
                return {
                    "status": "error",
                    "error": "No transcript available for summary generation"
                }

            extraction_points = config.get("extraction_points", DEFAULT_EXTRACTION_POINTS)

            # RAG: Retrieve contact briefing for relationship context injection.
            # Reuses the caller's db session — no per-participant session opens.
            try:
                from rag_service import get_contact_briefing

                rag_account_id = input_data.get("__account_id__")
                rag_user_id = input_data.get("__user_id__")
                if not rag_account_id:
                    record_skip(type="rag.skip", reason="no_account_id", metadata={"path": "text_gen_briefing"})
                elif not rag_user_id:
                    record_skip(type="rag.skip", reason="no_user_id", metadata={"path": "text_gen_briefing"})
                if rag_account_id and rag_user_id and db is not None:
                    rag_contact_id = None
                    rag_org_id = None

                    # Skip the workflow owner's own emails so the loop resolves
                    # to the customer, not us. Fireflies typically lists the
                    # meeting organiser (the workflow owner) first, so without
                    # this filter the loop matches them and breaks before
                    # reaching the customer participant.
                    owner_user = db.query(models.User).filter(models.User.id == rag_user_id).first()
                    internal_domains = []
                    if owner_user and owner_user.internal_domains:
                        internal_domains = [
                            d.strip().lower()
                            for d in owner_user.internal_domains.split(",")
                            if d.strip()
                        ]

                    # Resolve contact from participant emails — scoped to the
                    # workflow owner's user_id, never globally. Contact.email is
                    # not unique across tenants; an unscoped lookup could match
                    # another account's contact and leak their RAG context.
                    for p in participants:
                        p_email = None
                        if isinstance(p, dict):
                            p_email = p.get("email")
                        if not p_email:
                            continue
                        email_domain = p_email.split("@")[-1].lower() if "@" in p_email else ""
                        if internal_domains and any(
                            email_domain == d or email_domain.endswith("." + d)
                            for d in internal_domains
                        ):
                            continue
                        contact = db.query(models.Contact).filter(
                            models.Contact.email == p_email,
                            models.Contact.user_id == rag_user_id,
                        ).first()
                        if contact:
                            rag_contact_id = contact.id
                            rag_org_id = contact.contact_organization_id
                            break

                    if not rag_org_id:
                        rag_org_id = input_data.get("organization_id") or input_data.get("matched_org_id")

                    if rag_contact_id:
                        # Build query context from current meeting details
                        query_context = transcript[:1000] if transcript else "meeting context"
                        briefing = await get_contact_briefing(
                            db=db,
                            account_id=rag_account_id,
                            contact_id=rag_contact_id,
                            org_id=rag_org_id,
                            query_context=query_context,
                        )
                        if briefing:
                            input_data["__relationship_context__"] = briefing
                            logger.info(f"RAG: injecting relationship context for contact {rag_contact_id} ({len(briefing)} chars)")
                    else:
                        logger.info("RAG: no contact_id resolved, skipping briefing (first meeting)")
                        record_skip(
                            type="rag.skip",
                            reason="no_contact_match",
                            metadata={
                                "path": "text_gen_briefing",
                                "internal_domains": internal_domains,
                                "candidate_emails": [
                                    p.get("email") for p in (participants or [])
                                    if isinstance(p, dict) and p.get("email")
                                ][:10],
                            },
                        )
            except Exception as e:
                logger.warning(f"RAG: contact briefing retrieval failed (non-blocking): {e}")

            # Handle participants - can be list of strings or list of dicts
            participant_names = []
            if isinstance(participants, list):
                for p in participants:
                    if isinstance(p, dict):
                        participant_names.append(p.get("name", ""))
                    elif isinstance(p, str):
                        participant_names.append(p)

            # Single API call for both extraction and summary
            result = await extract_and_summarize(
                transcript=transcript,
                extraction_points=extraction_points,
                config=config,
                participants=participant_names,
                workflow_id=workflow_id,
                input_data=input_data,
                db=db,
            )

            if result.get("status") == "error":
                return {
                    "status": "error",
                    "error": f"Text generation failed: {result.get('error', 'Unknown error')}"
                }

            extracted_info = result.get("extracted_information", {})

            return {
                "status": "success",
                "data": {
                    "summary": result.get("summary", ""),
                    "extracted_information": extracted_info,
                    "extraction_points": extraction_points,
                    "participants": participants,
                    "transcript_length": len(transcript),
                    "extraction_timestamp": datetime.utcnow().isoformat(),
                    "variables_extracted": list(extracted_info.keys())
                }
            }
            
        except Exception as e:
            logger.error(f"Summary component execution failed: {str(e)}")
            return {
                "status": "error",
                "error": f"Summary generation failed: {str(e)}"
            }
    
    @staticmethod
    async def execute_whatsapp(config: dict, input_data: dict, db: Session = None) -> dict:
        try:
            if db is None:
                return {
                    "status": "error",
                    "error": "Internal error: db session not provided to execute_whatsapp",
                }

            workflow_id = input_data.get("workflow_id")
            if not workflow_id:
                return {
                    "status": "error",
                    "error": "workflow_id not found in input_data",
                }

            workflow = db.query(models.Workflow).filter(
                models.Workflow.id == workflow_id
            ).first()

            if not workflow:
                return {
                    "status": "error",
                    "error": f"Workflow {workflow_id} not found",
                }

            user = db.query(models.User).filter(
                models.User.id == workflow.owner_id
            ).first()

            if not user:
                return {
                    "status": "error",
                    "error": "Workflow owner not found",
                }

            from whatsapp_service import WhatsAppService

            service = WhatsAppService(db, user)

            return await service.execute_whatsapp_async(
                config=config,
                input_data=input_data,
                workflow_id=workflow_id,
                execution_id=input_data.get("execution_id"),
                component_id=config.get("component_id"),
            )

        except Exception as exc:
            logger.error("WhatsApp component execution failed: %s", exc, exc_info=True)
            return {
                "status": "error",
                "error": str(exc),
            }
           
    @staticmethod
    async def execute_sms(config: dict, input_data: dict, db: Session = None) -> dict:
        try:
            if db is None:
                return {
                    "status": "error",
                    "error": "Internal error: db session not provided to execute_sms",
                }

            workflow_id = input_data.get("workflow_id")
            if not workflow_id:
                return {
                    "status": "error",
                    "error": "workflow_id not found in input_data",
                }

            workflow = db.query(models.Workflow).filter(
                models.Workflow.id == workflow_id
            ).first()

            if not workflow:
                return {
                    "status": "error",
                    "error": f"Workflow {workflow_id} not found",
                }

            user = db.query(models.User).filter(
                models.User.id == workflow.owner_id
            ).first()

            if not user:
                return {
                    "status": "error",
                    "error": "Workflow owner not found",
                }

            from sms_service import SMSService

            service = SMSService(db, user)

            return await service.execute_sms_async(
                config=config,
                input_data=input_data,
                workflow_id=workflow_id,
                execution_id=input_data.get("execution_id"),
                component_id=config.get("component_id"),
            )

        except Exception as exc:
            logger.error("SMS component execution failed: %s", exc, exc_info=True)
            return {
                "status": "error",
                "error": str(exc),
            }
    
    @staticmethod
    async def execute_email(config: dict, input_data: dict, db: Session = None) -> dict:
        """Execute email component with AI generation and optional queuing (based on test_mode)"""
        from email_service import queue_email
        from datetime import datetime, timedelta

        try:
            # Check if this is a test execution
            test_mode = input_data.get("test_mode", False)

            # Get email configuration
            email_prompt = config.get("prompt", "Write a professional follow-up email based on the meeting summary.")
            subject_prompt = config.get("subject_prompt")  # Optional custom subject prompt
            recipient_field = config.get("recipient_field", "recipient_email")
            send_as = config.get("send_as", "new_thread")
            thread_parent_component_id = config.get("thread_parent_component_id")
            is_threaded_reply = send_as == "reply_to_component" and bool(thread_parent_component_id)

            # Extract workflow_id and other IDs from input_data
            workflow_id = input_data.get("workflow_id")
            execution_id = input_data.get("execution_id")  # May be passed in
            component_id = config.get("component_id")  # May be in config

            # Pass component config for resource manifest builder
            input_data["__component_config__"] = config

            # RAG (Phase 4): resolve contact_id + org_id + sequence used_chunk_ids so
            # get_email_context() can filter retrieval and apply the diversity penalty.
            # Reuses the caller's db session.
            if db is not None:
                try:
                    # Resolve contact_id from recipient or participants
                    _recipient_email = input_data.get("recipient_email")
                    _rag_user_id = input_data.get("__user_id__")
                    if not _recipient_email:
                        # Skip internal domains so the email-gen RAG context is
                        # scoped to the customer, not us. Without this the
                        # fallback may pick the meeting organiser (workflow
                        # owner) and pull our own org's chunks.
                        _owner_user = db.query(models.User).filter(
                            models.User.id == _rag_user_id
                        ).first() if _rag_user_id else None
                        _internal_domains = []
                        if _owner_user and _owner_user.internal_domains:
                            _internal_domains = [
                                d.strip().lower()
                                for d in _owner_user.internal_domains.split(",")
                                if d.strip()
                            ]
                        for _p in input_data.get("participants", []) or []:
                            if not (isinstance(_p, dict) and _p.get("email")):
                                continue
                            _p_email = _p["email"]
                            _domain = _p_email.split("@")[-1].lower() if "@" in _p_email else ""
                            if _internal_domains and any(
                                _domain == d or _domain.endswith("." + d)
                                for d in _internal_domains
                            ):
                                continue
                            _recipient_email = _p_email
                            break
                    if _recipient_email and _rag_user_id:
                        # Scope Contact lookup to the workflow owner — email is
                        # not unique across tenants, so a global query would
                        # attach another account's contact_id/org_id to the
                        # execution and pull their chunks into RAG retrieval.
                        _contact = db.query(models.Contact).filter(
                            models.Contact.email == _recipient_email,
                            models.Contact.user_id == _rag_user_id,
                        ).first()
                        if _contact:
                            input_data["__contact_id__"] = _contact.id
                            if _contact.contact_organization_id:
                                input_data["__org_id__"] = _contact.contact_organization_id

                    # Smart Context Diversity toggle (per-workflow, default ON)
                    if workflow_id:
                        _wf = db.query(models.Workflow).filter(models.Workflow.id == workflow_id).first()
                        if _wf and isinstance(_wf.rag_settings, dict):
                            input_data["__rag_apply_diversity__"] = _wf.rag_settings.get("smart_context_diversity", True)

                    # Pull used_chunk_ids from earlier emails in the same sequence_run
                    _sequence_run_id = input_data.get("sequence_run_id")
                    if _sequence_run_id:
                        _prior_used: List[int] = []
                        _prior_rows = db.query(models.EmailQueue).filter(
                            models.EmailQueue.sequence_run_id == _sequence_run_id,
                            models.EmailQueue.used_chunk_ids.isnot(None),
                        ).all()
                        for _row in _prior_rows:
                            if isinstance(_row.used_chunk_ids, list):
                                _prior_used.extend(int(x) for x in _row.used_chunk_ids if isinstance(x, (int, str)))
                        if _prior_used:
                            input_data["__sequence_used_chunk_ids__"] = list(dict.fromkeys(_prior_used))
                except Exception as _e:
                    logger.debug(f"[RAG] Failed to resolve contact/diversity context: {_e}")

            # Substitute variables in prompt using unified substitution function
            from variable_substitution import substitute_variables

            component_outputs = input_data.get("__component_outputs__", {})
            email_prompt_processed = substitute_variables(
                email_prompt,
                input_data,
                component_outputs,
                component_name="Email Component"
            )

            # Extract recipient email from input data
            recipient_email = input_data.get(recipient_field)
            recipient_name = input_data.get("recipient_name")

            # Try to extract from participants if not directly provided
            if not recipient_email:
                participants = input_data.get("participants", [])
                # Get the first external participant
                for participant in participants:
                    if isinstance(participant, dict):
                        email = participant.get("email", "")
                        if email:
                            recipient_email = email
                            recipient_name = participant.get("name")
                            break

            if not recipient_email:
                return {
                    "status": "error",
                    "error": f"No recipient email found. Please ensure '{recipient_field}' is in the input data or configure the recipient field in the email component settings."
                }

            # Initialize variables before AI generation try/except to avoid NameError in fallback path
            pre_send_check_config = None
            timing_reason = None
            generation_reason = None
            resources_used = None

            # Generate complete email with subject, body, and optimal send time using AI
            try:
                from ai_service import generate_email_with_metadata

                # Build delivery settings for AI
                delivery_settings = {
                    "send_timing": config.get("send_timing", "ai_optimized"),
                    "ai_optimization_target": config.get("ai_optimization_target", "open_rates"),
                    "ai_time_window": config.get("ai_time_window", "24_hours"),
                    "business_hours_only": config.get("business_hours_only", True),
                    "respect_timezone": config.get("respect_timezone", True),
                    "avoid_weekends": config.get("avoid_weekends", False)
                }

                # Generate email with metadata (subject, body, time)
                # The email_prompt_processed has variables substituted, and input_data
                # provides full pipeline context (summary, extracted info, participants)
                email_metadata = await generate_email_with_metadata(
                    email_prompt_processed,
                    delivery_settings,
                    workflow_id,
                    input_data,
                    db=db,
                )

                email_subject = (
                    email_metadata.get("email_subject", "Follow-up")
                    if not is_threaded_reply
                    else ""
                )
                email_body = email_metadata.get("email_body", "")
                email_time = email_metadata.get("email_time", "As soon as possible")
                timing_reason = email_metadata.get("timing_reason")
                generation_reason = email_metadata.get("generation_reason")
                resources_used = email_metadata.get("resources_used")
                if is_threaded_reply:
                    logger.info("[EMAIL] Threaded reply configured; no subject generated up front")
                else:
                    logger.info(f"[EMAIL] AI-generated subject: {email_subject}")
                logger.info(f"[EMAIL] AI-generated body ({len(email_body)} chars):\n{email_body[:1000]}")
                logger.info(f"[EMAIL] AI resources_used: {resources_used}")

                # Store resources_used in pre_send_check_config for send-time attachment resolution
                if resources_used:
                    if not pre_send_check_config:
                        pre_send_check_config = {}
                    pre_send_check_config["resources_used"] = resources_used

            except Exception as e:
                # Fallback to basic generation — only if AI call itself failed
                logger.error(f"[EMAIL] AI email generation FAILED, using fallback: {str(e)}", exc_info=True)
                email_subject = "" if is_threaded_reply else "Follow-up from our meeting"
                email_body = f"""Dear {recipient_name or 'there'},

Thank you for taking the time to meet with me. I wanted to follow up on our discussion.

Based on our conversation, I will send you additional details shortly.

Please let me know if you have any questions in the meantime.

Best regards"""
                email_time = "As soon as possible"

            # Resolve resource:ID placeholders to actual URLs (outside main try/except so failures don't nuke the body)
            import re
            if "resource:" in email_body and db is not None:
                def _resolve_resource_link(match):
                    resource_id = match.group(1)
                    try:
                        account_id = input_data.get("__account_id__")
                        query = db.query(models.Resource).filter(
                            models.Resource.id == int(resource_id)
                        )
                        if account_id:
                            query = query.filter(models.Resource.account_id == account_id)
                        res = query.first()
                        if res and res.type == "link" and res.url:
                            logger.info(f"[RESOURCES] Resolved resource:{resource_id} → {res.url}")
                            return res.url
                        else:
                            logger.warning(f"[RESOURCES] Could not resolve resource:{resource_id} (not found or not a link)")
                    except Exception as resolve_err:
                        logger.error(f"[RESOURCES] Error resolving resource:{resource_id}: {resolve_err}")
                    return match.group(0)  # Return original if resolution fails

                email_body = re.sub(r'resource:(\d+)', _resolve_resource_link, email_body)
                logger.info(f"[EMAIL] Body after resource resolution ({len(email_body)} chars):\n{email_body[:1000]}")

            # If custom subject_prompt is provided, generate subject separately
            if subject_prompt and subject_prompt.strip() and not is_threaded_reply:
                logger.info("Custom subject prompt provided, generating subject line separately")
                try:
                    from ai_service import generate_email_subject

                    # Process variables in subject_prompt using unified substitution
                    subject_prompt_processed = substitute_variables(
                        subject_prompt,
                        input_data,
                        component_outputs,
                        component_name="Email Component (Subject)"
                    )

                    # Generate custom subject with email body as context
                    custom_subject = await generate_email_subject(
                        subject_prompt_processed,
                        email_body,
                        delivery_settings,
                        workflow_id,
                        db=db,
                    )

                    # Override the auto-generated subject
                    email_subject = custom_subject
                    logger.info(f"Custom subject generated: {email_subject}")

                except Exception as subject_error:
                    logger.error(f"Custom subject generation failed, using auto-generated subject: {str(subject_error)}", exc_info=True)
                    # Keep the auto-generated subject from email_metadata

            # Calculate scheduled_at based on send timing
            send_timing = config.get("send_timing", "ai_optimized")
            scheduled_at = datetime.utcnow()

            if send_timing == "fixed_delay":
                delay_value = config.get("delay_value", 30)
                delay_unit = config.get("delay_unit", "minutes")

                if delay_unit == "minutes":
                    scheduled_at += timedelta(minutes=delay_value)
                elif delay_unit == "hours":
                    scheduled_at += timedelta(hours=delay_value)
                elif delay_unit == "days":
                    scheduled_at += timedelta(days=delay_value)

            elif send_timing == "ai_optimized":
                # For AI optimized, use a smart default (2 hours) for now
                # The email_time field contains the AI's recommendation
                scheduled_at += timedelta(hours=2)

            # TEST MODE: Return generated fields without queuing
            if test_mode:
                logger.info(f"Email component in TEST MODE - not queuing email")

                # Validate that variables were substituted correctly
                import re
                missing_variables = []

                # Check email body for unresolved variables
                body_vars = re.findall(r'\{\{([^}]+)\}\}', email_body)
                if body_vars:
                    missing_variables.extend([f"{{{{{{{{}}}}}}}}".format(v) for v in body_vars])
                    logger.warning(f"Unresolved variables found in email body: {body_vars}")

                # Check email subject for unresolved variables
                if email_subject:
                    subject_vars = re.findall(r'\{\{([^}]+)\}\}', email_subject)
                    if subject_vars:
                        missing_variables.extend([f"{{{{{{{{}}}}}}}}".format(v) for v in subject_vars])
                        logger.warning(f"Unresolved variables found in email subject: {subject_vars}")

                # Return warning status if variables are unresolved
                if missing_variables:
                    return {
                        "status": "warning",
                        "data": {
                            "test_mode": True,
                            "email_subject": email_subject,
                            "email_body": email_body,
                            "email_time": email_time,
                            "recipient": recipient_email,
                            "recipient_name": recipient_name,
                            "timing_reason": timing_reason,
                            "generation_reason": generation_reason,
                            "missing_variables": list(set(missing_variables)),
                            "warning": f"⚠️ Variables not found: {', '.join(list(set(missing_variables)))}",
                            "message": "Email generated but contains unresolved variables. Please check your variable names and ensure they exist in previous components."
                        }
                    }

                # All variables resolved successfully
                response_data = {
                    "status": "success",
                    "data": {
                        "test_mode": True,
                        "email_subject": email_subject,
                        "email_body": email_body,
                        "email_time": email_time,
                        "recipient": recipient_email,
                        "recipient_name": recipient_name,
                        "timing_reason": timing_reason,
                        "generation_reason": generation_reason,
                        "message": "Email generated successfully (test mode - not queued)"
                    }
                }
                logger.info(f"[EMAIL] Final response to frontend — subject: {email_subject}")
                logger.info(f"[EMAIL] Final response to frontend — body ({len(email_body)} chars):\n{email_body[:1000]}")
                return response_data

            # LIVE MODE: Queue the email AND return generated fields for logging
            if not workflow_id:
                return {
                    "status": "error",
                    "error": "workflow_id not found in input_data"
                }

            if db is None:
                return {
                    "status": "error",
                    "error": "Internal error: db session not provided to execute_email"
                }
            workflow = db.query(models.Workflow).filter(models.Workflow.id == workflow_id).first()
            if not workflow:
                return {
                    "status": "error",
                    "error": f"Workflow {workflow_id} not found"
                }
            user_id = workflow.owner_id

            # Get CC and BCC if configured and substitute variables
            cc_raw = config.get("cc", [])
            bcc_raw = config.get("bcc", [])

            # Apply variable substitution to CC and BCC email addresses
            cc = []
            if cc_raw:
                for email in cc_raw:
                    if email:  # Skip empty strings
                        substituted_email = substitute_variables(
                            email,
                            input_data,
                            component_outputs,
                            component_name="Email Component (CC)"
                        )
                        cc.append(substituted_email)
                        logger.info(f"CC email: '{email}' → '{substituted_email}'")

            bcc = []
            if bcc_raw:
                for email in bcc_raw:
                    if email:  # Skip empty strings
                        substituted_email = substitute_variables(
                            email,
                            input_data,
                            component_outputs,
                            component_name="Email Component (BCC)"
                        )
                        bcc.append(substituted_email)
                        logger.info(f"BCC email: '{email}' → '{substituted_email}'")

            # Build pre-send check params from component config
            # New multi-group format (pre_send_check) takes precedence
            pre_send_check_config = None
            pre_send_check_field = None
            pre_send_check_operator = None
            pre_send_check_value = None
            pre_send_check_context = None

            new_format = config.get("pre_send_check")
            if new_format and (new_format.get("condition_groups") or new_format.get("ai_filter")):
                participant_emails = [
                    p.get("email") for p in input_data.get("participants", [])
                    if isinstance(p, dict) and p.get("email")
                ]
                context = {"participant_emails": participant_emails}
                # Attach input_data for AI filter analysis (exclude large internal keys)
                if new_format.get("ai_filter") and new_format["ai_filter"].get("enabled"):
                    ai_input = {k: v for k, v in input_data.items() if k != "__component_outputs__"}
                    context["input_data"] = ai_input
                pre_send_check_config = {
                    **new_format,
                    "context": context,
                }
            else:
                # Fall back to old flat field format
                pre_send_check_field = config.get("pre_send_check_field") or None
                pre_send_check_operator = config.get("pre_send_check_operator") if pre_send_check_field else None
                pre_send_check_value = config.get("pre_send_check_value") if pre_send_check_field else None
                if pre_send_check_field:
                    participant_emails = [
                        p.get("email") for p in input_data.get("participants", [])
                        if isinstance(p, dict) and p.get("email")
                    ]
                    pre_send_check_context = {"participant_emails": participant_emails}

            # Queue the email
            result = await queue_email(
                db=db,
                user_id=user_id,
                recipient_email=recipient_email,
                subject=email_subject,
                body=email_body,
                scheduled_at=scheduled_at,
                workflow_id=workflow_id,
                execution_id=execution_id,
                component_id=component_id,
                recipient_name=recipient_name,
                cc=cc if cc else None,
                bcc=bcc if bcc else None,
                max_retries=config.get("max_retries", 3),
                pre_send_check_field=pre_send_check_field,
                pre_send_check_operator=pre_send_check_operator,
                pre_send_check_value=pre_send_check_value,
                pre_send_check_context=pre_send_check_context,
                pre_send_check_config=pre_send_check_config,
                timing_reason=timing_reason,
                generation_reason=generation_reason,
                thread_parent_component_id=thread_parent_component_id if is_threaded_reply else None,
            )

            if result["success"]:
                # RAG (Phase 4): persist used_chunk_ids on the queued email and embed the generated email
                try:
                    _email_id = result.get("email_id")
                    _chunk_ids = input_data.get("__rag_used_chunk_ids__")
                    if _email_id and _chunk_ids:
                        _eq = db.query(models.EmailQueue).filter(models.EmailQueue.id == _email_id).first()
                        if _eq:
                            _eq.used_chunk_ids = list(_chunk_ids)
                            db.commit()

                    _account_id = input_data.get("__account_id__")
                    _contact_id = input_data.get("__contact_id__")
                    _org_id = input_data.get("__org_id__")
                    _seq_run_id = input_data.get("sequence_run_id")
                    if _account_id and _email_id:
                        from rag_service import store_generated_email
                        await store_generated_email(
                            account_id=_account_id,
                            email_queue_id=_email_id,
                            subject=email_subject,
                            body=email_body,
                            contact_id=_contact_id,
                            org_id=_org_id,
                            sequence_run_id=_seq_run_id,
                            workflow_id=workflow_id,
                        )
                        logger.info(f"[RAG] Embedded generated email {_email_id} (contact={_contact_id}, org={_org_id})")
                except Exception as _rag_err:
                    logger.warning(f"[RAG] Post-queue embedding/tracking failed: {_rag_err}")

                return {
                    "status": "success",
                    "data": {
                        "test_mode": False,
                        "email_queued": True,
                        "email_id": result["email_id"],
                        "email_subject": email_subject,
                        "email_body": email_body,
                        "email_time": email_time,
                        "recipient": recipient_email,
                        "recipient_name": recipient_name,
                        "scheduled_at": scheduled_at.isoformat(),
                        "send_timing": send_timing,
                        "message": result["message"],
                        "timing_reason": timing_reason,
                        "generation_reason": generation_reason,
                    }
                }
            else:
                return {
                    "status": "error",
                    "error": f"Failed to queue email: {result.get('error', 'Unknown error')}"
                }

        except Exception as e:
            logger.error(f"Email component execution failed: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "error": f"Email execution failed: {str(e)}"
            }

    @staticmethod
    async def execute_conditional_logic(config: dict, input_data: dict, db: Session = None) -> dict:
        """Execute conditional logic component for pipeline flow control"""
        from conditional_logic import evaluate_single_condition, fetch_deal_crm_data

        # Get configuration
        data_source = config.get("data_source", "pipedrive")
        condition_groups = config.get("condition_groups", [])
        group_logic = config.get("group_logic", "AND")
        action_on_match = config.get("action_on_match", "continue")

        # Get workflow_id from input_data
        workflow_id = input_data.get("workflow_id")
        if not workflow_id:
            return {
                "status": "error",
                "error": "workflow_id not found in input_data"
            }

        if db is None:
            return {
                "status": "error",
                "error": "Internal error: db session not provided to execute_conditional_logic"
            }

        # Fetch real CRM data from Pipedrive via shared module
        crm_data = {}

        workflow = db.query(models.Workflow).filter(models.Workflow.id == workflow_id).first()
        if not workflow:
            return {
                "status": "error",
                "error": f"Workflow {workflow_id} not found"
            }
        user_id = workflow.owner_id

        # Extract participant emails from input_data
        participants = input_data.get("participants", [])
        participant_emails = [
            p.get("email", "") if isinstance(p, dict) else ""
            for p in participants
        ]
        participant_emails = [e for e in participant_emails if e]

        # Use shared module for deal lookup (handles internal domain filtering)
        crm_data = await fetch_deal_crm_data(db, user_id, participant_emails)

        if not crm_data:
            if not participant_emails:
                return {
                    "status": "error",
                    "error": "No external participants found. Conditional Logic requires external contact emails to look up deal data from Pipedrive. Please ensure your workflow has external participants or configure internal domains in Settings."
                }
            else:
                # Get external emails for error message (recompute for display)
                user = db.query(models.User).filter(models.User.id == user_id).first()
                internal_domains = []
                if user and user.internal_domains:
                    internal_domains = [d.strip().lower() for d in user.internal_domains.split(",") if d.strip()]
                external_emails = [
                    e for e in participant_emails
                    if not any(domain in e.split("@")[-1].lower() for domain in internal_domains)
                ]
                if not external_emails:
                    return {
                        "status": "error",
                        "error": "No external participants found. Conditional Logic requires external contact emails to look up deal data from Pipedrive. Please ensure your workflow has external participants or configure internal domains in Settings."
                    }
                return {
                    "status": "error",
                    "error": f"No Pipedrive deal found for external participants: {', '.join(external_emails)}. Please ensure there's a deal associated with these contacts in Pipedrive."
                }

        # Evaluate conditions using real CRM data and shared evaluation function
        group_results = []
        for group in condition_groups:
            condition_results = []
            for condition in group.get("conditions", []):
                field = condition.get("field")
                operator = condition.get("operator")
                value = condition.get("value")

                field_value = crm_data.get(field)

                # Special handling for stage field to support both stage IDs and stage names
                if field == "stage":
                    if value and value.isdigit():
                        field_value = crm_data.get("stage_id")
                    else:
                        field_value = crm_data.get("stage")

                # Use shared evaluation function
                result = evaluate_single_condition(field_value, operator, value)

                condition_results.append({
                    "field": field,
                    "operator": operator,
                    "value": value,
                    "field_value": field_value,
                    "result": result
                })

            # Apply group logic (AND/OR)
            if group.get("logic") == "AND":
                group_result = all(c["result"] for c in condition_results)
            else:
                group_result = any(c["result"] for c in condition_results)

            group_results.append({
                "group_id": group.get("id"),
                "logic": group.get("logic"),
                "conditions": condition_results,
                "result": group_result
            })

        # Apply overall group logic
        if group_logic == "AND":
            overall_result = all(g["result"] for g in group_results)
        else:
            overall_result = any(g["result"] for g in group_results)

        # Determine pipeline action
        should_continue = (overall_result and action_on_match == "continue") or (not overall_result and action_on_match == "stop")

        return {
            "status": "success",
            "data": {
                "data_source": data_source,
                "crm_data": crm_data,
                "evaluation_results": {
                    "groups": group_results,
                    "group_logic": group_logic,
                    "overall_result": overall_result
                },
                "action": action_on_match,
                "pipeline_continues": should_continue,
                "message": f"Conditions {'matched' if overall_result else 'not matched'} - Pipeline will {'continue' if should_continue else 'stop'}"
            }
        }
    
    @staticmethod
    async def execute_action(config: dict, input_data: dict, db: Session = None) -> dict:
        """Execute action component to push data to external systems"""
        from pipedrive_service import create_activity, update_deal, add_note
        from webhook_service import send_webhook, validate_webhook_config

        system = config.get("system", "pipedrive")
        action = config.get("action")

        # Handle webhook system
        if system == "custom_webhook":
            # Validate webhook configuration
            is_valid, error_message = validate_webhook_config(config)
            if not is_valid:
                return {
                    "status": "error",
                    "error": f"Invalid webhook configuration: {error_message}"
                }

            # Prepare variables for substitution
            variables = {}

            # Include extracted_information if available
            if "extracted_information" in input_data:
                variables.update(input_data["extracted_information"])

            # Include top-level fields from input_data
            for key, value in input_data.items():
                if key not in ["workflow_id", "test_mode", "extracted_information"]:
                    variables[key] = value

            # Send webhook
            webhook_result = send_webhook(
                url=config.get("webhook_url"),
                method=config.get("http_method", "POST"),
                headers={h.get("name"): h.get("value") for h in config.get("custom_headers", []) if h.get("name")},
                body_template=config.get("body_template"),
                variables=variables,
                auth_type=config.get("auth_type", "none"),
                auth_config=config.get("auth_config", {}),
                dry_run=input_data.get("test_mode") and config.get("test_dry_run", False)
            )

            if webhook_result.get("success"):
                return {
                    "status": "success",
                    "data": {
                        "system": "custom_webhook",
                        "webhook_result": webhook_result
                    }
                }
            else:
                return {
                    "status": "error",
                    "error": webhook_result.get("message", "Webhook request failed")
                }

        # Handle Pipedrive system
        if system != "pipedrive":
            return {
                "status": "error",
                "error": f"System '{system}' is not yet supported. Only Pipedrive and Custom Webhook are currently available."
            }

        # Get user_id from input_data (should be passed from workflow execution)
        workflow_id = input_data.get("workflow_id")
        if not workflow_id:
            return {
                "status": "error",
                "error": "workflow_id not found in input_data"
            }

        # Get user_id from workflow
        if db is None:
            return {
                "status": "error",
                "error": "Internal error: db session not provided to execute_action"
            }
        try:
            workflow = db.query(models.Workflow).filter(models.Workflow.id == workflow_id).first()
            if not workflow:
                return {
                    "status": "error",
                    "error": f"Workflow {workflow_id} not found"
                }
            user_id = workflow.owner_id

            # Map source fields to CRM fields
            standard_fields = config.get("standard_fields", [])
            custom_field_mappings = config.get("custom_field_mappings", [])

            # Debug logging
            logger.info(f"Action component config - standard_fields: {standard_fields}")
            logger.info(f"Action component config - custom_field_mappings: {custom_field_mappings}")
            logger.info(f"Input data keys: {list(input_data.keys())}")
            if "extracted_information" in input_data:
                logger.info(f"Extracted information keys: {list(input_data['extracted_information'].keys())}")
            else:
                logger.warning("No 'extracted_information' found in input_data")

            # Build mapped data from input_data
            mapped_data = {}

            # Map standard fields
            for mapping in standard_fields:
                field_name = mapping.get("fieldName")
                source_field = mapping.get("sourceField")

                logger.info(f"Processing standard field mapping: {field_name} <- {source_field}")

                if field_name and source_field:
                    # Try to get value from extracted_information first, then from top-level input_data
                    value = None
                    if "extracted_information" in input_data:
                        value = input_data["extracted_information"].get(source_field)
                        logger.info(f"  Checked extracted_information['{source_field}']: {value}")
                    if value is None:
                        value = input_data.get(source_field)
                        logger.info(f"  Checked input_data['{source_field}']: {value}")

                    if value is not None:
                        # Convert complex types (dict, list) to JSON string for Pipedrive
                        if isinstance(value, (dict, list)):
                            value = json.dumps(value, ensure_ascii=False)
                            logger.info(f"  Converted complex value to JSON string")
                        mapped_data[field_name] = value
                        logger.info(f"  ✓ Mapped {field_name} = {value}")
                    else:
                        logger.warning(f"  ✗ No value found for source field '{source_field}'")

            # Map custom fields
            for mapping in custom_field_mappings:
                crm_field = mapping.get("crmField")
                source_field = mapping.get("sourceField")

                logger.info(f"Processing custom field mapping: {crm_field} <- {source_field}")

                if crm_field and source_field:
                    value = None
                    if "extracted_information" in input_data:
                        value = input_data["extracted_information"].get(source_field)
                        logger.info(f"  Checked extracted_information['{source_field}']: {value}")
                    if value is None:
                        value = input_data.get(source_field)
                        logger.info(f"  Checked input_data['{source_field}']: {value}")

                    if value is not None:
                        # Convert complex types (dict, list) to JSON string for Pipedrive
                        if isinstance(value, (dict, list)):
                            value = json.dumps(value, ensure_ascii=False)
                            logger.info(f"  Converted complex value to JSON string")
                        mapped_data[crm_field] = value
                        logger.info(f"  ✓ Mapped {crm_field} = {value}")
                    else:
                        logger.warning(f"  ✗ No value found for source field '{source_field}'")

            # Automatic deal lookup based on participant emails
            # Only perform if deal_id is not already provided
            if "deal_id" not in mapped_data:
                from pipedrive_service import find_latest_deal_by_emails

                # Get user's internal domains
                user = db.query(models.User).filter(models.User.id == user_id).first()
                internal_domains = []
                if user and user.internal_domains:
                    internal_domains = [d.strip().lower() for d in user.internal_domains.split(",") if d.strip()]

                # Extract external participant emails
                participants = input_data.get("participants", [])
                external_emails = []

                for participant in participants:
                    email = participant.get("email", "") if isinstance(participant, dict) else ""
                    if email:
                        email_domain = email.split("@")[-1].lower() if "@" in email else ""
                        # Exclude internal emails
                        if not any(domain in email_domain for domain in internal_domains):
                            external_emails.append(email)

                # Lookup deal if we have external emails
                if external_emails:
                    logger.info(f"Looking up deal for external emails: {external_emails}")
                    deal_lookup_result = await find_latest_deal_by_emails(db, user_id, external_emails)

                    if deal_lookup_result.get("success") and deal_lookup_result.get("deal_id"):
                        # Automatically inject deal_id
                        mapped_data["deal_id"] = deal_lookup_result["deal_id"]
                        logger.info(f"Auto-injected deal_id: {deal_lookup_result['deal_id']} (from {deal_lookup_result['person_email']})")
                    else:
                        logger.warning(f"No deal found for emails: {external_emails}")
                else:
                    logger.info(f"No external emails found to lookup deal (all {len(participants)} participants are internal)")

            # Execute the appropriate action
            if action == "create_activity":
                # Create activity requires at minimum a subject
                if "subject" not in mapped_data:
                    return {
                        "status": "error",
                        "error": "Missing required field 'subject' for create_activity action"
                    }

                result = await create_activity(db, user_id, **mapped_data)

            elif action == "update_deal":
                # Update deal requires deal_id
                if "deal_id" not in mapped_data:
                    # Provide helpful error message
                    error_msg = "Missing required field 'deal_id' for update_deal action. "
                    if not external_emails:
                        error_msg += "No external participant emails found for automatic deal lookup. "
                        if participants:
                            error_msg += f"All {len(participants)} participants appear to be internal (filtered by your internal domains settings). "
                        else:
                            error_msg += "No participants found in the input data. "
                        error_msg += "Either configure internal domains in Settings, or manually map a deal_id field."
                    else:
                        error_msg += f"Automatic deal lookup failed for emails: {', '.join(external_emails)}. No matching deal found in Pipedrive. Please create a deal for this contact first, or manually map a deal_id field."

                    return {
                        "status": "error",
                        "error": error_msg
                    }

                # Check if there are any fields to update besides deal_id
                fields_to_update = {k: v for k, v in mapped_data.items() if k != "deal_id"}
                if not fields_to_update:
                    return {
                        "status": "error",
                        "error": "No fields configured to update. Please configure field mappings in the Action component (Standard Field Mapping or Custom Field Mapping). For example, map 'Title' to a Text Generation output like 'deal_summary'."
                    }

                result = await update_deal(db, user_id, **mapped_data)

            elif action == "add_note":
                # Add note requires content and at least one attachment entity
                if "content" not in mapped_data:
                    return {
                        "status": "error",
                        "error": "Missing required field 'content' for add_note action"
                    }

                result = await add_note(db, user_id, **mapped_data)

            else:
                return {
                    "status": "error",
                    "error": f"Unknown action type: {action}"
                }

            # Return result
            if result.get("success"):
                return {
                    "status": "success",
                    "data": {
                        "system": system,
                        "action": action,
                        "result": result,
                        "mapped_fields": list(mapped_data.keys())
                    }
                }
            else:
                return {
                    "status": "error",
                    "error": result.get("error", "Unknown error from Pipedrive API")
                }

        except Exception as e:
            logger.error(f"Action execution error: {str(e)}", exc_info=True)
            return {"status": "error", "error": str(e)}

    @staticmethod
    async def execute_company_name_matcher(config: dict, input_data: dict, db: Session = None) -> dict:
        """
        Execute advanced matching component - matches/creates organizations and contacts.

        Flow:
        1. Extract company name using AI
        2. Get organizer_email and filter external participants
        3. Match organizer email to Pipedrive user (for ownership)
        4. Match or CREATE organization in Pipedrive
        5. Create persons for external participants, linked to org
        6. Return comprehensive result with all created entities
        """
        from pipedrive_service import (
            get_all_organizations,
            create_organization,
            create_person,
            find_person_by_email,
            get_pipedrive_users_with_email
        )
        from ai_service import analyze_with_ai, match_organization_with_ai

        try:
            # Get configuration
            ai_prompt = config.get("ai_prompt", "Extract the company name from the data")
            output_variable_name = config.get("output_variable_name", "matched_org_id")
            create_if_not_found = config.get("create_if_not_found", True)
            create_contacts = config.get("create_contacts", True)

            # Get workflow_id from input_data
            workflow_id = input_data.get("workflow_id")
            if not workflow_id:
                return {"status": "error", "error": "workflow_id not found in input_data"}

            if db is None:
                return {"status": "error", "error": "Internal error: db session not provided to execute_company_name_matcher"}

            # Get user_id and internal_domains from workflow/user
            try:
                workflow = db.query(models.Workflow).filter(models.Workflow.id == workflow_id).first()
                if not workflow:
                    return {"status": "error", "error": f"Workflow {workflow_id} not found"}
                user_id = workflow.owner_id

                # Get user's internal domains for filtering participants
                user = db.query(models.User).filter(models.User.id == user_id).first()
                internal_domains = []
                if user and user.internal_domains:
                    internal_domains = [d.strip().lower() for d in user.internal_domains.split(",") if d.strip()]

                logger.info(f"Advanced matching started for user {user_id}, workflow {workflow_id}")
                logger.info(f"Internal domains configured: {internal_domains}")

                # Step 1: Extract company name using AI
                logger.info("Step 1: Extracting company name using AI prompt...")
                company_name_response = await analyze_with_ai(ai_prompt, input_data)
                company_name = company_name_response.strip()

                if not company_name:
                    return {"status": "error", "error": "AI could not determine company name from the provided prompt/data"}

                # Validate company name - reject invalid/placeholder names
                invalid_names = ["unknown", "n/a", "na", "none", "null", "undefined", "tbd", "not available", "not specified"]
                if company_name.lower() in invalid_names:
                    logger.warning(f"Invalid company name detected: '{company_name}' - skipping org creation")
                    return {
                        "status": "error",
                        "error": f"Cannot process invalid company name: '{company_name}'. Please ensure the transcript contains a valid company/organization name.",
                        "data": {"extracted_name": company_name, "reason": "invalid_name"}
                    }

                logger.info(f"Company name determined: {company_name}")

                # Step 2: Get organizer_email and filter external participants
                organizer_email = input_data.get("organizer_email", "").lower().strip()
                participants = input_data.get("participants", [])

                external_participants = []
                for participant in participants:
                    if isinstance(participant, dict):
                        email = participant.get("email", "").lower().strip()
                        name = participant.get("name", "")
                    else:
                        email = ""
                        name = ""

                    if email:
                        email_domain = email.split("@")[-1].lower() if "@" in email else ""
                        # Check if NOT an internal domain
                        is_internal = any(domain in email_domain for domain in internal_domains)
                        if not is_internal:
                            external_participants.append({"name": name or email.split("@")[0], "email": email})

                logger.info(f"Found {len(external_participants)} external participants (filtered from {len(participants)} total)")

                # Step 3: Match organizer email to Pipedrive user (for ownership)
                owner_id = None
                if organizer_email:
                    logger.info(f"Step 3: Matching organizer {organizer_email} to Pipedrive user...")
                    users_result = await get_pipedrive_users_with_email(db, user_id)
                    if users_result.get("success"):
                        for pd_user in users_result.get("users", []):
                            if pd_user.get("email", "").lower() == organizer_email:
                                owner_id = pd_user.get("id")
                                logger.info(f"Matched organizer to Pipedrive user ID {owner_id}")
                                break
                        if not owner_id:
                            logger.info(f"Organizer {organizer_email} not found in Pipedrive users")

                # Step 4: Fetch and match organization
                logger.info("Step 4: Fetching organizations from Pipedrive...")
                orgs_result = await get_all_organizations(db, user_id)

                if not orgs_result.get("success"):
                    return {"status": "error", "error": orgs_result.get("error", "Failed to fetch organizations from Pipedrive")}

                organizations = orgs_result.get("organizations", [])
                logger.info(f"Fetched {len(organizations)} organizations from Pipedrive")

                org_id = None
                org_name = None
                org_created = False
                match_confidence = None
                match_reasoning = ""

                # Try to match organization using AI (only if we have orgs to match against)
                if organizations:
                    logger.info("Step 5: Matching organization using AI...")
                    match_context = {"extracted_information": input_data.get("extracted_information", {})}

                    match_result = await match_organization_with_ai(
                        organizations,
                        company_name,
                        match_context,
                        workflow_id,
                        db=db,
                    )

                    if match_result.get("success") and match_result.get("organization_id"):
                        org_id = match_result["organization_id"]
                        match_confidence = match_result.get("confidence")
                        match_reasoning = match_result.get("reasoning", "")

                        # Find the organization name from the list
                        for org in organizations:
                            if org.get("id") == org_id:
                                org_name = org.get("name", "Unknown")
                                break

                        logger.info(f"Matched existing organization: {org_name} (ID: {org_id}, confidence: {match_confidence})")

                # Step 5b: Create organization if not found and enabled
                if not org_id and create_if_not_found:
                    logger.info(f"No match found. Creating organization: {company_name}")
                    create_result = await create_organization(
                        db, user_id,
                        name=company_name,
                        owner_id=owner_id
                    )

                    if create_result.get("success"):
                        org_id = create_result["organization_id"]
                        org_name = company_name
                        org_created = True
                        match_confidence = "created"
                        match_reasoning = "Organization was created because no match was found"
                        logger.info(f"Created new organization: {org_name} (ID: {org_id})")
                    else:
                        logger.error(f"Failed to create organization: {create_result.get('error')}")
                        return {
                            "status": "error",
                            "error": f"Failed to create organization: {create_result.get('error')}",
                            "data": {"company_name": company_name}
                        }

                if not org_id:
                    return {
                        "status": "error",
                        "error": "Could not match or create organization",
                        "data": {"company_name": company_name, "create_if_not_found": create_if_not_found}
                    }

                # Step 6: Create persons for external participants
                created_persons = []
                if create_contacts and external_participants:
                    logger.info(f"Step 6: Processing {len(external_participants)} external contacts...")

                    for participant in external_participants:
                        p_email = participant.get("email", "")
                        p_name = participant.get("name", "") or p_email.split("@")[0]

                        if not p_email:
                            continue

                        # Check if person already exists
                        existing = await find_person_by_email(db, user_id, p_email)

                        if existing.get("found"):
                            logger.info(f"Person already exists: {p_email} (ID: {existing['person_id']})")
                            created_persons.append({
                                "person_id": existing["person_id"],
                                "email": p_email,
                                "name": p_name,
                                "status": "existing"
                            })
                        else:
                            # Create new person linked to org
                            person_result = await create_person(
                                db, user_id,
                                name=p_name,
                                email=p_email,
                                org_id=org_id,
                                owner_id=owner_id
                            )

                            if person_result.get("success"):
                                created_persons.append({
                                    "person_id": person_result["person_id"],
                                    "email": p_email,
                                    "name": p_name,
                                    "status": "created"
                                })
                                logger.info(f"Created person: {p_name} ({p_email}) -> ID: {person_result['person_id']}")
                            else:
                                logger.warning(f"Failed to create person {p_email}: {person_result.get('error')}")
                                created_persons.append({
                                    "person_id": None,
                                    "email": p_email,
                                    "name": p_name,
                                    "status": "failed",
                                    "error": person_result.get("error")
                                })

                # Build comprehensive result
                persons_created_count = len([p for p in created_persons if p["status"] == "created"])
                persons_existing_count = len([p for p in created_persons if p["status"] == "existing"])

                result_message = f"Organization: {org_name} (ID: {org_id})"
                if org_created:
                    result_message += " [CREATED]"
                if created_persons:
                    result_message += f" | Contacts: {persons_created_count} created, {persons_existing_count} existing"

                logger.info(f"Advanced matching completed: {result_message}")

                return {
                    "status": "success",
                    "data": {
                        output_variable_name: org_id,
                        "organization_id": org_id,
                        "organization_name": org_name,
                        "organization_created": org_created,
                        "match_confidence": match_confidence,
                        "match_reasoning": match_reasoning,
                        "owner_id": owner_id,
                        "organizer_email": organizer_email,
                        "external_participants_count": len(external_participants),
                        "persons_created": created_persons,
                        "persons_created_count": persons_created_count,
                        "persons_existing_count": persons_existing_count,
                        "message": result_message
                    }
                }
            except Exception as inner_e:
                logger.error(f"Advanced matching inner error: {inner_e}", exc_info=True)
                return {"status": "error", "error": str(inner_e)}

        except Exception as e:
            logger.error(f"Advanced matching execution error: {str(e)}", exc_info=True)
            return {"status": "error", "error": str(e)}

    @staticmethod
    async def execute_advanced_action(config: dict, input_data: dict, db: Session = None) -> dict:
        """Execute advanced action component - update a single Pipedrive deal field"""
        from pipedrive_service import update_deal
        import re

        try:
            # Get configuration
            deal_id_source = config.get("deal_id_source", "")
            field_to_update = config.get("field_to_update", "")
            update_value = config.get("update_value", "")

            if not deal_id_source or not field_to_update:
                return {
                    "status": "error",
                    "error": "deal_id_source and field_to_update are required"
                }

            # Get workflow_id from input_data
            workflow_id = input_data.get("workflow_id")
            if not workflow_id:
                return {
                    "status": "error",
                    "error": "workflow_id not found in input_data"
                }

            if db is None:
                return {
                    "status": "error",
                    "error": "Internal error: db session not provided to execute_advanced_action"
                }

            # Get user_id from workflow
            try:
                workflow = db.query(models.Workflow).filter(models.Workflow.id == workflow_id).first()
                if not workflow:
                    return {
                        "status": "error",
                        "error": f"Workflow {workflow_id} not found"
                    }
                user_id = workflow.owner_id

                logger.info(f"Advanced action started for user {user_id}, workflow {workflow_id}")

                # Import unified substitution function
                from variable_substitution import substitute_variables as sub_vars, log_available_variables

                # Log available variables for debugging
                log_available_variables(input_data, component_name="Advanced Action")

                # Get component outputs for potential component-level references
                component_outputs = input_data.get("__component_outputs__", {})

                # Step 1: Extract deal_id from variable
                logger.info(f"Step 1: Extracting deal_id from: {deal_id_source}")
                deal_id_str = sub_vars(deal_id_source, input_data, component_outputs, "Advanced Action (deal_id)")

                try:
                    deal_id = int(deal_id_str)
                except (ValueError, TypeError):
                    return {
                        "status": "error",
                        "error": f"Invalid deal_id: '{deal_id_str}' (must be a number)"
                    }

                logger.info(f"Deal ID resolved to: {deal_id}")

                # Step 2: Substitute variables in update_value
                logger.info(f"Step 2: Processing update value: {update_value}")
                processed_value = sub_vars(update_value, input_data, component_outputs, "Advanced Action (value)")
                logger.info(f"Processed value: {processed_value}")

                # Step 3: Update the deal
                logger.info(f"Step 3: Updating deal {deal_id}, field '{field_to_update}' to '{processed_value}'")

                # Call update_deal with the single field as kwarg
                update_result = await update_deal(
                    db=db,
                    user_id=user_id,
                    deal_id=deal_id,
                    **{field_to_update: processed_value}
                )

                if not update_result.get("success"):
                    return {
                        "status": "error",
                        "error": update_result.get("error", "Failed to update deal in Pipedrive")
                    }

                logger.info(f"Successfully updated deal {deal_id}")

                return {
                    "status": "success",
                    "data": {
                        "deal_id": deal_id,
                        "field_updated": field_to_update,
                        "new_value": processed_value,
                        "message": f"Successfully updated {field_to_update} on deal {deal_id}"
                    }
                }
            except Exception as inner_e:
                logger.error(f"Advanced action inner error: {inner_e}", exc_info=True)
                return {"status": "error", "error": str(inner_e)}

        except Exception as e:
            logger.error(f"Advanced action execution error: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "error": str(e)
            }

    @staticmethod
    async def execute_component(component_type: str, config: dict, input_data: dict = None, db: Session = None) -> dict:
        """Route to appropriate executor based on component type.

        The caller (workflow executor or component test endpoint) owns the db session
        and passes it through so handlers reuse a single connection per workflow run.
        """
        executors = {
            "input_sources": ComponentExecutor.execute_input_sources,
            "text_generation": ComponentExecutor.execute_text_generation,
            "email": ComponentExecutor.execute_email,
            "sms": ComponentExecutor.execute_sms,
            "whatsapp": ComponentExecutor.execute_whatsapp,
            "conditional_logic": ComponentExecutor.execute_conditional_logic,
            "ai_filter": ComponentExecutor.execute_ai_filter,
            "action": ComponentExecutor.execute_action,
            "company_name_matcher": ComponentExecutor.execute_company_name_matcher,
            "advanced_action": ComponentExecutor.execute_advanced_action
        }

        if component_type not in executors:
            return {
                "status": "error",
                "error": f"Unknown component type: {component_type}"
            }

        try:
            return await executors[component_type](config, input_data or {}, db=db)
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }

def verify_workflow_ownership(workflow_id: int, current_user: models.User, db: Session):
    """Role-aware workflow access check. Delegates to auth.verify_workflow_access."""
    from auth import verify_workflow_access
    return verify_workflow_access(workflow_id, current_user, db)


# Trace types we keep when persisting rag_trace for the Execution Details view.
# We strip generic LLM call traces (anthropic.*) here because they bloat the
# payload by ~10× without adding RAG insight; if a future view needs them,
# read trace data from the in-flight buffer instead of the persisted column.
_RAG_TRACE_TYPE_PREFIXES = ("rag.", "openai.embeddings")
_RAG_TRACE_MAX_RESULTS = 5
_RAG_TRACE_CHUNK_PREVIEW_CHARS = 300


def _filter_rag_trace_for_persistence(trace_buf: list) -> list:
    """Keep only RAG-related entries and trim per-entry payload before write.

    Source data lives in `chunk_preview` (already 400 chars from rag_service);
    we shrink to 300 here and cap the results array per entry to 5 so a single
    execution can't store hundreds of KB of vector retrieval debris.
    """
    if not trace_buf:
        return []
    kept = []
    for entry in trace_buf:
        entry_type = entry.get("type", "")
        if not entry_type.startswith(_RAG_TRACE_TYPE_PREFIXES):
            continue
        # Shallow-copy so we don't mutate the live buffer (test endpoint may
        # still want the full thing).
        slim = dict(entry)
        resp = entry.get("response")
        if isinstance(resp, dict):
            slim_resp = dict(resp)
            results = slim_resp.get("results")
            if isinstance(results, list):
                trimmed = []
                for r in results[:_RAG_TRACE_MAX_RESULTS]:
                    if isinstance(r, dict):
                        rr = dict(r)
                        preview = rr.get("chunk_preview")
                        if isinstance(preview, str) and len(preview) > _RAG_TRACE_CHUNK_PREVIEW_CHARS:
                            rr["chunk_preview"] = preview[:_RAG_TRACE_CHUNK_PREVIEW_CHARS] + "…"
                        trimmed.append(rr)
                    else:
                        trimmed.append(r)
                slim_resp["results"] = trimmed
                slim_resp["results_total"] = len(results)
            slim["response"] = slim_resp
        kept.append(slim)
    return kept


async def execute_workflow_background(execution_id: int):
    """
    Background task to execute workflow

    IMPORTANT: This function creates its own database session to avoid race conditions.
    Never pass a database session from the request handler to a background task.
    """
    from database import SessionLocal
    from tracing import _trace_buffer  # private accessor — keeps indentation flat without re-wrapping the body

    # Create a NEW database session specifically for this background task
    # This prevents race conditions with the request handler's session
    db = SessionLocal()

    # Engage tracing so RAG entries from rag_service / ai_service flow into a
    # buffer we can persist on the execution row at finally time. We set the
    # ContextVar manually (rather than use `with trace_session():`) to avoid
    # re-indenting the entire ~350-line body. Reset happens in finally below.
    trace_buf: list = []
    trace_token = _trace_buffer.set(trace_buf)
    execution: Optional[models.Execution] = None

    try:
        from ai_service import reset_token_counter, get_token_totals, set_usage_context, set_usage_component_id, flush_usage_log
        reset_token_counter()

        execution = db.query(models.Execution).filter(models.Execution.id == execution_id).first()
        if not execution:
            return

        # Set up AI usage logging context
        workflow = db.query(models.Workflow).filter(models.Workflow.id == execution.workflow_id).first()
        if not workflow:
            return

        # Check acorn balance before executing (gate for webhook-triggered runs)
        owner = db.query(models.User).filter(models.User.id == workflow.owner_id).first()
        if owner:
            from acorn_service import get_account_for_user, check_user_can_execute
            account = get_account_for_user(owner, db)
            if account and not check_user_can_execute(owner, account, db):
                execution.status = "failed"
                execution.error_message = "Insufficient Acorn balance"
                execution.completed_at = datetime.utcnow()
                db.commit()
                logger.warning("Execution %d blocked: insufficient acorns for user %d", execution_id, owner.id)
                return

        set_usage_context(
            user_id=workflow.owner_id,
            source="execution",
            execution_id=execution.id,
        )

        # Get workflow components in order
        components = db.query(models.Component).filter(
            models.Component.workflow_id == execution.workflow_id
        ).order_by(models.Component.order).all()

        # Start with input data from webhook if available
        execution_data = execution.input_data if execution.input_data else {}
        component_outputs = {}  # Track each component's full output for component-level variables
        total_start_time = time.time()

        # Propagate the workflow owner's user_id into the execution context so
        # downstream components can scope Contact lookups (email is non-unique
        # across tenants — two accounts both have alice@customer.com — so a
        # global-by-email query would leak RAG context cross-tenant).
        if workflow and workflow.owner_id:
            execution_data["__user_id__"] = workflow.owner_id

        # Look up account_id for the workflow owner (needed for resource manifest)
        # Primary: use account from acorn check above
        # Fallback: look up via org_id directly
        if not account and owner and owner.org_id:
            account = db.query(models.Account).filter(
                models.Account.org_id == owner.org_id
            ).first()
        if account:
            execution_data["__account_id__"] = account.id
            logger.info(f"[RESOURCES] account_id={account.id} set via owner org_id={owner.org_id}")
        else:
            logger.warning(f"[RESOURCES] No account via org lookup (owner_id={workflow.owner_id}, org_id={owner.org_id if owner else None}), will derive from component resource configs")

        for component in components:
            # Track which component is currently executing for usage logging
            set_usage_component_id(component.id)
            # Ensure component id is always available to component executors
            # (notably email queue writes), regardless of saved config shape.
            component_config = {
                **(component.configuration or {}),
                "component_id": component.id,
            }

            # Create component execution record
            comp_execution = models.ComponentExecution(
                execution_id=execution.id,
                component_id=component.id,
                status="running",
                started_at=datetime.utcnow()
            )
            db.add(comp_execution)
            db.commit()
            
            # Execute component
            start_time = time.time()

            # For input_sources, pass the webhook data directly
            if component.type == "input_sources" and execution.input_data:
                input_data_with_workflow = {**execution.input_data, "workflow_id": execution.workflow_id}
                comp_execution.input_data = input_data_with_workflow  # Save input data
                db.commit()

                result = await ComponentExecutor.execute_component(
                    component.type,
                    component_config,
                    input_data_with_workflow,  # Pass webhook data with workflow ID to input source
                    db=db,
                )
            else:
                execution_data_with_workflow = {**execution_data, "workflow_id": execution.workflow_id}
                comp_execution.input_data = execution_data_with_workflow  # Save input data
                db.commit()

                result = await ComponentExecutor.execute_component(
                    component.type,
                    component_config,
                    execution_data_with_workflow,  # Pass accumulated data with workflow ID from previous components
                    db=db,
                )
            end_time = time.time()

            # Update component execution
            comp_execution.completed_at = datetime.utcnow()
            comp_execution.execution_time = int((end_time - start_time) * 1000)
            comp_execution.output_data = result
            
            if result.get("status") == "success":
                comp_execution.status = "completed"
                result_data = result.get("data", {})

                # Store component output with component name as key (for component-level variables)
                component_outputs[component.name] = result_data

                # Keep existing flat merge for backward compatibility (field-level variables)
                execution_data.update(result_data)

                # Add component_outputs to execution_data for downstream access
                execution_data["__component_outputs__"] = component_outputs

                # If this is an email component, store generation_reason on the Execution
                if component.type == "email" and result_data.get("generation_reason"):
                    execution.generation_reason = result_data["generation_reason"]

                # If this is a text_generation component, store extracted variables for reuse
                if component.type == "text_generation" and "extracted_information" in result_data:
                    extracted_info = result_data["extracted_information"]
                    extraction_points = result_data.get("extraction_points", [])

                    # Clear existing variables for this execution
                    db.query(models.ExtractedVariable).filter(
                        models.ExtractedVariable.execution_id == execution.id
                    ).delete()

                    # Store new extracted variables
                    for point in extraction_points:
                        variable_name = point.get("name", "")
                        variable_key = variable_name.lower().replace(" ", "_").replace("-", "_")
                        variable_value = extracted_info.get(variable_name)
                        data_type = point.get("type", "string")

                        if variable_name and variable_value is not None:
                            extracted_var = models.ExtractedVariable(
                                workflow_id=execution.workflow_id,
                                execution_id=execution.id,
                                variable_name=variable_name,
                                variable_key=variable_key,
                                variable_value=variable_value,
                                data_type=data_type
                            )
                            db.add(extracted_var)

                    db.commit()
                    logger.info(f"Stored {len(extraction_points)} extracted variables for execution {execution.id}")

                    # RAG: Embed structured Text Gen output + raw transcript for contact briefing
                    try:
                        from rag_service import store_text_gen_output, store_transcript_chunks

                        rag_account_id = execution_data.get("__account_id__")
                        if rag_account_id:
                            # Resolve contact_id from participants if possible
                            rag_contact_id = None
                            rag_org_id = None
                            rag_meeting_date = execution_data.get("meeting_date")
                            participants = execution_data.get("participants", [])

                            # Skip the workflow owner's own emails so embeddings
                            # get tagged with the customer's contact_id, not ours.
                            # Without this, every chunk gets attributed to the
                            # owner and pollutes future contact briefings.
                            owner_user = db.query(models.User).filter(
                                models.User.id == workflow.owner_id
                            ).first() if workflow.owner_id else None
                            internal_domains = []
                            if owner_user and owner_user.internal_domains:
                                internal_domains = [
                                    d.strip().lower()
                                    for d in owner_user.internal_domains.split(",")
                                    if d.strip()
                                ]

                            # Try to find a matching contact from participant emails
                            if participants:
                                for p in participants:
                                    p_email = None
                                    if isinstance(p, dict):
                                        p_email = p.get("email")
                                    if not p_email:
                                        continue
                                    email_domain = p_email.split("@")[-1].lower() if "@" in p_email else ""
                                    if internal_domains and any(
                                        email_domain == d or email_domain.endswith("." + d)
                                        for d in internal_domains
                                    ):
                                        continue
                                    contact = db.query(models.Contact).filter(
                                        models.Contact.email == p_email,
                                        models.Contact.user_id == workflow.owner_id,
                                    ).first()
                                    if contact:
                                        rag_contact_id = contact.id
                                        rag_org_id = contact.contact_organization_id
                                        break

                            # Also check execution_data for org_id from company_name_matcher
                            if not rag_org_id:
                                rag_org_id = execution_data.get("organization_id") or execution_data.get("matched_org_id")

                            # Store structured output embeddings
                            await store_text_gen_output(
                                db=db,
                                account_id=rag_account_id,
                                execution_id=execution.id,
                                extracted_information=extracted_info,
                                contact_id=rag_contact_id,
                                org_id=rag_org_id,
                                meeting_date=rag_meeting_date,
                            )

                            # RAG Phase 6: Thin transcript detection.
                            # Tier 1 fields: pain_points, next_steps, decision_status,
                            # primary_contact, exact_phrases. If 2+ are missing/empty,
                            # flag as thin and auto-compensate with broader RAG retrieval.
                            try:
                                _tier1_keys = ["pain_points", "next_steps", "decision_status", "primary_contact", "exact_phrases"]
                                _missing = 0
                                if isinstance(extracted_info, dict):
                                    # Normalize keys for matching
                                    _normalized = {k.lower().replace(" ", "_").replace("-", "_"): v for k, v in extracted_info.items()}
                                    for _k in _tier1_keys:
                                        _v = _normalized.get(_k)
                                        if _v is None:
                                            _missing += 1
                                        elif isinstance(_v, str) and (not _v.strip() or _v.strip().lower() in ("not mentioned", "none", "n/a")):
                                            _missing += 1
                                        elif isinstance(_v, list) and not _v:
                                            _missing += 1
                                is_thin = _missing >= 2

                                if is_thin:
                                    logger.info(f"[RAG] Thin transcript detected for execution {execution.id} ({_missing} Tier-1 fields missing) — running auto-compensation")
                                    # Expose flag on the execution_data so downstream Email components can see it
                                    execution_data["__is_thin_transcript__"] = True
                                    # Pull broader historical context with a higher limit
                                    if rag_contact_id:
                                        try:
                                            from rag_service import smart_retrieve
                                            _thin_context = await smart_retrieve(
                                                db=db,
                                                query_text="relationship history pain points budget next steps",
                                                account_id=rag_account_id,
                                                source_types=["text_gen_output", "transcript_chunk", "generated_email"],
                                                contact_id=rag_contact_id,
                                                org_id=rag_org_id,
                                                limit=10,
                                            )
                                            if _thin_context:
                                                execution_data["__thin_compensation_context__"] = [
                                                    {"source_type": r["source_type"], "chunk_text": r["chunk_text"][:500]}
                                                    for r in _thin_context
                                                ]
                                                logger.info(f"[RAG] Thin compensation pulled {len(_thin_context)} chunks")
                                        except Exception as _tc_err:
                                            logger.debug(f"Thin transcript compensation failed: {_tc_err}")

                                    # Optional user prompt — respect per-workflow toggle (default ON)
                                    _show_prompt = True
                                    if workflow.rag_settings and isinstance(workflow.rag_settings, dict):
                                        _show_prompt = workflow.rag_settings.get("thin_transcript_prompt", True)
                                    if _show_prompt:
                                        execution_data["__thin_transcript_user_prompt__"] = (
                                            "This meeting had limited notes. Consider adding a quick summary before the sequence runs."
                                        )
                            except Exception as _thin_err:
                                logger.debug(f"Thin transcript check failed (non-blocking): {_thin_err}")

                            # Store transcript chunk embeddings (fallback layer)
                            transcript = execution_data.get("transcript", "")
                            if transcript:
                                await store_transcript_chunks(
                                    db=db,
                                    account_id=rag_account_id,
                                    execution_id=execution.id,
                                    transcript=transcript,
                                    contact_id=rag_contact_id,
                                    org_id=rag_org_id,
                                    meeting_date=rag_meeting_date,
                                )

                            logger.info(f"RAG: embedded Text Gen output for execution {execution.id} (contact={rag_contact_id}, org={rag_org_id})")
                        else:
                            logger.debug("RAG: no account_id, skipping Text Gen embedding")
                    except Exception as e:
                        # RAG failure should never break the execution pipeline
                        logger.error(f"RAG embedding failed for execution {execution.id}: {e}")

                # Check if this is a conditional_logic component and if pipeline should stop
                if component.type == "conditional_logic":
                    pipeline_continues = result_data.get("pipeline_continues", True)

                    if not pipeline_continues:
                        # Conditional logic says to stop the pipeline
                        logger.info(f"Conditional logic component stopped pipeline execution at component {component.id}")
                        logger.info(f"Reason: {result_data.get('message', 'Conditions not matched')}")

                        # Mark execution as completed (not failed - this is expected behavior)
                        total_end_time = time.time()
                        execution.status = "completed"
                        execution.completed_at = datetime.utcnow()
                        execution.total_execution_time = int((total_end_time - total_start_time) * 1000)
                        execution.results = execution_data
                        # Add a flag to results to indicate it was stopped by conditional logic
                        execution.results["_stopped_by_conditional_logic"] = True
                        execution.results["_stop_reason"] = result_data.get("message", "Conditions not matched")
                        # Store token usage
                        token_totals = get_token_totals()
                        execution.total_prompt_tokens = token_totals["prompt_tokens"] or None
                        execution.total_completion_tokens = token_totals["completion_tokens"] or None
                        execution.total_tokens = token_totals["total_tokens"] or None
                        flush_usage_log(db)
                        db.commit()
                        return
                    else:
                        logger.info(f"Conditional logic component allows pipeline to continue: {result_data.get('message', '')}")
            else:
                comp_execution.status = "failed"
                comp_execution.error_message = result.get("error", "Unknown error")

                # Mark main execution as failed
                execution.status = "failed"
                execution.error_message = comp_execution.error_message
                execution.completed_at = datetime.utcnow()
                db.commit()
                return

            db.commit()
        
        # Mark execution as completed
        total_end_time = time.time()
        execution.status = "completed"
        execution.completed_at = datetime.utcnow()
        execution.total_execution_time = int((total_end_time - total_start_time) * 1000)
        execution.results = execution_data
        # Store token usage
        token_totals = get_token_totals()
        execution.total_prompt_tokens = token_totals["prompt_tokens"] or None
        execution.total_completion_tokens = token_totals["completion_tokens"] or None
        execution.total_tokens = token_totals["total_tokens"] or None
        flush_usage_log(db)
        db.commit()

        # Post-execution acorn debit
        try:
            owner = db.query(models.User).filter(models.User.id == workflow.owner_id).first()
            if owner:
                account = get_account_for_user(owner, db)
                if account:
                    total_cost_usd = 0.0
                    component_costs = {}
                    usage_logs = db.query(models.AiUsageLog).filter(
                        models.AiUsageLog.execution_id == execution.id
                    ).all()
                    for log_entry in usage_logs:
                        # billable_cost is cache-agnostic (user pays the same whether Anthropic cached or not);
                        # fall back to .cost for rows written before migration 032.
                        entry_cost = log_entry.billable_cost or log_entry.cost or 0
                        if entry_cost:
                            total_cost_usd += entry_cost
                            cid = str(log_entry.component_id) if log_entry.component_id else "unknown"
                            component_costs[cid] = round(component_costs.get(cid, 0.0) + entry_cost, 6)

                    if total_cost_usd > 0:
                        acorn_cost = usd_to_acorns(total_cost_usd, db)
                        spend_acorns(
                            account_id=account.id,
                            user_id=owner.id,
                            amount=acorn_cost,
                            description=f"Workflow execution: {workflow.name}",
                            db=db,
                            metadata={
                                "execution_id": execution.id,
                                "workflow_id": workflow.id,
                                "component_costs_usd": component_costs,
                            },
                            allow_overdraft=True,
                        )
                        db.commit()
        except Exception as e:
            logger.warning(f"Acorn debit failed for execution {execution.id}: {e}")

    except Exception as e:
        execution.status = "failed"
        execution.error_message = str(e)
        execution.completed_at = datetime.utcnow()
        # Still flush any usage logged before the error
        try:
            flush_usage_log(db)
        except Exception:
            pass
        db.commit()

    finally:
        # Persist a slimmed RAG-only slice of the trace buffer so the
        # Execution Details modal can render the same data the component-test
        # modal gets in real time. Best-effort — never let a trace-write
        # failure cascade into the execution status.
        try:
            rag_trace = _filter_rag_trace_for_persistence(trace_buf)
            if rag_trace and execution is not None:
                execution.rag_trace = rag_trace
                db.commit()
        except Exception as trace_err:
            logger.warning(
                f"Failed to persist rag_trace for execution {execution_id}: {trace_err}"
            )
            try:
                db.rollback()
            except Exception:
                pass
        # Reset the contextvar token regardless of write outcome so the next
        # background task starts with a clean buffer.
        try:
            _trace_buffer.reset(trace_token)
        except Exception:
            pass
        # Always close the database session to prevent connection leaks
        db.close()

@router.get(
    "/{workflow_id}/executions",
    response_model=List[Execution],
    summary="List Workflow Executions",
    description="Get recent execution history for a workflow"
)
async def get_workflow_executions(
    workflow_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    List recent executions for a workflow.

    Returns the last 50 executions with complete details including all component executions.
    Ordered by most recent first.

    Args:
        workflow_id: The workflow ID
        current_user: The authenticated user (injected)
        db: Database session (injected)

    Returns:
        List[Execution]: Last 50 executions with component execution details

    Raises:
        HTTPException 404: If workflow not found or user doesn't own it
    """
    verify_workflow_ownership(workflow_id, current_user, db)

    executions = db.query(models.Execution).options(
        joinedload(models.Execution.component_executions).joinedload(models.ComponentExecution.component)
    ).filter(
        models.Execution.workflow_id == workflow_id
    ).order_by(models.Execution.started_at.desc()).limit(50).all()

    # Manually convert to Pydantic models to include component names
    result = []
    for execution in executions:
        component_execs = [
            ComponentExecutionResult.from_orm(ce)
            for ce in execution.component_executions
        ]
        result.append(Execution(
            id=execution.id,
            workflow_id=execution.workflow_id,
            status=execution.status,
            started_at=execution.started_at,
            completed_at=execution.completed_at,
            total_execution_time=execution.total_execution_time,
            input_data=execution.input_data,
            results=execution.results,
            error_message=execution.error_message,
            generation_reason=execution.generation_reason,
            total_prompt_tokens=execution.total_prompt_tokens,
            total_completion_tokens=execution.total_completion_tokens,
            total_tokens=execution.total_tokens,
            component_executions=component_execs
        ))

    return result

@router.post(
    "/{workflow_id}/execute",
    response_model=Execution,
    status_code=status.HTTP_201_CREATED,
    summary="Execute Workflow",
    description="Trigger workflow execution with optional Fireflies transcript input"
)
async def execute_workflow(
    workflow_id: int,
    execution_data: ExecutionCreate,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(require_active_account),
    db: Session = Depends(get_db)
):
    """
    Trigger a workflow execution.

    Creates an execution record and processes the workflow in the background.
    Optionally fetches a Fireflies transcript to use as input data.

    Args:
        workflow_id: The workflow ID to execute
        execution_data: Execution parameters (optional fireflies_transcript_id, test_mode)
        background_tasks: Background task manager (injected)
        current_user: The authenticated user (injected)
        db: Database session (injected)

    Returns:
        Execution: The created execution record (status: "running")

    Raises:
        HTTPException 404: If workflow not found or user doesn't own it
        HTTPException 400: If workflow is inactive
        HTTPException 402: If insufficient acorn balance
        HTTPException 403: If no billing account found
    """
    workflow = verify_workflow_ownership(workflow_id, current_user, db)

    # Pre-execution acorn balance check
    account = get_account_for_user(current_user, db)
    if not account:
        raise HTTPException(status_code=403, detail="No billing account found")
    if not check_user_can_execute(current_user, account, db):
        raise HTTPException(
            status_code=402,
            detail="Insufficient Acorn balance. Please top up or ask your admin to allocate more Acorns."
        )

    # Check if workflow is active
    if not workflow.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot execute inactive workflow. Please activate the workflow first."
        )

    # If transcript ID is provided, fetch the transcript from Fireflies
    input_data = None
    if execution_data.fireflies_transcript_id:
        from fireflies_service import fetch_transcript
        try:
            transcript_data = await fetch_transcript(
                execution_data.fireflies_transcript_id,
                db,
                current_user.id
            )
            if transcript_data:
                input_data = {
                    **transcript_data,
                    "source": "fireflies_webhook"
                }
        except Exception as e:
            logger.error(f"Failed to fetch transcript {execution_data.fireflies_transcript_id}: {str(e)}")
            # Continue with execution but without transcript data

    # Create execution record
    db_execution = models.Execution(
        workflow_id=workflow_id,
        status="running",
        input_data=input_data
    )
    db.add(db_execution)
    db.commit()
    db.refresh(db_execution)

    # Start background execution
    # IMPORTANT: Do NOT pass the database session to background tasks!
    # The background task creates its own session to avoid race conditions
    background_tasks.add_task(execute_workflow_background, db_execution.id)

    return db_execution

@router.get("/{workflow_id}/latest", response_model=Execution)
async def get_latest_execution(
    workflow_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get the most recent execution for a workflow"""
    verify_workflow_ownership(workflow_id, current_user, db)

    execution = db.query(models.Execution).options(
        joinedload(models.Execution.component_executions).joinedload(models.ComponentExecution.component)
    ).filter(
        models.Execution.workflow_id == workflow_id
    ).order_by(models.Execution.started_at.desc()).first()

    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No executions found for this workflow"
        )

    # Manually convert to Pydantic model to include component names
    component_execs = [
        ComponentExecutionResult.from_orm(ce)
        for ce in execution.component_executions
    ]

    return Execution(
        id=execution.id,
        workflow_id=execution.workflow_id,
        status=execution.status,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
        total_execution_time=execution.total_execution_time,
        input_data=execution.input_data,
        results=execution.results,
        error_message=execution.error_message,
        generation_reason=execution.generation_reason,
        total_prompt_tokens=execution.total_prompt_tokens,
        total_completion_tokens=execution.total_completion_tokens,
        total_tokens=execution.total_tokens,
        acorns_used=_compute_acorns_used(execution.id, db),
        component_executions=component_execs
    )

@router.get(
    "/{workflow_id}/executions/{execution_id}",
    response_model=Execution,
    summary="Get Execution Details",
    description="Retrieve detailed information about a specific execution"
)
async def get_execution(
    workflow_id: int,
    execution_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific execution.

    Returns complete execution details including status, timing, input/output data,
    and all component execution results.

    Args:
        workflow_id: The workflow ID
        execution_id: The execution ID
        current_user: The authenticated user (injected)
        db: Database session (injected)

    Returns:
        Execution: Complete execution details with all component executions

    Raises:
        HTTPException 404: If workflow/execution not found or user doesn't own workflow
    """
    verify_workflow_ownership(workflow_id, current_user, db)

    execution = db.query(models.Execution).options(
        joinedload(models.Execution.component_executions).joinedload(models.ComponentExecution.component)
    ).filter(
        models.Execution.id == execution_id,
        models.Execution.workflow_id == workflow_id
    ).first()

    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found"
        )

    # Manually convert to Pydantic model to include component names
    component_execs = [
        ComponentExecutionResult.from_orm(ce)
        for ce in execution.component_executions
    ]

    return Execution(
        id=execution.id,
        workflow_id=execution.workflow_id,
        status=execution.status,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
        total_execution_time=execution.total_execution_time,
        input_data=execution.input_data,
        results=execution.results,
        error_message=execution.error_message,
        generation_reason=execution.generation_reason,
        total_prompt_tokens=execution.total_prompt_tokens,
        total_completion_tokens=execution.total_completion_tokens,
        total_tokens=execution.total_tokens,
        acorns_used=_compute_acorns_used(execution.id, db),
        component_executions=component_execs
    )

@router.get(
    "/{workflow_id}/executions/stats",
    response_model=ExecutionStats,
    summary="Get Execution Statistics",
    description="Get aggregate execution statistics for a specific workflow"
)
async def get_execution_stats(
    workflow_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get execution statistics for a workflow.

    Provides aggregate metrics including total executions, success/failure counts,
    currently running executions, and average execution time.

    Args:
        workflow_id: The workflow ID
        current_user: The authenticated user (injected)
        db: Database session (injected)

    Returns:
        ExecutionStats: Statistics for this workflow's executions

    Raises:
        HTTPException 404: If workflow not found or user doesn't own it
    """
    verify_workflow_ownership(workflow_id, current_user, db)
    
    total_executions = db.query(models.Execution).filter(
        models.Execution.workflow_id == workflow_id
    ).count()
    
    successful_executions = db.query(models.Execution).filter(
        models.Execution.workflow_id == workflow_id,
        models.Execution.status == "completed"
    ).count()
    
    failed_executions = db.query(models.Execution).filter(
        models.Execution.workflow_id == workflow_id,
        models.Execution.status == "failed"
    ).count()
    
    running_executions = db.query(models.Execution).filter(
        models.Execution.workflow_id == workflow_id,
        models.Execution.status == "running"
    ).count()
    
    # Calculate average execution time
    avg_time_result = db.query(
        models.Execution.total_execution_time
    ).filter(
        models.Execution.workflow_id == workflow_id,
        models.Execution.total_execution_time.isnot(None)
    ).all()
    
    avg_execution_time = None
    if avg_time_result:
        times = [r[0] for r in avg_time_result if r[0] is not None]
        if times:
            avg_execution_time = sum(times) / len(times)
    
    return ExecutionStats(
        total_executions=total_executions,
        successful_executions=successful_executions,
        failed_executions=failed_executions,
        running_executions=running_executions,
        avg_execution_time=avg_execution_time
    )


@router.get(
    "/{workflow_id}/executions/{execution_id}/summary",
    response_model=ExecutionSummaryResponse,
    summary="Get Execution Summary",
    description="Retrieve the summary generated by Text Generation component from a specific execution"
)
async def get_execution_summary(
    workflow_id: int,
    execution_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get the summary from an already executed workflow.

    Searches for a Text Generation component execution within the given execution
    and returns its summary if one was generated.

    Args:
        workflow_id: The workflow ID
        execution_id: The execution ID
        current_user: The authenticated user (injected)
        db: Database session (injected)

    Returns:
        ExecutionSummaryResponse: Summary data including the summary text,
        extracted information, and execution metadata

    Raises:
        HTTPException 404: If workflow/execution not found or user doesn't own workflow
    """
    verify_workflow_ownership(workflow_id, current_user, db)

    # Get the execution with its component executions
    execution = db.query(models.Execution).options(
        joinedload(models.Execution.component_executions).joinedload(models.ComponentExecution.component)
    ).filter(
        models.Execution.id == execution_id,
        models.Execution.workflow_id == workflow_id
    ).first()

    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found"
        )

    # Extract meeting info from execution input_data
    exec_input_data = execution.input_data or {}
    fireflies_meeting_id = exec_input_data.get("meeting_id")
    meeting_title = exec_input_data.get("meeting_title")

    # Find the text_generation component execution
    text_gen_execution = None
    for comp_exec in execution.component_executions:
        if comp_exec.component and comp_exec.component.type == "text_generation":
            text_gen_execution = comp_exec
            break

    # If no text_generation component exists in workflow
    if text_gen_execution is None:
        return ExecutionSummaryResponse(
            execution_id=execution.id,
            workflow_id=workflow_id,
            status=execution.status,
            has_summary=False,
            summary=None,
            extracted_information=None,
            component_name=None,
            executed_at=execution.started_at,
            fireflies_meeting_id=fireflies_meeting_id,
            meeting_title=meeting_title,
            message="This workflow does not have a Text Generation component"
        )

    # Check if component execution was successful
    if text_gen_execution.status != "completed":
        return ExecutionSummaryResponse(
            execution_id=execution.id,
            workflow_id=workflow_id,
            status=execution.status,
            has_summary=False,
            summary=None,
            extracted_information=None,
            component_name=text_gen_execution.component.name,
            executed_at=execution.started_at,
            fireflies_meeting_id=fireflies_meeting_id,
            meeting_title=meeting_title,
            message=f"Text Generation component did not complete successfully (status: {text_gen_execution.status})"
        )

    # Extract summary from output_data
    output_data = text_gen_execution.output_data or {}

    # Handle both formats: direct data or nested under "data" key
    data = output_data.get("data", output_data)
    summary = data.get("summary")
    extracted_info = data.get("extracted_information")

    if not summary:
        return ExecutionSummaryResponse(
            execution_id=execution.id,
            workflow_id=workflow_id,
            status=execution.status,
            has_summary=False,
            summary=None,
            extracted_information=extracted_info,
            component_name=text_gen_execution.component.name,
            executed_at=execution.started_at,
            fireflies_meeting_id=fireflies_meeting_id,
            meeting_title=meeting_title,
            message="Text Generation component ran but did not produce a summary"
        )

    return ExecutionSummaryResponse(
        execution_id=execution.id,
        workflow_id=workflow_id,
        status=execution.status,
        has_summary=True,
        summary=summary,
        extracted_information=extracted_info,
        component_name=text_gen_execution.component.name,
        executed_at=execution.started_at,
        fireflies_meeting_id=fireflies_meeting_id,
        meeting_title=meeting_title,
        message="Summary retrieved successfully"
    )


@router.get(
    "/summary/by-meeting/{meeting_id}",
    response_model=ExecutionSummaryResponse,
    summary="Get Summary by Fireflies Meeting ID",
    description="Retrieve the summary from an execution that processed a specific Fireflies meeting"
)
async def get_summary_by_meeting_id(
    meeting_id: str,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get the summary for a specific Fireflies meeting.

    Searches for executions that processed this meeting ID and returns
    the summary from the most recent successful execution.

    Args:
        meeting_id: The Fireflies meeting ID
        current_user: The authenticated user (injected)
        db: Database session (injected)

    Returns:
        ExecutionSummaryResponse: Summary data if found

    Raises:
        HTTPException 404: If no execution found for this meeting ID
    """
    # Owners/Admins see all org workflows; Members see only their own
    if current_user.role in (models.UserRole.owner, models.UserRole.admin):
        user_workflow_ids = [w.id for w in db.query(models.Workflow.id).join(
            models.User, models.Workflow.owner_id == models.User.id
        ).filter(
            models.User.org_id == current_user.org_id
        ).all()]
    else:
        user_workflow_ids = [w.id for w in db.query(models.Workflow.id).filter(
            models.Workflow.owner_id == current_user.id
        ).all()]

    if not user_workflow_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No workflows found for this user"
        )

    # Search for executions with this meeting_id in input_data
    # PostgreSQL JSON query: input_data->>'meeting_id' = meeting_id
    executions = db.query(models.Execution).options(
        joinedload(models.Execution.component_executions).joinedload(models.ComponentExecution.component)
    ).filter(
        models.Execution.workflow_id.in_(user_workflow_ids),
        models.Execution.input_data.isnot(None),
        # Use PostgreSQL ->> operator to extract JSON field as text
        models.Execution.input_data.op('->>')('meeting_id') == meeting_id
    ).order_by(models.Execution.started_at.desc()).all()

    if not executions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No execution found for Fireflies meeting ID: {meeting_id}"
        )

    # Find the first execution with a successful text_generation component
    for execution in executions:
        # Find text_generation component execution
        text_gen_execution = None
        for comp_exec in execution.component_executions:
            if comp_exec.component and comp_exec.component.type == "text_generation":
                text_gen_execution = comp_exec
                break

        if text_gen_execution is None:
            continue  # Try next execution

        if text_gen_execution.status != "completed":
            continue  # Try next execution

        # Extract summary from output_data
        output_data = text_gen_execution.output_data or {}
        data = output_data.get("data", output_data)
        summary = data.get("summary")
        extracted_info = data.get("extracted_information")

        if summary:
            input_data = execution.input_data or {}
            return ExecutionSummaryResponse(
                execution_id=execution.id,
                workflow_id=execution.workflow_id,
                status=execution.status,
                has_summary=True,
                summary=summary,
                extracted_information=extracted_info,
                component_name=text_gen_execution.component.name,
                executed_at=execution.started_at,
                fireflies_meeting_id=meeting_id,
                meeting_title=input_data.get("meeting_title"),
                message="Summary retrieved successfully"
            )

    # No successful summary found in any execution
    # Return info about the most recent execution
    latest = executions[0]
    input_data = latest.input_data or {}

    return ExecutionSummaryResponse(
        execution_id=latest.id,
        workflow_id=latest.workflow_id,
        status=latest.status,
        has_summary=False,
        summary=None,
        extracted_information=None,
        component_name=None,
        executed_at=latest.started_at,
        fireflies_meeting_id=meeting_id,
        meeting_title=input_data.get("meeting_title"),
        message="Execution found but no summary was generated"
    )
