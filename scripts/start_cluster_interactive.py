"""
Iniciador Interactivo del Clúster CloudMedVault (4 Nodos de Cómputo + Balanceador Dinámico).
Permite levantar toda la infraestructura en una sola terminal para explorarla desde el navegador.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
PYTHON_BIN = ROOT_DIR / ".venv" / "bin" / "python3"
if not PYTHON_BIN.exists():
    PYTHON_BIN = Path(sys.executable)

NODES_CONFIG = [
    {"id": "node-1", "port": 8001, "type": "ecs.c6i.large", "cap": "1.6", "az": "us-east-1a"},
    {"id": "node-2", "port": 8002, "type": "ecs.t3.medium", "cap": "1.0", "az": "us-east-1b"},
    {"id": "node-3", "port": 8003, "type": "ecs.t3.small", "cap": "0.6", "az": "us-east-1c"},
    {"id": "node-4", "port": 8004, "type": "ecs.c6i.large.spot", "cap": "1.4", "az": "us-east-1a"},
]


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT_DIR))
    from app.storage import CloudStorageManager

    CloudStorageManager(db_path=DATA_DIR / "cloudmedvault.db", s3_dir=DATA_DIR / "s3_bucket")

    procs = []
    try:
        for n in NODES_CONFIG:
            env = os.environ.copy()
            env["CLOUDMED_NODE_ID"] = n["id"]
            env["CLOUDMED_INSTANCE_TYPE"] = n["type"]
            env["CLOUDMED_NODE_CAPACITY"] = n["cap"]
            env["CLOUDMED_AZ"] = n["az"]
            env["CLOUDMED_DATA_DIR"] = str(DATA_DIR)
            p = subprocess.Popen(
                [
                    str(PYTHON_BIN),
                    "-m",
                    "uvicorn",
                    "app.node_service:app",
                    "--host",
                    "0.0.0.0",
                    "--port",
                    str(n["port"]),
                    "--log-level",
                    "warning",
                ],
                cwd=str(ROOT_DIR),
                env=env,
            )
            procs.append(p)

        lb_env = os.environ.copy()
        lb_env["CLOUDMED_RATE_LIMIT"] = "250"
        lb_proc = subprocess.Popen(
            [
                str(PYTHON_BIN),
                "-m",
                "uvicorn",
                "app.load_balancer:app",
                "--host",
                "0.0.0.0",
                "--port",
                "8080",
                "--log-level",
                "info",
            ],
            cwd=str(ROOT_DIR),
            env=lb_env,
        )
        procs.append(lb_proc)

        print("\n" + "=" * 72)
        print("  CLÚSTER CLOUDMEDVAULT ACTIVO Y ESCUCHANDO PETICIONES")
        print("=" * 72)
        print("  • Consola Web del Balanceador Dinámico : http://localhost:8080/")
        print("  • Estado JSON en Tiempo Real (Cluster) : http://localhost:8080/lb/status")
        print("  • Documentación Interactiva Swagger LB : http://localhost:8080/docs")
        print("  • Swagger UI Nodo 1 (Directo API)      : http://localhost:8001/docs")
        print("-" * 72)
        print("  Credenciales de prueba (POST /api/v1/auth/token):")
        print("    - Médico    : usuario 'dr.ramirez'      | clave 'MedCloud#2026!'")
        print("    - Admin MSPI: usuario 'admin.seguridad' | clave 'AdminMinTIC#2026!'")
        print("    - Sensor IoT: usuario 'gateway.iot'     | clave 'IoTGateway#2026!'")
        print("=" * 72)
        print("Presiona Ctrl+C para detener todos los nodos del clúster.\n")

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nDeteniendo clúster CloudMedVault...")
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=3)
            except Exception:
                p.kill()


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    main()
