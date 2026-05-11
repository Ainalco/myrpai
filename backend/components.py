from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
import logging

from database import get_db
from auth import get_current_active_user
from cache_service import cache_clear_pattern
import models

logger = logging.getLogger(__name__)

router = APIRouter()

SEND_AS_NEW_THREAD = "new_thread"
SEND_AS_REPLY_TO_COMPONENT = "reply_to_component"

# Pydantic models
class ComponentCreate(BaseModel):
    workflow_id: Optional[int] = None
    type: str
    name: str
    description: Optional[str] = None
    configuration: Optional[dict] = {}
    position_x: int = 0
    position_y: int = 0
    order: int = 0

class ComponentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    configuration: Optional[dict] = None
    position_x: Optional[int] = None
    position_y: Optional[int] = None
    order: Optional[int] = None

class Component(BaseModel):
    id: int
    workflow_id: int
    type: str
    name: str
    description: Optional[str] = None
    configuration: dict
    position_x: int
    position_y: int
    order: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class ConnectionCreate(BaseModel):
    from_component_id: int
    to_component_id: int
    condition: Optional[str] = None

class Connection(BaseModel):
    id: int
    from_component_id: int
    to_component_id: int
    condition: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

# Component type definitions for validation
COMPONENT_TYPES = {
    "input_sources": {
        "name": "Input Sources",
        "description": "External data source",
        "icon": "file",
        "category": "input",
        "is_advanced": False  # Available to all users
    },
    "text_generation": {
        "name": "Text Generation",
        "description": "Generate summaries, subject lines, or any text",
        "icon": "document",
        "category": "generation",
        "is_advanced": False  # Available to all users
    },
    "email": {
        "name": "Email",
        "description": "Generate and send follow-up emails",
        "icon": "mail",
        "category": "action",
        "is_advanced": False  # Available to all users
    },
    "sms": {
        "name": "SMS Message",
        "description": "Send AI-generated SMS follow-ups via Twilio",
        "icon": "smartphone",
        "category": "action",
        "is_advanced": False,
    },
    "whatsapp": {
    "name": "WhatsApp Message",
    "description": "Send AI-generated WhatsApp follow-ups via WhatsApp Business Cloud API",
    "icon": "message-circle",
    "category": "action",
    "is_advanced": False,
        "config_schema": {
            "ai_prompt": {
                "type": "textarea",
                "label": "AI Instructions",
                "placeholder": "Tell the AI what kind of WhatsApp message to write...",
                "required": True,
            },
            "recipient_phone_field": {
                "type": "text",
                "label": "Recipient Phone Field",
                "default": "recipient_phone",
            },
            "send_timing": {
                "type": "select",
                "options": ["immediate", "fixed_delay", "ai_decides"],
                "default": "immediate",
            },
            "delay_config": {
                "type": "object",
                "fields": {
                    "delay_hours": {"type": "number", "default": 0},
                    "delay_days": {"type": "number", "default": 0},
                    "business_hours_only": {"type": "toggle", "default": True},
                },
                "visible_when": {"send_timing": "fixed_delay"},
            },
            "ai_filter": {
                "type": "toggle",
                "label": "AI Quality Filter",
                "default": True,
            },
            "timeline_check": {
                "type": "toggle",
                "label": "Timeline Check",
                "default": True,
            },
            "message_style": {
                "type": "select",
                "label": "Message Style",
                "options": ["conversational", "professional", "brief"],
                "default": "conversational",
            },
            "fallback_template": {
                "type": "select",
                "label": "Template outside 24h window",
                "options": [
                    "meeting_followup_1",
                    "meeting_followup_2",
                    "meeting_followup_3",
                ],
                "default": "meeting_followup_1",
            },
        },
    },
    "conditional_logic": {
        "name": "Conditional Logic",
        "description": "Filter based on conditions",
        "icon": "branch",
        "category": "logic",
        "is_advanced": False  # Available to all users
    },
    "ai_filter": {
        "name": "AI Filter",
        "description": "Filter based on AI analysis",
        "icon": "brain",
        "category": "filter",
        "is_advanced": False  # Available to all users
    },
    "action": {
        "name": "Action",
        "description": "Push data to external systems",
        "icon": "external-link",
        "category": "action",
        "is_advanced": False  # Available to all users
    },
    "company_name_matcher": {
        "name": "Advanced Matching",
        "description": "AI-powered matching of organizations and deals from Pipedrive based on conversation data",
        "icon": "building",
        "category": "advanced",
        "is_advanced": True  # Only visible to power users
    },
    "advanced_action": {
        "name": "Advanced Action",
        "description": "Update a single field on a Pipedrive deal",
        "icon": "zap",
        "category": "action",
        "is_advanced": True  # Only visible to power users
    }
}

def verify_workflow_ownership(workflow_id: int, current_user: models.User, db: Session):
    """Role-aware workflow access check. Delegates to auth.verify_workflow_access."""
    from auth import verify_workflow_access
    return verify_workflow_access(workflow_id, current_user, db)


def _validate_email_threading_config(
    db: Session,
    workflow_id: int,
    component_type: str,
    component_id: Optional[int],
    component_order: int,
    configuration: Optional[dict],
) -> dict:
    """Validate and normalize same-thread config for email components."""
    config = dict(configuration or {})
    if component_type != "email":
        return config

    send_as = config.get("send_as") or SEND_AS_NEW_THREAD
    if send_as not in {SEND_AS_NEW_THREAD, SEND_AS_REPLY_TO_COMPONENT}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid send_as. Expected 'new_thread' or 'reply_to_component'.",
        )

    if send_as == SEND_AS_NEW_THREAD:
        config["send_as"] = SEND_AS_NEW_THREAD
        config["thread_parent_component_id"] = None
        return config

    parent_component_id = config.get("thread_parent_component_id")
    if not parent_component_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="thread_parent_component_id is required when send_as is 'reply_to_component'.",
        )

    parent_component = db.query(models.Component).filter(
        models.Component.id == parent_component_id,
        models.Component.workflow_id == workflow_id,
    ).first()
    if not parent_component:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="thread_parent_component_id must reference an existing component in the same workflow.",
        )
    if parent_component.type != "email":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="thread_parent_component_id must reference an email component.",
        )
    if component_id and parent_component.id == component_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An email component cannot reply to itself.",
        )
    if parent_component.order >= component_order:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="thread_parent_component_id must reference an earlier email component in the workflow.",
        )

    config["send_as"] = SEND_AS_REPLY_TO_COMPONENT
    config["thread_parent_component_id"] = int(parent_component_id)
    return config


