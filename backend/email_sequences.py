"""
Email Sequence Configuration Router
Handles CRUD operations for email sequences attached to workflows.
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel, Field
from datetime import datetime
import logging

from database import get_db
from auth import get_current_active_user, verify_workflow_access
import models

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class SequenceEmailCreate(BaseModel):
    """Schema for creating a new email in a sequence"""
    order: int = 1
    name: str = "Email"
    subject: str
    body: str
    timing_mode: str = "relative"  # "relative" or "specific"
    delay_value: Optional[int] = 1
    delay_unit: Optional[str] = "days"  # minutes, hours, days, weeks
    specific_day: Optional[str] = None  # monday, tuesday, etc.
    specific_time: Optional[str] = None  # HH:MM
    ai_decides_timing: bool = False
    ai_timing_context: Optional[str] = None
    is_enabled: bool = True
    generation_prompt: Optional[str] = None
    use_variables: List[str] = []


class SequenceEmailUpdate(BaseModel):
    """Schema for updating an email in a sequence"""
    order: Optional[int] = None
    name: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    timing_mode: Optional[str] = None
    delay_value: Optional[int] = None
    delay_unit: Optional[str] = None
    specific_day: Optional[str] = None
    specific_time: Optional[str] = None
    ai_decides_timing: Optional[bool] = None
    ai_timing_context: Optional[str] = None
    is_enabled: Optional[bool] = None
    generation_prompt: Optional[str] = None
    use_variables: Optional[List[str]] = None


class SequenceEmail(BaseModel):
    """Response schema for a sequence email"""
    id: int
    sequence_config_id: int
    order: int
    name: str
    subject: str
    body: str
    timing_mode: str
    delay_value: Optional[int] = None
    delay_unit: Optional[str] = None
    specific_day: Optional[str] = None
    specific_time: Optional[str] = None
    ai_decides_timing: bool
    ai_timing_context: Optional[str] = None
    is_enabled: bool
    generation_prompt: Optional[str] = None
    use_variables: List[str] = []
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SkipCondition(BaseModel):
    """Schema for a skip condition"""
    type: str  # "deal_stage", "deal_status", "contact_field", "days_since_last_email", "reply_received"
    operator: str  # "equals", "not_equals", "contains", "greater_than", "less_than"
    value: Any
    field: Optional[str] = None  # For custom field conditions


class EmailSequenceConfigCreate(BaseModel):
    """Schema for creating a new email sequence configuration"""
    name: str = "Follow-up Sequence"
    is_enabled: bool = True
    ai_optimize_timing: bool = False
    ai_optimization_prompt: Optional[str] = None
    send_method: str = "smtp"
    timezone: str = "America/New_York"
    business_hours_only: bool = True
    business_hours_start: str = "09:00"
    business_hours_end: str = "17:00"
    business_days: List[str] = ["monday", "tuesday", "wednesday", "thursday", "friday"]
    skip_conditions: List[SkipCondition] = []


class EmailSequenceConfigUpdate(BaseModel):
    """Schema for updating an email sequence configuration"""
    name: Optional[str] = None
    is_enabled: Optional[bool] = None
    ai_optimize_timing: Optional[bool] = None
    ai_optimization_prompt: Optional[str] = None
    send_method: Optional[str] = None
    timezone: Optional[str] = None
    business_hours_only: Optional[bool] = None
    business_hours_start: Optional[str] = None
    business_hours_end: Optional[str] = None
    business_days: Optional[List[str]] = None
    skip_conditions: Optional[List[Dict[str, Any]]] = None


class EmailSequenceConfig(BaseModel):
    """Response schema for email sequence configuration"""
    id: int
    workflow_id: int
    name: str
    is_enabled: bool
    ai_optimize_timing: bool
    ai_optimization_prompt: Optional[str] = None
    send_method: str
    timezone: str
    business_hours_only: bool
    business_hours_start: str
    business_hours_end: str
    business_days: List[str]
    skip_conditions: List[Dict[str, Any]] = []
    emails: List[SequenceEmail] = []
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class GenerateEmailsRequest(BaseModel):
    """Request schema for AI email generation"""
    transcript_summary: Dict[str, Any]  # The extracted variables/summary from transcript
    num_emails: int = 3
    custom_prompt: Optional[str] = None
    tone: str = "professional"  # professional, friendly, formal, casual
    include_variables: List[str] = []


class GenerateEmailsResponse(BaseModel):
    """Response schema for AI email generation"""
    emails: List[Dict[str, Any]]
    generation_metadata: Dict[str, Any]


class OptimizeTimingRequest(BaseModel):
    """Request schema for AI timing optimization"""
    transcript_summary: Dict[str, Any]
    emails: List[Dict[str, Any]]  # List of emails with current timing
    custom_prompt: Optional[str] = None


class OptimizeTimingResponse(BaseModel):
    """Response schema for AI timing optimization"""
    optimized_timing: List[Dict[str, Any]]
    reasoning: str


# ============================================================================
# SEQUENCE CONFIG ENDPOINTS
# ============================================================================

@router.get("/test")
async def test_router():
    """Test endpoint to verify router is working"""
    return {"status": "Email sequences router working!"}


@router.get(
    "/workflow/{workflow_id}",
    response_model=Optional[EmailSequenceConfig],
    summary="Get Email Sequence Config",
    description="Get the email sequence configuration for a workflow"
)
async def get_sequence_config(
    workflow_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get the email sequence configuration for a workflow.
    Returns None if no sequence is configured yet.
    """
    # Verify workflow access
    workflow = verify_workflow_access(workflow_id, current_user, db)

    # Get sequence config with emails eager loaded
    config = db.query(models.EmailSequenceConfig).options(
        joinedload(models.EmailSequenceConfig.emails)
    ).filter(
        models.EmailSequenceConfig.workflow_id == workflow_id
    ).first()

    return config


