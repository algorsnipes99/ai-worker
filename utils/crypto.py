import base64
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from dotenv import load_dotenv
load_dotenv()

NONCE_SIZE = 12


def _get_key() -> bytes:
    key_b64 = os.getenv('ENCRYPTION_KEY')
    if not key_b64:
        raise ValueError("ENCRYPTION_KEY environment variable is not set")
    return base64.b64decode(key_b64)


def encrypt(plaintext: str) -> str:
    """Encrypt a string with AES-256-GCM, returning base64(nonce || ciphertext || tag)."""
    aesgcm = AESGCM(_get_key())
    nonce = os.urandom(NONCE_SIZE)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)
    return base64.b64encode(nonce + ciphertext).decode('utf-8')


def decrypt(token: str) -> str:
    """Decrypt a base64(nonce || ciphertext || tag) string produced by encrypt()."""
    aesgcm = AESGCM(_get_key())
    raw = base64.b64decode(token)
    nonce, ciphertext = raw[:NONCE_SIZE], raw[NONCE_SIZE:]
    return aesgcm.decrypt(nonce, ciphertext, None).decode('utf-8')
