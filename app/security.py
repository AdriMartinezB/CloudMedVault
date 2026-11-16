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
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        aad = aad_str.encode("utf-8") if aad_str else None
        envelope = self.encrypt_bytes(raw, aad)
        return json.dumps(envelope)

    def decrypt_json(self, encrypted_str: str, aad_str: str = "") -> Dict[str, Any]:
        """Descifra un JSON previamente protegido con AES-256-GCM."""
        envelope = json.loads(encrypted_str)
        aad = aad_str.encode("utf-8") if aad_str else None
        raw = self.decrypt_bytes(envelope, aad)
        return json.loads(raw.decode("utf-8"))


def pseudonymize_pii(national_id: str) -> str:
    """
    Pseudonimiza el documento de identidad del paciente usando HMAC-SHA256
    para cumplir con la Ley 1581 de 2012 (Habeas Data) y MinTIC MSPI.
    """
    normalized = national_id.strip().upper().encode("utf-8")
    digest = hmac.new(PII_HMAC_SALT.encode("utf-8"), normalized, hashlib.sha256).hexdigest()
    return f"PID-{digest[:24]}"


def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    """Genera hash seguro de contraseña con PBKDF2-HMAC-SHA256."""
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return f"pbkdf2_sha256$100000${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verifica una contraseña contra su hash PBKDF2-HMAC-SHA256 en tiempo constante."""
    try:
        _, iterations_str, salt_b64, dk_b64 = stored_hash.split("$")
        salt = base64.b64decode(salt_b64)
        expected_dk = base64.b64decode(dk_b64)
        computed_dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations_str)
        )
        return hmac.compare_digest(expected_dk, computed_dk)
    except Exception:
        return False


# Usuarios preconfigurados con control de acceso basado en roles (RBAC)
USERS_DB: Dict[str, Dict[str, Any]] = {
    "dr.ramirez": {
        "password_hash": hash_password("MedCloud#2026!"),
        "role": "medico",
        "full_name": "Dr. Carlos Ramírez (Cardiología)",
        "permissions": ["records:read", "records:write", "documents:read", "documents:write", "telemetry:read"],
    },
    "admin.seguridad": {
        "password_hash": hash_password("AdminMinTIC#2026!"),
        "role": "admin",
        "full_name": "Ing. Laura Gómez (Oficial de Seguridad MSPI)",
        "permissions": [
            "records:read",
            "records:write",
            "documents:read",
            "documents:write",
            "telemetry:read",
            "telemetry:write",
            "audit:verify",
        ],
    },
    "gateway.iot": {
        "password_hash": hash_password("IoTGateway#2026!"),
        "role": "iot_sensor",
        "full_name": "Concentrador UCI Telemetría Biomédica",
        "permissions": ["telemetry:write"],
    },
}


def authenticate_and_issue_jwt(username: str, password: str) -> Optional[Dict[str, Any]]:
    """Autentica credenciales de usuario y emite un token JWT firmado (HS256)."""
    user = USERS_DB.get(username)
    if not user or not verify_password(password, user["password_hash"]):
        return None
    now = int(time.time())
    payload = {
        "sub": username,
        "role": user["role"],
        "name": user["full_name"],
        "permissions": user["permissions"],
        "iat": now,
        "exp": now + JWT_EXPIRATION_SECONDS,
        "iss": "CloudMedVault-IAM-MinTIC",
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": JWT_EXPIRATION_SECONDS,
        "role": user["role"],
        "permissions": user["permissions"],
    }


def verify_jwt_token(token: str, required_permission: Optional[str] = None) -> Dict[str, Any]:
    """Valida firma, expiración y permisos RBAC de un token JWT."""
    payload = jwt.decode(
        token,
        JWT_SECRET_KEY,
        algorithms=[JWT_ALGORITHM],
        issuer="CloudMedVault-IAM-MinTIC",
    )
    if required_permission and required_permission not in payload.get("permissions", []):
        raise PermissionError(
            f"Acceso denegado (RBAC): el rol '{payload.get('role')}' no posee el permiso '{required_permission}'."
        )
    return payload


# Patrones WAF para prevención de inyección SQL, XSS y Path Traversal (OWASP Top 10 / MinTIC)
WAF_BLOCK_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("SQL_INJECTION", re.compile(r"(?i)(\bUNION\s+SELECT\b|\bDROP\s+TABLE\b|\bOR\s+1\s*=\s*1\b|--\s*$|;\s*DELETE\s+FROM)")),
    ("XSS_ATTACK", re.compile(r"(?i)(<\s*script\b|javascript\s*:|onerror\s*=|onload\s*=)")),
    ("PATH_TRAVERSAL", re.compile(r"(\.\./\.\./|/etc/passwd|c:\\windows\\system32)", re.IGNORECASE)),
]


def inspect_payload_waf(content: str) -> Tuple[bool, Optional[str]]:
    """
    Inspecciona una carga útil entrante frente a reglas WAF.
    Retorna (es_seguro, amenaza_detectada).
    """
    for rule_name, pattern in WAF_BLOCK_PATTERNS:
        if pattern.search(content):
            return False, rule_name
    return True, None
