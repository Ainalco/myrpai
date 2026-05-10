"""
Configuration utilities for the application.
Handles environment variables and URL generation.
"""
import os
from typing import Optional

# Optionally load environment variables from .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv not available, environment variables should be set externally
    pass


def get_webhook_base_url() -> str:
    """
    Generate the base URL for webhooks based on environment configuration.

    Returns:
        str: Base URL for webhook endpoints (e.g., "https://example.com/api" or "http://localhost:9000/api")
    """
    domain_name = os.getenv("DOMAIN_NAME", "localhost")
    use_ssl = os.getenv("USE_SSL", "false").lower() == "true"

    # Use SSL if enabled
    if use_ssl:
        return f"https://{domain_name}/api"
    else:
        return f"http://{domain_name}/api"


def get_webhook_url(webhook_id: int, token: str, integration_type: str = "fireflies") -> str:
    """
    Generate a complete webhook URL for a specific webhook.
    
    Args:
        webhook_id: The webhook ID
        token: The webhook token
        integration_type: The type of integration (default: "fireflies")
    
    Returns:
        str: Complete webhook URL
    """
    base_url = get_webhook_base_url()
    return f"{base_url}/webhooks/{integration_type}/{webhook_id}/{token}"


def get_domain_name() -> str:
    """Get the configured domain name."""
    return os.getenv("DOMAIN_NAME", "localhost")


def is_ssl_enabled() -> bool:
    """Check if SSL is enabled."""
    return os.getenv("USE_SSL", "false").lower() == "true"


def get_deployment_mode() -> str:
    """Get the deployment mode."""
    return os.getenv("DEPLOYMENT_MODE", "development")