def _validate_workflow_email_threading_config(db: Session, workflow_id: int) -> None:
    """Validate threading consistency across all components in a workflow."""
    ordered_components = db.query(models.Component).filter(
        models.Component.workflow_id == workflow_id
    ).order_by(models.Component.order.asc(), models.Component.id.asc()).all()

    for component in ordered_components:
        try:
            normalized = _validate_email_threading_config(
                db=db,
                workflow_id=workflow_id,
                component_type=component.type,
                component_id=component.id,
                component_order=component.order,
                configuration=component.configuration or {},
            )
            if component.type == "email" and normalized != (component.configuration or {}):
                component.configuration = normalized
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else "Invalid threading configuration."
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Email threading validation failed for '{component.name}': {detail}",
            ) from exc


def _commit_with_threading_validation(db: Session, workflow_id: int) -> None:
    """Flush + validate + commit atomically, rolling back on any failure."""
    try:
        db.flush()
        _validate_workflow_email_threading_config(db, workflow_id)
        db.commit()
    except Exception:
        db.rollback()
        raise

@router.get(
    "/types",
    summary="Get Component Types",
    description="Retrieve all available component types and their metadata"
)
async def get_component_types(
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Get all available component types.

    Returns a dictionary of component types with their names, descriptions, icons, and categories.
    Used by the frontend to display available components when building workflows.

    Filters out advanced components if user doesn't have enable_advanced_components flag.

    Returns:
        dict: Component types dictionary with metadata for each type
    """
    # If user has advanced components enabled, return all types
    if current_user.enable_advanced_components:
        return COMPONENT_TYPES

    # Otherwise, filter out advanced components
    filtered_types = {
        key: value for key, value in COMPONENT_TYPES.items()
        if not value.get("is_advanced", False)
    }

    return filtered_types

@router.get(
    "/{workflow_id}/components",
    response_model=List[Component],
    summary="List Workflow Components",
    description="Get all components in a workflow, ordered by execution sequence"
)
async def get_workflow_components(
    workflow_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    List all components in a workflow.

    Returns components ordered by their execution order (order field).
    Input source component is always first (order 0).

    Args:
        workflow_id: The workflow ID
        current_user: The authenticated user (injected)
        db: Database session (injected)

    Returns:
        List[Component]: All components in execution order

    Raises:
        HTTPException 404: If workflow not found or user doesn't own it
    """
    verify_workflow_ownership(workflow_id, current_user, db)
    
    components = db.query(models.Component).filter(
        models.Component.workflow_id == workflow_id
    ).order_by(models.Component.order).all()
    
    return components

@router.post(
    "/{workflow_id}/components",
    response_model=Component,
    status_code=status.HTTP_201_CREATED,
    summary="Create Component",
    description="Add a new component to the workflow with automatic order assignment"
)
async def create_component(
    workflow_id: int,
    component_data: ComponentCreate,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Create a new component in a workflow.

    Validates component type and prevents creating duplicate input_sources components
    (only one allowed per workflow). Automatically assigns the next available order number.

    Args:
        workflow_id: The workflow ID
        component_data: Component configuration
        current_user: The authenticated user (injected)
        db: Database session (injected)

    Returns:
        Component: The newly created component

    Raises:
        HTTPException 404: If workflow not found or user doesn't own it
        HTTPException 400: If component type is invalid or duplicate input_source
    """
    verify_workflow_ownership(workflow_id, current_user, db)

    if component_data.type not in COMPONENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid component type: {component_data.type}"
        )
    
    # Prevent creation of additional input source components
    if component_data.type == "input_sources":
        existing_input_source = db.query(models.Component).filter(
            models.Component.workflow_id == workflow_id,
            models.Component.type == "input_sources"
        ).first()

        if existing_input_source:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only one input source component is allowed per workflow. Use the existing input source component."
            )
        # Input source must always be order 0
        component_data.order = 0
    else:
        # For non-input-source components, auto-assign the next available order
        # Get the highest order in the workflow
        max_order = db.query(models.Component.order).filter(
            models.Component.workflow_id == workflow_id
        ).order_by(models.Component.order.desc()).first()

        # Assign next order (max + 1, or 1 if only input source exists)
        if max_order and max_order[0] is not None:
            component_data.order = max_order[0] + 1
        else:
            component_data.order = 1  # First non-input-source component

    # Ensure workflow_id matches URL parameter
    component_data.workflow_id = workflow_id

    # Set default configuration for ai_filter components
    if component_data.type == "ai_filter" and not component_data.configuration:
        component_data.configuration = {
            "ai_prompt": "Analyze the following information and determine if the client shows high buying intent. Return 'high intent', 'medium intent', or 'low intent' based on their engagement, questions, and interest level.",
            "condition_operator": "contains",
            "condition_value": "high intent",
            "case_sensitive": False,
            # "haiku" is ~10× cheaper than Sonnet and fine for yes/no classification.
            # Only applies to newly-created filters — existing components with no "model"
            # key continue to resolve to Sonnet, preserving their prior behavior.
            "model": "haiku",
        }

    component_data.configuration = _validate_email_threading_config(
        db=db,
        workflow_id=workflow_id,
        component_type=component_data.type,
        component_id=None,
        component_order=component_data.order,
        configuration=component_data.configuration,
    )

    db_component = models.Component(**component_data.dict())
    db.add(db_component)
    _commit_with_threading_validation(db, workflow_id)
    db.refresh(db_component)
    return db_component

@router.put(
    "/{workflow_id}/components/{component_id}",
    response_model=Component,
    summary="Update Component",
    description="Update component properties with validation for order restrictions"
)
async def update_component(
    workflow_id: int,
    component_id: int,
    component_data: ComponentUpdate,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Update an existing component.

    Allows partial updates (only provided fields are updated). Enforces rules:
    - Input source components must remain at order 0
    - Only input source components can have order 0

    Args:
        workflow_id: The workflow ID
        component_id: The component ID to update
        component_data: Fields to update (all optional)
        current_user: The authenticated user (injected)
        db: Database session (injected)

    Returns:
        Component: The updated component

    Raises:
        HTTPException 404: If workflow/component not found or user doesn't own it
        HTTPException 400: If order validation fails
    """
    verify_workflow_ownership(workflow_id, current_user, db)
    
    component = db.query(models.Component).filter(
        models.Component.id == component_id,
        models.Component.workflow_id == workflow_id
    ).first()
    
    if not component:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Component not found"
        )
    
    update_data = component_data.dict(exclude_unset=True)
    
    # Prevent changing order of input source components
    if component.type == "input_sources" and "order" in update_data:
        if update_data["order"] != 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Input source components must always be at order 0 (first in workflow)."
            )
    
    # Prevent other components from having order 0
    if "order" in update_data and update_data["order"] == 0 and component.type != "input_sources":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only input source components can have order 0."
        )

    if "configuration" in update_data:
        target_order = update_data.get("order", component.order)
        update_data["configuration"] = _validate_email_threading_config(
            db=db,
            workflow_id=workflow_id,
            component_type=component.type,
            component_id=component.id,
            component_order=target_order,
            configuration=update_data["configuration"],
        )
    elif component.type == "email" and "order" in update_data:
        update_data["configuration"] = _validate_email_threading_config(
            db=db,
            workflow_id=workflow_id,
            component_type=component.type,
            component_id=component.id,
            component_order=update_data["order"],
            configuration=component.configuration,
        )
    
    for field, value in update_data.items():
        setattr(component, field, value)

    _commit_with_threading_validation(db, workflow_id)
    db.refresh(component)
    return component

