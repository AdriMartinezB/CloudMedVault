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
    """
    Controlador central de Balanceo de Carga Dinámico, Auto-Scaling y Rate Limiting.
    """

    def __init__(self) -> None:
        self.nodes: List[BackendNodeDescriptor] = [
            BackendNodeDescriptor(
                node_id="node-1",
                url=os.environ.get("NODE_1_URL", "http://127.0.0.1:8001"),
                capacity_weight=1.6,
                availability_zone="us-east-1a",
                is_elastic_standby=False,
            ),
            BackendNodeDescriptor(
                node_id="node-2",
                url=os.environ.get("NODE_2_URL", "http://127.0.0.1:8002"),
                capacity_weight=1.0,
                availability_zone="us-east-1b",
                is_elastic_standby=False,
            ),
            BackendNodeDescriptor(
                node_id="node-3",
                url=os.environ.get("NODE_3_URL", "http://127.0.0.1:8003"),
                capacity_weight=0.6,
                availability_zone="us-east-1c",
                is_elastic_standby=False,
            ),
            BackendNodeDescriptor(
                node_id="node-4",
                url=os.environ.get("NODE_4_URL", "http://127.0.0.1:8004"),
                capacity_weight=1.4,
                availability_zone="us-east-1a",
                is_elastic_standby=True,
            ),
        ]
        self.algorithm_mode: str = "rajammal_dynamic"  # o "round_robin"
        self._rr_index: int = 0
        self.scaling_events: List[Dict[str, Any]] = []
        self.telemetry_history: List[Dict[str, Any]] = []
        self._last_scale_change: float = 0.0

        # Rate Limiter por cliente (ventana deslizante de 5 segundos)
        self.rate_limit_max_req: int = int(os.environ.get("CLOUDMED_RATE_LIMIT", "250"))
        self.rate_limit_window_sec: float = 5.0
        self._client_windows: Dict[str, List[float]] = {}
        self.rate_limited_count: int = 0

    def check_rate_limit(self, client_key: str) -> bool:
        """Verifica si el cliente supera el límite de peticiones por ventana (Protección DDoS)."""
        now = time.time()
        timestamps = self._client_windows.get(client_key, [])
        cutoff = now - self.rate_limit_window_sec
        valid_ts = [t for t in timestamps if t > cutoff]
        if len(valid_ts) >= self.rate_limit_max_req:
            self._client_windows[client_key] = valid_ts
            self.rate_limited_count += 1
            return False
        valid_ts.append(now)
        self._client_windows[client_key] = valid_ts
        return True

    def evaluate_auto_scaling(self) -> None:
        """
        Evalúa la carga promedio del clúster y activa/desactiva el nodo elástico (node-4)
        para manejar cargas variables eficientemente.
        """
        active_nodes = [n for n in self.nodes if n.active_in_pool and n.healthy]
        if not active_nodes:
            return
        for n in active_nodes:
            n.compute_rajammal_load_and_fitness()

        avg_load = sum(n.last_load_index for n in active_nodes) / len(active_nodes)
        total_in_flight = sum(n.in_flight_local for n in active_nodes)
        standby_node = next((n for n in self.nodes if n.is_elastic_standby), None)
        if not standby_node or not standby_node.healthy:
            return

        now = time.time()
        # Scale-Out cuando hay concurrencia activa >= 4 y la carga supera el umbral (o ráfaga >= 6)
        if (
            not standby_node.active_in_pool
            and total_in_flight >= 4
            and (avg_load >= SCALE_OUT_THRESHOLD or total_in_flight >= 6)
        ):
            standby_node.active_in_pool = True
            self._last_scale_change = now
            self.scaling_events.append(
                {
                    "timestamp": round(now, 3),
                    "action": "SCALE_OUT",
                    "node_id": standby_node.node_id,
                    "cluster_avg_load": round(avg_load, 4),
                    "total_in_flight": total_in_flight,
                    "reason": f"Carga media {avg_load:.2f} >= {SCALE_OUT_THRESHOLD} con concurrencia={total_in_flight}",
                }
            )
        # Scale-In cuando la concurrencia desciende de forma sostenida (Fase de Enfriamiento)
        elif (
            standby_node.active_in_pool
            and total_in_flight <= 2
            and (now - self._last_scale_change) >= 0.35
        ):
            standby_node.active_in_pool = False
            self._last_scale_change = now
            self.scaling_events.append(
                {
                    "timestamp": round(now, 3),
                    "action": "SCALE_IN",
                    "node_id": standby_node.node_id,
                    "cluster_avg_load": round(avg_load, 4),
                    "total_in_flight": total_in_flight,
                    "reason": f"Concurrencia reducida a {total_in_flight} <= 2 (Liberación de nodo elástico para ahorro de costos)",
                }
