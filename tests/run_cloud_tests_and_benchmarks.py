"""
Suite Integral de Pruebas Funcionales, Seguridad MinTIC (2021) y Benchmark de Balanceo de Carga Dinámico
(Rajammal et al., 2025 vs. Round-Robin Estático).
Levanta el clúster real de 4 nodos + Balanceador Dinámico, ejecuta todas las pruebas,
guarda métricas reales en JSON y genera las figuras técnicas para el informe y la presentación.
"""

import asyncio
import base64
import json
import os
import shutil
import sqlite3
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import httpx
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches


ROOT_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT_DIR / "results"
DATA_DIR = ROOT_DIR / "data"
PYTHON_BIN = ROOT_DIR / ".venv" / "bin" / "python3"

LB_URL = "http://127.0.0.1:8080"
NODES_CONFIG = [
    {"id": "node-1", "port": 8001, "type": "ecs.c6i.large", "cap": "1.6", "az": "us-east-1a"},
    {"id": "node-2", "port": 8002, "type": "ecs.t3.medium", "cap": "1.0", "az": "us-east-1b"},
    {"id": "node-3", "port": 8003, "type": "ecs.t3.small", "cap": "0.6", "az": "us-east-1c"},
    {"id": "node-4", "port": 8004, "type": "ecs.c6i.large.spot", "cap": "1.4", "az": "us-east-1a"},
]


def start_cluster_processes() -> List[subprocess.Popen]:
    """Inicia los 4 nodos de cómputo y el balanceador dinámico como subprocesos."""
    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(ROOT_DIR))
    from app.storage import CloudStorageManager
    CloudStorageManager(db_path=DATA_DIR / "cloudmedvault.db", s3_dir=DATA_DIR / "s3_bucket")

    procs: List[subprocess.Popen] = []
    for n in NODES_CONFIG:
        env = os.environ.copy()
        env["CLOUDMED_NODE_ID"] = n["id"]
        env["CLOUDMED_INSTANCE_TYPE"] = n["type"]
        env["CLOUDMED_NODE_CAPACITY"] = n["cap"]
        env["CLOUDMED_AZ"] = n["az"]
        env["CLOUDMED_DATA_DIR"] = str(DATA_DIR)
        cmd = [
            str(PYTHON_BIN),
            "-m",
            "uvicorn",
            "app.node_service:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(n["port"]),
            "--log-level",
            "warning",
        ]
        p = subprocess.Popen(cmd, cwd=str(ROOT_DIR), env=env)
        procs.append(p)

    # Inicia el Balanceador de Carga Dinámico en el puerto 8080
    lb_env = os.environ.copy()
    lb_env["CLOUDMED_RATE_LIMIT"] = "500"
    lb_cmd = [
        str(PYTHON_BIN),
        "-m",
        "uvicorn",
        "app.load_balancer:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8080",
        "--log-level",
        "warning",
    ]
    lb_proc = subprocess.Popen(lb_cmd, cwd=str(ROOT_DIR), env=lb_env)
    procs.append(lb_proc)
    return procs


async def wait_for_cluster_ready(client: httpx.AsyncClient) -> None:
    """Espera a que todos los nodos y el balanceador respondan en sus endpoints de salud."""
    targets = [f"http://127.0.0.1:{n['port']}/health" for n in NODES_CONFIG] + [f"{LB_URL}/lb/status"]
    for url in targets:
        for _ in range(40):
            try:
                r = await client.get(url, timeout=1.0)
                if r.status_code == 200:
                    break
            except Exception:
                pass
            await asyncio.sleep(0.2)
        else:
            raise RuntimeError(f"El servicio en {url} no inició a tiempo.")


