"""
Unit tests for config.py
Tests configuration utility functions with mocked environment variables
"""
import pytest
from unittest.mock import patch

from config import (
    get_webhook_base_url,
    get_webhook_url,
    get_domain_name,
    is_ssl_enabled,
    get_deployment_mode
)


class TestGetWebhookBaseUrl:
    """Test get_webhook_base_url function"""

    @patch.dict("os.environ", {"DOMAIN_NAME": "localhost:3000", "USE_SSL": "false"})
    def test_development_with_port(self):
        """Test webhook base URL in development with port"""
        # Act
        url = get_webhook_base_url()

        # Assert
        assert url == "http://localhost:3000/api"

    @patch.dict("os.environ", {"DOMAIN_NAME": "localhost:8080", "USE_SSL": "false"})
    def test_custom_port(self):
        """Test webhook base URL with custom port"""
        # Act
        url = get_webhook_base_url()

        # Assert
        assert url == "http://localhost:8080/api"

    @patch.dict("os.environ", {"DOMAIN_NAME": "example.com", "USE_SSL": "true"})
    def test_production_with_ssl(self):
        """Test webhook base URL in production with SSL"""
        # Act
        url = get_webhook_base_url()

        # Assert
        assert url == "https://example.com/api"

    @patch.dict("os.environ", {"DOMAIN_NAME": "example.com", "USE_SSL": "false"})
    def test_production_without_ssl(self):
        """Test webhook base URL in production without SSL"""
        # Act
        url = get_webhook_base_url()

        # Assert
        assert url == "http://example.com/api"

    @patch.dict("os.environ", {"DOMAIN_NAME": "example.com:8080", "USE_SSL": "false"})
    def test_production_custom_port(self):
        """Test webhook base URL with custom port"""
        # Act
        url = get_webhook_base_url()

        # Assert
        assert url == "http://example.com:8080/api"

    @patch.dict("os.environ", {}, clear=True)
    def test_default_values(self):
        """Test webhook base URL with all default values"""
        # Act
        url = get_webhook_base_url()

        # Assert
        # Should default to localhost without SSL
        assert url == "http://localhost/api"

    @patch.dict("os.environ", {"DOMAIN_NAME": "staging.example.com", "USE_SSL": "true"})
    def test_subdomain_with_ssl(self):
        """Test webhook base URL with subdomain and SSL"""
        # Act
        url = get_webhook_base_url()

        # Assert
        assert url == "https://staging.example.com/api"


class TestGetWebhookUrl:
    """Test get_webhook_url function"""

    @patch.dict("os.environ", {"DOMAIN_NAME": "localhost:3000", "USE_SSL": "false"})
    def test_webhook_url_default_integration(self):
        """Test complete webhook URL generation with default integration type"""
        # Act
        url = get_webhook_url(webhook_id=123, token="abc_token_xyz")

        # Assert
        assert url == "http://localhost:3000/api/webhooks/fireflies/123/abc_token_xyz"

    @patch.dict("os.environ", {"DOMAIN_NAME": "localhost:3000", "USE_SSL": "false"})
    def test_webhook_url_custom_integration(self):
        """Test webhook URL generation with custom integration type"""
        # Act
        url = get_webhook_url(webhook_id=456, token="token_123", integration_type="pipedrive")

        # Assert
        assert url == "http://localhost:3000/api/webhooks/pipedrive/456/token_123"

    @patch.dict("os.environ", {"DOMAIN_NAME": "example.com", "USE_SSL": "true"})
    def test_webhook_url_production_https(self):
        """Test webhook URL generation in production with HTTPS"""
        # Act
        url = get_webhook_url(webhook_id=789, token="secure_token")

        # Assert
        assert url == "https://example.com/api/webhooks/fireflies/789/secure_token"

    @patch.dict("os.environ", {"DOMAIN_NAME": "localhost:3000", "USE_SSL": "false"})
    def test_webhook_url_with_special_characters_in_token(self):
        """Test webhook URL with special characters in token"""
        # Act
        url = get_webhook_url(webhook_id=1, token="abc-123_xyz.token")

        # Assert
        assert url == "http://localhost:3000/api/webhooks/fireflies/1/abc-123_xyz.token"


class TestGetDomainName:
    """Test get_domain_name function"""

    @patch.dict("os.environ", {"DOMAIN_NAME": "example.com"})
    def test_get_domain_name_configured(self):
        """Test getting configured domain name"""
        # Act
        domain = get_domain_name()

        # Assert
        assert domain == "example.com"

    @patch.dict("os.environ", {}, clear=True)
    def test_get_domain_name_default(self):
        """Test getting default domain name"""
        # Act
        domain = get_domain_name()

        # Assert
        assert domain == "localhost"

    @patch.dict("os.environ", {"DOMAIN_NAME": "staging.myapp.io"})
    def test_get_domain_name_subdomain(self):
        """Test getting subdomain"""
        # Act
        domain = get_domain_name()

        # Assert
        assert domain == "staging.myapp.io"


