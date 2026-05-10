"""
Webhook Service for sending HTTP requests to external endpoints.
Supports multiple authentication methods and variable substitution.
"""

import logging
import re
import json
import base64
from typing import Dict, Any, Optional, Tuple
import httpx
from httpx import Response

logger = logging.getLogger(__name__)

# Timeout for webhook requests (in seconds)
WEBHOOK_TIMEOUT = 30.0


def substitute_variables(template: str, variables: Dict[str, Any]) -> str:
    """
    Replace {{variable_name}} placeholders in a template string with actual values.

    Args:
        template: String containing {{variable}} placeholders
        variables: Dictionary of variable names to values

    Returns:
        String with all variables substituted
    """
    if not template:
        return template

    def replace_match(match):
        var_name = match.group(1).strip()
        value = variables.get(var_name, f"{{{{{var_name}}}}}")  # Keep placeholder if not found

        # Convert non-string values to JSON representation
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        elif value is None:
            return "null"
        elif isinstance(value, bool):
            return "true" if value else "false"
        else:
            return str(value)

    # Replace all {{variable}} patterns
    result = re.sub(r'\{\{([^}]+)\}\}', replace_match, template)
    return result


def build_auth_headers(auth_type: str, auth_config: Dict[str, Any]) -> Dict[str, str]:
    """
    Build authentication headers based on auth type and config.

    Args:
        auth_type: One of 'none', 'bearer', 'basic', 'api_key'
        auth_config: Configuration dict with auth credentials

    Returns:
        Dictionary of headers to add for authentication
    """
    headers = {}

    if auth_type == "bearer":
        token = auth_config.get("token", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"

    elif auth_type == "basic":
        username = auth_config.get("username", "")
        password = auth_config.get("password", "")
        if username or password:
            credentials = f"{username}:{password}"
            encoded = base64.b64encode(credentials.encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"

    elif auth_type == "api_key":
        header_name = auth_config.get("header_name", "X-API-Key")
        api_key = auth_config.get("key", "")
        if api_key:
            headers[header_name] = api_key

    # auth_type == "none" returns empty dict

    return headers


def send_webhook(
    url: str,
    method: str,
    headers: Optional[Dict[str, str]] = None,
    body_template: Optional[str] = None,
    variables: Optional[Dict[str, Any]] = None,
    auth_type: str = "none",
    auth_config: Optional[Dict[str, Any]] = None,
    timeout: float = WEBHOOK_TIMEOUT,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Send an HTTP request to a webhook endpoint.

    Args:
        url: Target URL (can contain {{variables}})
        method: HTTP method (GET, POST, PUT, PATCH, DELETE)
        headers: Custom headers dict
        body_template: Request body template (JSON string with {{variables}})
        variables: Dict of variables for substitution
        auth_type: Authentication type ('none', 'bearer', 'basic', 'api_key')
        auth_config: Authentication configuration
        timeout: Request timeout in seconds
        dry_run: If True, only preview the request without sending

    Returns:
        Dict with request/response details and success status
    """
    if variables is None:
        variables = {}

    if headers is None:
        headers = {}

    if auth_config is None:
        auth_config = {}

    try:
        # Substitute variables in URL
        final_url = substitute_variables(url, variables)

        # Build authentication headers
        auth_headers = build_auth_headers(auth_type, auth_config)

        # Substitute variables in custom headers
        final_headers = {}
        for key, value in headers.items():
            final_headers[key] = substitute_variables(value, variables)

        # Merge auth headers with custom headers (custom headers take precedence)
        final_headers = {**auth_headers, **final_headers}

        # Substitute variables in body template
        final_body = None
        if body_template:
            body_str = substitute_variables(body_template, variables)

            # Try to parse as JSON to validate
            try:
                final_body = json.loads(body_str)
            except json.JSONDecodeError:
                # If not valid JSON, send as string
                final_body = body_str

        # Prepare request preview
        request_preview = {
            "url": final_url,
            "method": method.upper(),
            "headers": final_headers,
            "body": final_body
        }

        # If dry run, return preview without sending
        if dry_run:
            logger.info(f"Webhook dry-run preview: {method.upper()} {final_url}")
            return {
                "success": True,
                "dry_run": True,
                "request": request_preview,
                "message": "Dry-run mode: Request preview generated successfully"
            }

        # Send actual HTTP request
        logger.info(f"Sending webhook: {method.upper()} {final_url}")

        with httpx.Client(timeout=timeout) as client:
            response = client.request(
                method=method.upper(),
                url=final_url,
                headers=final_headers,
                json=final_body if isinstance(final_body, dict) else None,
                content=final_body if isinstance(final_body, str) else None
            )

        # Parse response
        response_data = {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": None
        }

        # Try to parse response as JSON
        try:
            response_data["body"] = response.json()
        except Exception:
            response_data["body"] = response.text

        # Check if request was successful
        success = 200 <= response.status_code < 300

        if success:
            logger.info(f"Webhook sent successfully: {response.status_code}")
        else:
            logger.warning(f"Webhook returned non-2xx status: {response.status_code}")

        return {
            "success": success,
            "dry_run": False,
            "request": request_preview,
            "response": response_data,
            "message": f"Request completed with status {response.status_code}"
        }

    except httpx.TimeoutException as e:
        logger.error(f"Webhook timeout: {str(e)}")
        return {
            "success": False,
            "dry_run": dry_run,
            "error": "Request timeout",
            "message": f"Request timed out after {timeout} seconds"
        }

    except httpx.RequestError as e:
        logger.error(f"Webhook request error: {str(e)}")
        return {
            "success": False,
            "dry_run": dry_run,
            "error": "Request failed",
            "message": str(e)
        }

    except Exception as e:
        logger.error(f"Webhook error: {str(e)}", exc_info=True)
        return {
            "success": False,
            "dry_run": dry_run,
            "error": "Internal error",
            "message": str(e)
        }


def validate_webhook_config(config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Validate webhook configuration.

    Args:
        config: Webhook configuration dict

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check required fields
    if not config.get("webhook_url"):
        return False, "Webhook URL is required"

    if not config.get("http_method"):
        return False, "HTTP method is required"

    # Validate HTTP method
    valid_methods = ["GET", "POST", "PUT", "PATCH", "DELETE"]
    if config.get("http_method", "").upper() not in valid_methods:
        return False, f"Invalid HTTP method. Must be one of: {', '.join(valid_methods)}"

    # Validate auth type
    valid_auth_types = ["none", "bearer", "basic", "api_key"]
    auth_type = config.get("auth_type", "none")
    if auth_type not in valid_auth_types:
        return False, f"Invalid auth type. Must be one of: {', '.join(valid_auth_types)}"

    # Validate auth config based on type
    auth_config = config.get("auth_config", {})

    if auth_type == "bearer" and not auth_config.get("token"):
        return False, "Bearer token is required for Bearer authentication"

    if auth_type == "basic":
        if not auth_config.get("username") and not auth_config.get("password"):
            return False, "Username or password is required for Basic authentication"

    if auth_type == "api_key":
        if not auth_config.get("key"):
            return False, "API key is required for API Key authentication"
        if not auth_config.get("header_name"):
            return False, "Header name is required for API Key authentication"

    # Validate body template is valid JSON if provided
    if config.get("body_template"):
        try:
            # Try to parse with placeholder variables
            template = config["body_template"]
            # Just check if it looks like valid JSON structure
            if template.strip() and not template.strip().startswith(('{', '[')):
                return False, "Body template must be valid JSON"
        except Exception:
            pass  # Allow templates with variables

    return True, None
