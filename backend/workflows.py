from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import desc, func as sql_func, or_
from pydantic import AliasChoices, BaseModel, Field
from datetime import datetime
import json

from database import get_db
from auth import get_current_active_user, verify_workflow_access
import models

router = APIRouter()

# Pydantic models
class FreshCheckSettings(BaseModel):
    """Per-workflow Fresh Check rule toggles.

    The Fresh Check pipeline (see #180) has 8 rules. Rules 1-7 are user-
    togglable and persisted here. Rule 8 (DNC) is intentionally absent:
    it's locked-on in the UI and enforced deterministically by the
    dnc_status DB columns in _rag_presend_decision, so there is no
    sensible "off" state to store. See #174 for the schema and #175 for
    the tag-to-rule mapping.
    """
    # Rule 1 — [reply] / [cross_workflow]: contact replied to any email
    reply_received: bool = True
    # Rule 2 — [inbox]: manually-synced inbound email outside the workflow
    inbox_email: bool = True
    # Rule 3 — [activity]: meeting / call / note / other touchpoint logged
    activity_logged: bool = True
    # Rule 4 — [pulse]: ContactPulse sentiment shifted negative (Oak+ gated)
    pulse_shift: bool = True
    # Rule 5 — [org_signal]: sibling contact in the same org sent a signal
    org_signal: bool = True
    # Rule 6 — [crm_change]: deal stage or contact fields moved in the CRM
    crm_change: bool = True
    # Rule 7 — [note]: a note_added event carried a "flag" type
    flagged_note: bool = True


class RagSettings(BaseModel):
    """Per-workflow RAG toggles. Defaults ON; stored in workflows.rag_settings JSON."""
    smart_context_diversity: bool = True
    thin_transcript_prompt: bool = True
    fresh_check: FreshCheckSettings = FreshCheckSettings()

class WorkflowCreate(BaseModel):
    name: str
    description: Optional[str] = None
    universal_rules: Optional[str] = None
    rag_settings: Optional[RagSettings] = None

class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    universal_rules: Optional[str] = None
    is_active: Optional[bool] = None
    rag_settings: Optional[RagSettings] = None

class ComponentBase(BaseModel):
    type: str
    name: str
    description: Optional[str] = None
    configuration: Optional[dict] = {}
    position_x: int = 0
    position_y: int = 0
    order: int = 0

