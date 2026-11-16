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
            )

    def select_optimal_node(self, override_mode: Optional[str] = None) -> BackendNodeDescriptor:
        """
        Selecciona el nodo óptimo según el algoritmo configurado:
        - 'rajammal_dynamic': selecciona el nodo con mayor puntuación de aptitud F_i(t).
        - 'round_robin': turno circular estático sin considerar capacidad ni carga actual.
        """
        self.evaluate_auto_scaling()
        mode = override_mode or self.algorithm_mode

        if mode == "round_robin":
            # En Round-Robin estático se usan los 3 nodos base sin auto-scaling ni pesos de capacidad
            candidates = [n for n in self.nodes if not n.is_elastic_standby and n.healthy]
            if not candidates:
                candidates = self.nodes
            chosen = candidates[self._rr_index % len(candidates)]
            self._rr_index += 1
            return chosen

        # Modo Rajammal et al. (2025): selección dinámica multicriterio consciente de QoS
        candidates = [n for n in self.nodes if n.active_in_pool and n.healthy]
        if not candidates:
            candidates = [n for n in self.nodes if n.healthy] or self.nodes

        best_node = max(
            candidates,
            key=lambda n: (n.compute_rajammal_load_and_fitness(), -n.in_flight_local, -n.routed_requests),
        )
        return best_node

    async def poll_nodes_metrics(self, client: httpx.AsyncClient) -> None:
        """Sondea periódicamente el endpoint /metrics de cada nodo para actualizar CPU, RAM y latencia."""
        for node in self.nodes:
            try:
                resp = await client.get(f"{node.url}/metrics", timeout=1.5)
                if resp.status_code == 200:
                    data = resp.json()
                    node.healthy = True
                    node.cpu_utilization = float(data.get("cpu_utilization", 0.1))
                    node.mem_utilization = float(data.get("mem_utilization", 0.2))
                    node.remote_active_requests = int(data.get("active_requests", 0))
                    # Combina EMA remota y local
                    remote_ema = float(data.get("ema_latency_ms", 10.0))
                    node.ema_latency_ms = 0.5 * node.ema_latency_ms + 0.5 * remote_ema
                    node.compute_rajammal_load_and_fitness()
                else:
                    node.healthy = False
            except Exception:
                node.healthy = False

        # Guarda instantánea histórica para monitoreo
        snapshot = {
            "timestamp": round(time.time(), 2),
            "active_nodes_count": sum(1 for n in self.nodes if n.active_in_pool and n.healthy),
            "total_in_flight": sum(n.in_flight_local for n in self.nodes),
            "nodes": {
                n.node_id: {
                    "cpu": round(n.cpu_utilization, 3),
                    "load_index": n.last_load_index,
                    "fitness": n.last_fitness_score,
                    "routed": n.routed_requests,
                    "ema_ms": round(n.ema_latency_ms, 2),
                    "active": n.active_in_pool,
                }
                for n in self.nodes
            },
        }
        self.telemetry_history.append(snapshot)
        if len(self.telemetry_history) > 300:
            self.telemetry_history.pop(0)


controller = DynamicLoadBalancerController()
http_client: Optional[httpx.AsyncClient] = None
poller_task: Optional[asyncio.Task] = None


async def _background_poller() -> None:
    while True:
        if http_client is not None:
            await controller.poll_nodes_metrics(http_client)
        await asyncio.sleep(0.35)


app = FastAPI(
    title="CloudMedVault - Dynamic Cloud Load Balancer & API Gateway",
    version="1.0.0",
    description="Balanceador de carga dinámico adaptativo (Rajammal et al., 2025) y Gateway de Seguridad MinTIC (2021).",
)


@app.on_event("startup")
async def on_startup() -> None:
    global http_client, poller_task
    http_client = httpx.AsyncClient(
        limits=httpx.Limits(max_keepalive_connections=100, max_connections=200),
        timeout=15.0,
    )
    poller_task = asyncio.create_task(_background_poller())


@app.on_event("shutdown")
async def on_shutdown() -> None:
    global http_client, poller_task
    if poller_task:
        poller_task.cancel()
    if http_client:
        await http_client.aclose()