@router.delete(
    "/{workflow_id}/components/{component_id}",
    summary="Delete Component",
    description="Remove a component from the workflow (input sources cannot be deleted)"
)
async def delete_component(
    workflow_id: int,
    component_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Delete a component from a workflow.

    Input source components cannot be deleted as they are required for workflow execution.

    Args:
        workflow_id: The workflow ID
        component_id: The component ID to delete
        current_user: The authenticated user (injected)
        db: Database session (injected)

    Returns:
        dict: Success message

    Raises:
        HTTPException 404: If workflow/component not found or user doesn't own it
        HTTPException 400: If attempting to delete an input_sources component
    """
    verify_workflow_ownership(workflow_id, current_user, db)
    
    component = db.query(models.Component).filter(
        models.Component.id == component_id,
        models.Component.workflow_id == workflow_id
    ).first()
    
    if not component:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Component not found"
        )
    
    # Prevent deletion of input source components
    if component.type == "input_sources":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Input source components cannot be deleted. They are required for workflow execution."
        )

    if component.type == "email":
        dependent_components = db.query(models.Component).filter(
            models.Component.workflow_id == workflow_id,
            models.Component.type == "email",
        ).all()
        for dependent in dependent_components:
            cfg = dict(dependent.configuration or {})
            if cfg.get("send_as") == SEND_AS_REPLY_TO_COMPONENT and cfg.get("thread_parent_component_id") == component.id:
                cfg["send_as"] = SEND_AS_NEW_THREAD
                cfg["thread_parent_component_id"] = None
                cfg["threading_warning_code"] = "parent_deleted"
                cfg["threading_warning_parent_component_id"] = component.id
                cfg["threading_warning_parent_component_name"] = component.name
                dependent.configuration = cfg
    
    db.delete(component)
    _commit_with_threading_validation(db, workflow_id)
    return {"message": "Component deleted successfully"}

# Config-specific endpoint for components
class ComponentConfigUpdate(BaseModel):
    configuration: dict

@router.put(
    "/{component_id}/config",
    response_model=Component,
    summary="Update Component Configuration",
    description="Update only the configuration field of a component"
)
async def update_component_config(
    component_id: int,
    config_data: ComponentConfigUpdate,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Update component configuration only.

    Allows updating the configuration object without affecting other component properties
    like name, description, or position.

    Args:
        component_id: The component ID
        config_data: New configuration object
        current_user: The authenticated user (injected)
        db: Database session (injected)

    Returns:
        Component: The updated component

    Raises:
        HTTPException 404: If component not found or user doesn't own the workflow
    """
    # Get component and verify ownership through workflow
    component = db.query(models.Component).filter(
        models.Component.id == component_id
    ).first()
    
    if not component:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Component not found"
        )
    
    # Verify workflow ownership
    verify_workflow_ownership(component.workflow_id, current_user, db)
    
    # Update only the configuration
    component.configuration = _validate_email_threading_config(
        db=db,
        workflow_id=component.workflow_id,
        component_type=component.type,
        component_id=component.id,
        component_order=component.order,
        configuration=config_data.configuration,
    )

    _commit_with_threading_validation(db, component.workflow_id)
    db.refresh(component)
    return component

