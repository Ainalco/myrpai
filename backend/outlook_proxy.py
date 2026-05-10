"""
Outlook API Proxy Router

Proxies requests to the external Outlook API service to avoid CORS issues.
Backend-to-backend requests don't have CORS restrictions.

The external Outlook service uses the same infrastructure as Gmail:
- AUTH_URL: For authentication (login, token validation)
- BASE_URL: For Outlook operations (accounts, send, etc.)

We forward the user's JWT token from our system to the external API.
"""

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, List
import httpx
import os
import logging

from auth import get_current_active_user, security
from models import User

logger = logging.getLogger(__name__)

router = APIRouter()

# Outlook API URLs (default to local Docker scurry-email service)
# Auth URL - for authentication and token validation
OUTLOOK_AUTH_URL = os.getenv("OUTLOOK_AUTH_URL", "http://backend:9000/api")
# Base URL - for Outlook operations (accounts, send, etc.)
OUTLOOK_API_BASE_URL = os.getenv("OUTLOOK_API_BASE_URL", "http://scurry-email/outlook")

# HTTP client timeout
TIMEOUT = 30.0


def get_auth_header(credentials: HTTPAuthorizationCredentials) -> dict:
    """Build authorization header to forward to external Outlook API."""
    return {"Authorization": f"Bearer {credentials.credentials}"}


async def validate_token_with_auth_service(credentials: HTTPAuthorizationCredentials) -> Optional[dict]:
    """
    Validate the JWT token with the external auth service.
    Returns user data if valid, None if invalid.
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                f"{OUTLOOK_AUTH_URL}/auth/me",
                headers=get_auth_header(credentials)
            )
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"Token validation failed: {response.status_code}")
                return None
    except Exception as e:
        logger.error(f"Token validation error: {str(e)}")
        return None


# Response models

class OutlookAccount(BaseModel):
    id: int
    email: str
    display_name: Optional[str] = None
    is_active: bool
    token_status: Optional[str] = None
    created_at: Optional[str] = None


class OutlookAuthUrlResponse(BaseModel):
    success: bool
    auth_url: Optional[str] = None
    error: Optional[str] = None


class OutlookAccountsResponse(BaseModel):
    success: bool
    accounts: List[OutlookAccount] = []
    error: Optional[str] = None


class OutlookDisconnectResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    error: Optional[str] = None


class OutlookSendEmailRequest(BaseModel):
    account_id: int
    to: str
    to_name: Optional[str] = None
    subject: str
    body: str
    cc: Optional[List[str]] = None
    bcc: Optional[List[str]] = None
    track_opens: bool = True
    track_clicks: bool = True
    in_reply_to: Optional[str] = None
    references: Optional[str] = None


class OutlookSendEmailResponse(BaseModel):
    success: bool
    message_id: Optional[str] = None
    email_id: Optional[int] = None
    thread_id: Optional[str] = None
    message_id_header: Optional[str] = None
    error: Optional[str] = None


# Internal function for sending emails (can be called from email_service)
async def send_email_via_outlook(
    jwt_token: str,
    account_id: int,
    to: str,
    subject: str,
    body: str,
    to_name: Optional[str] = None,
    cc: Optional[List[str]] = None,
    bcc: Optional[List[str]] = None,
    track_opens: bool = True,
    track_clicks: bool = True,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
) -> dict:
    """
    Send an email via the Outlook API.

    This function can be called internally by email_service.py for queue processing.

    Args:
        jwt_token: The user's JWT token for authentication
        account_id: The Outlook account ID to send from
        to: Recipient email address
        subject: Email subject
        body: Email body (HTML supported)
        to_name: Optional recipient name
        cc: Optional list of CC addresses
        bcc: Optional list of BCC addresses
        track_opens: Whether to track email opens
        track_clicks: Whether to track link clicks

    Returns:
        dict with success, message_id/email_id, or error
    """
    try:
        payload = {
            "account_id": account_id,
            "to": to,
            "subject": subject,
            "body": body,
            "track_opens": track_opens,
            "track_clicks": track_clicks
        }

        if to_name:
            payload["to_name"] = to_name
        if cc:
            payload["cc"] = cc
        if bcc:
            payload["bcc"] = bcc
        if in_reply_to:
            payload["in_reply_to"] = in_reply_to
        if references:
            payload["references"] = references

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{OUTLOOK_API_BASE_URL}/email/send.php",
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {jwt_token}"
                }
            )

            logger.info(f"Outlook send response status: {response.status_code}")

            if response.status_code != 200:
                logger.error(f"Outlook send error: {response.text[:500]}")
                return {
                    "success": False,
                    "error": f"Outlook API error: {response.status_code}"
                }

            data = response.json()
            logger.info(f"Outlook send response: {data}")

            # Handle nested structure
            result_data = data.get("data", {})

            return {
                "success": data.get("success", False),
                "message_id": result_data.get("message_id") or data.get("message_id"),
                "email_id": result_data.get("email_id") or data.get("email_id"),
                "thread_id": result_data.get("thread_id") or data.get("thread_id"),
                "message_id_header": result_data.get("message_id_header") or data.get("message_id_header"),
                "error": data.get("error")
            }

    except httpx.TimeoutException:
        logger.error("Outlook send timeout")
        return {"success": False, "error": "Outlook API request timed out"}
    except Exception as e:
        logger.error(f"Outlook send error: {str(e)}")
        return {"success": False, "error": str(e)}


# Function to get the first active Outlook account for a user
async def get_active_outlook_account(jwt_token: str) -> Optional[dict]:
    """
    Get the first active Outlook account for the authenticated user.

    Returns:
        dict with account info or None if no active account
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                f"{OUTLOOK_API_BASE_URL}/email/accounts.php",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {jwt_token}"
                },
                params={"provider": "outlook"}
            )

            if response.status_code != 200:
                return None

            data = response.json()
            accounts = data.get("data", {}).get("accounts", []) or data.get("accounts", [])

            # Find first active Outlook account with valid token
            for acc in accounts:
                provider = acc.get("provider", "").lower()
                if provider == "outlook" and acc.get("is_active") and acc.get("token_status") == "valid":
                    return {
                        "id": acc.get("id"),
                        "email": acc.get("email_address") or acc.get("email"),
                        "display_name": acc.get("display_name")
                    }

            return None

    except Exception as e:
        logger.error(f"Error getting active Outlook account: {str(e)}")
        return None