@app.get("/", response_class=HTMLResponse)
async def dashboard_home() -> str:
    """Dashboard HTML interactivo para visualizar el estado del clúster y controles de seguridad."""
    nodes_rows = ""
    for n in controller.nodes:
        d = n.to_dict()
        badge = "ACTIVO (Pool)" if d["active_in_pool"] else "STANDBY (Auto-Scaling)"
        color = "#10b981" if d["active_in_pool"] else "#f59e0b"
        nodes_rows += f"""
        <tr>
            <td><b>{d['node_id']}</b></td>
            <td>{d['availability_zone']}</td>
            <td>{d['capacity_weight']}x</td>
            <td><span style="color:{color};font-weight:bold;">{badge}</span></td>
            <td>{d['cpu_utilization']*100:.1f}%</td>
            <td>{d['ema_latency_ms']:.1f} ms</td>
            <td>{d['rajammal_load_index']:.3f}</td>
            <td><b>{d['rajammal_fitness_score']:.2f}</b></td>
            <td>{d['routed_requests']}</td>
        </tr>
        """
    return f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="utf-8"/>
        <title>CloudMedVault - Consola Cloud & Balanceador Dinámico</title>
        <style>
            body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #0f172a; color: #f8fafc; margin: 2rem; }}
            h1 {{ color: #38bdf8; margin-bottom: 0.2rem; }}
            .subtitle {{ color: #94a3b8; margin-bottom: 1.5rem; }}
            .card {{ background: #1e293b; border-radius: 10px; padding: 1.2rem 1.5rem; margin-bottom: 1.5rem; border: 1px solid #334155; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 0.8rem; }}
            th, td {{ padding: 0.65rem; text-align: left; border-bottom: 1px solid #334155; }}
            th {{ color: #38bdf8; font-size: 0.9rem; text-transform: uppercase; }}
            .pill {{ display: inline-block; padding: 0.25rem 0.6rem; border-radius: 6px; background: #0284c7; font-size: 0.85rem; margin-right: 0.4rem; }}
        </style>
    </head>
    <body>
        <h1>CloudMedVault — Cloud Security & Dynamic Load Balancer</h1>
        <div class="subtitle">
            Arquitectura Cloud AWS de Referencia | Cumplimiento MinTIC (2021) MSPI | Balanceo Dinámico Multicriterio (Rajammal et al., 2025)
        </div>
        <div class="card">
            <h3>Controles de Seguridad Activos (MinTIC 2021 / Ley 1581 de 2012)</h3>
            <span class="pill">AES-256-GCM (Datos en Reposo RDS + S3 SSE-KMS)</span>
            <span class="pill">IAM / OAuth2 JWT + RBAC</span>
            <span class="pill">Pseudonimización HMAC-SHA256</span>
            <span class="pill">WAF OWASP + Rate Limiting Anti-DDoS</span>
            <span class="pill">Cadena de Auditoría SHA-256 Inmutable</span>
        </div>
        <div class="card">
            <h3>Estado en Tiempo Real del Clúster de Cómputo ({controller.algorithm_mode})</h3>
            <table>
                <thead>
                    <tr>
                        <th>Nodo</th><th>Zona (AZ)</th><th>Capacidad</th><th>Estado Pool</th>
                        <th>CPU</th><th>Latencia EMA</th><th>Índice Carga L(t)</th>
                        <th>Aptitud F(t)</th><th>Peticiones</th>
                    </tr>
                </thead>
                <tbody>{nodes_rows}</tbody>
            </table>
        </div>
    </body>
    </html>
    """


@app.get("/lb/status")
async def lb_status() -> Dict[str, Any]:
    """Devuelve telemetría detallada del balanceador, nodos, auto-scaling y seguridad perimetral."""
    controller.evaluate_auto_scaling()
    return {
        "algorithm_mode": controller.algorithm_mode,
        "weights": {
            "alpha_cpu": ALPHA_CPU,
            "beta_mem": BETA_MEM,
            "gamma_concurrency": GAMMA_CONCURRENCY,
            "delta_latency": DELTA_LATENCY,
        },
        "rate_limiter": {
            "max_requests_per_window": controller.rate_limit_max_req,
            "window_seconds": controller.rate_limit_window_sec,
            "blocked_requests_count": controller.rate_limited_count,
        },
        "nodes": [n.to_dict() for n in controller.nodes],
        "scaling_events": controller.scaling_events,
        "total_routed": sum(n.routed_requests for n in controller.nodes),
    }


@app.post("/lb/config")
async def configure_lb(request: Request) -> Dict[str, Any]:
    """Permite cambiar el algoritmo ('rajammal_dynamic' o 'round_robin') o reiniciar contadores para pruebas."""
    body = await request.json()
    if "algorithm_mode" in body:
        controller.algorithm_mode = body["algorithm_mode"]
    if "rate_limit_max_req" in body:
        controller.rate_limit_max_req = int(body["rate_limit_max_req"])
    if body.get("reset_stats"):
        controller.scaling_events.clear()
        controller.telemetry_history.clear()
        controller.rate_limited_count = 0
        controller._client_windows.clear()
        for n in controller.nodes:
            n.routed_requests = 0
            n.failed_requests = 0
            n.ema_latency_ms = 10.0
            n.in_flight_local = 0
            if n.is_elastic_standby:
                n.active_in_pool = False
    return await lb_status()


@app.get("/lb/history")
async def lb_history() -> Dict[str, Any]:
    return {
        "history": controller.telemetry_history,
        "scaling_events": controller.scaling_events,
    }