@router.get(
    "/{workflow_id}/connections",
    response_model=List[Connection],
    summary="List Workflow Connections",
    description="Get all connections between components in a workflow"
)
async def get_workflow_connections(
    workflow_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    List all connections in a workflow.

    Returns all connections that link components together, defining the execution flow.

    Args:
        workflow_id: The workflow ID
        current_user: The authenticated user (injected)
        db: Database session (injected)

    Returns:
        List[Connection]: All connections in the workflow

    Raises:
        HTTPException 404: If workflow not found or user doesn't own it
    """
    verify_workflow_ownership(workflow_id, current_user, db)
    
    # Get connections for components in this workflow
    component_ids = db.query(models.Component.id).filter(
        models.Component.workflow_id == workflow_id
    ).subquery()
    
    connections = db.query(models.Connection).filter(
        models.Connection.from_component_id.in_(component_ids)
    ).all()
    
    return connections

@router.post(
    "/{workflow_id}/connections",
    response_model=Connection,
    status_code=status.HTTP_201_CREATED,
    summary="Create Connection",
    description="Create a connection between two components in the workflow"
)
async def create_connection(
    workflow_id: int,
    connection_data: ConnectionCreate,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Create a connection between two components.

    Validates that both components belong to the specified workflow before creating the connection.

    Args:
        workflow_id: The workflow ID
        connection_data: Connection details (from_component_id, to_component_id, optional condition)
        current_user: The authenticated user (injected)
        db: Database session (injected)

    Returns:
        Connection: The newly created connection

    Raises:
        HTTPException 404: If workflow not found or user doesn't own it
        HTTPException 400: If components don't belong to the workflow
    """
    verify_workflow_ownership(workflow_id, current_user, db)

    # Verify both components belong to this workflow
    from_component = db.query(models.Component).filter(
        models.Component.id == connection_data.from_component_id,
        models.Component.workflow_id == workflow_id
    ).first()
    
    to_component = db.query(models.Component).filter(
        models.Component.id == connection_data.to_component_id,
        models.Component.workflow_id == workflow_id
    ).first()
    
    if not from_component or not to_component:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both components must belong to the specified workflow"
        )
    
    db_connection = models.Connection(**connection_data.dict())
    db.add(db_connection)
    db.commit()
    db.refresh(db_connection)
    return db_connection

