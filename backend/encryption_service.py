"""
Encryption service for securely storing and retrieving API keys
Uses Fernet (symmetric encryption) from the cryptography library
"""
import os
import logging
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Get encryption key from environment variable
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

if not ENCRYPTION_KEY:
    logger.warning(
        "ENCRYPTION_KEY not set in environment. "
        "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
    )
    raise ValueError("ENCRYPTION_KEY environment variable is required")


def _get_fernet() -> Fernet:
    """
    Get Fernet cipher instance using the encryption key from environment

    Returns:
        Fernet: Configured Fernet cipher instance
    """
    try:
        # Ensure key is in bytes format
        key_bytes = ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY
        return Fernet(key_bytes)
    except Exception as e:
        logger.error(f"Failed to initialize Fernet cipher: {e}")
        raise ValueError(f"Invalid ENCRYPTION_KEY format: {e}")


def encrypt_api_key(plain_key: str) -> str:
    """
    Encrypt an API key for secure storage

    Args:
        plain_key: The plain text API key to encrypt

    Returns:
        str: Base64-encoded encrypted key

    Raises:
        ValueError: If encryption fails
    """
    if not plain_key:
        raise ValueError("Cannot encrypt empty API key")

    try:
        fernet = _get_fernet()
        # Encrypt the key and return as string
        encrypted_bytes = fernet.encrypt(plain_key.encode())
        return encrypted_bytes.decode()
    except Exception as e:
        logger.error(f"Failed to encrypt API key: {e}")
        raise ValueError(f"Encryption failed: {e}")


def decrypt_api_key(encrypted_key: str) -> str:
    """
    Decrypt an API key for use

    Args:
        encrypted_key: The base64-encoded encrypted key from database

    Returns:
        str: Decrypted plain text API key

    Raises:
        ValueError: If decryption fails or key is invalid
    """
    if not encrypted_key:
        raise ValueError("Cannot decrypt empty encrypted key")

    try:
        fernet = _get_fernet()
        # Decrypt the key and return as string
        decrypted_bytes = fernet.decrypt(encrypted_key.encode())
        return decrypted_bytes.decode()
    except InvalidToken:
        logger.error("Invalid token - decryption failed. Key may be corrupted or encrypted with different key.")
        raise ValueError("Failed to decrypt API key - invalid or corrupted data")
    except Exception as e:
        logger.error(f"Failed to decrypt API key: {e}")
        raise ValueError(f"Decryption failed: {e}")


def verify_encryption_key() -> bool:
    """
    Verify that the encryption key is valid by performing a test encryption/decryption

    Returns:
        bool: True if encryption key is valid, False otherwise
    """
    try:
        test_data = "test_api_key_12345"
        encrypted = encrypt_api_key(test_data)
        decrypted = decrypt_api_key(encrypted)
        return decrypted == test_data
    except Exception as e:
        logger.error(f"Encryption key verification failed: {e}")
        return False
