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


