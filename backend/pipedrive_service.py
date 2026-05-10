import httpx
import logging
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from datetime import datetime
from cache_service import cache_get, cache_set, cache_clear_pattern
from tracing import traced_call

logger = logging.getLogger(__name__)


def _redact_pipedrive_url(url: str) -> str:
    """Strip api_token from query string for trace display."""
    return url.split("api_token=")[0] + "api_token=***" if "api_token=" in url else url

PIPEDRIVE_API_BASE = "https://api.pipedrive.com/v1"


async def get_pipedrive_api_key(db: Session, user_id: int) -> Optional[str]:
    """Get Pipedrive API key for user from encrypted storage"""
    try:
        from api_keys import get_decrypted_api_key
        api_key = get_decrypted_api_key(db, user_id, "pipedrive")
        if api_key:
            logger.info(f"Using personal Pipedrive API key for user {user_id}")
            return api_key
        logger.warning(f"No Pipedrive API key found for user {user_id}")
        return None
    except Exception as e:
        logger.error(f"Failed to retrieve Pipedrive API key: {e}")
        return None


async def create_activity(
    db: Session,
    user_id: int,
    subject: str,
    activity_type: str = "task",
    due_date: Optional[str] = None,
    due_time: Optional[str] = None,
    duration: Optional[str] = None,
    deal_id: Optional[int] = None,
    person_id: Optional[int] = None,
    org_id: Optional[int] = None,
    note: Optional[str] = None,
    location: Optional[str] = None,
    public_description: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Create an activity in Pipedrive

    Args:
        db: Database session
        user_id: User ID for API key lookup
        subject: Activity title (required)
        activity_type: Type of activity (e.g., 'call', 'meeting', 'task', 'lunch', 'email')
        due_date: Due date in YYYY-MM-DD format
        due_time: Due time in HH:MM format
        duration: Duration in HH:MM format
        deal_id: ID of deal this activity is associated with
        person_id: ID of person this activity is associated with
        org_id: ID of organization this activity is associated with
        note: Note about the activity
        location: Location of the activity
        public_description: Additional details visible in the activity
        **kwargs: Additional fields to pass to Pipedrive API

    Returns:
        Dict containing success status and created activity data or error message
    """
    api_key = await get_pipedrive_api_key(db, user_id)
    if not api_key:
        return {
            "success": False,
            "error": "Pipedrive API key not configured. Please add your API key in settings."
        }

    # Build request payload with required and optional fields
    payload = {
        "subject": subject,
        "type": activity_type
    }

    # Add optional fields if provided
    if due_date:
        payload["due_date"] = due_date
    if due_time:
        payload["due_time"] = due_time
    if duration:
        payload["duration"] = duration
    if deal_id:
        payload["deal_id"] = deal_id
    if person_id:
        payload["person_id"] = person_id
    if org_id:
        payload["org_id"] = org_id
    if note:
        payload["note"] = note
    if location:
        payload["location"] = location
    if public_description:
        payload["public_description"] = public_description

    # Add any additional custom fields
    for key, value in kwargs.items():
        if value is not None and key not in payload:
            payload[key] = value

    url = f"{PIPEDRIVE_API_BASE}/activities?api_token={api_key}"

    try:
        async with httpx.AsyncClient() as client:
            async with traced_call(
                "pipedrive.create_activity",
                request={"url": _redact_pipedrive_url(url), "payload": payload},
            ) as t:
                response = await client.post(url, json=payload, timeout=30.0)
                response.raise_for_status()
                data = response.json()
                if t:
                    t["response"] = {
                        "status_code": response.status_code,
                        "success": data.get("success"),
                        "activity_id": (data.get("data") or {}).get("id"),
                        "error": data.get("error"),
                    }

            if data.get("success"):
                activity_data = data.get("data", {})
                logger.info(f"Created Pipedrive activity: {activity_data.get('id')}")
                return {
                    "success": True,
                    "activity_id": activity_data.get("id"),
                    "activity_data": activity_data,
                    "message": f"Activity '{subject}' created successfully"
                }
            else:
                error_msg = data.get("error", "Unknown error from Pipedrive API")
                logger.error(f"Pipedrive API error: {error_msg}")
                return {
                    "success": False,
                    "error": f"Pipedrive API error: {error_msg}"
                }

    except httpx.HTTPError as e:
        logger.error(f"HTTP error creating Pipedrive activity: {str(e)}")
        return {
            "success": False,
            "error": f"Failed to create activity: {str(e)}"
        }
    except Exception as e:
        logger.error(f"Error creating Pipedrive activity: {str(e)}")
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }


async def update_deal(
    db: Session,
    user_id: int,
    deal_id: int,
    title: Optional[str] = None,
    value: Optional[float] = None,
    currency: Optional[str] = None,
    status: Optional[str] = None,
    stage_id: Optional[int] = None,
    probability: Optional[int] = None,
    expected_close_date: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Update a deal in Pipedrive

    Args:
        db: Database session
        user_id: User ID for API key lookup
        deal_id: ID of the deal to update (required)
        title: Deal title
        value: Deal value
        currency: Deal currency (e.g., 'USD', 'EUR')
        status: Deal status ('open', 'won', 'lost', 'deleted')
        stage_id: ID of the pipeline stage
        probability: Deal probability (0-100)
        expected_close_date: Expected close date in YYYY-MM-DD format
        **kwargs: Additional fields to update (including custom fields)

    Returns:
        Dict containing success status and updated deal data or error message
    """
    api_key = await get_pipedrive_api_key(db, user_id)
    if not api_key:
        return {
            "success": False,
            "error": "Pipedrive API key not configured. Please add your API key in settings."
        }

    # Build request payload with only provided fields
    payload = {}

    if title is not None:
        payload["title"] = title
    if value is not None:
        payload["value"] = value
    if currency is not None:
        payload["currency"] = currency
    if status is not None:
        payload["status"] = status
    if stage_id is not None:
        payload["stage_id"] = stage_id
    if probability is not None:
        payload["probability"] = probability
    if expected_close_date is not None:
        payload["expected_close_date"] = expected_close_date

    # Add any additional custom fields
    for key, value in kwargs.items():
        if value is not None and key not in payload:
            payload[key] = value

    if not payload:
        return {
            "success": False,
            "error": "No fields provided to update"
        }

    url = f"{PIPEDRIVE_API_BASE}/deals/{deal_id}?api_token={api_key}"

    # Log the payload being sent for debugging
    logger.info(f"Updating Pipedrive deal {deal_id} with payload: {payload}")

    try:
        async with httpx.AsyncClient() as client:
            async with traced_call(
                "pipedrive.update_deal",
                request={"url": _redact_pipedrive_url(url), "deal_id": deal_id, "payload": payload},
            ) as t:
                response = await client.put(url, json=payload, timeout=30.0)

                try:
                    response_data = response.json()
                except:
                    response_data = {"text": response.text}

                if response.status_code != 200:
                    logger.error(f"Pipedrive API returned {response.status_code}: {response_data}")

                if t:
                    t["response"] = {
                        "status_code": response.status_code,
                        "success": response_data.get("success") if isinstance(response_data, dict) else None,
                        "error": response_data.get("error") if isinstance(response_data, dict) else None,
                    }

                response.raise_for_status()

            if response_data.get("success"):
                deal_data = response_data.get("data", {})
                logger.info(f"Updated Pipedrive deal: {deal_id}")
                return {
                    "success": True,
                    "deal_id": deal_id,
                    "deal_data": deal_data,
                    "message": f"Deal {deal_id} updated successfully"
                }
            else:
                error_msg = response_data.get("error", "Unknown error from Pipedrive API")
                logger.error(f"Pipedrive API error: {error_msg}")
                return {
                    "success": False,
                    "error": f"Pipedrive API error: {error_msg}"
                }

    except httpx.HTTPStatusError as e:
        # Get the response body for better error messages
        try:
            error_detail = e.response.json()
            error_message = error_detail.get("error", error_detail.get("error_info", str(error_detail)))
        except:
            error_message = e.response.text or str(e)

        logger.error(f"HTTP {e.response.status_code} error updating Pipedrive deal {deal_id}. Payload: {payload}. Error: {error_message}")
        return {
            "success": False,
            "error": f"Pipedrive API error ({e.response.status_code}): {error_message}"
        }
    except httpx.HTTPError as e:
        logger.error(f"HTTP error updating Pipedrive deal: {str(e)}")
        return {
            "success": False,
            "error": f"Failed to update deal: {str(e)}"
        }
    except Exception as e:
        logger.error(f"Error updating Pipedrive deal: {str(e)}")
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }


async def add_note(
    db: Session,
    user_id: int,
    content: str,
    deal_id: Optional[int] = None,
    person_id: Optional[int] = None,
    org_id: Optional[int] = None,
    lead_id: Optional[int] = None,
    pinned_to_deal_flag: Optional[bool] = None,
    pinned_to_person_flag: Optional[bool] = None,
    pinned_to_organization_flag: Optional[bool] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Add a note in Pipedrive

    Args:
        db: Database session
        user_id: User ID for API key lookup
        content: Note content in HTML format (required)
        deal_id: ID of deal to attach note to
        person_id: ID of person to attach note to
        org_id: ID of organization to attach note to
        lead_id: ID of lead to attach note to
        pinned_to_deal_flag: Whether to pin note to deal
        pinned_to_person_flag: Whether to pin note to person
        pinned_to_organization_flag: Whether to pin note to organization
        **kwargs: Additional fields

    Note: At least one of deal_id, person_id, org_id, or lead_id must be specified

    Returns:
        Dict containing success status and created note data or error message
    """
    api_key = await get_pipedrive_api_key(db, user_id)
    if not api_key:
        return {
            "success": False,
            "error": "Pipedrive API key not configured. Please add your API key in settings."
        }

    # Validate that at least one attachment entity is specified
    if not any([deal_id, person_id, org_id, lead_id]):
        return {
            "success": False,
            "error": "At least one of deal_id, person_id, org_id, or lead_id must be specified"
        }

    # Build request payload
    payload = {
        "content": content
    }

    # Add attachment entities if provided
    if deal_id:
        payload["deal_id"] = deal_id
    if person_id:
        payload["person_id"] = person_id
    if org_id:
        payload["org_id"] = org_id
    if lead_id:
        payload["lead_id"] = lead_id

    # Add pinning flags if provided
    if pinned_to_deal_flag is not None:
        payload["pinned_to_deal_flag"] = 1 if pinned_to_deal_flag else 0
    if pinned_to_person_flag is not None:
        payload["pinned_to_person_flag"] = 1 if pinned_to_person_flag else 0
    if pinned_to_organization_flag is not None:
        payload["pinned_to_organization_flag"] = 1 if pinned_to_organization_flag else 0

    # Add any additional fields
    for key, value in kwargs.items():
        if value is not None and key not in payload:
            payload[key] = value

    url = f"{PIPEDRIVE_API_BASE}/notes?api_token={api_key}"

    try:
        async with httpx.AsyncClient() as client:
            async with traced_call(
                "pipedrive.add_note",
                request={"url": _redact_pipedrive_url(url), "payload": payload},
            ) as t:
                response = await client.post(url, json=payload, timeout=30.0)
                response.raise_for_status()
                data = response.json()
                if t:
                    t["response"] = {
                        "status_code": response.status_code,
                        "success": data.get("success"),
                        "note_id": (data.get("data") or {}).get("id"),
                        "error": data.get("error"),
                    }

            if data.get("success"):
                note_data = data.get("data", {})
                logger.info(f"Created Pipedrive note: {note_data.get('id')}")
                return {
                    "success": True,
                    "note_id": note_data.get("id"),
                    "note_data": note_data,
                    "message": "Note created successfully"
                }
            else:
                error_msg = data.get("error", "Unknown error from Pipedrive API")
                logger.error(f"Pipedrive API error: {error_msg}")
                return {
                    "success": False,
                    "error": f"Pipedrive API error: {error_msg}"
                }

    except httpx.HTTPError as e:
        logger.error(f"HTTP error creating Pipedrive note: {str(e)}")
        return {
            "success": False,
            "error": f"Failed to create note: {str(e)}"
        }
    except Exception as e:
        logger.error(f"Error creating Pipedrive note: {str(e)}")
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }


async def get_available_fields(
    db: Session,
    user_id: int,
    action_type: str
) -> Dict[str, Any]:
    """
    Get available fields from Pipedrive for a specific action type
    Results are cached for 24 hours to reduce API calls.

    Args:
        db: Database session
        user_id: User ID for API key lookup
        action_type: Type of action ('create_activity', 'update_deal', 'add_note')

    Returns:
        Dict containing success status and list of available fields
    """
    # Check cache first
    cache_key = f"pipedrive:fields:{user_id}:{action_type}"
    cached_result = cache_get(cache_key)
    if cached_result:
        logger.info(f"Returning cached Pipedrive fields for action '{action_type}' (user {user_id})")
        return cached_result

    api_key = await get_pipedrive_api_key(db, user_id)
    if not api_key:
        return {
            "success": False,
            "error": "Pipedrive API key not configured. Please add your API key in settings.",
            "fields": []
        }

    try:
        async with httpx.AsyncClient() as client:
            fields = []

            if action_type == "create_activity":
                # Fetch activity fields
                url = f"{PIPEDRIVE_API_BASE}/activityFields?api_token={api_key}"
                response = await client.get(url, timeout=30.0)
                response.raise_for_status()
                data = response.json()

                if data.get("success"):
                    pipedrive_fields = data.get("data", [])

                    # Map Pipedrive field data to our format
                    for field in pipedrive_fields:
                        field_key = field.get("key", "")
                        field_name = field.get("name", "")
                        field_type = field.get("field_type", "")
                        is_custom = field.get("edit_flag", True)

                        if field_key and field_name:
                            fields.append({
                                "value": field_key,
                                "label": field_name,
                                "type": field_type,
                                "is_custom": is_custom,
                                "required": field.get("mandatory_flag", False)
                            })

            elif action_type == "update_deal":
                # Fetch deal fields
                url = f"{PIPEDRIVE_API_BASE}/dealFields?api_token={api_key}"
                response = await client.get(url, timeout=30.0)
                response.raise_for_status()
                data = response.json()

                if data.get("success"):
                    pipedrive_fields = data.get("data", [])

                    for field in pipedrive_fields:
                        field_key = field.get("key", "")
                        field_name = field.get("name", "")
                        field_type = field.get("field_type", "")
                        is_custom = field.get("edit_flag", True)

                        if field_key and field_name:
                            fields.append({
                                "value": field_key,
                                "label": field_name,
                                "type": field_type,
                                "is_custom": is_custom,
                                "required": field.get("mandatory_flag", False)
                            })

            elif action_type == "add_note":
                # Notes have a simpler structure - only content and attachment entities
                fields = [
                    {"value": "content", "label": "Content (HTML)", "type": "text", "is_custom": False, "required": True},
                    {"value": "deal_id", "label": "Deal ID", "type": "int", "is_custom": False, "required": False},
                    {"value": "person_id", "label": "Person ID", "type": "int", "is_custom": False, "required": False},
                    {"value": "org_id", "label": "Organization ID", "type": "int", "is_custom": False, "required": False},
                    {"value": "lead_id", "label": "Lead ID", "type": "int", "is_custom": False, "required": False},
                ]

            logger.info(f"Fetched {len(fields)} fields for action type '{action_type}'")
            result = {
                "success": True,
                "fields": fields,
                "action_type": action_type
            }

            # Cache the result for 24 hours (86400 seconds)
            # Fields don't change frequently, so longer TTL is appropriate
            cache_set(cache_key, result, ttl=86400)
            logger.info(f"Cached Pipedrive fields for action '{action_type}' (user {user_id})")

            return result

    except httpx.HTTPError as e:
        logger.error(f"HTTP error fetching Pipedrive fields: {str(e)}")
        return {
            "success": False,
            "error": f"Failed to fetch fields from Pipedrive: {str(e)}",
            "fields": []
        }
    except Exception as e:
        logger.error(f"Error fetching Pipedrive fields: {str(e)}")
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "fields": []
        }


async def get_pipedrive_pipelines(
    db: Session,
    user_id: int
) -> Dict[str, Any]:
    """
    Get all pipelines from Pipedrive
    Results are cached for 24 hours.

    Returns:
        Dict containing success status and list of pipelines [{id, name}]
    """
    # Check cache first
    cache_key = f"pipedrive:pipelines:{user_id}"
    cached_result = cache_get(cache_key)
    if cached_result:
        logger.info(f"Returning cached Pipedrive pipelines for user {user_id}")
        return cached_result

    api_key = await get_pipedrive_api_key(db, user_id)
    if not api_key:
        return {
            "success": False,
            "error": "Pipedrive API key not configured.",
            "pipelines": []
        }

    try:
        async with httpx.AsyncClient() as client:
            url = f"{PIPEDRIVE_API_BASE}/pipelines?api_token={api_key}"
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
            data = response.json()

            if data.get("success"):
                pipelines = []
                for pipeline in data.get("data", []):
                    pipeline_id = pipeline.get("id")
                    pipeline_name = pipeline.get("name")
                    active = pipeline.get("active", True)

                    # Only include active pipelines
                    if pipeline_id and pipeline_name and active:
                        pipelines.append({
                            "id": pipeline_id,
                            "name": pipeline_name
                        })

                result = {
                    "success": True,
                    "pipelines": pipelines
                }

                # Cache for 24 hours
                cache_set(cache_key, result, ttl=86400)
                logger.info(f"Cached {len(pipelines)} Pipedrive pipelines for user {user_id}")

                return result
            else:
                return {
                    "success": False,
                    "error": "Failed to fetch pipelines from Pipedrive",
                    "pipelines": []
                }

    except Exception as e:
        logger.error(f"Error fetching Pipedrive pipelines: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "pipelines": []
        }


async def get_deal_stages(
    db: Session,
    user_id: int
) -> Dict[str, Any]:
    """
    Get all pipeline stages from Pipedrive grouped by pipeline
    Results are cached for 24 hours.

    Returns:
        Dict containing:
        - success: bool
        - stages: Dict[str, str] (flat mapping for backward compatibility)
        - stages_by_pipeline: Dict[str, Dict] (grouped by pipeline)
    """
    # Check cache first
    cache_key = f"pipedrive:stages:{user_id}"
    cached_result = cache_get(cache_key)
    if cached_result:
        logger.info(f"Returning cached Pipedrive stages for user {user_id}")
        return cached_result

    api_key = await get_pipedrive_api_key(db, user_id)
    if not api_key:
        return {
            "success": False,
            "error": "Pipedrive API key not configured.",
            "stages": {},
            "stages_by_pipeline": {}
        }

    try:
        # Fetch both stages and pipelines
        async with httpx.AsyncClient() as client:
            # Fetch stages
            stages_url = f"{PIPEDRIVE_API_BASE}/stages?api_token={api_key}"
            stages_response = await client.get(stages_url, timeout=30.0)
            stages_response.raise_for_status()
            stages_data = stages_response.json()

            # Fetch pipelines to get pipeline names
            pipelines_url = f"{PIPEDRIVE_API_BASE}/pipelines?api_token={api_key}"
            pipelines_response = await client.get(pipelines_url, timeout=30.0)
            pipelines_response.raise_for_status()
            pipelines_data = pipelines_response.json()

            if stages_data.get("success") and pipelines_data.get("success"):
                # Create pipeline ID to name mapping
                pipeline_names = {}
                for pipeline in pipelines_data.get("data", []):
                    pipeline_id = pipeline.get("id")
                    pipeline_name = pipeline.get("name")
                    if pipeline_id and pipeline_name:
                        pipeline_names[pipeline_id] = pipeline_name

                logger.info(f"Found {len(pipeline_names)} pipelines: {list(pipeline_names.values())}")

                # Build both flat stages dict (for backward compatibility)
                # and grouped stages_by_pipeline
                stages = {}
                stages_by_pipeline = {}
                stages_without_pipeline = []

                for stage in stages_data.get("data", []):
                    stage_id = stage.get("id")
                    stage_name = stage.get("name")
                    pipeline_id = stage.get("pipeline_id")

                    if stage_id and stage_name:
                        # Flat mapping (backward compatibility)
                        stages[str(stage_id)] = stage_name

                        if pipeline_id:
                            # Grouped by pipeline
                            pipeline_id_str = str(pipeline_id)
                            if pipeline_id_str not in stages_by_pipeline:
                                stages_by_pipeline[pipeline_id_str] = {
                                    "pipeline_name": pipeline_names.get(pipeline_id, f"Pipeline {pipeline_id}"),
                                    "stages": []
                                }

                            stages_by_pipeline[pipeline_id_str]["stages"].append({
                                "id": str(stage_id),
                                "name": stage_name
                            })
                        else:
                            stages_without_pipeline.append({
                                "id": str(stage_id),
                                "name": stage_name
                            })

                if stages_without_pipeline:
                    logger.warning(f"Found {len(stages_without_pipeline)} stages without pipeline_id: {[s['name'] for s in stages_without_pipeline[:5]]}")

                logger.info(f"Built stages_by_pipeline with {len(stages_by_pipeline)} pipelines and {len(stages)} total stages")

                result = {
                    "success": True,
                    "stages": stages,  # Flat mapping for backward compatibility
                    "stages_by_pipeline": stages_by_pipeline  # Grouped by pipeline (new)
                }

                # Cache for 24 hours
                cache_set(cache_key, result, ttl=86400)
                logger.info(f"Cached {len(stages)} Pipedrive stages across {len(stages_by_pipeline)} pipelines for user {user_id}")

                return result
            else:
                return {
                    "success": False,
                    "error": "Failed to fetch stages from Pipedrive",
                    "stages": {},
                    "stages_by_pipeline": {}
                }

    except Exception as e:
        logger.error(f"Error fetching Pipedrive stages: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "stages": {},
            "stages_by_pipeline": {}
        }


async def get_enriched_deal_data(
    db: Session,
    user_id: int,
    deal_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Enrich deal data with human-readable labels for stages, status, etc.

    Args:
        db: Database session
        user_id: User ID for API key lookup
        deal_data: Raw deal data from Pipedrive API

    Returns:
        Enriched deal data with readable labels
    """
    enriched = deal_data.copy()

    # Get stage name
    stage_id = deal_data.get("stage_id")
    if stage_id:
        stages_result = await get_deal_stages(db, user_id)
        if stages_result.get("success"):
            stages = stages_result.get("stages", {})
            stage_name = stages.get(str(stage_id))
            if stage_name:
                enriched["stage_name"] = stage_name

    # Map status to readable label
    status = deal_data.get("status")
    if status:
        status_labels = {
            "open": "Open",
            "won": "Won",
            "lost": "Lost",
            "deleted": "Deleted"
        }
        enriched["status_label"] = status_labels.get(status, status)

    return enriched


async def get_pipedrive_users(
    db: Session,
    user_id: int
) -> Dict[str, Any]:
    """
    Get all users from Pipedrive account
    Results are cached for 24 hours.

    Returns:
        Dict containing success status and list of users
    """
    # Check cache first
    cache_key = f"pipedrive:users:{user_id}"
    cached_result = cache_get(cache_key)
    if cached_result:
        logger.info(f"Returning cached Pipedrive users for user {user_id}")
        return cached_result

    api_key = await get_pipedrive_api_key(db, user_id)
    if not api_key:
        return {
            "success": False,
            "error": "Pipedrive API key not configured.",
            "users": []
        }

    try:
        async with httpx.AsyncClient() as client:
            url = f"{PIPEDRIVE_API_BASE}/users?api_token={api_key}"
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
            data = response.json()

            if data.get("success"):
                users = []
                for user in data.get("data", []):
                    user_name = user.get("name")
                    if user_name:
                        users.append(user_name)

                result = {
                    "success": True,
                    "users": users
                }

                # Cache for 24 hours
                cache_set(cache_key, result, ttl=86400)
                logger.info(f"Cached {len(users)} Pipedrive users for user {user_id}")

                return result
            else:
                return {
                    "success": False,
                    "error": "Failed to fetch users from Pipedrive",
                    "users": []
                }

    except Exception as e:
        logger.error(f"Error fetching Pipedrive users: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "users": []
        }


async def get_pipedrive_currencies(
    db: Session,
    user_id: int
) -> Dict[str, Any]:
    """
    Get all currencies from Pipedrive account
    Results are cached for 24 hours.

    Returns:
        Dict containing success status and list of currency codes
    """
    # Check cache first
    cache_key = f"pipedrive:currencies:{user_id}"
    cached_result = cache_get(cache_key)
    if cached_result:
        logger.info(f"Returning cached Pipedrive currencies for user {user_id}")
        return cached_result

    api_key = await get_pipedrive_api_key(db, user_id)
    if not api_key:
        return {
            "success": False,
            "error": "Pipedrive API key not configured.",
            "currencies": []
        }

    try:
        async with httpx.AsyncClient() as client:
            url = f"{PIPEDRIVE_API_BASE}/currencies?api_token={api_key}"
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
            data = response.json()

            if data.get("success"):
                currencies = []
                for currency in data.get("data", []):
                    currency_code = currency.get("code")
                    if currency_code:
                        currencies.append(currency_code)

                result = {
                    "success": True,
                    "currencies": currencies
                }

                # Cache for 24 hours
                cache_set(cache_key, result, ttl=86400)
                logger.info(f"Cached {len(currencies)} Pipedrive currencies for user {user_id}")

                return result
            else:
                return {
                    "success": False,
                    "error": "Failed to fetch currencies from Pipedrive",
                    "currencies": []
                }

    except Exception as e:
        logger.error(f"Error fetching Pipedrive currencies: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "currencies": []
        }


async def find_latest_deal_by_emails(
    db: Session,
    user_id: int,
    emails: List[str]
) -> Dict[str, Any]:
    """
    Find the latest deal associated with any of the provided email addresses

    Args:
        db: Database session
        user_id: User ID for API key lookup
        emails: List of email addresses to search for

    Returns:
        Dict containing deal_id and deal data, or None if no deal found
    """
    api_key = await get_pipedrive_api_key(db, user_id)
    if not api_key:
        return {
            "success": False,
            "error": "Pipedrive API key not configured. Please add your API key in settings."
        }

    if not emails:
        return {
            "success": False,
            "error": "No email addresses provided for deal lookup"
        }

    try:
        async with httpx.AsyncClient() as client:
            all_deals = []

            # Search for deals by each email address
            for email in emails:
                # First, find the person by email
                person_url = f"{PIPEDRIVE_API_BASE}/persons/search?term={email}&fields=email&api_token={api_key}"
                person_response = await client.get(person_url, timeout=30.0)
                person_response.raise_for_status()
                person_data = person_response.json()

                if person_data.get("success") and person_data.get("data"):
                    items = person_data.get("data", {}).get("items", [])

                    for item in items:
                        person = item.get("item", {})
                        person_id = person.get("id")

                        if person_id:
                            # Get deals for this person
                            deals_url = f"{PIPEDRIVE_API_BASE}/persons/{person_id}/deals?api_token={api_key}"
                            deals_response = await client.get(deals_url, timeout=30.0)
                            deals_response.raise_for_status()
                            deals_data = deals_response.json()

                            if deals_data.get("success") and deals_data.get("data"):
                                for deal in deals_data.get("data", []):
                                    all_deals.append({
                                        "id": deal.get("id"),
                                        "title": deal.get("title"),
                                        "status": deal.get("status"),
                                        "update_time": deal.get("update_time"),
                                        "add_time": deal.get("add_time"),
                                        "person_email": email,
                                        "person_id": person_id,
                                        "full_data": deal
                                    })

            if not all_deals:
                logger.info(f"No deals found for emails: {emails}")
                return {
                    "success": False,
                    "error": "No deals found for the provided email addresses",
                    "deal_id": None
                }

            # Sort by update_time (most recently updated first)
            all_deals.sort(key=lambda x: x.get("update_time", ""), reverse=True)
            latest_deal = all_deals[0]

            logger.info(f"Found {len(all_deals)} total deals, using latest: Deal ID {latest_deal['id']} (updated: {latest_deal['update_time']})")

            # Enrich the deal data with readable labels
            enriched_deal_data = await get_enriched_deal_data(db, user_id, latest_deal["full_data"])

            return {
                "success": True,
                "deal_id": latest_deal["id"],
                "deal_title": latest_deal["title"],
                "deal_status": latest_deal["status"],
                "person_email": latest_deal["person_email"],
                "person_id": latest_deal["person_id"],
                "total_deals_found": len(all_deals),
                "deal_data": enriched_deal_data
            }

    except httpx.HTTPError as e:
        logger.error(f"HTTP error finding deals by emails: {str(e)}")
        return {
            "success": False,
            "error": f"Failed to search Pipedrive for deals: {str(e)}"
        }
    except Exception as e:
        logger.error(f"Error finding deals by emails: {str(e)}")
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }


async def get_all_organizations(
    db: Session,
    user_id: int
) -> Dict[str, Any]:
    """
    Get all organizations from Pipedrive
    Results are cached for 1 hour.

    Args:
        db: Database session
        user_id: User ID for API key lookup

    Returns:
        Dict containing success status and list of organizations
    """
    # Check cache first
    cache_key = f"pipedrive:organizations:{user_id}"
    cached_result = cache_get(cache_key)
    if cached_result:
        logger.info(f"Returning cached Pipedrive organizations for user {user_id}")
        return cached_result

    api_key = await get_pipedrive_api_key(db, user_id)
    if not api_key:
        return {
            "success": False,
            "error": "Pipedrive API key not configured. Please add your API key in settings.",
            "organizations": []
        }

    try:
        async with httpx.AsyncClient() as client:
            all_organizations = []
            start = 0
            limit = 500  # Max allowed by Pipedrive API
            has_more = True

            # Paginate through all organizations
            while has_more:
                url = f"{PIPEDRIVE_API_BASE}/organizations?start={start}&limit={limit}&api_token={api_key}"
                response = await client.get(url, timeout=30.0)
                response.raise_for_status()
                data = response.json()

                if data.get("success"):
                    organizations = data.get("data", [])
                    if organizations:
                        for org in organizations:
                            all_organizations.append({
                                "id": org.get("id"),
                                "name": org.get("name"),
                                "address": org.get("address"),
                                "owner_id": org.get("owner_id")
                            })

                    # Check if there are more results
                    additional_data = data.get("additional_data", {})
                    pagination = additional_data.get("pagination", {})
                    has_more = pagination.get("more_items_in_collection", False)

                    if has_more:
                        start = pagination.get("next_start", start + limit)
                        logger.info(f"Fetching more organizations, start: {start}")
                else:
                    logger.error(f"Pipedrive API error: {data.get('error', 'Unknown error')}")
                    has_more = False

            logger.info(f"Fetched {len(all_organizations)} organizations from Pipedrive")

            result = {
                "success": True,
                "organizations": all_organizations,
                "count": len(all_organizations)
            }

            # Cache for 1 hour (3600 seconds)
            cache_set(cache_key, result, ttl=3600)

            return result

    except httpx.HTTPError as e:
        logger.error(f"HTTP error fetching Pipedrive organizations: {str(e)}")
        return {
            "success": False,
            "error": f"Failed to fetch organizations from Pipedrive: {str(e)}",
            "organizations": []
        }
    except Exception as e:
        logger.error(f"Error fetching Pipedrive organizations: {str(e)}")
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "organizations": []
        }