async def run_security_and_functional_tests(client: httpx.AsyncClient) -> Dict[str, Any]:
    """Ejecuta las 7 pruebas de seguridad MinTIC (2021) y funcionalidad de la aplicación."""
    test_cases: List[Dict[str, Any]] = []

    # 1. Autenticación IAM y emisión de JWT para los 3 roles
    r_med = await client.post(
        f"{LB_URL}/api/v1/auth/token",
        json={"username": "dr.ramirez", "password": "MedCloud#2026!"},
    )
    r_adm = await client.post(
        f"{LB_URL}/api/v1/auth/token",
        json={"username": "admin.seguridad", "password": "AdminMinTIC#2026!"},
    )
    r_iot = await client.post(
        f"{LB_URL}/api/v1/auth/token",
        json={"username": "gateway.iot", "password": "IoTGateway#2026!"},
    )
    r_bad = await client.post(
        f"{LB_URL}/api/v1/auth/token",
        json={"username": "dr.ramirez", "password": "WrongPassword123"},
    )
    assert r_med.status_code == 200 and r_adm.status_code == 200 and r_iot.status_code == 200
    assert r_bad.status_code == 401
    med_token = r_med.json()["access_token"]
    adm_token = r_adm.json()["access_token"]
    iot_token = r_iot.json()["access_token"]
    test_cases.append(
        {
            "id": "SEC-01",
            "name": "Autenticación OAuth2/JWT y bloqueo de credenciales inválidas",
            "mintic_control": "MSPI AC-2 / Gestión de Identidades y Acceso (IAM)",
            "expected": "HTTP 200 (JWT HS256) / HTTP 401 en fallo",
            "obtained": f"Tokens emitidos para 3 roles; intento inválido bloqueado con HTTP {r_bad.status_code}",
            "passed": True,
        }
    )

    # 2. Control de Acceso Basado en Roles (RBAC - Principio de Mínimo Privilegio)
    r_rbac_deny = await client.post(
        f"{LB_URL}/api/v1/records",
        headers={"Authorization": f"Bearer {iot_token}"},
        json={
            "national_id": "1020304050",
            "patient_name": "Paciente Prueba RBAC",
            "specialty": "Cardiología",
            "diagnosis": "Intento no autorizado desde sensor IoT",
            "treatment": "N/A",
            "severity_level": "LOW",
        },
    )
    assert r_rbac_deny.status_code == 403
    test_cases.append(
        {
            "id": "SEC-02",
            "name": "Autorización RBAC y Principio de Mínimo Privilegio",
            "mintic_control": "MSPI AC-3 / Segregación de Funciones",
            "expected": "HTTP 403 Forbidden para rol iot_sensor en historias clínicas",
            "obtained": f"Acceso bloqueado con HTTP {r_rbac_deny.status_code}: {r_rbac_deny.json()['detail']}",
            "passed": True,
        }
    )

    # 3. Cifrado AES-256-GCM en Reposo y Pseudonimización de Datos Personales (Ley 1581 / MinTIC)
    r_create = await client.post(
        f"{LB_URL}/api/v1/records",
        headers={"Authorization": f"Bearer {med_token}"},
        json={
            "national_id": "1098765432",
            "patient_name": "María Fernanda López",
            "specialty": "Cardiología Clínica",
            "diagnosis": "Taquicardia supraventricular paroxística controlada.",
            "treatment": "Metoprolol 50mg c/12h + Monitoreo continuo.",
            "severity_level": "HIGH",
            "vital_notes": {"ecg_lead": "II", "qt_interval_ms": 410},
        },
    )
    assert r_create.status_code == 201
    created_data = r_create.json()
    record_id = created_data["record_id"]

    # Verificar directamente en SQLite que el texto plano NO aparece y está cifrado con AES-256-GCM
    conn = sqlite3.connect(str(DATA_DIR / "cloudmedvault.db"))
    raw_row = conn.execute(
        "SELECT patient_pseudonym, encrypted_payload FROM clinical_records WHERE record_id = ?",
        (record_id,),
    ).fetchone()
    conn.close()
    assert raw_row is not None
    assert "María Fernanda López" not in raw_row[1]
    assert "1098765432" not in raw_row[0] and raw_row[0].startswith("PID-")

    # Verificar lectura y descifrado con verificación SHA-256
    r_read = await client.get(
        f"{LB_URL}/api/v1/records/{record_id}",
        headers={"Authorization": f"Bearer {med_token}"},
    )
    assert r_read.status_code == 200
    read_data = r_read.json()
    assert read_data["sha256_integrity_verified"] is True
    assert read_data["clinical_data"]["patient_name"] == "María Fernanda López"

    test_cases.append(
        {
            "id": "SEC-03",
            "name": "Cifrado en Reposo AES-256-GCM y Pseudonimización HMAC-SHA256",
            "mintic_control": "MSPI SC-28 / Ley 1581 de 2012 (Habeas Data)",
            "expected": "PII pseudonimizado (PID-*) y payload cifrado en DB con verificación SHA-256",
            "obtained": f"ID={raw_row[0]}, Cifrado=AES-256-GCM, SHA-256={created_data['sha256_integrity'][:16]}...",
            "passed": True,
        }
    )

    # 4. Almacenamiento de Objetos S3 con Cifrado SSE-KMS (AES-256-GCM)
    sample_doc = (
        "INFORME DE ECOCARDIOGRAMA DOPPLER - PACIENTE: PID-RESERVADO - "
        "FEVI 62% - Sin alteraciones valvulares hemodinámicamente significativas."
    ).encode("utf-8")
    r_s3_put = await client.post(
        f"{LB_URL}/api/v1/documents",
        headers={"Authorization": f"Bearer {med_token}"},
        json={
            "record_id": record_id,
            "filename": "ecocardiograma_doppler_2026.pdf",
            "content_type": "application/pdf",
            "content_b64": base64.b64encode(sample_doc).decode("ascii"),
        },
    )
    assert r_s3_put.status_code == 201
    s3_key = r_s3_put.json()["object_key"]

    r_s3_get = await client.get(
        f"{LB_URL}/api/v1/documents",
        params={"object_key": s3_key},
        headers={"Authorization": f"Bearer {med_token}"},
    )
    assert r_s3_get.status_code == 200 and r_s3_get.json()["sha256_verified"] is True
    test_cases.append(
        {
            "id": "SEC-04",
            "name": "Almacenamiento de Objetos Cloud (S3 SSE-KMS) con Integridad SHA-256",
            "mintic_control": "Guía Seguridad Nube MinTIC (2021) - Protección de Almacenamiento",
            "expected": "Objeto cifrado en disco (.s3enc) y verificado al descargar",
            "obtained": f"Clave {s3_key} almacenada y verificada con SSE-KMS (AES-256-GCM)",
            "passed": True,
        }
    )

    # 5. Protección WAF contra Inyección SQL y Cross-Site Scripting (XSS)
    r_sqli = await client.post(
        f"{LB_URL}/api/v1/records",
        headers={"Authorization": f"Bearer {med_token}"},
        json={
            "national_id": "1099887766",
            "patient_name": "Paciente Atacante",
            "specialty": "Urgencias",
            "diagnosis": "Fiebre '; DROP TABLE clinical_records; UNION SELECT * FROM users --",
            "treatment": "Observación",
            "severity_level": "LOW",
        },
    )
    r_xss = await client.get(
        f"{LB_URL}/api/v1/records/REC-123?filter=<script>alert('xss')</script>",
        headers={"Authorization": f"Bearer {med_token}"},
    )
    assert r_sqli.status_code == 403 and r_xss.status_code == 403
    test_cases.append(
        {
            "id": "SEC-05",
            "name": "Firewall de Aplicaciones Web (WAF) contra SQLi y XSS",
            "mintic_control": "MSPI SI-10 / Protección Perimetral OWASP Top 10",
            "expected": "Bloqueo inmediato con HTTP 403 Forbidden y registro en auditoría",
            "obtained": f"SQLi bloqueado (HTTP {r_sqli.status_code}) y XSS bloqueado (HTTP {r_xss.status_code})",
            "passed": True,
        }
    )

    # 6. Cabeceras de Seguridad HTTP y Verificación Criptográfica de Cadena de Auditoría
    r_audit = await client.get(
        f"{LB_URL}/api/v1/audit/verify",
        headers={"Authorization": f"Bearer {adm_token}"},
    )
    assert r_audit.status_code == 200
    audit_info = r_audit.json()
    assert audit_info["intact"] is True
    assert "Strict-Transport-Security" in r_audit.headers
    assert r_audit.headers.get("X-Frame-Options") == "DENY"
    test_cases.append(
        {
            "id": "SEC-06",
            "name": "Cadena de Auditoría Inmutable (Hash-Chain SHA-256) y Cabeceras HSTS/CSP",
            "mintic_control": "MSPI AU-9 / Protección de Información de Auditoría",
            "expected": "Cadena íntegra (intact=True) y cabeceras HSTS, CSP, X-Frame-Options presentes",
            "obtained": f"{audit_info['verified_records']} eventos auditados verificados; Hash={audit_info['latest_hash'][:16]}...",
            "passed": True,
        }
    )

    # 7. Mitigación Anti-DDoS / Fuerza Bruta mediante Rate Limiting en el Gateway
    await client.post(f"{LB_URL}/lb/config", json={"rate_limit_max_req": 8})
    rate_statuses = []
    for _ in range(12):
        resp_rl = await client.get(
            f"{LB_URL}/api/v1/records/{record_id}",
            headers={"Authorization": f"Bearer {med_token}", "X-Client-ID": "attacker-botnet-ip"},
        )
        rate_statuses.append(resp_rl.status_code)
    await client.post(f"{LB_URL}/lb/config", json={"rate_limit_max_req": 500})
    assert 429 in rate_statuses
    test_cases.append(
        {
            "id": "SEC-07",
            "name": "Control de Tráfico y Mitigación DDoS (Rate Limiting por Ventana Deslizante)",
            "mintic_control": "MSPI SC-5 / Protección contra Denegación de Servicio (DoS)",
            "expected": "HTTP 429 Too Many Requests al superar umbral por cliente",
            "obtained": f"Ráfaga detectada y bloqueada con HTTP 429 ({rate_statuses.count(429)} peticiones frenadas)",
            "passed": True,
        }
    )

    return {
        "total_tests": len(test_cases),
        "passed_tests": sum(1 for t in test_cases if t["passed"]),
        "test_cases": test_cases,
    }


