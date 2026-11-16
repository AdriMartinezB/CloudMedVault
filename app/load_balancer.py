"""
Balanceador de Carga Dinámico Adaptativo y Auto-Scaler Cloud
Basado en técnicas de balanceo multicriterio consciente de recursos y QoS (Rajammal et al., 2025)
y controles de seguridad perimetral MinTIC (2021).
"""

import asyncio
import os
import time
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse


# Pesos multicriterio del modelo dinámico (Rajammal et al., 2025)
ALPHA_CPU = 0.35
BETA_MEM = 0.15
GAMMA_CONCURRENCY = 0.30
DELTA_LATENCY = 0.20
SLA_TARGET_LATENCY_MS = 45.0
MAX_CONCURRENCY_REF = 10.0

# Umbrales de Auto-Scaling Elástico
SCALE_OUT_THRESHOLD = 0.36
SCALE_IN_THRESHOLD = 0.26


class BackendNodeDescriptor:
    """Estado y métricas en tiempo real de un nodo de cómputo en el clúster."""

    def __init__(
        self,
        node_id: str,
        url: str,
        capacity_weight: float,
        availability_zone: str,
        is_elastic_standby: bool = False,
    ) -> None:
        self.node_id = node_id
        self.url = url.rstrip("/")
        self.capacity_weight = capacity_weight
        self.availability_zone = availability_zone
        self.is_elastic_standby = is_elastic_standby
        self.active_in_pool: bool = not is_elastic_standby
        self.healthy: bool = True

        # Métricas reportadas y locales en tiempo real
        self.cpu_utilization: float = 0.10
        self.mem_utilization: float = 0.22
        self.in_flight_local: int = 0
        self.remote_active_requests: int = 0
        self.ema_latency_ms: float = 10.0
        self.routed_requests: int = 0
        self.failed_requests: int = 0
        self.last_load_index: float = 0.10
        self.last_fitness_score: float = capacity_weight / 0.10

    def compute_rajammal_load_and_fitness(self) -> float:
        """
        Calcula el Índice Compuesto de Carga L_i(t) y la Aptitud Dinámica F_i(t)
        siguiendo el enfoque adaptativo multicriterio (Rajammal et al., 2025):
          L_i(t) = α·CPU_i + β·MEM_i + γ·(Conn_i / (Cap_i · C_max)) + δ·(Lat_i / SLA)
          F_i(t) = Cap_i / max(0.05, L_i(t))
        """
        effective_conn = max(self.in_flight_local, self.remote_active_requests)
        norm_conn = min(2.0, (effective_conn + 0.35) / max(0.5, self.capacity_weight * 3.5))
        norm_lat = min(2.0, self.ema_latency_ms / SLA_TARGET_LATENCY_MS)
        instant_cpu = min(
            0.99,
            self.cpu_utilization + (self.in_flight_local * 0.14 / max(0.5, self.capacity_weight)),
        )
        wear_factor = (self.routed_requests * 0.0035) / max(0.5, self.capacity_weight)

        load_index = (
            (ALPHA_CPU * instant_cpu)
            + (BETA_MEM * self.mem_utilization)
            + (GAMMA_CONCURRENCY * norm_conn)
            + (DELTA_LATENCY * norm_lat)
            + wear_factor
        )
        self.last_load_index = round(load_index, 4)
        self.last_fitness_score = round(self.capacity_weight / max(0.05, load_index), 4)
        return self.last_fitness_score

    def to_dict(self) -> Dict[str, Any]:
        self.compute_rajammal_load_and_fitness()
        return {
            "node_id": self.node_id,
            "url": self.url,
            "availability_zone": self.availability_zone,
            "capacity_weight": self.capacity_weight,
            "is_elastic_standby": self.is_elastic_standby,
            "active_in_pool": self.active_in_pool,
            "healthy": self.healthy,
            "cpu_utilization": round(self.cpu_utilization, 4),
            "mem_utilization": round(self.mem_utilization, 4),
            "in_flight_requests": self.in_flight_local,
            "ema_latency_ms": round(self.ema_latency_ms, 2),
            "rajammal_load_index": self.last_load_index,
            "rajammal_fitness_score": self.last_fitness_score,
            "routed_requests": self.routed_requests,
            "failed_requests": self.failed_requests,
        }


class DynamicLoadBalancerController:
