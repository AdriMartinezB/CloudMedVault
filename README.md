# CloudMedVault — Unidad 3: Seguridad en Entornos de Nube (Actividad 6)

Implementación funcional de una aplicación en la nube (**CloudMedVault**: Gestión de Historias Clínicas Electrónicas, Documentos Clínicos en S3 y Telemetría Biomédica IoT UCI) con:
- **Arquitectura de referencia en AWS** (`ECS Fargate`, `ALB`, `RDS Multi-AZ`, `Amazon S3 SSE-KMS`, `AWS KMS`, `WAFv2`) y despliegue local contenerizado (`Docker Compose`).
- **Cumplimiento de los Lineamientos de Seguridad del MinTIC (2021)** — Modelo de Seguridad y Privacidad de la Información (MSPI) y **Ley 1581 de 2012** (Habeas Data).
- **Balanceo de Carga Dinámico Multicriterio y Auto-Scaling Elástico** basado en **Rajammal et al. (2025)**.

## Estructura del Proyecto

- `app/security.py`: Cifrado autenticado `AES-256-GCM` en reposo, pseudonimización `HMAC-SHA256`, hashing `PBKDF2-HMAC-SHA256`, emisión/validación de tokens `JWT (HS256)` con RBAC (`medico`, `admin`, `iot_sensor`) y reglas WAF OWASP.
- `app/storage.py`: Almacenamiento híbrido Cloud (Base de datos transaccional SQLite WAL simulando Amazon RDS Multi-AZ + Bucket de objetos cifrados simulando Amazon S3 con `SSE-KMS`) y cadena de auditoría inmutable (`Hash-Chain SHA-256`).
- `app/node_service.py`: Microservicio de nodo de cómputo en `FastAPI` con endpoints clínicos, cabeceras de seguridad HTTP (`HSTS`, `CSP`, `X-Frame-Options`) y telemetría QoS en tiempo real (`/health`, `/metrics`).
- `app/load_balancer.py`: Balanceador de carga dinámico adaptativo (`Rajammal et al., 2025`), controlador de `Auto-Scaling` (`Scale-Out` / `Scale-In`), `Rate Limiting` perimetral y consola web interactiva.
- `tests/run_cloud_tests_and_benchmarks.py`: Suite automatizada que levanta el clúster de 4 nodos + balanceador, ejecuta las 7 pruebas de seguridad MinTIC (2021), corre el benchmark comparativo (`Round-Robin` vs. `Rajammal Dinámico`) y genera las gráficas en `results/`.
- `scripts/generate_deliverables.py`: Genera el Informe Técnico en PDF y la Presentación en formatos PPTX y PDF dentro de `entregables/`.
- `Dockerfile`, `docker-compose.yml`, `infra/aws_cloudformation.yaml`: Infraestructura como Código (IaC).

## Ejecución Rápida

```bash
# 1. Ejecutar las pruebas de seguridad, el clúster de 4 nodos y el benchmark comparativo
.venv/bin/python3 tests/run_cloud_tests_and_benchmarks.py
```
