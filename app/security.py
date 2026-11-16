"""
Módulo de Seguridad y Cumplimiento Normativo MinTIC (2021) - MSPI
Implementa controles criptográficos, gestión de identidades (IAM/RBAC),
pseudonimización de datos personales (Ley 1581 de 2012) y protección perimetral WAF.
"""

import base64
import hashlib
import hmac
import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import jwt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


# Claves maestras simuladas (en producción gestionadas en AWS KMS / Secrets Manager)
MASTER_KMS_KEY_SEED = os.environ.get(
    "CLOUDMED_KMS_MASTER_KEY",
    "MinTIC-2021-MSPI-AWS-KMS-MasterKey-CloudMedVault-2026-SecretKey!",
)
JWT_SECRET_KEY = os.environ.get(
    "CLOUDMED_JWT_SECRET",
    "CloudMedVault-JWT-HS256-SigningKey-MinTIC-Compliance-2026!",
)
PII_HMAC_SALT = os.environ.get(
    "CLOUDMED_PII_SALT",
    "Ley1581-2012-HabeasData-Pseudonymization-Salt-2026",
)
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_SECONDS = 3600


def _derive_aes256_key(context: str = "default-dek") -> bytes:
    """Deriva una clave de 256 bits (32 bytes) estilo KMS Envelope Encryption."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=f"aws-kms-context:{context}".encode("utf-8"),
        iterations=50_000,
    )
    return kdf.derive(MASTER_KMS_KEY_SEED.encode("utf-8"))


class CryptoVault:
    """
    Servicio de cifrado autenticado AES-256-GCM para datos en reposo
    (historias clínicas y objetos S3) cumpliendo lineamientos MinTIC (2021).
    """

    def __init__(self, key_context: str = "clinical-records-v1"):
        self.key_context = key_context
        self._key = _derive_aes256_key(key_context)
        self._aesgcm = AESGCM(self._key)

    def encrypt_bytes(self, plaintext: bytes, associated_data: Optional[bytes] = None) -> Dict[str, str]:
        """Cifra bytes con AES-256-GCM y retorna nonce + ciphertext en Base64 junto al hash SHA-256."""
        nonce = os.urandom(12)  # 96-bit IV recomendado por NIST SP 800-38D
        ciphertext = self._aesgcm.encrypt(nonce, plaintext, associated_data)
        sha256_plain = hashlib.sha256(plaintext).hexdigest()
        return {
            "algorithm": "AES-256-GCM",
            "key_context": self.key_context,
            "nonce_b64": base64.b64encode(nonce).decode("ascii"),
            "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
            "sha256_integrity": sha256_plain,
        }

    def decrypt_bytes(self, envelope: Dict[str, str], associated_data: Optional[bytes] = None) -> bytes:
        """Descifra un sobre AES-256-GCM y verifica la integridad criptográfica SHA-256."""
        nonce = base64.b64decode(envelope["nonce_b64"])
        ciphertext = base64.b64decode(envelope["ciphertext_b64"])
        plaintext = self._aesgcm.decrypt(nonce, ciphertext, associated_data)
        computed_hash = hashlib.sha256(plaintext).hexdigest()
        if envelope.get("sha256_integrity") and computed_hash != envelope["sha256_integrity"]:
            raise ValueError("Fallo de verificación de integridad SHA-256 en el objeto descifrado.")
        return plaintext

    def encrypt_json(self, payload: Dict[str, Any], aad_str: str = "") -> str:
        """Serializa un diccionario JSON y lo cifra con AES-256-GCM."""
