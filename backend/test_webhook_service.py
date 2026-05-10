"""
Simple test to verify webhook service functions work correctly.
Run with: python test_webhook_service.py
"""

import json
from webhook_service import substitute_variables, build_auth_headers, validate_webhook_config


def test_substitute_variables():
    """Test variable substitution"""
    print("Testing substitute_variables...")

    template = "Hello {{name}}, your budget is {{budget}} and participants are {{participants}}"
    variables = {
        "name": "John",
        "budget": 50000,
        "participants": ["Alice", "Bob"]
    }

    result = substitute_variables(template, variables)
    print(f"  Template: {template}")
    print(f"  Variables: {variables}")
    print(f"  Result: {result}")
    assert "John" in result
    assert "50000" in result
    assert "[" in result  # List should be JSON-ified
    print("  ✓ Test passed\n")


def test_build_auth_headers():
    """Test authentication header building"""
    print("Testing build_auth_headers...")

    # Test Bearer
    headers = build_auth_headers("bearer", {"token": "my-secret-token"})
    print(f"  Bearer: {headers}")
    assert headers["Authorization"] == "Bearer my-secret-token"

    # Test Basic
    headers = build_auth_headers("basic", {"username": "user", "password": "pass"})
    print(f"  Basic: {headers}")
    assert "Authorization" in headers
    assert headers["Authorization"].startswith("Basic ")

    # Test API Key
    headers = build_auth_headers("api_key", {"header_name": "X-API-Key", "key": "secret"})
    print(f"  API Key: {headers}")
    assert headers["X-API-Key"] == "secret"

    # Test None
    headers = build_auth_headers("none", {})
    print(f"  None: {headers}")
    assert len(headers) == 0

    print("  ✓ All auth tests passed\n")


def test_validate_webhook_config():
    """Test webhook configuration validation"""
    print("Testing validate_webhook_config...")

    # Valid config
    config = {
        "webhook_url": "https://example.com/webhook",
        "http_method": "POST",
        "auth_type": "bearer",
        "auth_config": {"token": "test-token"}
    }
    is_valid, error = validate_webhook_config(config)
    print(f"  Valid config: is_valid={is_valid}, error={error}")
    assert is_valid is True

    # Missing URL
    config = {
        "http_method": "POST",
        "auth_type": "none"
    }
    is_valid, error = validate_webhook_config(config)
    print(f"  Missing URL: is_valid={is_valid}, error={error}")
    assert is_valid is False
    assert "URL" in error

    # Invalid method
    config = {
        "webhook_url": "https://example.com/webhook",
        "http_method": "INVALID",
        "auth_type": "none"
    }
    is_valid, error = validate_webhook_config(config)
    print(f"  Invalid method: is_valid={is_valid}, error={error}")
    assert is_valid is False

    # Bearer without token
    config = {
        "webhook_url": "https://example.com/webhook",
        "http_method": "POST",
        "auth_type": "bearer",
        "auth_config": {}
    }
    is_valid, error = validate_webhook_config(config)
    print(f"  Bearer without token: is_valid={is_valid}, error={error}")
    assert is_valid is False
    assert "token" in error.lower()

    print("  ✓ All validation tests passed\n")


if __name__ == "__main__":
    print("=" * 60)
    print("Webhook Service Unit Tests")
    print("=" * 60 + "\n")

    try:
        test_substitute_variables()
        test_build_auth_headers()
        test_validate_webhook_config()

        print("=" * 60)
        print("✓ ALL TESTS PASSED")
        print("=" * 60)
    except AssertionError as e:
        print("\n" + "=" * 60)
        print("✗ TEST FAILED")
        print("=" * 60)
        raise
    except Exception as e:
        print("\n" + "=" * 60)
        print(f"✗ ERROR: {e}")
        print("=" * 60)
        raise
