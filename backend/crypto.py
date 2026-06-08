import base64
import hashlib
import hmac
import json
import os
from functools import lru_cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes


ENCRYPTION_PREFIX = "enc:v1:"


class CryptoConfigError(RuntimeError):
    pass


def is_encrypted_value(value):
    return isinstance(value, str) and value.startswith(ENCRYPTION_PREFIX)


def normalize_index_value(value):
    return " ".join(str(value or "").strip().lower().split())


class FieldCrypto:
    def __init__(self, data_key, blind_index_key=None, key_id="local"):
        if len(data_key) != 32:
            raise CryptoConfigError("Encryption data key must decode to exactly 32 bytes")
        self.data_key = data_key
        self.blind_index_key = blind_index_key or self._derive_key(data_key, b"transition-portal:blind-index:v1")
        self.key_id = key_id
        self.aesgcm = AESGCM(data_key)

    def encrypt(self, value):
        if value is None or value == "" or is_encrypted_value(value):
            return value
        payload = json.dumps({"v": value}, default=str, separators=(",", ":")).encode("utf-8")
        nonce = os.urandom(12)
        ciphertext = self.aesgcm.encrypt(nonce, payload, None)
        return f"{ENCRYPTION_PREFIX}{base64.urlsafe_b64encode(nonce + ciphertext).decode('ascii')}"

    def decrypt(self, value):
        if not is_encrypted_value(value):
            return value
        raw = base64.urlsafe_b64decode(value[len(ENCRYPTION_PREFIX):].encode("ascii"))
        nonce, ciphertext = raw[:12], raw[12:]
        payload = self.aesgcm.decrypt(nonce, ciphertext, None)
        decoded = json.loads(payload.decode("utf-8"))
        return decoded.get("v")

    def blind_index(self, value):
        normalized = normalize_index_value(value)
        if not normalized:
            return None
        digest = hmac.new(self.blind_index_key, normalized.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"bidx:v1:{digest}"

    @staticmethod
    def _derive_key(data_key, info):
        return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info).derive(data_key)


def _b64decode_key(value, name):
    try:
        return base64.b64decode(value)
    except Exception as exc:
        raise CryptoConfigError(f"{name} must be a valid base64 encoded 32-byte key") from exc


def _decrypt_kms_data_key(ciphertext_b64, region):
    try:
        import boto3
    except ImportError as exc:
        raise CryptoConfigError("boto3 is required when ENCRYPTION_DATA_KEY_KMS_CIPHERTEXT_B64 is configured") from exc
    client = boto3.client("kms", region_name=region or None)
    response = client.decrypt(CiphertextBlob=base64.b64decode(ciphertext_b64))
    plaintext = response.get("Plaintext")
    if not plaintext:
        raise CryptoConfigError("AWS KMS did not return a plaintext data key")
    return plaintext


@lru_cache(maxsize=1)
def get_crypto():
    try:
        from config import get_config
        get_config()
    except Exception:
        pass

    kms_ciphertext = os.getenv("ENCRYPTION_DATA_KEY_KMS_CIPHERTEXT_B64", "").strip()
    raw_key = os.getenv("ENCRYPTION_DATA_KEY_B64", "").strip()
    key_id = os.getenv("ENCRYPTION_KEY_ID", "").strip() or "local"

    if kms_ciphertext:
        data_key = _decrypt_kms_data_key(kms_ciphertext, os.getenv("AWS_REGION", "").strip())
        key_id = os.getenv("AWS_KMS_KEY_ID", "").strip() or key_id or "aws-kms"
    elif raw_key:
        data_key = _b64decode_key(raw_key, "ENCRYPTION_DATA_KEY_B64")
    else:
        raise CryptoConfigError(
            "Missing encryption key. Configure ENCRYPTION_DATA_KEY_B64 locally or "
            "ENCRYPTION_DATA_KEY_KMS_CIPHERTEXT_B64 with AWS KMS in hosted environments."
        )

    blind_key_b64 = os.getenv("BLIND_INDEX_KEY_B64", "").strip()
    blind_key = _b64decode_key(blind_key_b64, "BLIND_INDEX_KEY_B64") if blind_key_b64 else None
    return FieldCrypto(data_key=data_key, blind_index_key=blind_key, key_id=key_id)


def encrypt_value(value):
    return get_crypto().encrypt(value)


def decrypt_value(value):
    return get_crypto().decrypt(value)


def blind_index(value):
    return get_crypto().blind_index(value)
