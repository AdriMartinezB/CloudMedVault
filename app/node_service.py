"""
Servicio de Nodo de Cómputo Cloud (Instancia FastAPI)
Representa un contenedor/instancia en AWS ECS Fargate / EC2 Auto Scaling Group.
Expone endpoints clínicos asegurados con JWT/RBAC, cabeceras de seguridad MinTIC (2021)
y telemetría de recursos en tiempo real para el Balanceador Dinámico (Rajammal et al., 2025).
"""

import asyncio
import base64
import hashlib
import os
import time
from typing import Any, Dict, Optional

import psutil
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from app.security import (
    authenticate_and_issue_jwt,
    inspect_payload_waf,
    verify_jwt_token,
)
from app.storage import CloudStorageManager


NODE_ID = os.environ.get("CLOUDMED_NODE_ID", "node-1")
NODE_INSTANCE_TYPE = os.environ.get("CLOUDMED_INSTANCE_TYPE", "ecs.c6i.large")
NODE_CAPACITY = float(os.environ.get("CLOUDMED_NODE_CAPACITY", "1.0"))
NODE_AZ = os.environ.get("CLOUDMED_AZ", "us-east-1a")

storage = CloudStorageManager()
process_handle = psutil.Process(os.getpid())


class NodeTelemetryState:
    """Mantiene métricas de carga y QoS en tiempo real del nodo de cómputo."""

    def __init__(self) -> None:
        self.active_requests: int = 0
        self.total_requests: int = 0
        self.error_count: int = 0
        self.ema_latency_ms: float = 8.0
        self.peak_concurrency: int = 0
        self.started_at: float = time.time()
        self.synthetic_cpu_pressure: float = 0.0

    def record_start(self) -> None:
        self.active_requests += 1
        if self.active_requests > self.peak_concurrency:
            self.peak_concurrency = self.active_requests

    def record_end(self, elapsed_ms: float, is_error: bool = False) -> None:
        self.active_requests = max(0, self.active_requests - 1)
        self.total_requests += 1
        if is_error:
            self.error_count += 1
        alpha = 0.25
        self.ema_latency_ms = (alpha * elapsed_ms) + ((1.0 - alpha) * self.ema_latency_ms)

    def snapshot(self) -> Dict[str, Any]:
        # Combina presión de concurrencia real y capacidad relativa del nodo
        concurrency_ratio = self.active_requests / max(0.5, NODE_CAPACITY * 8.0)
        base_cpu = 0.08 + min(0.88, concurrency_ratio * 0.72 + self.synthetic_cpu_pressure)
        base_mem = 0.22 + min(0.70, (self.active_requests * 0.04) / max(0.5, NODE_CAPACITY))
        return {
            "node_id": NODE_ID,
            "instance_type": NODE_INSTANCE_TYPE,
            "availability_zone": NODE_AZ,
            "capacity_weight": NODE_CAPACITY,
            "status": "HEALTHY",
            "cpu_utilization": round(min(0.99, base_cpu), 4),
            "mem_utilization": round(min(0.98, base_mem), 4),
            "active_requests": self.active_requests,
            "peak_concurrency": self.peak_concurrency,
            "ema_latency_ms": round(self.ema_latency_ms, 3),
            "total_requests": self.total_requests,
            "error_count": self.error_count,
            "uptime_sec": round(time.time() - self.started_at, 1),
        }


telemetry_state = NodeTelemetryState()

app = FastAPI(
    title=f"CloudMedVault Compute Node ({NODE_ID})",
    version="1.0.0",
    description="Microservicio Cloud con cumplimiento MinTIC (2021) y telemetría QoS.",
)


# Modelos Pydantic de entrada
class AuthRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)


class ClinicalRecordCreate(BaseModel):
    national_id: str = Field(..., min_length=5, max_length=32, description="Cédula/ID del paciente")
    patient_name: str = Field(..., min_length=3, max_length=120)
    specialty: str = Field(..., min_length=3, max_length=60)
    diagnosis: str = Field(..., min_length=5, max_length=2000)
    treatment: str = Field(..., min_length=5, max_length=2000)
    severity_level: str = Field(default="MODERATE", pattern="^(LOW|MODERATE|HIGH|CRITICAL)$")
    vital_notes: Dict[str, Any] = Field(default_factory=dict)


class S3DocumentUpload(BaseModel):
    record_id: str = Field(..., min_length=5, max_length=40)
    filename: str = Field(..., min_length=3, max_length=120)
    content_type: str = Field(default="application/pdf")
    content_b64: str = Field(..., description="Contenido del documento clínico en Base64")


class IoTTelemetryPayload(BaseModel):
    device_id: str = Field(..., min_length=4, max_length=48)
    national_id: str = Field(..., min_length=5, max_length=32)
    heart_rate_bpm: int = Field(..., ge=20, le=260)
    spo2_percent: float = Field(..., ge=50.0, le=100.0)
    systolic_bp: int = Field(..., ge=40, le=260)
    diastolic_bp: int = Field(..., ge=20, le=180)
    temperature_c: float = Field(..., ge=30.0, le=44.0)
    compute_complexity: int = Field(default=1, ge=1, le=10)


import urllib.parse