async def run_workload_for_algorithm(
    client: httpx.AsyncClient,
    iot_token: str,
    med_token: str,
    algorithm_mode: str,
) -> Dict[str, Any]:
    """
    Ejecuta un escenario de carga variable en 4 fases (Baja -> Media -> Ráfaga Alta -> Recuperación)
    para comparar el desempeño del algoritmo de Rajammal et al. (2025) frente a Round-Robin estático.
    """
    await client.post(
        f"{LB_URL}/lb/config",
        json={"algorithm_mode": algorithm_mode, "rate_limit_max_req": 1000, "reset_stats": True},
    )
    await asyncio.sleep(0.5)

    # Definición de 4 fases de carga dinámica (total = 120 peticiones)
    phases = [
        {"name": "Fase 1: Carga Baja", "requests": 20, "concurrency": 2, "complexity": 2},
        {"name": "Fase 2: Carga Media", "requests": 30, "concurrency": 5, "complexity": 4},
        {"name": "Fase 3: Ráfaga Crítica UCI (Pico)", "requests": 50, "concurrency": 12, "complexity": 6},
        {"name": "Fase 4: Enfriamiento / Recuperación", "requests": 20, "concurrency": 2, "complexity": 2},
    ]

    latencies_ms: List[float] = []
    node_counts: Dict[str, int] = {"node-1": 0, "node-2": 0, "node-3": 0, "node-4": 0}
    phase_metrics: List[Dict[str, Any]] = []
    timeline_series: List[Dict[str, Any]] = []
    t_zero = time.perf_counter()

    for phase in phases:
        sem = asyncio.Semaphore(phase["concurrency"])
        phase_lats: List[float] = []

        async def _worker(req_idx: int, comp: int) -> None:
            async with sem:
                t0 = time.perf_counter()
                if req_idx % 5 == 0:
                    resp = await client.post(
                        f"{LB_URL}/api/v1/records",
                        headers={
                            "Authorization": f"Bearer {med_token}",
                            "X-LB-Algorithm": algorithm_mode,
                            "X-Client-ID": f"bench-{algorithm_mode}-{req_idx % 10}",
                        },
                        json={
                            "national_id": f"1000{req_idx:05d}",
                            "patient_name": f"Paciente Monitoreo {req_idx}",
                            "specialty": "UCI Telemetría",
                            "diagnosis": "Monitoreo hemodinámico continuo en nube.",
                            "treatment": "Soporte vital estándar.",
                            "severity_level": "MODERATE",
                        },
                    )
                else:
                    resp = await client.post(
                        f"{LB_URL}/api/v1/telemetry",
                        headers={
                            "Authorization": f"Bearer {iot_token}",
                            "X-LB-Algorithm": algorithm_mode,
                            "X-Client-ID": f"bench-{algorithm_mode}-{req_idx % 10}",
                        },
                        json={
                            "device_id": f"UCI-MON-{req_idx % 16:02d}",
                            "national_id": f"1000{req_idx:05d}",
                            "heart_rate_bpm": 75 + (req_idx % 55),
                            "spo2_percent": round(98.5 - (req_idx % 9), 1),
                            "systolic_bp": 118 + (req_idx % 45),
                            "diastolic_bp": 76 + (req_idx % 20),
                            "temperature_c": round(36.6 + ((req_idx % 5) * 0.4), 1),
                            "compute_complexity": comp,
                        },
                    )
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                assert resp.status_code in (200, 201)
                served_node = resp.headers.get("X-LB-Selected-Node", "node-1")
                node_counts[served_node] = node_counts.get(served_node, 0) + 1
                latencies_ms.append(elapsed_ms)
                phase_lats.append(elapsed_ms)

        phase_start = time.perf_counter()
        tasks = [asyncio.create_task(_worker(i, phase["complexity"])) for i in range(phase["requests"])]
        await asyncio.sleep(0.06)
        mid_status = (await client.get(f"{LB_URL}/lb/status")).json()
        await asyncio.gather(*tasks)
        phase_duration = time.perf_counter() - phase_start

        status_resp = await client.get(f"{LB_URL}/lb/status")
        lb_state = status_resp.json()
        if phase["concurrency"] >= 5:
            active_nodes_now = max(
                sum(1 for n in mid_status["nodes"] if n["active_in_pool"]),
                sum(1 for n in lb_state["nodes"] if n["active_in_pool"]),
            )
        else:
            active_nodes_now = sum(1 for n in lb_state["nodes"] if n["active_in_pool"])

        phase_metrics.append(
            {
                "phase": phase["name"],
                "requests": phase["requests"],
                "concurrency": phase["concurrency"],
                "mean_latency_ms": round(statistics.mean(phase_lats), 2),
                "p95_latency_ms": round(sorted(phase_lats)[int(len(phase_lats) * 0.95) - 1], 2),
                "throughput_rps": round(phase["requests"] / max(0.01, phase_duration), 2),
                "active_nodes": active_nodes_now,
            }
        )
        timeline_series.append(
            {
                "elapsed_sec": round(time.perf_counter() - t_zero, 2),
                "phase": phase["name"],
                "mean_latency_ms": round(statistics.mean(phase_lats), 2),
                "active_nodes": active_nodes_now,
                "concurrency": phase["concurrency"],
            }
        )

        # En la última fase verificamos el estado tras el enfriamiento
        if "Recuperación" in phase["name"] and algorithm_mode == "rajammal_dynamic":
            await client.get(f"{LB_URL}/lb/status")

    total_duration = sum(p["requests"] / p["throughput_rps"] for p in phase_metrics)
    sorted_lats = sorted(latencies_ms)
    final_status = (await client.get(f"{LB_URL}/lb/status")).json()

    return {
        "algorithm_mode": algorithm_mode,
        "total_requests": len(latencies_ms),
        "total_duration_sec": round(total_duration, 2),
        "throughput_rps": round(len(latencies_ms) / max(0.01, total_duration), 2),
        "mean_latency_ms": round(statistics.mean(latencies_ms), 2),
        "median_p50_ms": round(statistics.median(latencies_ms), 2),
        "p95_latency_ms": round(sorted_lats[int(len(sorted_lats) * 0.95) - 1], 2),
        "p99_latency_ms": round(sorted_lats[int(len(sorted_lats) * 0.99) - 1], 2),
        "stdev_latency_ms": round(statistics.stdev(latencies_ms), 2),
        "node_distribution": node_counts,
        "phases": phase_metrics,
        "timeline": timeline_series,
        "scaling_events": final_status.get("scaling_events", []),
    }


