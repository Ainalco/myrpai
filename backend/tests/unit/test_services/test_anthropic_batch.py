"""Unit tests for anthropic_batch URL validation (SSRF guard)."""
import pytest

from anthropic_batch import (
    ALLOWED_RESULTS_HOSTS,
    AnthropicBatchError,
    _validate_results_url,
)


class TestValidateResultsUrl:
    def test_accepts_allowlisted_https_host(self):
        for host in ALLOWED_RESULTS_HOSTS:
            _validate_results_url(f"https://{host}/v1/messages/batches/abc/results")

    def test_rejects_non_allowlisted_host(self):
        with pytest.raises(AnthropicBatchError, match="unexpected URL"):
            _validate_results_url("https://evil.example/results")

    def test_rejects_http_scheme(self):
        with pytest.raises(AnthropicBatchError, match="unexpected URL"):
            _validate_results_url("http://api.anthropic.com/results")

    def test_rejects_cloud_metadata_endpoint(self):
        with pytest.raises(AnthropicBatchError):
            _validate_results_url("http://169.254.169.254/latest/meta-data/")

    def test_rejects_empty_and_garbage(self):
        for url in ["", "not-a-url", "file:///etc/passwd", "ftp://api.anthropic.com/x"]:
            with pytest.raises(AnthropicBatchError):
                _validate_results_url(url)
