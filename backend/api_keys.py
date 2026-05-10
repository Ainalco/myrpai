"""
API Key Management endpoints
Handles secure storage and retrieval of user API keys for third-party services
"""
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_
from pydantic import BaseModel, Field
import logging
import httpx

from database import get_db
from auth import get_current_active_user
import models
from encryption_service import encrypt_api_key, decrypt_api_key

router = APIRouter()
logger = logging.getLogger(__name__)

# Supported services with their identifiers
SUPPORTED_SERVICES = ["fireflies", "pipedrive"]


# Pydantic models
class ApiKeyCreate(BaseModel):
    """Request model for creating/updating an API key"""
    service_name: str = Field(..., description="Service name (e.g., 'fireflies', 'pipedrive')")
    api_key: str = Field(..., description="The API key to store", min_length=1)

    class Config:
        json_schema_extra = {
            "example": {
                "service_name": "fireflies",
                "api_key": "your-api-key-here"
            }
        }


class ApiKeyInfo(BaseModel):
    """Response model for API key information (never includes actual key)"""
    id: int
    service_name: str
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    # Note: Never include encrypted_key or decrypted key in responses

    class Config:
        from_attributes = True


class ApiKeyTestRequest(BaseModel):
    """Request model for testing an API key"""
    service_name: str
    api_key: str


class ApiKeyTestResponse(BaseModel):
    """Response model for API key test results"""
    success: bool
    message: str
    service_name: str


class ApiKeyStatus(BaseModel):
    """Simple status indicating if a key exists"""
    service_name: str
    configured: bool


# Helper functions
def get_user_api_key_record(
    db: Session,
    user_id: int,
    service_name: str,
    only_active: bool = True
) -> Optional[models.ApiKey]:
    """
    Get API key record for a user and service

    Args:
        db: Database session
        user_id: User ID
        service_name: Service identifier
        only_active: If True, only return active keys

    Returns:
        ApiKey record or None
    """
    query = db.query(models.ApiKey).filter(
        and_(
            models.ApiKey.user_id == user_id,
            models.ApiKey.service_name == service_name
        )
    )

    if only_active:
        query = query.filter(models.ApiKey.is_active == True)

    return query.first()


def get_decrypted_api_key(
    db: Session,
    user_id: int,
    service_name: str
) -> Optional[str]:
    """
    Get decrypted API key for a user and service

    Args:
        db: Database session
        user_id: User ID
        service_name: Service identifier

    Returns:
        Decrypted API key or None if not found
    """
    api_key_record = get_user_api_key_record(db, user_id, service_name)

    if not api_key_record:
        return None

    try:
        decrypted_key = decrypt_api_key(api_key_record.encrypted_key)

        # Update last_used_at timestamp
        api_key_record.last_used_at = datetime.utcnow()
        db.commit()

        return decrypted_key
    except Exception as e:
        logger.error(f"Failed to decrypt API key for user {user_id}, service {service_name}: {e}")
        return None


async def test_fireflies_api_key(api_key: str) -> tuple[bool, str]:
    """
    Test Fireflies API key by making a simple query

    Args:
        api_key: The Fireflies API key to test

    Returns:
        Tuple of (success: bool, message: str)
    """
    query = """
    query {
        user {
            email
            name
        }
    }
    """

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {"query": query}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.fireflies.ai/graphql",
                json=payload,
                headers=headers,
                timeout=10.0
            )

            if response.status_code == 200:
                data = response.json()
                if "errors" in data:
                    return False, f"API key authentication failed: {data['errors']}"
                if "data" in data and data["data"].get("user"):
                    return True, "API key is valid and working"
                return False, "Unexpected response format from Fireflies API"
            elif response.status_code == 401:
                return False, "Invalid API key or unauthorized"
            else:
                return False, f"API request failed with status {response.status_code}"

    except httpx.TimeoutException:
        return False, "Request timed out - please try again"
    except Exception as e:
        logger.error(f"Error testing Fireflies API key: {e}")
        return False, f"Connection error: {str(e)}"


