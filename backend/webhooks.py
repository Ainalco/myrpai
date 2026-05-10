from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime, timezone
import hashlib
import secrets
import json
import asyncio

from database import get_db
from auth import get_current_active_user, verify_workflow_access
import models
from fireflies_service import fetch_transcript, get_meeting_url
from config import get_webhook_url

router = APIRouter()

class WebhookCreate(BaseModel):
    workflow_id: int
    component_id: int
    name: str
    description: Optional[str] = None
    
class WebhookResponse(BaseModel):
    id: int
    workflow_id: int
    component_id: int
    webhook_url: str
    webhook_token: str
    name: str
    description: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

class FirefliesWebhookPayload(BaseModel):
    meetingId: str  # Fireflies uses camelCase
    eventType: str  # "Transcription completed", "Meeting started", etc.
    
    # Optional fields that might be included in future versions or different events
    meeting_id: Optional[str] = None
    transcript_id: Optional[str] = None
    meeting_title: Optional[str] = None
    meeting_url: Optional[str] = None
    meeting_date: Optional[str] = None
    duration: Optional[int] = None
    participants: Optional[list] = None
    transcript: Optional[str] = None
    summary: Optional[str] = None
    action_items: Optional[list] = None
    keywords: Optional[list] = None
    sentiment: Optional[Dict[str, Any]] = None

@router.post(
    "/webhooks/create",
    response_model=WebhookResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Webhook",
    description="Create or update a webhook for an input source component"
)
async def create_webhook(
    webhook_data: WebhookCreate,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Create or update a webhook for an input source component.

    Generates a unique webhook URL with security token for external services (like Fireflies.ai)
    to send data to the workflow. If a webhook already exists for the component, it updates
    the existing webhook and regenerates the security token.

    Args:
        webhook_data: Webhook configuration (workflow_id, component_id, name, description)
        current_user: The authenticated user (injected)
        db: Database session (injected)

    Returns:
        WebhookResponse: Created/updated webhook with URL and token

    Raises:
        HTTPException 404: If workflow/component not found or user doesn't own them
    """
    # Verify workflow access
    workflow = verify_workflow_access(webhook_data.workflow_id, current_user, db)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found"
        )
    
    # Verify component belongs to workflow
    component = db.query(models.Component).filter(
        models.Component.id == webhook_data.component_id,
        models.Component.workflow_id == webhook_data.workflow_id,
        models.Component.type == "input_sources"
    ).first()
    
    if not component:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Input source component not found"
        )
    
    # Determine integration type from webhook name
    integration_type = "fireflies"  # Default to fireflies for now
    if "fireflies" in webhook_data.name.lower():
        integration_type = "fireflies"
    
    # Generate unique webhook token
    webhook_token = secrets.token_urlsafe(32)
    
    # Check if webhook already exists for this component
    existing_webhook = db.query(models.Webhook).filter(
        models.Webhook.component_id == webhook_data.component_id
    ).first()
    
    if existing_webhook:
        # Update existing webhook
        existing_webhook.name = webhook_data.name
        existing_webhook.description = webhook_data.description
        existing_webhook.webhook_token = webhook_token
        existing_webhook.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing_webhook)
        
        # Generate webhook URL using configuration
        webhook_url = get_webhook_url(existing_webhook.id, webhook_token, "fireflies")
        existing_webhook.webhook_url = webhook_url
        
        return existing_webhook
    else:
        # Create new webhook
        db_webhook = models.Webhook(
            workflow_id=webhook_data.workflow_id,
            component_id=webhook_data.component_id,
            name=webhook_data.name,
            description=webhook_data.description,
            webhook_token=webhook_token
        )
        db.add(db_webhook)
        db.commit()
        db.refresh(db_webhook)
        
        # Generate webhook URL using configuration
        webhook_url = get_webhook_url(db_webhook.id, webhook_token, "fireflies")
        db_webhook.webhook_url = webhook_url
        db.commit()
        
        return db_webhook

@router.get(
    "/webhooks/{workflow_id}",
    response_model=list[WebhookResponse],
    summary="List Workflow Webhooks",
    description="Get all webhooks configured for a workflow"
)
async def get_workflow_webhooks(
    workflow_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    List all webhooks for a workflow.

    Returns all webhooks with their URLs and tokens. Use these URLs to configure
    external services to send data to your workflow.

    Args:
        workflow_id: The workflow ID
        current_user: The authenticated user (injected)
        db: Database session (injected)

    Returns:
        list[WebhookResponse]: All webhooks for the workflow

    Raises:
        HTTPException 404: If workflow not found or user doesn't own it
    """
    # Verify workflow access
    workflow = verify_workflow_access(workflow_id, current_user, db)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found"
        )
    
    webhooks = db.query(models.Webhook).filter(
        models.Webhook.workflow_id == workflow_id
    ).all()
    
    # Add webhook URLs to response
    for webhook in webhooks:
        webhook.webhook_url = get_webhook_url(webhook.id, webhook.webhook_token, "fireflies")
    
    return webhooks