@router.delete(
    "/{workflow_id}/connections/{connection_id}",
    summary="Delete Connection",
    description="Remove a connection between components"
)
async def delete_connection(
    workflow_id: int,
    connection_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Delete a connection from the workflow.

    Args:
        workflow_id: The workflow ID
        connection_id: The connection ID to delete
        current_user: The authenticated user (injected)
        db: Database session (injected)

    Returns:
        dict: Success message

    Raises:
        HTTPException 404: If workflow/connection not found or user doesn't own workflow
    """
    verify_workflow_ownership(workflow_id, current_user, db)
    
    connection = db.query(models.Connection).filter(
        models.Connection.id == connection_id
    ).first()
    
    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found"
        )
    
    db.delete(connection)
    db.commit()
    return {"message": "Connection deleted successfully"}

# Component testing endpoint
class ComponentTestData(BaseModel):
    test_data: Optional[dict] = None
    fireflies_transcript_id: Optional[str] = None


def _inject_rag_ids_for_test(
    target_component: models.Component,
    input_data: dict,
    db: Session,
) -> dict:
    """Inject __account_id__/__user_id__/__contact_id__/__org_id__ for tests.

    Mirrors what `execute_workflow_background` does on real runs, so RAG fires
    during component tests too. Without this the tests silently skip RAG —
    the gating checks in ai_service / executions short-circuit on missing
    `__account_id__`. Best-effort: never fail the test path because of this.
    """
    try:
        workflow = db.query(models.Workflow).filter(
            models.Workflow.id == target_component.workflow_id
        ).first()
        if not workflow or not workflow.owner_id:
            return input_data

        input_data["__user_id__"] = workflow.owner_id

        owner = db.query(models.User).filter(
            models.User.id == workflow.owner_id
        ).first()
        account = None
        if owner and owner.org_id:
            account = db.query(models.Account).filter(
                models.Account.org_id == owner.org_id
            ).first()
        if account:
            input_data["__account_id__"] = account.id

        # Resolve contact_id / org_id from participants — same domain filter
        # as the real execution path so we skip the workflow owner's own
        # emails and match the actual customer contact.
        internal_domains: list[str] = []
        if owner and owner.internal_domains:
            internal_domains = [
                d.strip().lower()
                for d in owner.internal_domains.split(",")
                if d.strip()
            ]
        for p in input_data.get("participants") or []:
            if not (isinstance(p, dict) and p.get("email")):
                continue
            p_email = p["email"]
            domain = p_email.split("@")[-1].lower() if "@" in p_email else ""
            if internal_domains and any(
                domain == d or domain.endswith("." + d)
                for d in internal_domains
            ):
                continue
            contact = db.query(models.Contact).filter(
                models.Contact.email == p_email,
                models.Contact.user_id == workflow.owner_id,
            ).first()
            if contact:
                input_data["__contact_id__"] = contact.id
                if contact.contact_organization_id:
                    input_data["__org_id__"] = contact.contact_organization_id
                break
    except Exception as e:
        logger.warning(f"_inject_rag_ids_for_test failed (non-blocking): {e}")
    return input_data


async def execute_upstream_components(
    target_component: models.Component,
    initial_input_data: dict,
    db: Session
) -> dict:
    """
    Execute all components that come before the target component in the workflow.
    This ensures variables like {{summary}} from Text Generation are available
    when testing downstream components like Email.

    Args:
        target_component: The component being tested
        initial_input_data: Starting data (e.g., from Fireflies transcript)
        db: Database session

    Returns:
        Accumulated data from all upstream component executions
    """
    from executions import ComponentExecutor

    # RAG visibility: inject account/user/contact/org IDs into the initial
    # input_data the same way execute_workflow_background does, so RAG fires
    # during component tests instead of silently no-op'ing on `if rag_account_id`.
    # We mutate initial_input_data in place (and the per-component copies below
    # inherit via update) so every upstream and the target component sees them.
    initial_input_data = _inject_rag_ids_for_test(target_component, initial_input_data, db)

    # Get all components in the workflow ordered by execution order
    all_components = db.query(models.Component).filter(
        models.Component.workflow_id == target_component.workflow_id
    ).order_by(models.Component.order).all()

    # Find components that come before the target component
    upstream_components = [c for c in all_components if c.order < target_component.order]

    if not upstream_components:
        logger.info(f"Test: No upstream components for '{target_component.name}'")
        return initial_input_data

    logger.info(f"Test: Running {len(upstream_components)} upstream component(s) before '{target_component.name}'")

    # Execute each upstream component in order
    accumulated_data = initial_input_data.copy()
    component_outputs = {}

    for component in upstream_components:
        logger.info(f"Test: Running upstream component '{component.name}' ({component.type})")

        # Track AI usage per upstream component
        from ai_service import set_usage_component_id
        set_usage_component_id(component.id)

        # Execute the component
        result = await ComponentExecutor.execute_component(
            component.type,
            component.configuration or {},
            {**accumulated_data, "workflow_id": target_component.workflow_id, "test_mode": True},
            db=db,
        )

        if result.get("status") == "success":
            result_data = result.get("data", {})
            # Store component output by name (for {{component:Name}} syntax)
            component_outputs[component.name] = result_data
            # Flat merge for field-level variables ({{summary}}, etc.)
            accumulated_data.update(result_data)
            logger.info(f"Test: Upstream component '{component.name}' completed successfully")
        else:
            logger.warning(f"Test: Upstream component '{component.name}' failed: {result.get('error')}")
            # Continue anyway - downstream component might not need this output

    # Add component outputs for component-level variable references
    accumulated_data["__component_outputs__"] = component_outputs

    return accumulated_data

class PreSendTestRequest(BaseModel):
    test_type: str  # "crm" or "ai_filter"
    component_id: int
    # CRM test fields
    condition_groups: Optional[list] = None
    group_logic: Optional[str] = "AND"
    data_source: Optional[str] = "pipedrive"
    # AI filter test fields
    ai_prompt: Optional[str] = None
    condition_operator: Optional[str] = None
    condition_value: Optional[str] = None
    case_sensitive: Optional[bool] = False
    model: Optional[str] = None  # "sonnet" | "haiku" — resolver defaults to sonnet when unset


@router.post(
    "/pre-send-check/test",
    summary="Test Pre-Send Check",
    description="Test CRM condition groups or AI filter pre-send check against real data"
)
async def test_pre_send_check(
    payload: PreSendTestRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Test a pre-send check (CRM or AI filter) using real data from the most recent execution.
    """
    import time
    test_start = time.time()

    # Get component and verify ownership
    component = db.query(models.Component).filter(
        models.Component.id == payload.component_id
    ).first()
    if not component:
        raise HTTPException(status_code=404, detail="Component not found")

    from auth import verify_workflow_access
    workflow = verify_workflow_access(component.workflow_id, current_user, db)

    # Get participant emails from most recent execution
    recent_exec = db.query(models.Execution).filter(
        models.Execution.workflow_id == workflow.id,
        models.Execution.status == "completed"
    ).order_by(models.Execution.started_at.desc()).first()

    participant_emails = []
    input_data = {}
    if recent_exec and recent_exec.results:
        results = recent_exec.results if isinstance(recent_exec.results, dict) else {}
        input_data = results
        # Try to extract participant emails from execution results
        participants = results.get("participants", results.get("Participants", ""))
        if isinstance(participants, str):
            import re
            participant_emails = re.findall(r'[\w.+-]+@[\w-]+\.[\w.-]+', participants)
        elif isinstance(participants, list):
            participant_emails = participants

    try:
        if payload.test_type == "crm":
            from conditional_logic import evaluate_pre_send_check_groups

            if not participant_emails:
                return {
                    "success": True,
                    "passed": True,
                    "reason": "No participant emails found in recent execution data — skipped",
                    "duration": round(time.time() - test_start, 2)
                }

            config = {
                "condition_groups": payload.condition_groups or [],
                "group_logic": payload.group_logic or "AND",
                "data_source": payload.data_source or "pipedrive",
                "context": {"participant_emails": participant_emails}
            }

            passed, reason = await evaluate_pre_send_check_groups(
                db, current_user.id, config
            )

            return {
                "success": True,
                "passed": passed,
                "reason": reason,
                "participant_emails": participant_emails,
                "duration": round(time.time() - test_start, 2)
            }

        elif payload.test_type == "ai_filter":
            from conditional_logic import evaluate_pre_send_ai_filter

            if not input_data:
                return {
                    "success": True,
                    "passed": True,
                    "reason": "No execution data found to test AI filter against",
                    "duration": round(time.time() - test_start, 2)
                }

            ai_config = {
                "ai_prompt": payload.ai_prompt or "",
                "condition_operator": payload.condition_operator or "contains",
                "condition_value": payload.condition_value or "",
                "case_sensitive": payload.case_sensitive or False,
                "model": payload.model,
            }

            passed, reason = await evaluate_pre_send_ai_filter(ai_config, input_data, db=db)

            return {
                "success": True,
                "passed": passed,
                "reason": reason,
                "duration": round(time.time() - test_start, 2)
            }

        else:
            raise HTTPException(status_code=400, detail=f"Unknown test_type: {payload.test_type}")

    except Exception as e:
        logger.error(f"Pre-send check test failed: {e}", exc_info=True)
        return {
            "success": False,
            "passed": False,
            "reason": f"Test error: {str(e)}",
            "duration": round(time.time() - test_start, 2)
        }


@router.post(
    "/{component_id}/test",
    summary="Test Component",
    description="Test a component with custom data, Fireflies transcript, or recent execution data"
)
async def test_component(
    component_id: int,
    test_payload: Optional[ComponentTestData] = None,
    trace: bool = Query(False, description="Capture per-call API trace and include it in the response"),
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Test a component execution with various data sources.

    Supports three modes:
    1. **Fireflies Transcript**: Provide `fireflies_transcript_id` to fetch and use transcript data
    2. **Custom Data**: Provide `test_data` with custom input for testing
    3. **Recent Execution**: If neither provided, uses data from the most recent workflow execution

    Args:
        component_id: The component ID to test
        test_payload: Optional test configuration (transcript ID or custom data)
        current_user: The authenticated user (injected)
        db: Database session (injected)

    Returns:
        dict: Test results including component output or error details

    Raises:
        HTTPException 404: If component not found or user doesn't own workflow
    """
    # Get component and verify ownership through workflow
    component = db.query(models.Component).filter(
        models.Component.id == component_id
    ).first()

    if not component:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Component not found"
        )

    # Verify workflow ownership
    verify_workflow_ownership(component.workflow_id, current_user, db)

    # Check acorn balance before running test
    from acorn_service import get_account_for_user, check_user_can_execute
    account = get_account_for_user(current_user, db)
    if not account:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No billing account found")
    if not check_user_can_execute(current_user, account, db):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Insufficient Acorn balance to run this test."
        )

    # Import the component executor
    from executions import ComponentExecutor
    from tracing import _trace_buffer
    import time

    test_start_time = time.time()
    logger.info(f"Testing component {component_id} ({component.type}) | Name: '{component.name}'")

    # Set up AI usage tracking BEFORE upstream execution so upstream costs are captured
    from ai_service import set_usage_context, set_usage_component_id, flush_usage_log, reset_token_counter, get_token_totals
    reset_token_counter()
    set_usage_context(
        user_id=current_user.id,
        source="component_test",
        component_id=None,
    )

    # When trace=true, install a trace buffer in the async context so instrumented
    # call sites (rag_service, ai_service, fireflies_service, pipedrive_service,
    # email_service) push entries onto it. We set/reset the ContextVar manually
    # here (rather than `with trace_session()`) to avoid re-indenting the
    # existing try/except block. trace_buf is None when tracing is off.
    trace_buf: list | None = [] if trace else None
    trace_token = _trace_buffer.set(trace_buf) if trace else None

    try:
        # Determine input data source
        input_data = {}

        # If Fireflies transcript ID is provided, fetch from Fireflies
        if test_payload and test_payload.fireflies_transcript_id:
            from fireflies_service import fetch_transcript
            try:
                transcript_data = await fetch_transcript(
                    test_payload.fireflies_transcript_id,
                    db,
                    current_user.id
                )
                if transcript_data:
                    # Run all upstream components to populate variables like {{summary}}
                    # This ensures downstream components (like Email) have access to
                    # outputs from upstream components (like Text Generation)
                    input_data = await execute_upstream_components(
                        target_component=component,
                        initial_input_data={**transcript_data, "source": "fireflies_webhook"},
                        db=db
                    )
                else:
                    raise ValueError("Transcript not found")
            except Exception as e:
                return {
                    "success": False,
                    "component_id": component.id,
                    "component_name": component.name,
                    "component_type": component.type,
                    "error": f"Failed to fetch Fireflies transcript: {str(e)}"
                }

        # If custom test data is provided (e.g. demo transcripts), run upstream components too
        elif test_payload and test_payload.test_data:
            input_data = await execute_upstream_components(
                target_component=component,
                initial_input_data=test_payload.test_data,
                db=db
            )

        # Otherwise, try to use data from the most recent workflow execution
        else:
            logger.info(f"Looking for most recent execution for workflow {component.workflow_id}")

            # Get the most recent execution for this workflow (completed or failed)
            # We can still use data from failed executions if earlier components succeeded
            recent_execution = db.query(models.Execution).filter(
                models.Execution.workflow_id == component.workflow_id,
                models.Execution.status.in_(["completed", "failed"])
            ).order_by(models.Execution.started_at.desc()).first()

            if recent_execution:
                logger.info(f"Found execution {recent_execution.id} (completed at {recent_execution.completed_at})")

                # Start with the execution's input data (from Fireflies webhook)
                input_data = recent_execution.input_data.copy() if recent_execution.input_data else {}
                logger.info(f"Started with execution input_data keys: {list(input_data.keys())}")

                # Get all component executions for this execution to build accumulated data
                component_executions = db.query(models.ComponentExecution).filter(
                    models.ComponentExecution.execution_id == recent_execution.id,
                    models.ComponentExecution.status == "completed"
                ).order_by(models.ComponentExecution.id).all()

                logger.info(f"Found {len(component_executions)} completed component executions")

                # Build component outputs for component-level variable references
                # This mirrors the behavior in execute_workflow_background (executions.py:1375)
                component_outputs = {}

                # Accumulate data from each component execution
                for comp_exec in component_executions:
                    comp = db.query(models.Component).filter(models.Component.id == comp_exec.component_id).first()
                    comp_name = comp.name if comp else f"Component {comp_exec.component_id}"

                    if comp_exec.output_data and comp_exec.output_data.get("status") == "success":
                        result_data = comp_exec.output_data.get("data", {})
                        logger.info(f"  Component '{comp_name}' output keys: {list(result_data.keys())}")

                        # Store component output with name as key (for {{component:Name}} syntax)
                        component_outputs[comp_name] = result_data

                        # Also flat merge for backward compatibility (field-level variables)
                        input_data.update(result_data)
                    else:
                        logger.warning(f"  Component '{comp_name}' has no success data")

                # Add component outputs to input_data for component-level variable references
                if component_outputs:
                    input_data["__component_outputs__"] = component_outputs
                    logger.info(f"Built component_outputs with keys: {list(component_outputs.keys())}")

                logger.info(f"After accumulation, input_data keys: {list(input_data.keys())}")
                if "extracted_information" in input_data:
                    logger.info(f"  extracted_information keys: {list(input_data['extracted_information'].keys())}")
                else:
                    logger.warning("  No extracted_information in accumulated data!")

            else:
                # No previous execution found - guide user to run workflow first
                return {
                    "success": False,
                    "component_id": component.id,
                    "component_name": component.name,
                    "component_type": component.type,
                    "error": "No workflow execution data available. Please run your workflow at least once before testing individual components. This ensures the test uses real data from your Fireflies transcripts and Text Generation outputs.",
                    "suggestion": "Click 'Run Workflow' to execute the entire workflow, then try testing this component again."
                }

        # Add workflow_id to input data (needed by some components like Action)
        input_data["workflow_id"] = component.workflow_id

        # Mark this as a test execution (important for email component to skip queuing)
        input_data["test_mode"] = True

        # Inject account/user/contact/org IDs (idempotent — execute_upstream_components
        # already does this, but cover the no-upstream case where it's bypassed).
        input_data = _inject_rag_ids_for_test(component, input_data, db)

        # Switch usage tracking to the target component (don't clear upstream records)
        set_usage_component_id(component.id)

        # Execute the component
        logger.info(f"Executing component {component_id} with input data keys: {list(input_data.keys())}")
        execution_start = time.time()

        result = await ComponentExecutor.execute_component(
            component.type,
            component.configuration or {},
            input_data,
            db=db,
        )

        execution_duration = time.time() - execution_start
        total_duration = time.time() - test_start_time

        # Get cost from in-memory records BEFORE flushing (deterministic, no DB timing issues)
        from ai_service import get_usage_cost
        total_cost_usd = get_usage_cost()

        # Flush AI usage to database
        token_totals = get_token_totals()
        flush_usage_log(db)
        db.commit()

        # Deduct acorns based on AI cost
        acorns_spent = 0.0
        if total_cost_usd > 0:
            try:
                from acorn_service import spend_acorns, usd_to_acorns
                if account:
                    acorns_spent = usd_to_acorns(total_cost_usd, db)
                    spend_acorns(
                        account_id=account.id,
                        user_id=current_user.id,
                        amount=acorns_spent,
                        description=f"Component test: {component.name}",
                        db=db,
                        metadata={"component_id": component.id, "component_type": component.type},
                        allow_overdraft=True,
                    )
                    db.commit()
                    logger.info(f"Acorn debit for component test: {acorns_spent:.4f} acorns (${total_cost_usd:.6f} USD)")
            except Exception as acorn_err:
                logger.warning(f"Acorn debit failed for component test {component.id}: {acorn_err}")

        logger.info(
            f"Component test completed | Component: {component.id} ({component.type}) | "
            f"Execution time: {execution_duration:.2f}s | Total time: {total_duration:.2f}s | "
            f"Status: {'success' if result.get('status') == 'success' else 'error'} | "
            f"Tokens: {token_totals['total_tokens']} | Acorns: {acorns_spent:.2f}"
        )

        response = {
            "success": True,
            "component_id": component.id,
            "component_name": component.name,
            "component_type": component.type,
            "results": result,
            "token_usage": token_totals,
            "acorns_spent": round(acorns_spent, 2),
        }
        if trace_buf is not None:
            response["trace"] = list(trace_buf)
        return response

    except Exception as e:
        total_duration = time.time() - test_start_time
        logger.error(f"Component test failed for {component.id} after {total_duration:.2f}s: {str(e)}", exc_info=True)
        # Still flush any usage logged before the error
        try:
            from ai_service import flush_usage_log
            flush_usage_log(db)
            db.commit()
        except Exception:
            pass
        response = {
            "success": False,
            "component_id": component.id,
            "component_name": component.name,
            "component_type": component.type,
            "error": str(e)
        }
        if trace_buf is not None:
            response["trace"] = list(trace_buf)
        return response
    finally:
        if trace_token is not None:
            _trace_buffer.reset(trace_token)


@router.get("/pipedrive/fields/{action_type}")
async def get_pipedrive_fields(
    action_type: str,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get available Pipedrive CRM fields for a specific action type.
    These are fetched from the user's actual Pipedrive account.
    """
    try:
        from pipedrive_service import get_available_fields

        result = await get_available_fields(db, current_user.id, action_type)

        if result.get("success"):
            return {
                "success": True,
                "action_type": action_type,
                "fields": result.get("fields", [])
            }
        else:
            return {
                "success": False,
                "action_type": action_type,
                "error": result.get("error", "Unknown error"),
                "fields": []
            }

    except Exception as e:
        logger.error(f"Error fetching Pipedrive fields for action {action_type}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch Pipedrive fields: {str(e)}"
        )


@router.post("/pipedrive/cache/clear")
async def clear_pipedrive_cache(
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Clear cached Pipedrive fields for the current user.
    Use this when you add new custom fields in Pipedrive and want to see them immediately.
    """
    try:
        # Clear all Pipedrive field caches for this user
        pattern = f"pipedrive:fields:{current_user.id}:*"
        deleted_count = cache_clear_pattern(pattern)

        logger.info(f"Cleared {deleted_count} Pipedrive field cache entries for user {current_user.id}")

        return {
            "success": True,
            "message": f"Cleared {deleted_count} cached Pipedrive field entries",
            "cache_cleared": deleted_count > 0
        }
    except Exception as e:
        logger.error(f"Error clearing Pipedrive cache: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear cache: {str(e)}"
        )


@router.get("/pipedrive/pipelines")
async def get_pipedrive_pipelines_endpoint(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get all Pipedrive pipelines for the current user.
    Returns a list of pipelines that can be used to filter stages.
    """
    try:
        from pipedrive_service import get_pipedrive_pipelines

        result = await get_pipedrive_pipelines(db, current_user.id)

        if result.get("success"):
            return {
                "success": True,
                "pipelines": result.get("pipelines", [])
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("error", "Failed to fetch pipelines from Pipedrive")
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching Pipedrive pipelines: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch Pipedrive pipelines: {str(e)}"
        )


@router.get("/pipedrive/stages")
async def get_pipedrive_stages(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get all Pipedrive pipeline stages for the current user.
    Returns stages grouped by pipeline and a flat list for backward compatibility.
    """
    try:
        from pipedrive_service import get_deal_stages

        result = await get_deal_stages(db, current_user.id)

        if result.get("success"):
            stages = result.get("stages", {})
            stages_by_pipeline = result.get("stages_by_pipeline", {})

            # Convert to list of stage names (for backward compatibility)
            stage_list = list(stages.values())

            return {
                "success": True,
                "stages": stage_list,  # Flat list (backward compatibility)
                "stage_mapping": stages,  # ID -> name mapping
                "stages_by_pipeline": stages_by_pipeline  # Grouped by pipeline (new)
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("error", "Failed to fetch stages from Pipedrive")
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching Pipedrive stages: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch Pipedrive stages: {str(e)}"
        )


@router.get("/pipedrive/users")
async def get_pipedrive_users(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get all Pipedrive users (potential deal owners) for the current user.
    """
    try:
        from pipedrive_service import get_pipedrive_users

        result = await get_pipedrive_users(db, current_user.id)

        if result.get("success"):
            return {
                "success": True,
                "users": result.get("users", [])
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("error", "Failed to fetch users from Pipedrive")
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching Pipedrive users: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch Pipedrive users: {str(e)}"
        )


@router.get("/pipedrive/currencies")
async def get_pipedrive_currencies(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get all currencies supported in Pipedrive for the current user's account.
    """
    try:
        from pipedrive_service import get_pipedrive_currencies

        result = await get_pipedrive_currencies(db, current_user.id)

        if result.get("success"):
            return {
                "success": True,
                "currencies": result.get("currencies", [])
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("error", "Failed to fetch currencies from Pipedrive")
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching Pipedrive currencies: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch Pipedrive currencies: {str(e)}"
        )


@router.get("/{component_id}/available-variables")
async def get_available_variables(
    component_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get available variables from components that come before this component in the workflow.
    These variables can be used as source fields in field mapping.
    """
    try:
        # Get the current component
        component = db.query(models.Component).filter(
            models.Component.id == component_id
        ).first()

        if not component:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Component not found"
            )

        # Verify workflow access
        from auth import verify_workflow_access
        workflow = verify_workflow_access(component.workflow_id, current_user, db)

        # Get all components in the workflow that come before this component (lower order)
        previous_components = db.query(models.Component).filter(
            models.Component.workflow_id == component.workflow_id,
            models.Component.order < component.order
        ).order_by(models.Component.order).all()

        available_variables = []

        # First, add component-level variables (entire component outputs)
        for prev_comp in previous_components:
            available_variables.append({
                "value": f"component:{prev_comp.name}",
                "label": f"All outputs from {prev_comp.name}",
                "source_component_id": prev_comp.id,
                "source_component_name": prev_comp.name,
                "source_component_type": prev_comp.type,
                "variable_type": "component",
                "is_component_level": True
            })

        # Then, extract field-level variables from each previous component based on type
        for prev_comp in previous_components:
            config = prev_comp.configuration or {}

            # Text Generation component provides extraction points AND summary
            if prev_comp.type == "text_generation":
                # Add the summary field itself (the main output of text generation)
                available_variables.append({
                    "value": "summary",
                    "label": f"Summary ({prev_comp.name})",
                    "source_component_id": prev_comp.id,
                    "source_component_name": prev_comp.name,
                    "source_component_type": prev_comp.type,
                    "variable_type": "string"
                })

                # Add extraction points as variables
                extraction_points = config.get("extraction_points", [])

                for point in extraction_points:
                    variable_name = point.get("name", "")
                    if variable_name:
                        # Create a clean variable key
                        variable_key = variable_name.lower().replace(" ", "_").replace("-", "_")
                        available_variables.append({
                            "value": variable_name,  # Use original name as value
                            "label": f"{variable_name} ({prev_comp.name})",  # Use actual component name
                            "source_component_id": prev_comp.id,
                            "source_component_name": prev_comp.name,
                            "source_component_type": prev_comp.type,
                            "variable_type": point.get("type", "string")
                        })

            # Input Sources component provides basic transcript data
            elif prev_comp.type == "input_sources":
                basic_fields = [
                    {"value": "transcript", "label": "Transcript", "type": "string"},
                    {"value": "participants", "label": "Participants", "type": "array"},
                    {"value": "meeting_title", "label": "Meeting Title", "type": "string"},
                    {"value": "meeting_date", "label": "Meeting Date", "type": "string"},
                    {"value": "duration", "label": "Duration", "type": "number"},
                ]

                for field in basic_fields:
                    available_variables.append({
                        "value": field["value"],
                        "label": f"{field['label']} ({prev_comp.name})",  # Use actual component name
                        "source_component_id": prev_comp.id,
                        "source_component_name": prev_comp.name,
                        "source_component_type": prev_comp.type,
                        "variable_type": field["type"]
                    })

            # Email component provides email_subject and email_body
            elif prev_comp.type == "email":
                # Add the email subject
                available_variables.append({
                    "value": "email_subject",
                    "label": f"Email Subject ({prev_comp.name})",
                    "source_component_id": prev_comp.id,
                    "source_component_name": prev_comp.name,
                    "source_component_type": prev_comp.type,
                    "variable_type": "string"
                })

                # Add the email body
                available_variables.append({
                    "value": "email_body",
                    "label": f"Email Body ({prev_comp.name})",
                    "source_component_id": prev_comp.id,
                    "source_component_name": prev_comp.name,
                    "source_component_type": prev_comp.type,
                    "variable_type": "string"
                })

            # Advanced Matching component provides organization matching and contact creation outputs
            elif prev_comp.type == "company_name_matcher":
                # Get the configured output variable name (default: matched_org_id)
                output_var_name = config.get("output_variable_name", "matched_org_id")

                matching_fields = [
                    {"value": output_var_name, "label": f"Matched Org ID ({prev_comp.name})", "type": "number"},
                    {"value": "organization_id", "label": f"Organization ID ({prev_comp.name})", "type": "number"},
                    {"value": "organization_name", "label": f"Organization Name ({prev_comp.name})", "type": "string"},
                    {"value": "organization_created", "label": f"Org Was Created ({prev_comp.name})", "type": "boolean"},
                    {"value": "match_confidence", "label": f"Match Confidence ({prev_comp.name})", "type": "string"},
                    {"value": "match_reasoning", "label": f"Match Reasoning ({prev_comp.name})", "type": "string"},
                    {"value": "owner_id", "label": f"Owner ID ({prev_comp.name})", "type": "number"},
                    {"value": "organizer_email", "label": f"Organizer Email ({prev_comp.name})", "type": "string"},
                    {"value": "external_participants_count", "label": f"External Participants Count ({prev_comp.name})", "type": "number"},
                    {"value": "persons_created_count", "label": f"Contacts Created Count ({prev_comp.name})", "type": "number"},
                    {"value": "persons_existing_count", "label": f"Contacts Existing Count ({prev_comp.name})", "type": "number"},
                ]

                for field in matching_fields:
                    available_variables.append({
                        "value": field["value"],
                        "label": field["label"],
                        "source_component_id": prev_comp.id,
                        "source_component_name": prev_comp.name,
                        "source_component_type": prev_comp.type,
                        "variable_type": field["type"]
                    })

        logger.info(f"Found {len(available_variables)} available variables for component {component_id}")
        return {
            "component_id": component_id,
            "available_variables": available_variables
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching available variables for component {component_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch available variables: {str(e)}"
        )