async def test_pipedrive_api_key(api_key: str) -> tuple[bool, str]:
    """
    Test Pipedrive API key by fetching user info

    Args:
        api_key: The Pipedrive API key to test

    Returns:
        Tuple of (success: bool, message: str)
    """
    # Pipedrive API key format is usually: company_domain:api_token
    # or just the token, depending on their setup
    # We'll try to fetch the user info endpoint

    try:
        async with httpx.AsyncClient() as client:
            # Try to get user info - this endpoint works with just the API token
            response = await client.get(
                f"https://api.pipedrive.com/v1/users/me?api_token={api_key}",
                timeout=10.0
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    return True, "API key is valid and working"
                return False, "API key validation failed"
            elif response.status_code == 401:
                return False, "Invalid API key or unauthorized"
            else:
                return False, f"API request failed with status {response.status_code}"

    except httpx.TimeoutException:
        return False, "Request timed out - please try again"
    except Exception as e:
        logger.error(f"Error testing Pipedrive API key: {e}")
        return False, f"Connection error: {str(e)}"


# API Endpoints
@router.post("/api-keys", response_model=ApiKeyInfo, status_code=status.HTTP_201_CREATED)
async def create_or_update_api_key(
    key_data: ApiKeyCreate,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Create or update an API key for the current user

    - Creates a new key if one doesn't exist for the service
    - Updates the existing key if one already exists
    - Keys are encrypted before storage
    """
    # Validate service name
    if key_data.service_name.lower() not in SUPPORTED_SERVICES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported service. Supported services: {', '.join(SUPPORTED_SERVICES)}"
        )

    service_name = key_data.service_name.lower()

    try:
        # Encrypt the API key
        encrypted_key = encrypt_api_key(key_data.api_key)
    except ValueError as e:
        logger.error(f"Encryption failed for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to encrypt API key"
        )

    # Check if key already exists for this user and service
    existing_key = get_user_api_key_record(
        db,
        current_user.id,
        service_name,
        only_active=False  # Get even inactive keys
    )

    if existing_key:
        # Update existing key
        existing_key.encrypted_key = encrypted_key
        existing_key.is_active = True
        existing_key.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing_key)
        logger.info(f"Updated API key for user {current_user.id}, service {service_name}")
        return existing_key
    else:
        # Create new key
        new_key = models.ApiKey(
            user_id=current_user.id,
            service_name=service_name,
            encrypted_key=encrypted_key,
            is_active=True
        )
        db.add(new_key)
        db.commit()
        db.refresh(new_key)
        logger.info(f"Created new API key for user {current_user.id}, service {service_name}")
        return new_key


@router.get("/api-keys", response_model=List[ApiKeyInfo])
async def list_api_keys(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    List all API keys configured by the current user

    Returns metadata only - never returns the actual keys
    """
    keys = db.query(models.ApiKey).filter(
        models.ApiKey.user_id == current_user.id,
        models.ApiKey.is_active == True
    ).all()

    return keys


@router.get("/api-keys/{service_name}", response_model=ApiKeyStatus)
async def check_api_key_status(
    service_name: str,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Check if an API key is configured for a specific service

    Returns only a boolean status - never returns the actual key
    """
    key = get_user_api_key_record(db, current_user.id, service_name.lower())

    return ApiKeyStatus(
        service_name=service_name.lower(),
        configured=key is not None
    )


@router.delete("/api-keys/{service_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    service_name: str,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Delete (deactivate) an API key for a specific service

    Keys are soft-deleted by setting is_active=False
    """
    key = get_user_api_key_record(
        db,
        current_user.id,
        service_name.lower(),
        only_active=True
    )

    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active API key found for service: {service_name}"
        )

    # Soft delete by marking as inactive
    key.is_active = False
    key.updated_at = datetime.utcnow()
    db.commit()

    logger.info(f"Deactivated API key for user {current_user.id}, service {service_name}")
    return None


@router.post("/api-keys/test", response_model=ApiKeyTestResponse)
async def test_api_key(
    test_request: ApiKeyTestRequest,
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Test an API key without saving it

    This allows users to verify their key works before storing it
    """
    service_name = test_request.service_name.lower()

    if service_name not in SUPPORTED_SERVICES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported service. Supported services: {', '.join(SUPPORTED_SERVICES)}"
        )

    # Test the appropriate service
    if service_name == "fireflies":
        success, message = await test_fireflies_api_key(test_request.api_key)
    elif service_name == "pipedrive":
        success, message = await test_pipedrive_api_key(test_request.api_key)
    else:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"Testing not implemented for service: {service_name}"
        )

    return ApiKeyTestResponse(
        success=success,
        message=message,
        service_name=service_name
    )