class TestIsSslEnabled:
    """Test is_ssl_enabled function"""

    @patch.dict("os.environ", {"USE_SSL": "true"})
    def test_ssl_enabled_lowercase_true(self):
        """Test SSL enabled with lowercase 'true'"""
        # Act
        result = is_ssl_enabled()

        # Assert
        assert result is True

    @patch.dict("os.environ", {"USE_SSL": "TRUE"})
    def test_ssl_enabled_uppercase_true(self):
        """Test SSL enabled with uppercase 'TRUE'"""
        # Act
        result = is_ssl_enabled()

        # Assert
        assert result is True

    @patch.dict("os.environ", {"USE_SSL": "True"})
    def test_ssl_enabled_mixed_case_true(self):
        """Test SSL enabled with mixed case 'True'"""
        # Act
        result = is_ssl_enabled()

        # Assert
        assert result is True

    @patch.dict("os.environ", {"USE_SSL": "false"})
    def test_ssl_disabled_false(self):
        """Test SSL disabled with 'false'"""
        # Act
        result = is_ssl_enabled()

        # Assert
        assert result is False

    @patch.dict("os.environ", {}, clear=True)
    def test_ssl_disabled_default(self):
        """Test SSL disabled by default"""
        # Act
        result = is_ssl_enabled()

        # Assert
        assert result is False

    @patch.dict("os.environ", {"USE_SSL": "1"})
    def test_ssl_disabled_invalid_value(self):
        """Test SSL disabled with invalid value"""
        # Act
        result = is_ssl_enabled()

        # Assert
        assert result is False  # Only "true" (case-insensitive) should enable SSL


class TestGetDeploymentMode:
    """Test get_deployment_mode function"""

    @patch.dict("os.environ", {"DEPLOYMENT_MODE": "development"})
    def test_deployment_mode_development(self):
        """Test getting development deployment mode"""
        # Act
        mode = get_deployment_mode()

        # Assert
        assert mode == "development"

    @patch.dict("os.environ", {"DEPLOYMENT_MODE": "production"})
    def test_deployment_mode_production(self):
        """Test getting production deployment mode"""
        # Act
        mode = get_deployment_mode()

        # Assert
        assert mode == "production"

    @patch.dict("os.environ", {"DEPLOYMENT_MODE": "staging"})
    def test_deployment_mode_staging(self):
        """Test getting staging deployment mode"""
        # Act
        mode = get_deployment_mode()

        # Assert
        assert mode == "staging"

    @patch.dict("os.environ", {}, clear=True)
    def test_deployment_mode_default(self):
        """Test default deployment mode"""
        # Act
        mode = get_deployment_mode()

        # Assert
        assert mode == "development"

    @patch.dict("os.environ", {"DEPLOYMENT_MODE": "testing"})
    def test_deployment_mode_custom(self):
        """Test custom deployment mode value"""
        # Act
        mode = get_deployment_mode()

        # Assert
        assert mode == "testing"


class TestConfigIntegration:
    """Integration tests for config functions working together"""

    @patch.dict("os.environ", {
        "DEPLOYMENT_MODE": "production",
        "DOMAIN_NAME": "app.example.com",
        "USE_SSL": "true"
    })
    def test_production_config_all_functions(self):
        """Test all config functions in production environment"""
        # Act
        domain = get_domain_name()
        ssl_enabled = is_ssl_enabled()
        mode = get_deployment_mode()
        base_url = get_webhook_base_url()
        webhook_url = get_webhook_url(1, "token123")

        # Assert
        assert domain == "app.example.com"
        assert ssl_enabled is True
        assert mode == "production"
        assert base_url == "https://app.example.com/api"
        assert webhook_url == "https://app.example.com/api/webhooks/fireflies/1/token123"

    @patch.dict("os.environ", {
        "DEPLOYMENT_MODE": "development",
        "DOMAIN_NAME": "localhost:3000",
        "USE_SSL": "false"
    }, clear=True)
    def test_development_config_all_functions(self):
        """Test all config functions in development environment"""
        # Act
        domain = get_domain_name()
        ssl_enabled = is_ssl_enabled()
        mode = get_deployment_mode()
        base_url = get_webhook_base_url()
        webhook_url = get_webhook_url(2, "devtoken")

        # Assert
        assert domain == "localhost:3000"
        assert ssl_enabled is False
        assert mode == "development"
        assert base_url == "http://localhost:3000/api"
        assert webhook_url == "http://localhost:3000/api/webhooks/fireflies/2/devtoken"