async def get_deals_by_organization(
    db: Session,
    user_id: int,
    org_id: int
) -> Dict[str, Any]:
    """
    Get all deals for a specific organization from Pipedrive

    Args:
        db: Database session
        user_id: User ID for API key lookup
        org_id: Organization ID to get deals for

    Returns:
        Dict containing success status and list of deals
    """
    api_key = await get_pipedrive_api_key(db, user_id)
    if not api_key:
        return {
            "success": False,
            "error": "Pipedrive API key not configured. Please add your API key in settings.",
            "deals": []
        }

    try:
        async with httpx.AsyncClient() as client:
            url = f"{PIPEDRIVE_API_BASE}/organizations/{org_id}/deals?api_token={api_key}"
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
            data = response.json()

            if data.get("success"):
                deals = data.get("data", [])

                # Extract relevant deal information
                deal_list = []
                if deals:
                    for deal in deals:
                        deal_list.append({
                            "id": deal.get("id"),
                            "title": deal.get("title"),
                            "value": deal.get("value"),
                            "currency": deal.get("currency"),
                            "status": deal.get("status"),
                            "stage_id": deal.get("stage_id"),
                            "update_time": deal.get("update_time"),
                            "add_time": deal.get("add_time"),
                            "full_data": deal
                        })

                logger.info(f"Found {len(deal_list)} deals for organization {org_id}")

                return {
                    "success": True,
                    "deals": deal_list,
                    "count": len(deal_list),
                    "org_id": org_id
                }
            else:
                error_msg = data.get("error", "Unknown error from Pipedrive API")
                logger.error(f"Pipedrive API error: {error_msg}")
                return {
                    "success": False,
                    "error": f"Pipedrive API error: {error_msg}",
                    "deals": []
                }

    except httpx.HTTPError as e:
        logger.error(f"HTTP error fetching deals for organization {org_id}: {str(e)}")
        return {
            "success": False,
            "error": f"Failed to fetch deals from Pipedrive: {str(e)}",
            "deals": []
        }
    except Exception as e:
        logger.error(f"Error fetching deals for organization {org_id}: {str(e)}")
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "deals": []
        }