@router.post(
    "/workflow/{workflow_id}",
    response_model=EmailSequenceConfig,
    status_code=status.HTTP_201_CREATED,
    summary="Create Email Sequence Config",
    description="Create a new email sequence configuration for a workflow"
)
async def create_sequence_config(
    workflow_id: int,
    config_data: EmailSequenceConfigCreate,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Create a new email sequence configuration for a workflow.
    A workflow can only have one sequence configuration.
    """
    # Verify workflow access
    workflow = verify_workflow_access(workflow_id, current_user, db)

    # Check if config already exists
    existing = db.query(models.EmailSequenceConfig).filter(
        models.EmailSequenceConfig.workflow_id == workflow_id
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email sequence configuration already exists for this workflow. Use PUT to update."
        )

    # Convert skip_conditions to dict format for JSON storage
    skip_conditions_data = [cond.dict() if hasattr(cond, 'dict') else cond for cond in config_data.skip_conditions]

    # Create new config
    db_config = models.EmailSequenceConfig(
        workflow_id=workflow_id,
        name=config_data.name,
        is_enabled=config_data.is_enabled,
        ai_optimize_timing=config_data.ai_optimize_timing,
        ai_optimization_prompt=config_data.ai_optimization_prompt,
        send_method=config_data.send_method,
        timezone=config_data.timezone,
        business_hours_only=config_data.business_hours_only,
        business_hours_start=config_data.business_hours_start,
        business_hours_end=config_data.business_hours_end,
        business_days=config_data.business_days,
        skip_conditions=skip_conditions_data
    )
    db.add(db_config)
    db.commit()
    db.refresh(db_config)

    # Re-query with eager load to include emails relationship in response
    db_config = db.query(models.EmailSequenceConfig).options(
        joinedload(models.EmailSequenceConfig.emails)
    ).filter(models.EmailSequenceConfig.id == db_config.id).first()

    logger.info(f"Created email sequence config for workflow {workflow_id}")
    return db_config


@router.put(
    "/workflow/{workflow_id}",
    response_model=EmailSequenceConfig,
    summary="Update Email Sequence Config",
    description="Update the email sequence configuration for a workflow"
)
async def update_sequence_config(
    workflow_id: int,
    config_data: EmailSequenceConfigUpdate,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Update the email sequence configuration for a workflow.
    """
    # Verify workflow access
    workflow = verify_workflow_access(workflow_id, current_user, db)

    # Get existing config
    config = db.query(models.EmailSequenceConfig).filter(
        models.EmailSequenceConfig.workflow_id == workflow_id
    ).first()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email sequence configuration not found. Create one first."
        )

    # Update fields
    update_data = config_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(config, field, value)

    db.commit()
    db.refresh(config)

    # Re-query with eager load to include emails relationship in response
    config = db.query(models.EmailSequenceConfig).options(
        joinedload(models.EmailSequenceConfig.emails)
    ).filter(models.EmailSequenceConfig.id == config.id).first()

    logger.info(f"Updated email sequence config for workflow {workflow_id}")
    return config