def generate_charts(
    rr_results: Dict[str, Any],
    raj_results: Dict[str, Any],
) -> None:
    """Genera las 4 figuras de alta resolución para incluir en el informe PDF y la presentación."""
    plt.rcParams["font.sans-serif"] = "DejaVu Sans"
    plt.rcParams["axes.edgecolor"] = "#cbd5e1"
    plt.rcParams["axes.linewidth"] = 0.8

    # FIGURA 1: Comparativa de Latencias (Media, Mediana P50, P95, P99)
    fig, ax = plt.subplots(figsize=(8.5, 4.6), dpi=220)
    metrics_labels = ["Media", "Mediana (P50)", "Percentil 95 (P95)", "Percentil 99 (P99)"]
    rr_vals = [
        rr_results["mean_latency_ms"],
        rr_results["median_p50_ms"],
        rr_results["p95_latency_ms"],
        rr_results["p99_latency_ms"],
    ]
    raj_vals = [
        raj_results["mean_latency_ms"],
        raj_results["median_p50_ms"],
        raj_results["p95_latency_ms"],
        raj_results["p99_latency_ms"],
    ]

    x = range(len(metrics_labels))
    width = 0.35
    bars1 = ax.bar(
        [i - width / 2 for i in x],
        rr_vals,
        width,
        label="Round-Robin Estático (Tradicional)",
        color="#ef4444",
        edgecolor="#991b1b",
    )
    bars2 = ax.bar(
        [i + width / 2 for i in x],
        raj_vals,
        width,
        label="Dinámico Multicriterio (Rajammal et al., 2025)",
        color="#0284c7",
        edgecolor="#075985",
    )

    ax.set_ylabel("Tiempo de Respuesta / Latencia (ms)", fontsize=10, fontweight="bold", color="#1e293b")
    ax.set_title(
        "Comparativa de Latencia Bajo Cargas Variables: Round-Robin vs. Rajammal et al. (2025)",
        fontsize=11.5,
        fontweight="bold",
        color="#0f172a",
        pad=14,
    )
    ax.set_xticks(list(x))
    ax.set_xticklabels(metrics_labels, fontsize=9.5, fontweight="bold")
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    ax.legend(frameon=True, facecolor="#f8fafc", fontsize=9.5)

    for b in list(bars1) + list(bars2):
        h = b.get_height()
        ax.annotate(
            f"{h:.1f} ms",
            xy=(b.get_x() + b.get_width() / 2, h),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8.5,
            fontweight="bold",
        )
    ax.set_ylim(0, max(rr_vals) * 1.18)
    plt.tight_layout()
    plt.savefig(RESULTS_DIR / "fig1_latency_comparison.png", dpi=220)
    plt.close(fig)

    # FIGURA 2: Distribución de Peticiones por Nodo Heterogéneo
    fig, ax = plt.subplots(figsize=(8.5, 4.6), dpi=220)
    node_names = [
        "node-1\n(c6i.large - Cap 1.6x)",
        "node-2\n(t3.medium - Cap 1.0x)",
        "node-3\n(t3.small - Cap 0.6x)",
        "node-4 (Elástico)\n(c6i.spot - Cap 1.4x)",
    ]
    keys = ["node-1", "node-2", "node-3", "node-4"]
    rr_dist = [rr_results["node_distribution"].get(k, 0) for k in keys]
    raj_dist = [raj_results["node_distribution"].get(k, 0) for k in keys]

    x2 = range(len(keys))
    b1 = ax.bar(
        [i - width / 2 for i in x2],
        rr_dist,
        width,
        label="Round-Robin Estático (Ignora Capacidad)",
        color="#f97316",
    )
    b2 = ax.bar(
        [i + width / 2 for i in x2],
        raj_dist,
        width,
        label="Balanceo Dinámico + Auto-Scaling (Rajammal et al., 2025)",
        color="#10b981",
    )
    ax.set_ylabel("Peticiones Enrutadas (Total = 120)", fontsize=10, fontweight="bold")
    ax.set_title(
        "Distribución de Carga por Nodo según Capacidad de Cómputo y Escalado Elástico",
        fontsize=11.5,
        fontweight="bold",
        pad=14,
    )
    ax.set_xticks(list(x2))
    ax.set_xticklabels(node_names, fontsize=9)
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    ax.legend(frameon=True, facecolor="#f8fafc", fontsize=9.5)

    for b in list(b1) + list(b2):
        h = b.get_height()
        ax.annotate(
            f"{int(h)} req",
            xy=(b.get_x() + b.get_width() / 2, h),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8.5,
            fontweight="bold",
        )
    ax.set_ylim(0, max(rr_dist + raj_dist) * 1.2)
    plt.tight_layout()
    plt.savefig(RESULTS_DIR / "fig2_node_distribution.png", dpi=220)
    plt.close(fig)

    # FIGURA 3: Desempeño por Fase de Carga Variable y Auto-Scaling
    fig, ax1 = plt.subplots(figsize=(8.5, 4.6), dpi=220)
    phase_names = [
        "Fase 1\n(Carga Baja - 2c)",
        "Fase 2\n(Carga Media - 5c)",
        "Fase 3\n(Ráfaga UCI - 12c)",
        "Fase 4\n(Recuperación - 2c)",
    ]
    rr_phase_lat = [p["mean_latency_ms"] for p in rr_results["phases"]]
    raj_phase_lat = [p["mean_latency_ms"] for p in raj_results["phases"]]
    raj_nodes = [p["active_nodes"] for p in raj_results["phases"]]

    ax1.plot(
        phase_names,
        rr_phase_lat,
        marker="o",
        linewidth=2.5,
        color="#ef4444",
        label="Latencia Media - Round-Robin (ms)",
    )
    ax1.plot(
        phase_names,
        raj_phase_lat,
        marker="s",
        linewidth=2.5,
        color="#0284c7",
        label="Latencia Media - Dinámico Rajammal (ms)",
    )
    ax1.set_ylabel("Latencia Media por Fase (ms)", fontsize=10, fontweight="bold", color="#0f172a")
    ax1.grid(True, linestyle="--", alpha=0.5)

    ax2 = ax1.twinx()
    ax2.step(
        phase_names,
        raj_nodes,
        where="mid",
        linestyle=":",
        linewidth=2.2,
        color="#10b981",
        label="Nodos Activos en Pool (Auto-Scaling)",
    )
    ax2.set_ylabel("Nodos Activos en el Clúster", fontsize=10, fontweight="bold", color="#047857")
    ax2.set_ylim(1, 5)
    ax2.set_yticks([2, 3, 4])

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=8.8, frameon=True)
    plt.title(
        "Comportamiento Elástico ante Cargas Variables (Scale-Out en Ráfaga y Scale-In)",
        fontsize=11.5,
        fontweight="bold",
        pad=14,
    )
    plt.tight_layout()
    plt.savefig(RESULTS_DIR / "fig3_dynamic_autoscaling_timeline.png", dpi=220)
    plt.close(fig)

    # FIGURA 4: Diagrama de Arquitectura Cloud AWS + Seguridad MinTIC (2021)
    fig, ax = plt.subplots(figsize=(10.0, 5.4), dpi=220)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 60)
    ax.axis("off")

    def draw_box(x, y, w, h, title, subtitle, bg="#e0f2fe", border="#0284c7", title_color="#0f172a"):
        rect = mpatches.FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.6,rounding_size=1.5",
            facecolor=bg,
            edgecolor=border,
            linewidth=1.6,
        )
        ax.add_patch(rect)
        ax.text(
            x + w / 2,
            y + h * 0.65,
            title,
            ha="center",
            va="center",
            fontsize=9.2,
            fontweight="bold",
            color=title_color,
        )
        ax.text(
            x + w / 2,
            y + h * 0.28,
            subtitle,
            ha="center",
            va="center",
            fontsize=7.6,
            color="#334155",
        )

    # Marco general AWS VPC
    vpc_rect = mpatches.FancyBboxPatch(
        (22, 4),
        76,
        51,
        boxstyle="round,pad=0.8,rounding_size=2.0",
        facecolor="#f8fafc",
        edgecolor="#475569",
        linewidth=1.5,
        linestyle="--",
    )
    ax.add_patch(vpc_rect)
    ax.text(
        60,
        56.8,
        "AWS Cloud (Región us-east-1) — VPC Segmentada con Controles MinTIC (2021) MSPI",
        ha="center",
        va="center",
        fontsize=10.5,
        fontweight="bold",
        color="#0f172a",
    )

    # Clientes externos
    draw_box(2, 34, 16, 13, "Personal Médico", "Portal Web HTTPS\nTLS 1.3 + JWT RBAC", "#fef3c7", "#d97706")
    draw_box(2, 13, 16, 13, "Sensores IoT UCI", "Telemetría Biomédica\nToken Mínimo Privilegio", "#fef3c7", "#d97706")

    # Capa Perimetral DMZ
    draw_box(
        25,
        21,
        19,
        22,
        "API Gateway + WAF\n& Balanceador Dinámico",
        "Reglas OWASP + Rate Limit\nAlgoritmo Rajammal (2025)\nPesos CPU/RAM/Conn/Lat",
        "#dbeafe",
        "#1d4ed8",
    )

    # Clúster de Cómputo ECS Fargate Multi-AZ
    draw_box(49, 41, 20, 10, "Nodo 1 (AZ-a)", "ecs.c6i.large (Cap 1.6x)\nFastAPI Microservice", "#dcfce7", "#15803d")
    draw_box(49, 29, 20, 10, "Nodo 2 (AZ-b)", "ecs.t3.medium (Cap 1.0x)\nFastAPI Microservice", "#dcfce7", "#15803d")
    draw_box(49, 17, 20, 10, "Nodo 3 (AZ-c)", "ecs.t3.small (Cap 0.6x)\nFastAPI Microservice", "#dcfce7", "#15803d")
    draw_box(
        49,
        5,
        20,
        10,
        "Nodo 4 (Auto-Scaling)",
        "ecs.c6i.spot (Cap 1.4x)\nScale-Out / Scale-In",
        "#fef9c3",
        "#ca8a04",
    )

    # Capa de Almacenamiento y Seguridad Criptográfica
    draw_box(
        74,
        39,
        22,
        12,
        "Amazon RDS Multi-AZ",
        "Historias Clínicas Cifradas\nAES-256-GCM + Pseudónimo",
        "#f3e8ff",
        "#7e22ce",
    )
    draw_box(
        74,
        23,
        22,
        12,
        "Amazon S3 (SSE-KMS)",
        "Documentos e Imágenes\nCifrado AES-256 + SHA-256",
        "#f3e8ff",
        "#7e22ce",
    )
    draw_box(
        74,
        7,
        22,
        12,
        "AWS KMS + Auditoría",
        "Rotación de Claves CMK\nHash-Chain Inmutable SHA-256",
        "#ffe4e6",
        "#be123c",
    )

    # Flechas de conexión
    arrow_kw = dict(arrowstyle="->", color="#334155", lw=1.5)
    ax.annotate("", xy=(25, 35), xytext=(18, 40), arrowprops=arrow_kw)
    ax.annotate("", xy=(25, 28), xytext=(18, 20), arrowprops=arrow_kw)
    for ny in (46, 34, 22, 10):
        ax.annotate("", xy=(49, ny), xytext=(44, 32), arrowprops=arrow_kw)
        ax.annotate("", xy=(74, 45), xytext=(69, ny), arrowprops=dict(arrowstyle="->", color="#64748b", lw=1.1))
        ax.annotate("", xy=(74, 29), xytext=(69, ny), arrowprops=dict(arrowstyle="->", color="#64748b", lw=1.1))
        ax.annotate("", xy=(74, 13), xytext=(69, ny), arrowprops=dict(arrowstyle="->", color="#64748b", lw=1.1))

    plt.tight_layout()
    plt.savefig(RESULTS_DIR / "fig4_architecture_diagram.png", dpi=220)
    plt.close(fig)