class Component(ComponentBase):
    id: int
    workflow_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class Workflow(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    universal_rules: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    components: List[Component] = []
    owner_name: Optional[str] = None
    rag_settings: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True

class WorkflowStats(BaseModel):
    total_workflows: int
    active_workflows: int
    total_executions: int
    successful_executions: int
    failed_executions: int
    avg_execution_time: Optional[float] = None

class ConnectionBase(BaseModel):
    from_component_original_id: int = Field(
        validation_alias=AliasChoices("from_component_original_id", "from_component_id")
    )
    to_component_original_id: int = Field(
        validation_alias=AliasChoices("to_component_original_id", "to_component_id")
    )
    condition: Optional[str] = None

class WorkflowImportData(BaseModel):
    workflow: Dict[str, Any]
    components: List[Dict[str, Any]]
    connections: List[ConnectionBase]


class WorkflowValidationError(BaseModel):
    component_id: Optional[int] = None
    component_name: Optional[str] = None
    field: Optional[str] = None
    message: str


class WorkflowValidationResponse(BaseModel):
    valid: bool
    errors: List[WorkflowValidationError] = []

@router.get(
    "/",
    response_model=List[Workflow],
    summary="List Workflows",
    description="Get all workflows owned by the current user"
)
async def get_workflows(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    List all workflows for the authenticated user.

    Returns workflows sorted by most recent activity (updated_at or created_at).
    Each workflow includes its associated components.

    Args:
        current_user: The authenticated user (injected)
        db: Database session (injected)

    Returns:
        List[Workflow]: All workflows owned by the user, sorted by most recent first
    """
    # Owners/Admins see all org workflows; Members see only their own
    if current_user.role in (models.UserRole.owner, models.UserRole.admin):
        workflows = db.query(models.Workflow).join(
            models.User, models.Workflow.owner_id == models.User.id
        ).filter(
            models.User.org_id == current_user.org_id
        ).order_by(
            desc(sql_func.coalesce(models.Workflow.updated_at, models.Workflow.created_at))
        ).all()
    else:
        workflows = db.query(models.Workflow).filter(
            models.Workflow.owner_id == current_user.id
        ).order_by(
            desc(sql_func.coalesce(models.Workflow.updated_at, models.Workflow.created_at))
        ).all()
    # Attach owner name for display (helps admins identify workflow creators)
    for wf in workflows:
        if wf.owner:
            wf.owner_name = wf.owner.full_name or wf.owner.email
    return workflows

@router.post(
    "/",
    response_model=Workflow,
    status_code=status.HTTP_201_CREATED,
    summary="Create Workflow",
    description="Create a new workflow with automatic input source component"
)
async def create_workflow(
    workflow_data: WorkflowCreate,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Create a new workflow.

    Automatically creates a mandatory Input Source component at order 0, which serves as
    the entry point for the workflow to receive data from external integrations.

    Args:
        workflow_data: Workflow creation data (name, description, universal_rules)
        current_user: The authenticated user (injected)
        db: Database session (injected)

    Returns:
        Workflow: The newly created workflow with its input source component
    """
    # Create the workflow
    db_workflow = models.Workflow(
        name=workflow_data.name,
        description=workflow_data.description,
        universal_rules=workflow_data.universal_rules,
        rag_settings=workflow_data.rag_settings.dict() if workflow_data.rag_settings else None,
        owner_id=current_user.id
    )
    db.add(db_workflow)
    db.commit()
    db.refresh(db_workflow)
    
    # Automatically create the mandatory input source component
    input_source_component = models.Component(
        workflow_id=db_workflow.id,
        type="input_sources",
        name="Input Source",
        description="Entry point for the workflow - receives data from external sources",
        configuration={"integrations": {}},
        position_x=100,
        position_y=100,
        order=0  # Always at the top
    )
    db.add(input_source_component)
    db.commit()
    db.refresh(input_source_component)
    
    # Refresh workflow to include the new component
    db.refresh(db_workflow)
    return db_workflow

@router.get(
    "/{workflow_id}",
    response_model=Workflow,
    summary="Get Workflow",
    description="Retrieve a specific workflow by ID"
)
async def get_workflow(
    workflow_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get a specific workflow by ID.

    Returns the complete workflow including all associated components.
    Only accessible to the workflow owner.

    Args:
        workflow_id: The workflow ID
        current_user: The authenticated user (injected)
        db: Database session (injected)

    Returns:
        Workflow: The requested workflow with all components

    Raises:
        HTTPException 404: If workflow not found or user doesn't own it
    """
    workflow = verify_workflow_access(workflow_id, current_user, db)
    if workflow.owner:
        workflow.owner_name = workflow.owner.full_name or workflow.owner.email
    return workflow


@router.post(
    "/{workflow_id}/validate",
    response_model=WorkflowValidationResponse,
    summary="Validate Workflow",
    description="Validate workflow component configuration before saving or publishing"
)
async def validate_workflow(
    workflow_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    workflow = verify_workflow_access(workflow_id, current_user, db)

    from components import _validate_email_threading_config
    from fastapi import HTTPException

    errors: List[WorkflowValidationError] = []
    ordered_components = db.query(models.Component).filter(
        models.Component.workflow_id == workflow.id
    ).order_by(models.Component.order.asc(), models.Component.id.asc()).all()

    for component in ordered_components:
        try:
            _validate_email_threading_config(
                db=db,
                workflow_id=workflow.id,
                component_type=component.type,
                component_id=component.id,
                component_order=component.order,
                configuration=component.configuration or {},
            )
        except HTTPException as exc:
            errors.append(
                WorkflowValidationError(
                    component_id=component.id,
                    component_name=component.name,
                    field="thread_parent_component_id",
                    message=str(exc.detail),
                )
            )

    return WorkflowValidationResponse(valid=not errors, errors=errors)

@router.put(
    "/{workflow_id}",
    response_model=Workflow,
    summary="Update Workflow",
    description="Update workflow properties like name, description, rules, or active status"
)
async def update_workflow(
    workflow_id: int,
    workflow_data: WorkflowUpdate,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Update an existing workflow.

    Allows updating name, description, universal_rules, and is_active status.
    Only fields provided in the request will be updated (partial update supported).

    Args:
        workflow_id: The workflow ID to update
        workflow_data: Fields to update (all optional)
        current_user: The authenticated user (injected)
        db: Database session (injected)

    Returns:
        Workflow: The updated workflow

    Raises:
        HTTPException 404: If workflow not found or user doesn't own it
    """
    workflow = verify_workflow_access(workflow_id, current_user, db)

    update_data = workflow_data.dict(exclude_unset=True)
    # rag_settings comes in as a nested Pydantic model; serialize to a plain
    # dict for the JSON column, and merge with existing settings so a partial
    # toggle update doesn't drop unspecified keys.
    #
    # Assign a *fresh* dict rather than mutating workflow.rag_settings in place.
    # The column is declared as Column(JSON) without MutableDict.as_mutable, so
    # SQLAlchemy's default dirty check is identity-based: an in-place update on
    # the existing dict leaves the attribute identity unchanged and the UPDATE
    # is never emitted — the endpoint returns 200 but the row is unchanged on
    # next read.
    if "rag_settings" in update_data and update_data["rag_settings"] is not None:
        incoming = update_data["rag_settings"]
        update_data["rag_settings"] = {**(workflow.rag_settings or {}), **incoming}

    for field, value in update_data.items():
        setattr(workflow, field, value)

    db.commit()
    db.refresh(workflow)
    return workflow

@router.delete(
    "/{workflow_id}",
    summary="Delete Workflow",
    description="Permanently delete a workflow and all associated components"
)
async def delete_workflow(
    workflow_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Delete a workflow permanently.

    Deletes the workflow and all associated components, connections, and executions.
    This action cannot be undone.

    Args:
        workflow_id: The workflow ID to delete
        current_user: The authenticated user (injected)
        db: Database session (injected)

    Returns:
        dict: Success message

    Raises:
        HTTPException 404: If workflow not found or user doesn't own it
    """
    workflow = db.query(models.Workflow).filter(
        models.Workflow.id == workflow_id,
    ).first()

    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    # Owners/Admins can delete any org workflow; Members only their own
    if current_user.role in (models.UserRole.owner, models.UserRole.admin):
        owner = db.query(models.User).filter(models.User.id == workflow.owner_id).first()
        if not owner or owner.org_id != current_user.org_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    elif workflow.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    # Manually delete records that reference components/executions but lack
    # ORM cascade relationships, to avoid FK constraint violations.
    component_ids = [c.id for c in workflow.components]
    execution_ids = [e.id for e in workflow.executions]

    if component_ids:
        # Nullify FKs in ai_usage_log so usage data is preserved
        db.query(models.AiUsageLog).filter(
            models.AiUsageLog.component_id.in_(component_ids)
        ).update({models.AiUsageLog.component_id: None}, synchronize_session=False)
        db.query(models.Connection).filter(
            (models.Connection.from_component_id.in_(component_ids)) |
            (models.Connection.to_component_id.in_(component_ids))
        ).delete(synchronize_session=False)

    if execution_ids:
        db.query(models.AiUsageLog).filter(
            models.AiUsageLog.execution_id.in_(execution_ids)
        ).update({models.AiUsageLog.execution_id: None}, synchronize_session=False)

    db.delete(workflow)
    db.commit()
    return {"message": "Workflow deleted successfully"}

@router.get(
    "/stats/dashboard",
    response_model=WorkflowStats,
    summary="Get Dashboard Statistics",
    description="Get aggregate statistics across all user workflows"
)
async def get_dashboard_stats(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get dashboard statistics for all user workflows.

    Provides aggregate metrics including total workflows, active workflows,
    execution counts (total, successful, failed), and average execution time.

    Args:
        current_user: The authenticated user (injected)
        db: Database session (injected)

    Returns:
        WorkflowStats: Aggregated statistics across all workflows owned by the user
    """
    # Owners/Admins see org-wide stats; Members see only their own
    if current_user.role in (models.UserRole.owner, models.UserRole.admin):
        wf_filter = db.query(models.Workflow).join(
            models.User, models.Workflow.owner_id == models.User.id
        ).filter(models.User.org_id == current_user.org_id)
        wf_id_query = db.query(models.Workflow.id).join(
            models.User, models.Workflow.owner_id == models.User.id
        ).filter(models.User.org_id == current_user.org_id)
    else:
        wf_filter = db.query(models.Workflow).filter(models.Workflow.owner_id == current_user.id)
        wf_id_query = db.query(models.Workflow.id).filter(models.Workflow.owner_id == current_user.id)

    total_workflows = wf_filter.count()
    active_workflows = wf_filter.filter(models.Workflow.is_active == True).count()

    # Get execution stats
    user_workflow_ids = wf_id_query.subquery()
    
    total_executions = db.query(models.Execution).filter(
        models.Execution.workflow_id.in_(user_workflow_ids)
    ).count()
    
    successful_executions = db.query(models.Execution).filter(
        models.Execution.workflow_id.in_(user_workflow_ids),
        models.Execution.status == "completed"
    ).count()
    
    failed_executions = db.query(models.Execution).filter(
        models.Execution.workflow_id.in_(user_workflow_ids),
        models.Execution.status == "failed"
    ).count()
    
    # Calculate average execution time
    avg_time_result = db.query(
        models.Execution.total_execution_time
    ).filter(
        models.Execution.workflow_id.in_(user_workflow_ids),
        models.Execution.total_execution_time.isnot(None)
    ).all()
    
    avg_execution_time = None
    if avg_time_result:
        times = [r[0] for r in avg_time_result if r[0] is not None]
        if times:
            avg_execution_time = sum(times) / len(times)
    
    return WorkflowStats(
        total_workflows=total_workflows,
        active_workflows=active_workflows,
        total_executions=total_executions,
        successful_executions=successful_executions,
        failed_executions=failed_executions,
        avg_execution_time=avg_execution_time
    )

@router.get("/{workflow_id}/export")
async def export_workflow(
    workflow_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Export workflow configuration including components and connections"""
    workflow = verify_workflow_access(workflow_id, current_user, db)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found"
        )

    # Get components
    components = db.query(models.Component).filter(
        models.Component.workflow_id == workflow_id
    ).all()

    # Get connections
    component_ids = [comp.id for comp in components]
    if component_ids:
        connections = db.query(models.Connection).filter(
            or_(
                models.Connection.from_component_id.in_(component_ids),
                models.Connection.to_component_id.in_(component_ids),
            )
        ).all()
    else:
        connections = []

    # Build export data
    export_data = {
        "workflow": {
            "name": workflow.name,
            "description": workflow.description,
            "universal_rules": workflow.universal_rules,
            "is_active": workflow.is_active
        },
        "components": [
            {
                "type": comp.type,
                "name": comp.name,
                "description": comp.description,
                "configuration": comp.configuration,
                "position_x": comp.position_x,
                "position_y": comp.position_y,
                "order": comp.order,
                "original_id": comp.id  # Keep original ID for connection mapping
            }
            for comp in components
        ],
        "connections": [
            {
                "from_component_original_id": conn.from_component_id,
                "to_component_original_id": conn.to_component_id,
                "condition": conn.condition
            }
            for conn in connections
        ]
    }

    return export_data

@router.post("/{workflow_id}/import")
async def import_workflow(
    workflow_id: int,
    import_data: WorkflowImportData,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Import workflow configuration, replacing existing components and connections"""
    workflow = verify_workflow_access(workflow_id, current_user, db)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found"
        )

    try:
        # Update workflow metadata
        if "name" in import_data.workflow:
            workflow.name = import_data.workflow["name"]
        if "description" in import_data.workflow:
            workflow.description = import_data.workflow["description"]
        if "universal_rules" in import_data.workflow:
            workflow.universal_rules = import_data.workflow["universal_rules"]

        # Delete existing components and connections
        existing_component_ids = [
            component_id
            for (component_id,) in db.query(models.Component.id).filter(
                models.Component.workflow_id == workflow_id
            ).all()
        ]
        if existing_component_ids:
            db.query(models.Connection).filter(
                or_(
                    models.Connection.from_component_id.in_(existing_component_ids),
                    models.Connection.to_component_id.in_(existing_component_ids),
                )
            ).delete(synchronize_session=False)
        db.query(models.Component).filter(
            models.Component.workflow_id == workflow_id
        ).delete()

        # Create new components and build ID mapping
        id_mapping = {}  # Map from original_id to new_id

        for comp_data in import_data.components:
            original_id = comp_data.get("original_id")
            new_component = models.Component(
                workflow_id=workflow_id,
                type=comp_data["type"],
                name=comp_data["name"],
                description=comp_data.get("description"),
                configuration=comp_data.get("configuration", {}),
                position_x=comp_data.get("position_x", 0),
                position_y=comp_data.get("position_y", 0),
                order=comp_data.get("order", 0)
            )
            db.add(new_component)
            db.flush()  # Get the new ID

            if original_id:
                id_mapping[original_id] = new_component.id

        # Remap same-thread references to the duplicated component ids.
        # Export data stores thread_parent_component_id from the source workflow;
        # when importing into a different workflow these ids must be translated.
        for comp_data in import_data.components:
            original_id = comp_data.get("original_id")
            if not original_id:
                continue
            new_component_id = id_mapping.get(original_id)
            if not new_component_id:
                continue

            new_component = db.query(models.Component).filter(
                models.Component.id == new_component_id
            ).first()
            if not new_component:
                continue

            cfg = dict(new_component.configuration or {})
            if (
                new_component.type == "email"
                and cfg.get("send_as") == "reply_to_component"
                and cfg.get("thread_parent_component_id")
            ):
                old_parent_id = cfg.get("thread_parent_component_id")
                remapped_parent_id = id_mapping.get(old_parent_id)
                if remapped_parent_id:
                    cfg["thread_parent_component_id"] = remapped_parent_id
                    new_component.configuration = cfg

        # Create connections using the ID mapping
        for conn_data in import_data.connections:
            conn = conn_data.model_dump() if hasattr(conn_data, "model_dump") else dict(conn_data)
            from_original_id = conn.get("from_component_original_id")
            to_original_id = conn.get("to_component_original_id")

            if from_original_id in id_mapping and to_original_id in id_mapping:
                new_connection = models.Connection(
                    from_component_id=id_mapping[from_original_id],
                    to_component_id=id_mapping[to_original_id],
                    condition=conn.get("condition")
                )
                db.add(new_connection)

        db.commit()
        db.refresh(workflow)

        return {"message": "Workflow imported successfully", "workflow_id": workflow_id}

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to import workflow: {str(e)}"
        )