async def get_pipedrive_users_with_email(
    db: Session,
    user_id: int
) -> Dict[str, Any]:
    """
    Get all users from Pipedrive with full details including email.
    Results are cached for 24 hours.

    Args:
        db: Database session
        user_id: User ID for API key lookup

    Returns:
        Dict containing success status and list of users [{id, name, email}]
    """
    cache_key = f"pipedrive:users_full:{user_id}"
    cached_result = cache_get(cache_key)
    if cached_result:
        return cached_result

    api_key = await get_pipedrive_api_key(db, user_id)
    if not api_key:
        return {"success": False, "error": "Pipedrive API key not configured.", "users": []}

    try:
        async with httpx.AsyncClient() as client:
            url = f"{PIPEDRIVE_API_BASE}/users?api_token={api_key}"
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
            data = response.json()

            if data.get("success"):
                users = []
                for user in data.get("data", []):
                    users.append({
                        "id": user.get("id"),
                        "name": user.get("name"),
                        "email": user.get("email", "").lower()
                    })

                result = {"success": True, "users": users}
                cache_set(cache_key, result, ttl=86400)  # 24 hours
                logger.info(f"Fetched {len(users)} Pipedrive users with email")
                return result
            else:
                return {"success": False, "error": "Failed to fetch users", "users": []}

    except Exception as e:
        logger.error(f"Error fetching Pipedrive users: {str(e)}")
        return {"success": False, "error": str(e), "users": []}


