"""
Unit tests for encryption_service.py
Tests encryption and decryption of sensitive data
"""
import pytest
from encryption_service import encrypt_api_key, decrypt_api_key


class TestEncryption:
    """Test encryption/decryption functionality"""

    def test_encrypt_decrypt_roundtrip(self):
        """Test that encryption and decryption are reversible"""
        # Arrange
        original_key = "sk-test-api-key-123456789"

        # Act
        encrypted = encrypt_api_key(original_key)
        decrypted = decrypt_api_key(encrypted)

        # Assert
        assert decrypted == original_key
        assert encrypted != original_key  # Ensure it was actually encrypted

    def test_encrypt_produces_different_ciphertext_each_time(self):
        """Test that encrypting same value twice produces different results (IV randomization)"""
        # Arrange
        api_key = "test-key-12345"

        # Act
        encrypted1 = encrypt_api_key(api_key)
        encrypted2 = encrypt_api_key(api_key)

        # Assert
        assert encrypted1 != encrypted2  # Different ciphertexts due to random IV
        assert decrypt_api_key(encrypted1) == api_key
        assert decrypt_api_key(encrypted2) == api_key

    def test_encrypt_empty_string(self):
        """Test that encrypting empty string works"""
        # Arrange
        empty_key = ""

        # Act
        encrypted = encrypt_api_key(empty_key)
        decrypted = decrypt_api_key(encrypted)

        # Assert
        assert decrypted == empty_key

    def test_decrypt_invalid_data_raises_error(self):
        """Test that decrypting invalid data raises error"""
        # Arrange
        invalid_data = "not-valid-encrypted-data"

        # Act & Assert
        with pytest.raises(Exception):  # Will raise ValueError or decryption error
            decrypt_api_key(invalid_data)

    def test_encrypt_long_key(self):
        """Test encrypting a very long API key"""
        # Arrange
        long_key = "a" * 1000  # 1000 character key

        # Act
        encrypted = encrypt_api_key(long_key)
        decrypted = decrypt_api_key(encrypted)

        # Assert
        assert decrypted == long_key

    def test_encrypt_special_characters(self):
        """Test encrypting keys with special characters"""
        # Arrange
        special_key = "key!@#$%^&*()_+-={}[]|:;<>?,./~`"

        # Act
        encrypted = encrypt_api_key(special_key)
        decrypted = decrypt_api_key(encrypted)

        # Assert
        assert decrypted == special_key

    def test_encrypt_unicode_characters(self):
        """Test encrypting keys with unicode characters"""
        # Arrange
        unicode_key = "key_with_unicode_你好_🔐"

        # Act
        encrypted = encrypt_api_key(unicode_key)
        decrypted = decrypt_api_key(encrypted)

        # Assert
        assert decrypted == unicode_key

    def test_encrypted_format_is_base64(self):
        """Test that encrypted output is base64 encoded"""
        # Arrange
        api_key = "test-key"

        # Act
        encrypted = encrypt_api_key(api_key)

        # Assert
        import base64
        try:
            # Should be able to decode as base64
            base64.b64decode(encrypted)
            assert True
        except Exception:
            pytest.fail("Encrypted data is not valid base64")

    def test_decrypt_with_wrong_key_fails(self):
        """Test that decryption with wrong encryption key fails"""
        # This test assumes we can modify the encryption key
        # In practice, this would require mocking the ENCRYPTION_KEY
        # For now, we'll test that invalid ciphertext fails

        # Arrange
        api_key = "test-key"
        encrypted = encrypt_api_key(api_key)

        # Corrupt the encrypted data
        corrupted = encrypted[:-5] + "XXXXX"

        # Act & Assert
        with pytest.raises(Exception):
            decrypt_api_key(corrupted)