# Endpoints

@router.get("/auth-url", response_model=OutlookAuthUrlResponse)
async def get_outlook_auth_url(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get the Outlook OAuth authorization URL.

    Proxies the request to the external Outlook API service.
    Forwards the user's JWT token for authentication.
    """
    logger.info(f"User {current_user.id} requesting Outlook auth URL")
    logger.info(f"Using auth URL: {OUTLOOK_AUTH_URL}")
    logger.info(f"Using base URL: {OUTLOOK_API_BASE_URL}")

    try:
        # First, try to validate token with auth service
        auth_user = await validate_token_with_auth_service(credentials)
        if auth_user:
            logger.info(f"Token validated with auth service: {auth_user}")
        else:
            logger.warning("Token validation with auth service failed, proceeding anyway")

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            # Try the Outlook connect endpoint
            url = f"{OUTLOOK_API_BASE_URL}/auth/connect.php"
            logger.info(f"Calling Outlook connect URL: {url}")

            response = await client.get(
                url,
                headers={
                    "Content-Type": "application/json",
                    **get_auth_header(credentials)
                }
            )

            logger.info(f"Outlook connect response status: {response.status_code}")
            if response.status_code != 200:
                logger.error(f"Outlook connect response body: {response.text[:500]}")

            response.raise_for_status()
            data = response.json()
            logger.info(f"Outlook connect response data: {data}")

            # Handle nested structure: {"success": true, "data": {"auth_url": "..."}}
            auth_url = data.get("data", {}).get("auth_url") or data.get("auth_url")

            return OutlookAuthUrlResponse(
                success=data.get("success", False),
                auth_url=auth_url,
                error=data.get("error")
            )

    except httpx.HTTPStatusError as e:
        logger.error(f"Outlook API auth URL error: {e.response.status_code} - {e.response.text[:500]}")
        return OutlookAuthUrlResponse(
            success=False,
            error=f"Outlook API error: {e.response.status_code}"
        )
    except Exception as e:
        logger.error(f"Failed to get Outlook auth URL: {str(e)}")
        return OutlookAuthUrlResponse(
            success=False,
            error=str(e)
        )


@router.get("/accounts", response_model=OutlookAccountsResponse)
async def get_outlook_accounts(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get connected Outlook accounts for the current user.

    Proxies the request to the external API service.
    Forwards the user's JWT token for authentication.
    """
    logger.info(f"User {current_user.id} fetching Outlook accounts")

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            url = f"{OUTLOOK_API_BASE_URL}/email/accounts.php"
            logger.info(f"Calling Outlook accounts URL: {url}")

            response = await client.get(
                url,
                headers={
                    "Content-Type": "application/json",
                    **get_auth_header(credentials)
                },
                params={"provider": "outlook"}
            )

            logger.info(f"Outlook accounts response status: {response.status_code}")
            if response.status_code != 200:
                logger.error(f"Outlook accounts response body: {response.text[:500]}")

            response.raise_for_status()
            data = response.json()
            logger.info(f"Outlook accounts response data: {data}")

            accounts = []
            # Handle nested data structure: {"success": true, "data": {"accounts": [...]}}
            accounts_data = data.get("data", {}).get("accounts", []) or data.get("accounts", [])
            if data.get("success") and accounts_data:
                for acc in accounts_data:
                    # Filter for Outlook accounts only
                    provider = acc.get("provider", "").lower()
                    if provider != "outlook":
                        continue
                    # Map API fields to our model
                    accounts.append(OutlookAccount(
                        id=acc.get("id", 0),
                        email=acc.get("email_address", "") or acc.get("email", ""),
                        display_name=acc.get("display_name"),
                        is_active=bool(acc.get("is_active", 0)),
                        token_status=acc.get("token_status"),
                        created_at=acc.get("created_at")
                    ))

            return OutlookAccountsResponse(
                success=data.get("success", False),
                accounts=accounts,
                error=data.get("error")
            )

    except httpx.HTTPStatusError as e:
        logger.error(f"Outlook API accounts error: {e.response.status_code} - {e.response.text[:500]}")
        return OutlookAccountsResponse(
            success=False,
            accounts=[],
            error=f"Outlook API error: {e.response.status_code}"
        )
    except Exception as e:
        logger.error(f"Failed to get Outlook accounts: {str(e)}")
        return OutlookAccountsResponse(
            success=False,
            accounts=[],
            error=str(e)
        )


@router.post("/disconnect/{account_id}", response_model=OutlookDisconnectResponse)
async def disconnect_outlook_account(
    account_id: int,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    current_user: User = Depends(get_current_active_user)
):
    """
    Disconnect an Outlook account.

    Proxies the request to the external API service.
    Forwards the user's JWT token for authentication.
    """
    logger.info(f"User {current_user.id} disconnecting Outlook account {account_id}")

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{OUTLOOK_API_BASE_URL}/auth/disconnect.php",
                json={"account_id": account_id},
                headers={
                    "Content-Type": "application/json",
                    **get_auth_header(credentials)
                }
            )
            response.raise_for_status()
            data = response.json()
            logger.info(f"Outlook disconnect response: {data}")

            return OutlookDisconnectResponse(
                success=data.get("success", False),
                message=data.get("message"),
                error=data.get("error")
            )

    except httpx.HTTPStatusError as e:
        logger.error(f"Outlook API disconnect error: {e.response.status_code}")
        return OutlookDisconnectResponse(
            success=False,
            error=f"Outlook API error: {e.response.status_code}"
        )
    except Exception as e:
        logger.error(f"Failed to disconnect Outlook account: {str(e)}")
        return OutlookDisconnectResponse(
            success=False,
            error=str(e)
        )


@router.post("/send", response_model=OutlookSendEmailResponse)
async def send_outlook_email(
    request: OutlookSendEmailRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    current_user: User = Depends(get_current_active_user)
):
    """
    Send an email via Outlook API.

    Proxies the request to the external API service.
    Requires a connected Outlook account.
    """
    logger.info(f"User {current_user.id} sending email via Outlook account {request.account_id}")
    logger.info(f"To: {request.to}, Subject: {request.subject[:50]}...")

    result = await send_email_via_outlook(
        jwt_token=credentials.credentials,
        account_id=request.account_id,
        to=request.to,
        subject=request.subject,
        body=request.body,
        to_name=request.to_name,
        cc=request.cc,
        bcc=request.bcc,
        track_opens=request.track_opens,
        track_clicks=request.track_clicks
    )

    return OutlookSendEmailResponse(
        success=result.get("success", False),
        message_id=result.get("message_id"),
        email_id=result.get("email_id"),
        error=result.get("error")
    )