async def create_organization(
    db: Session,
    user_id: int,
    name: str,
    owner_id: Optional[int] = None,
    address: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Create a new organization in Pipedrive.

    Args:
        db: Database session
        user_id: User ID for API key lookup
        name: Organization name (required)
        owner_id: Pipedrive user ID who owns the organization
        address: Organization address
        **kwargs: Additional custom fields

    Returns:
        Dict containing success status and created organization data
    """
    api_key = await get_pipedrive_api_key(db, user_id)
    if not api_key:
        return {"success": False, "error": "Pipedrive API key not configured."}

    payload = {"name": name}

    if owner_id:
        payload["owner_id"] = owner_id
    if address:
        payload["address"] = address

    for key, value in kwargs.items():
        if value is not None:
            payload[key] = value

    url = f"{PIPEDRIVE_API_BASE}/organizations?api_token={api_key}"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=30.0)
            response.raise_for_status()
            data = response.json()

            if data.get("success"):
                org_data = data.get("data", {})
                logger.info(f"Created Pipedrive organization: {org_data.get('id')} - {name}")

                # Clear organizations cache since we added a new one
                cache_clear_pattern(f"pipedrive:organizations:{user_id}")

                return {
                    "success": True,
                    "organization_id": org_data.get("id"),
                    "organization_data": org_data,
                    "message": f"Organization '{name}' created successfully"
                }
            else:
                error_msg = data.get("error", "Unknown error")
                return {"success": False, "error": f"Pipedrive API error: {error_msg}"}

    except httpx.HTTPError as e:
        logger.error(f"HTTP error creating organization: {str(e)}")
        return {"success": False, "error": f"Failed to create organization: {str(e)}"}
    except Exception as e:
        logger.error(f"Error creating organization: {str(e)}")
        return {"success": False, "error": f"Unexpected error: {str(e)}"}


async def create_person(
    db: Session,
    user_id: int,
    name: str,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    org_id: Optional[int] = None,
    owner_id: Optional[int] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Create a new person (contact) in Pipedrive.

    Args:
        db: Database session
        user_id: User ID for API key lookup
        name: Person name (required)
        email: Person email address
        phone: Person phone number
        org_id: ID of organization to link this person to
        owner_id: Pipedrive user ID who owns this person

    Returns:
        Dict containing success status and created person data
    """
    api_key = await get_pipedrive_api_key(db, user_id)
    if not api_key:
        return {"success": False, "error": "Pipedrive API key not configured."}

    payload = {"name": name}

    if email:
        # Pipedrive expects emails as array of objects
        payload["email"] = [{"value": email, "primary": True, "label": "work"}]
    if phone:
        payload["phone"] = [{"value": phone, "primary": True, "label": "work"}]
    if org_id:
        payload["org_id"] = org_id
    if owner_id:
        payload["owner_id"] = owner_id

    for key, value in kwargs.items():
        if value is not None:
            payload[key] = value

    url = f"{PIPEDRIVE_API_BASE}/persons?api_token={api_key}"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=30.0)
            response.raise_for_status()
            data = response.json()

            if data.get("success"):
                person_data = data.get("data", {})
                logger.info(f"Created Pipedrive person: {person_data.get('id')} - {name}")
                return {
                    "success": True,
                    "person_id": person_data.get("id"),
                    "person_data": person_data,
                    "message": f"Person '{name}' created successfully"
                }
            else:
                error_msg = data.get("error", "Unknown error")
                return {"success": False, "error": f"Pipedrive API error: {error_msg}"}

    except httpx.HTTPError as e:
        logger.error(f"HTTP error creating person: {str(e)}")
        return {"success": False, "error": f"Failed to create person: {str(e)}"}
    except Exception as e:
        logger.error(f"Error creating person: {str(e)}")
        return {"success": False, "error": f"Unexpected error: {str(e)}"}