@router.delete(
    "/workflow/{workflow_id}",
    summary="Delete Email Sequence Config",
    description="Delete the email sequence configuration for a workflow"
)
async def delete_sequence_config(
    workflow_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Delete the email sequence configuration for a workflow.
    This also deletes all associated emails.
    """
    # Verify workflow access
    workflow = verify_workflow_access(workflow_id, current_user, db)

    # Get existing config
    config = db.query(models.EmailSequenceConfig).filter(
        models.EmailSequenceConfig.workflow_id == workflow_id
    ).first()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email sequence configuration not found"
        )

    db.delete(config)
    db.commit()

    logger.info(f"Deleted email sequence config for workflow {workflow_id}")
    return {"message": "Email sequence configuration deleted successfully"}


# ============================================================================
# SEQUENCE EMAIL ENDPOINTS
# ============================================================================

@router.post(
    "/{config_id}/emails",
    response_model=SequenceEmail,
    status_code=status.HTTP_201_CREATED,
    summary="Add Email to Sequence",
    description="Add a new email to a sequence"
)
async def add_sequence_email(
    config_id: int,
    email_data: SequenceEmailCreate,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Add a new email to a sequence.
    """
    # Verify ownership through workflow
    config = db.query(models.EmailSequenceConfig).filter(
        models.EmailSequenceConfig.id == config_id,
    ).first()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email sequence configuration not found")
    verify_workflow_access(config.workflow_id, current_user, db)

    # Create email
    db_email = models.SequenceEmail(
        sequence_config_id=config_id,
        order=email_data.order,
        name=email_data.name,
        subject=email_data.subject,
        body=email_data.body,
        timing_mode=email_data.timing_mode,
        delay_value=email_data.delay_value,
        delay_unit=email_data.delay_unit,
        specific_day=email_data.specific_day,
        specific_time=email_data.specific_time,
        ai_decides_timing=email_data.ai_decides_timing,
        ai_timing_context=email_data.ai_timing_context,
        is_enabled=email_data.is_enabled,
        generation_prompt=email_data.generation_prompt,
        use_variables=email_data.use_variables
    )
    db.add(db_email)
    db.commit()
    db.refresh(db_email)

    logger.info(f"Added email to sequence config {config_id}")
    return db_email


@router.put(
    "/emails/{email_id}",
    response_model=SequenceEmail,
    summary="Update Sequence Email",
    description="Update an email in a sequence"
)
async def update_sequence_email(
    email_id: int,
    email_data: SequenceEmailUpdate,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Update an email in a sequence.
    """
    # Get email and verify ownership
    email = db.query(models.SequenceEmail).join(models.EmailSequenceConfig).filter(
        models.SequenceEmail.id == email_id,
    ).first()
    if not email:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sequence email not found")
    verify_workflow_access(email.sequence_config.workflow_id, current_user, db)

    # Update fields
    update_data = email_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(email, field, value)

    db.commit()
    db.refresh(email)

    logger.info(f"Updated sequence email {email_id}")
    return email


@router.delete(
    "/emails/{email_id}",
    summary="Delete Sequence Email",
    description="Delete an email from a sequence"
)
async def delete_sequence_email(
    email_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Delete an email from a sequence.
    """
    # Get email and verify ownership
    email = db.query(models.SequenceEmail).join(models.EmailSequenceConfig).filter(
        models.SequenceEmail.id == email_id,
    ).first()
    if not email:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sequence email not found")
    verify_workflow_access(email.sequence_config.workflow_id, current_user, db)

    db.delete(email)
    db.commit()

    logger.info(f"Deleted sequence email {email_id}")
    return {"message": "Email deleted successfully"}


@router.post(
    "/{config_id}/emails/reorder",
    summary="Reorder Sequence Emails",
    description="Update the order of emails in a sequence"
)
async def reorder_sequence_emails(
    config_id: int,
    email_ids: List[int],
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Reorder emails in a sequence.
    Pass a list of email IDs in the desired order.
    """
    # Verify ownership
    config = db.query(models.EmailSequenceConfig).filter(
        models.EmailSequenceConfig.id == config_id,
    ).first()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email sequence configuration not found")
    verify_workflow_access(config.workflow_id, current_user, db)

    # Update order for each email
    for index, email_id in enumerate(email_ids, start=1):
        email = db.query(models.SequenceEmail).filter(
            models.SequenceEmail.id == email_id,
            models.SequenceEmail.sequence_config_id == config_id
        ).first()
        if email:
            email.order = index

    db.commit()

    logger.info(f"Reordered emails in sequence config {config_id}")
    return {"message": "Emails reordered successfully", "new_order": email_ids}


# ============================================================================
# AI GENERATION ENDPOINTS
# ============================================================================

@router.post(
    "/workflow/{workflow_id}/generate-emails",
    response_model=GenerateEmailsResponse,
    summary="Generate Emails with AI",
    description="Use AI to generate email content based on transcript summary"
)
async def generate_emails_with_ai(
    workflow_id: int,
    request: GenerateEmailsRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Generate email content using AI based on the transcript summary.
    Returns suggested emails that can be added to the sequence.
    """
    from ai_service import generate_sequence_emails, set_usage_context, flush_usage_log

    # Verify workflow access
    workflow = verify_workflow_access(workflow_id, current_user, db)

    try:
        set_usage_context(user_id=current_user.id, source="sequence_generation")
        result = await generate_sequence_emails(
            transcript_summary=request.transcript_summary,
            num_emails=request.num_emails,
            custom_prompt=request.custom_prompt,
            tone=request.tone,
            include_variables=request.include_variables,
            workflow_id=workflow_id
        )
        flush_usage_log(db)
        db.flush()
        return result
    except Exception as e:
        logger.error(f"Error generating emails: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate emails: {str(e)}"
        )


@router.post(
    "/workflow/{workflow_id}/optimize-timing",
    response_model=OptimizeTimingResponse,
    summary="Optimize Email Timing with AI",
    description="Use AI to suggest optimal timing for sequence emails"
)
async def optimize_timing_with_ai(
    workflow_id: int,
    request: OptimizeTimingRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Use AI to analyze the transcript and suggest optimal timing for each email.
    """
    from ai_service import optimize_email_timing, set_usage_context, flush_usage_log

    # Verify workflow access
    workflow = verify_workflow_access(workflow_id, current_user, db)

    try:
        set_usage_context(user_id=current_user.id, source="sequence_generation")
        result = await optimize_email_timing(
            transcript_summary=request.transcript_summary,
            emails=request.emails,
            custom_prompt=request.custom_prompt,
            workflow_id=workflow_id
        )
        flush_usage_log(db)
        db.flush()
        return result
    except Exception as e:
        logger.error(f"Error optimizing timing: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to optimize timing: {str(e)}"
        )


# ============================================================================
# PREVIEW & TEST ENDPOINTS
# ============================================================================

@router.post(
    "/workflow/{workflow_id}/preview",
    summary="Preview Sequence Execution",
    description="Preview how a sequence would execute with sample data"
)
async def preview_sequence_execution(
    workflow_id: int,
    sample_data: Dict[str, Any],
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Preview how the sequence would execute with sample extracted data.
    Shows timing calculations, variable substitutions, and skip conditions.
    """
    from variable_substitution import substitute_variables
    from datetime import datetime, timedelta
    import pytz

    # Verify workflow access
    workflow = verify_workflow_access(workflow_id, current_user, db)

    # Get sequence config
    config = db.query(models.EmailSequenceConfig).filter(
        models.EmailSequenceConfig.workflow_id == workflow_id
    ).first()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No email sequence configuration found"
        )

    # Build preview
    preview = {
        "sequence_name": config.name,
        "timezone": config.timezone,
        "business_hours": f"{config.business_hours_start} - {config.business_hours_end}" if config.business_hours_only else "Any time",
        "skip_conditions_count": len(config.skip_conditions or []),
        "emails": []
    }

    # Calculate timing for each email
    tz = pytz.timezone(config.timezone)
    base_time = datetime.now(tz)
    current_time = base_time

    for email in config.emails:
        if not email.is_enabled:
            continue

        # Calculate send time
        if email.timing_mode == "relative":
            if email.delay_unit == "minutes":
                current_time = current_time + timedelta(minutes=email.delay_value)
            elif email.delay_unit == "hours":
                current_time = current_time + timedelta(hours=email.delay_value)
            elif email.delay_unit == "days":
                current_time = current_time + timedelta(days=email.delay_value)
            elif email.delay_unit == "weeks":
                current_time = current_time + timedelta(weeks=email.delay_value)

        # Substitute variables in subject/body for preview
        substituted_subject = email.subject
        substituted_body = email.body

        # Simple variable substitution for preview
        for key, value in sample_data.items():
            placeholder = f"{{{{{key}}}}}"
            if isinstance(value, str):
                substituted_subject = substituted_subject.replace(placeholder, value)
                substituted_body = substituted_body.replace(placeholder, value)

        preview["emails"].append({
            "order": email.order,
            "name": email.name,
            "scheduled_for": current_time.isoformat(),
            "timing": f"{email.delay_value} {email.delay_unit}" if email.timing_mode == "relative" else f"{email.specific_day} at {email.specific_time}",
            "ai_decides_timing": email.ai_decides_timing,
            "subject_preview": substituted_subject[:100],
            "body_preview": substituted_body[:200] + "..." if len(substituted_body) > 200 else substituted_body
        })

    return preview