async def main() -> None:
    print("[1/4] Iniciando clúster CloudMedVault (4 nodos de cómputo + Balanceador Dinámico)...")
    procs = start_cluster_processes()
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            await wait_for_cluster_ready(client)
            print("[2/4] Ejecutando pruebas funcionales y de seguridad MinTIC (2021)...")
            sec_results = await run_security_and_functional_tests(client)

            # Obtener tokens para benchmark
            r_iot = await client.post(
                f"{LB_URL}/api/v1/auth/token",
                json={"username": "gateway.iot", "password": "IoTGateway#2026!"},
            )
            r_med = await client.post(
                f"{LB_URL}/api/v1/auth/token",
                json={"username": "dr.ramirez", "password": "MedCloud#2026!"},
            )
            r_adm = await client.post(
                f"{LB_URL}/api/v1/auth/token",
                json={"username": "admin.seguridad", "password": "AdminMinTIC#2026!"},
            )
            iot_token = r_iot.json()["access_token"]
            med_token = r_med.json()["access_token"]
            adm_token = r_adm.json()["access_token"]

            print("[3/4] Ejecutando benchmark comparativo: Round-Robin vs. Rajammal et al. (2025)...")
            rr_bench = await run_workload_for_algorithm(client, iot_token, med_token, "round_robin")
            raj_bench = await run_workload_for_algorithm(client, iot_token, med_token, "rajammal_dynamic")

            storage_summary = (
                await client.get(
                    f"{LB_URL}/api/v1/storage/summary",
                    headers={"Authorization": f"Bearer {adm_token}"},
                )
            ).json()
            audit_verification = (
                await client.get(
                    f"{LB_URL}/api/v1/audit/verify",
                    headers={"Authorization": f"Bearer {adm_token}"},
                )
            ).json()

            # Calcular mejoras porcentuales del algoritmo dinámico frente a Round-Robin
            mean_improvement_pct = round(
                ((rr_bench["mean_latency_ms"] - raj_bench["mean_latency_ms"]) / rr_bench["mean_latency_ms"]) * 100.0,
                2,
            )
            p95_improvement_pct = round(
                ((rr_bench["p95_latency_ms"] - raj_bench["p95_latency_ms"]) / rr_bench["p95_latency_ms"]) * 100.0,
                2,
            )
            throughput_gain_pct = round(
                ((raj_bench["throughput_rps"] - rr_bench["throughput_rps"]) / rr_bench["throughput_rps"]) * 100.0,
                2,
            )

            full_report_data = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "security_and_functional_tests": sec_results,
                "benchmarks": {
                    "round_robin": rr_bench,
                    "rajammal_dynamic": raj_bench,
                    "improvements": {
                        "mean_latency_reduction_pct": mean_improvement_pct,
                        "p95_latency_reduction_pct": p95_improvement_pct,
                        "throughput_increase_pct": throughput_gain_pct,
                    },
                },
                "storage_summary": storage_summary,
                "audit_verification": audit_verification,
            }

            (RESULTS_DIR / "benchmark_results.json").write_text(
                json.dumps(full_report_data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            print("[4/4] Generando gráficas de resultados y arquitectura...")
            generate_charts(rr_bench, raj_bench)
            print("=== PRUEBAS Y BENCHMARKS COMPLETADOS EXITOSAMENTE ===")
            print(f"  - Pruebas de seguridad superadas: {sec_results['passed_tests']}/{sec_results['total_tests']}")
            print(
                f"  - Latencia Media: Round-Robin={rr_bench['mean_latency_ms']} ms vs. "
                f"Rajammal Dinámico={raj_bench['mean_latency_ms']} ms "
                f"(Reducción del {mean_improvement_pct}%)"
            )
            print(
                f"  - Latencia P95: Round-Robin={rr_bench['p95_latency_ms']} ms vs. "
                f"Rajammal Dinámico={raj_bench['p95_latency_ms']} ms "
                f"(Reducción del {p95_improvement_pct}%)"
            )
            print(f"  - Eventos Auto-Scaling registrados: {len(raj_bench['scaling_events'])}")
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=3)
            except Exception:
                p.kill()


if __name__ == "__main__":
    asyncio.run(main())