@router.post(
    "/webhooks/fireflies/{webhook_id}/{token}",
    summary="Receive Fireflies Webhook",
    description="Receive webhook notifications from Fireflies.ai when meeting transcripts are ready",
    response_description="Status of webhook processing and workflow execution",
    status_code=status.HTTP_200_OK
)
async def receive_fireflies_webhook(
    webhook_id: int,
    token: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Receive and process webhook notifications from Fireflies.ai.

    This is a public endpoint that Fireflies.ai calls when events occur (e.g., transcription completed).
    The endpoint validates the webhook token, fetches the full transcript data from the Fireflies API,
    creates a workflow execution, and triggers the associated workflow in the background.

    **Authentication**: This endpoint uses webhook token authentication instead of user authentication,
    as it is called by the external Fireflies.ai service.

    **Process Flow**:
    1. Validates the webhook ID and token
    2. Parses the incoming webhook payload
    3. For "transcription completed" events, fetches the full transcript from Fireflies API
    4. Creates a new workflow execution with the transcript data
    5. Triggers the workflow to process the transcript in the background

    Args:
        webhook_id (int): The unique identifier of the webhook
        token (str): The security token for webhook authentication
        request (Request): The incoming webhook request containing the Fireflies payload
        background_tasks (BackgroundTasks): FastAPI background task manager
        db (Session): Database session

    Returns:
        dict: Response containing:
            - status: "success" or "error"
            - message: Descriptive message about the processing
            - execution_id: ID of the created workflow execution (on success)
            - meeting_id: Fireflies meeting ID
            - event_type: Type of event received from Fireflies

    Raises:
        HTTPException:
            - 401: Invalid webhook token
            - 400: Invalid request payload
            - 500: Internal server error during processing

    **Example Fireflies Payload**:
    ```json
    {
        "meetingId": "abc123",
        "eventType": "Transcription completed",
        "meeting_title": "Sales Call with Client",
        "meeting_date": "2024-01-15T10:30:00Z"
    }
    ```

    **Example Response**:
    ```json
    {
        "status": "success",
        "message": "Webhook received and workflow triggered",
        "execution_id": 42,
        "meeting_id": "abc123",
        "event_type": "Transcription completed"
    }
    ```
    """
    try:
        print(f"Received webhook request for ID: {webhook_id}")
        
        # Verify webhook token
        webhook = db.query(models.Webhook).filter(
            models.Webhook.id == webhook_id,
            models.Webhook.webhook_token == token
        ).first()
        
        if not webhook:
            print(f"Invalid webhook token for ID: {webhook_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook token"
            )

        # Check if workflow is active
        workflow = db.query(models.Workflow).filter(
            models.Workflow.id == webhook.workflow_id
        ).first()

        if not workflow or not workflow.is_active:
            print(f"Workflow {webhook.workflow_id} is inactive, ignoring webhook")
            return {
                "status": "ignored",
                "message": "Workflow is inactive. Activate the workflow to process webhooks.",
                "workflow_id": webhook.workflow_id,
                "meeting_id": "unknown",
                "event_type": "ignored"
            }

        # Parse request body
        try:
            payload = await request.json()
            print(f"Received payload: {payload}")  # Debug logging
        except Exception as e:
            print(f"Failed to parse JSON payload: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid request payload: {str(e)}"
            )
        
        # Log the webhook event for debugging
        meeting_id = payload.get("meetingId") or payload.get("meeting_id", "unknown")
        event_type = payload.get("eventType") or payload.get("event", "unknown")
        
        print(f"Received Fireflies webhook event: {event_type}")
        print(f"Meeting ID: {meeting_id}")
        
        # Fetch the actual transcript data from Fireflies API
        transcript_data = None
        meeting_url = None
        
        try:
            # Only fetch transcript for completed transcription events
            if event_type.lower() in ["transcription completed", "transcript_ready", "completed"]:
                print(f"Fetching transcript for meeting {meeting_id}...")
                transcript_data = await fetch_transcript(meeting_id)
                meeting_url = await get_meeting_url(meeting_id)
                print(f"Successfully fetched transcript data: {bool(transcript_data)}")
            else:
                print(f"Skipping transcript fetch for event type: {event_type}")
        except Exception as e:
            print(f"Failed to fetch transcript for meeting {meeting_id}: {str(e)}")
            # Continue with webhook processing even if transcript fetch fails
        
        # Sync meeting to contact system (creates MeetingHistory + activities)
        if transcript_data and workflow:
            try:
                from fireflies_sync import sync_meeting_to_contacts
                sync_result = await sync_meeting_to_contacts(
                    db=db,
                    user_id=workflow.user_id,
                    transcript_data=transcript_data,
                    meeting_url=meeting_url,
                )
                if sync_result.get("meetingsCreated"):
                    print(f"Synced meeting to {sync_result['contactsLinked']} contacts ({sync_result['meetingsCreated']} new)")
            except Exception as e:
                # Meeting sync failure should never block workflow execution
                print(f"Meeting sync failed (non-blocking): {str(e)}")

        # Prepare the data for workflow execution
        if transcript_data:
            # Use the real transcript data
            workflow_input = {
                "source": "fireflies_webhook",
                "meeting_id": meeting_id,
                "event_type": event_type,
                "transcript_id": payload.get("transcript_id", meeting_id),
                "meeting_title": transcript_data.get("meeting_title", f"Meeting {meeting_id}"),
                "meeting_url": meeting_url or transcript_data.get("meeting_url", ""),
                "meeting_date": transcript_data.get("meeting_date", ""),
                "duration": transcript_data.get("duration", 0),
                "participants": transcript_data.get("participants", []),
                "transcript": transcript_data.get("transcript", ""),
                "raw_payload": payload,  # Store the complete raw payload
                "fireflies_data": transcript_data,  # Store the complete Fireflies API response
                "webhook_received_at": datetime.now(timezone.utc).isoformat()
            }
        else:
            # Fallback to webhook notification data only
            workflow_input = {
                "source": "fireflies_webhook",
                "meeting_id": meeting_id,
                "event_type": event_type,
                "transcript_id": payload.get("transcript_id"),
                "meeting_title": f"Meeting {meeting_id}",
                "meeting_url": payload.get("meeting_url", ""),
                "meeting_date": payload.get("meeting_date", ""),
                "duration": payload.get("duration", 0),
                "participants": payload.get("participants", []),
                "transcript": f"Transcript pending for meeting {meeting_id}",
                "raw_payload": payload,
                "transcript_fetch_failed": True,
                "webhook_received_at": datetime.now(timezone.utc).isoformat()
            }
        
        # Create execution for this webhook trigger
        execution = models.Execution(
            workflow_id=webhook.workflow_id,
            status="pending",
            input_data=workflow_input
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)
        
        # Process the webhook data through the workflow
        try:
            # Import here to avoid circular imports
            from executions import execute_workflow_background

            # Start background processing of the workflow
            # IMPORTANT: Do NOT pass the database session to background tasks!
            # The background task creates its own session to avoid race conditions
            background_tasks.add_task(execute_workflow_background, execution.id)
            
            return {
                "status": "success",
                "message": "Webhook received and workflow triggered",
                "execution_id": execution.id,
                "meeting_id": meeting_id,
                "event_type": event_type
            }
        except Exception as e:
            execution.status = "failed"
            execution.error_message = str(e)
            db.commit()
            
            return {
                "status": "error",
                "message": "Webhook received but workflow execution failed",
                "error": str(e)
            }
    
    except Exception as e:
        print(f"Unexpected error in webhook handler: {str(e)}")
        print(f"Error type: {type(e)}")
        import traceback
        traceback.print_exc()
        
        # Try to update execution status if it exists
        try:
            execution = db.query(models.Execution).filter(
                models.Execution.workflow_id == webhook.workflow_id
            ).order_by(models.Execution.id.desc()).first()
            if execution:
                execution.status = "failed"
                execution.error_message = str(e)
                db.commit()
        except:
            pass
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )

@router.delete(
    "/webhooks/{webhook_id}",
    summary="Delete Webhook",
    description="Remove a webhook and invalidate its URL"
)
async def delete_webhook(
    webhook_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Delete a webhook.

    Permanently removes the webhook and invalidates its URL. External services
    using this webhook URL will no longer be able to trigger the workflow.

    Args:
        webhook_id: The webhook ID to delete
        current_user: The authenticated user (injected)
        db: Database session (injected)

    Returns:
        dict: Success message

    Raises:
        HTTPException 404: If webhook not found
        HTTPException 403: If user doesn't own the associated workflow
    """
    webhook = db.query(models.Webhook).filter(
        models.Webhook.id == webhook_id
    ).first()
    
    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found"
        )
    
    # Verify workflow access
    workflow = verify_workflow_access(webhook.workflow_id, current_user, db)
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this webhook"
        )
    
    db.delete(webhook)
    db.commit()
    
    return {"message": "Webhook deleted successfully"}