@app.middleware("http")
async def security_and_metrics_middleware(request: Request, call_next):
    """
    Middleware que aplica cabeceras de seguridad MinTIC (2021),
    inspección WAF y contabilización de métricas QoS en tiempo real.
    """
    start_ns = time.perf_counter_ns()
    is_probe = request.url.path in ("/health", "/metrics")
    if not is_probe:
        telemetry_state.record_start()

    is_err = False
    try:
        # Inspección rápida WAF en query string (decodificando URL encoding)
        raw_query = urllib.parse.unquote(str(request.url.query))
        safe, rule = inspect_payload_waf(raw_query)
        if not safe:
            is_err = True
            storage.append_audit_log(
                "anonymous", "unknown", f"WAF_BLOCK_{rule}", str(request.url.path), NODE_ID, "BLOCKED"
            )
            return Response(
                content=f'{{"detail":"Bloqueado por WAF MinTIC: regla {rule}"}}',
                status_code=403,
                media_type="application/json",
            )

        response: Response = await call_next(request)
        if response.status_code >= 500:
            is_err = True

        # Cabeceras de Seguridad Obligatorias (Guía de Seguridad Web / Nube MinTIC 2021)
        response.headers["X-Served-By-Node"] = NODE_ID
        response.headers["X-Node-AZ"] = NODE_AZ
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response
    except Exception:
        is_err = True
        raise
    finally:
        if not is_probe:
            elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
            telemetry_state.record_end(elapsed_ms, is_err)


def require_permission(permission: str):
    """Dependencia FastAPI que valida el token Bearer JWT y el permiso RBAC requerido."""

    async def _verifier(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=401,
                detail="Token de autenticación Bearer ausente o inválido (MinTIC IAM Control).",
            )
        token = authorization.split(" ", 1)[1].strip()
        try:
            return verify_jwt_token(token, required_permission=permission)
        except PermissionError as exc:
            storage.append_audit_log("jwt_user", "restricted", f"RBAC_DENIED:{permission}", "api", NODE_ID, "DENIED")
            raise HTTPException(status_code=403, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=401, detail=f"Token JWT inválido o expirado: {exc}")

    return _verifier


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    return {
        "status": "HEALTHY",
        "node_id": NODE_ID,
        "availability_zone": NODE_AZ,
        "capacity_weight": NODE_CAPACITY,
    }


@app.get("/metrics")
async def node_metrics() -> Dict[str, Any]:
    return telemetry_state.snapshot()


@app.post("/api/v1/auth/token")
async def login_for_access_token(body: AuthRequest) -> Dict[str, Any]:
    token_data = authenticate_and_issue_jwt(body.username, body.password)
    if not token_data:
        storage.append_audit_log(body.username, "unauthenticated", "AUTH_LOGIN_FAILED", "iam", NODE_ID, "FAILED")
        raise HTTPException(status_code=401, detail="Credenciales inválidas.")
    storage.append_audit_log(body.username, token_data["role"], "AUTH_LOGIN_SUCCESS", "iam", NODE_ID, "SUCCESS")
    token_data["issued_by_node"] = NODE_ID
    return token_data


@app.post("/api/v1/records", status_code=201)
async def create_record(
    payload: ClinicalRecordCreate,
    claims: Dict[str, Any] = Depends(require_permission("records:write")),
) -> Dict[str, Any]:
    # Inspección WAF del diagnóstico y tratamiento
    safe, threat = inspect_payload_waf(f"{payload.diagnosis} {payload.treatment} {payload.patient_name}")
    if not safe:
        storage.append_audit_log(
            claims["sub"], claims["role"], f"WAF_BLOCK_{threat}", "records", NODE_ID, "BLOCKED"
        )
        raise HTTPException(status_code=403, detail=f"Carga útil bloqueada por regla WAF: {threat}")

    # Simulación realista de procesamiento criptográfico / validación acorde a la capacidad del nodo
    compute_delay = (0.012 / max(0.4, NODE_CAPACITY)) + (telemetry_state.active_requests * 0.003)
    await asyncio.sleep(min(0.15, compute_delay))

    return storage.create_clinical_record(
        national_id=payload.national_id,
        patient_name=payload.patient_name,
        specialty=payload.specialty,
        diagnosis=payload.diagnosis,
        treatment=payload.treatment,
        severity_level=payload.severity_level,
        vital_notes=payload.vital_notes,
        actor=claims["sub"],
        role=claims["role"],
        node_id=NODE_ID,
    )


@app.get("/api/v1/records/{record_id}")
async def read_record(
    record_id: str,
    claims: Dict[str, Any] = Depends(require_permission("records:read")),
) -> Dict[str, Any]:
    compute_delay = 0.008 / max(0.4, NODE_CAPACITY)
    await asyncio.sleep(min(0.10, compute_delay))
    record = storage.get_clinical_record(
        record_id=record_id,
        actor=claims["sub"],
        role=claims["role"],
        node_id=NODE_ID,
    )
    if not record:
        raise HTTPException(status_code=404, detail="Historia clínica no encontrada.")
    return record


@app.post("/api/v1/documents", status_code=201)
async def upload_document(
    payload: S3DocumentUpload,
    claims: Dict[str, Any] = Depends(require_permission("documents:write")),
) -> Dict[str, Any]:
    try:
        raw_bytes = base64.b64decode(payload.content_b64)
    except Exception:
        raise HTTPException(status_code=400, detail="Contenido Base64 inválido.")

    compute_delay = 0.014 / max(0.4, NODE_CAPACITY)
    await asyncio.sleep(min(0.12, compute_delay))

    return storage.put_s3_encrypted_object(
        record_id=payload.record_id,
        filename=payload.filename,
        content_type=payload.content_type,
        raw_bytes=raw_bytes,
        actor=claims["sub"],
        role=claims["role"],
        node_id=NODE_ID,
    )


@app.get("/api/v1/documents")
async def download_document(
    object_key: str = Query(..., description="Clave S3 del objeto cifrado"),