async def find_person_by_email(
    db: Session,
    user_id: int,
    email: str
) -> Dict[str, Any]:
    """
    Search for a person by email in Pipedrive.

    Args:
        db: Database session
        user_id: User ID for API key lookup
        email: Email address to search for

    Returns:
        Dict containing success status and person data if found
    """
    api_key = await get_pipedrive_api_key(db, user_id)
    if not api_key:
        return {"success": False, "error": "Pipedrive API key not configured.", "found": False, "person": None}

    try:
        async with httpx.AsyncClient() as client:
            # Use the search endpoint with email field filter
            url = f"{PIPEDRIVE_API_BASE}/persons/search?term={email}&fields=email&api_token={api_key}"
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
            data = response.json()

            if data.get("success"):
                items = data.get("data", {}).get("items", [])
                if items:
                    person = items[0].get("item", {})
                    logger.info(f"Found existing person for email {email}: ID {person.get('id')}")
                    return {
                        "success": True,
                        "found": True,
                        "person_id": person.get("id"),
                        "person": person
                    }
                return {"success": True, "found": False, "person": None}
            else:
                return {"success": False, "error": "Search failed", "found": False, "person": None}

    except Exception as e:
        logger.error(f"Error searching person by email: {str(e)}")
        return {"success": False, "error": str(e), "found": False, "person": None}
