"""
Capa de Almacenamiento Cloud Híbrido:
1. Base de Datos Transaccional (simulando AWS RDS Multi-AZ cifrado) en SQLite WAL.
2. Almacenamiento de Objetos (simulando Amazon S3 con Server-Side Encryption SSE-KMS).
3. Cadena de Auditoría Inmutable (Hash-Chain SHA-256) según MinTIC (2021).
"""

import hashlib
import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.security import CryptoVault, pseudonymize_pii


BASE_DATA_DIR = Path(os.environ.get("CLOUDMED_DATA_DIR", "data"))
DB_PATH = BASE_DATA_DIR / "cloudmedvault.db"
S3_BUCKET_DIR = BASE_DATA_DIR / "s3_bucket"


class CloudStorageManager:
    """Gestiona la persistencia en base de datos relacional y bucket de objetos cifrados."""

    def __init__(self, db_path: Path = DB_PATH, s3_dir: Path = S3_BUCKET_DIR):
        self.db_path = Path(db_path)
        self.s3_dir = Path(s3_dir)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.s3_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.record_vault = CryptoVault("rds-clinical-records-kms")
        self.s3_vault = CryptoVault("s3-clinical-objects-kms")
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000;")
        return conn

    def _init_db(self) -> None:
        with self._lock:
            for attempt in range(10):
                conn = self._get_conn()
                try:
                    conn.execute("PRAGMA journal_mode=WAL;")
                    conn.execute("PRAGMA synchronous=NORMAL;")
                    conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS clinical_records (
                        record_id TEXT PRIMARY KEY,
                        patient_pseudonym TEXT NOT NULL,
                        specialty TEXT NOT NULL,
                        severity_level TEXT NOT NULL,
                        encrypted_payload TEXT NOT NULL,
                        payload_sha256 TEXT NOT NULL,
                        created_by TEXT NOT NULL,
                        processed_by_node TEXT NOT NULL,
                        created_at REAL NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS s3_objects_metadata (
                        object_key TEXT PRIMARY KEY,
                        record_id TEXT NOT NULL,
                        filename TEXT NOT NULL,
                        content_type TEXT NOT NULL,
                        size_bytes INTEGER NOT NULL,
                        sha256_plaintext TEXT NOT NULL,
                        storage_path TEXT NOT NULL,
                        uploaded_by TEXT NOT NULL,
                        processed_by_node TEXT NOT NULL,
                        created_at REAL NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS iot_telemetry (
                        telemetry_id TEXT PRIMARY KEY,
                        device_id TEXT NOT NULL,
                        patient_pseudonym TEXT NOT NULL,
                        heart_rate_bpm INTEGER NOT NULL,
                        spo2_percent REAL NOT NULL,
                        systolic_bp INTEGER NOT NULL,
                        diastolic_bp INTEGER NOT NULL,
                        temperature_c REAL NOT NULL,
                        anomaly_detected INTEGER NOT NULL,
                        risk_score REAL NOT NULL,
                        processed_by_node TEXT NOT NULL,
                        created_at REAL NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS audit_logs (
                        seq_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_id TEXT NOT NULL,
                        timestamp REAL NOT NULL,
                        actor TEXT NOT NULL,
                        role TEXT NOT NULL,
                        action TEXT NOT NULL,
                        resource_id TEXT NOT NULL,
                        node_id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        prev_hash TEXT NOT NULL,
                        entry_hash TEXT NOT NULL
                    );
                    """
                    )
                    conn.commit()
                    break
                except sqlite3.OperationalError:
                    if attempt == 9:
                        raise
                    time.sleep(0.1 * (attempt + 1))
                finally:
                    conn.close()

    def append_audit_log(
        self,
        actor: str,
        role: str,
        action: str,
        resource_id: str,
        node_id: str,
        status: str = "SUCCESS",
    ) -> Dict[str, Any]:
        """Registra un evento en la cadena de auditoría inmutable con encadenamiento SHA-256."""
        with self._lock:
            for attempt in range(10):
                conn = self._get_conn()
                try:
                    conn.isolation_level = None
                    conn.execute("BEGIN IMMEDIATE")
                    cur = conn.execute(
                        "SELECT entry_hash FROM audit_logs ORDER BY seq_id DESC LIMIT 1"
                    )
                    row = cur.fetchone()
                    prev_hash = row["entry_hash"] if row else "0" * 64
                    event_id = f"AUD-{uuid.uuid4().hex[:12].upper()}"
                    ts = round(time.time(), 6)
                    canonical = f"{event_id}|{ts:.6f}|{actor}|{role}|{action}|{resource_id}|{node_id}|{status}|{prev_hash}"
                    entry_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                    conn.execute(
                        """
                        INSERT INTO audit_logs
                        (event_id, timestamp, actor, role, action, resource_id, node_id, status, prev_hash, entry_hash)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (event_id, ts, actor, role, action, resource_id, node_id, status, prev_hash, entry_hash),
                    )
                    conn.execute("COMMIT")
                    return {
                        "event_id": event_id,
                        "timestamp": ts,
                        "prev_hash": prev_hash,
                        "entry_hash": entry_hash,
                    }
                except sqlite3.OperationalError:
                    try:
                        conn.execute("ROLLBACK")
                    except Exception:
                        pass
                    if attempt == 9:
                        raise
                    time.sleep(0.05 * (attempt + 1))
                finally:
                    conn.close()
        raise RuntimeError("No se pudo registrar el evento de auditoría")

    def verify_audit_chain(self) -> Dict[str, Any]:
        """Verifica criptográficamente toda la cadena de auditoría para detectar alteraciones."""
        conn = self._get_conn()
        try:
            rows = conn.execute("SELECT * FROM audit_logs ORDER BY seq_id ASC").fetchall()
            expected_prev = "0" * 64
            verified_count = 0
            for r in rows:
                canonical = (
                    f"{r['event_id']}|{r['timestamp']:.6f}|{r['actor']}|{r['role']}|"
                    f"{r['action']}|{r['resource_id']}|{r['node_id']}|{r['status']}|{r['prev_hash']}"
                )
                recalculated = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                if r["prev_hash"] != expected_prev or recalculated != r["entry_hash"]:
                    return {
                        "intact": False,
                        "verified_records": verified_count,
                        "corrupted_seq_id": r["seq_id"],
                    }
                expected_prev = r["entry_hash"]
                verified_count += 1
            return {
                "intact": True,
                "verified_records": verified_count,
                "latest_hash": expected_prev,
            }
        finally:
            conn.close()

    def create_clinical_record(
        self,
        national_id: str,
        patient_name: str,
        specialty: str,
        diagnosis: str,
        treatment: str,
        severity_level: str,
        vital_notes: Dict[str, Any],
        actor: str,
        role: str,
        node_id: str,
    ) -> Dict[str, Any]:
        """Guarda una historia clínica cifrada con AES-256-GCM y pseudonimiza la cédula del paciente."""
        record_id = f"REC-{uuid.uuid4().hex[:10].upper()}"
        patient_pseudonym = pseudonymize_pii(national_id)
        sensitive_body = {
            "patient_name": patient_name,
            "national_id_masked": f"***{national_id[-4:]}" if len(national_id) >= 4 else "****",
            "diagnosis": diagnosis,
            "treatment": treatment,
            "vital_notes": vital_notes,
        }
        encrypted_str = self.record_vault.encrypt_json(sensitive_body, aad_str=record_id)
        envelope = json.loads(encrypted_str)
        created_at = time.time()

        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO clinical_records
                    (record_id, patient_pseudonym, specialty, severity_level, encrypted_payload,
                     payload_sha256, created_by, processed_by_node, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record_id,
                        patient_pseudonym,
                        specialty,
                        severity_level,
                        encrypted_str,
                        envelope["sha256_integrity"],
                        actor,
                        node_id,
                        created_at,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

        audit = self.append_audit_log(actor, role, "CREATE_CLINICAL_RECORD", record_id, node_id)
        return {
            "record_id": record_id,
            "patient_pseudonym": patient_pseudonym,
            "specialty": specialty,
            "severity_level": severity_level,
            "encryption": "AES-256-GCM (AWS KMS Envelope)",
            "sha256_integrity": envelope["sha256_integrity"],
            "processed_by_node": node_id,
            "audit_event_id": audit["event_id"],
            "created_at": created_at,
        }

    def get_clinical_record(
        self, record_id: str, actor: str, role: str, node_id: str
    ) -> Optional[Dict[str, Any]]:
        """Recupera y descifra una historia clínica verificando su firma de integridad."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM clinical_records WHERE record_id = ?", (record_id,)
            ).fetchone()
        finally:
            conn.close()

        if not row:
            self.append_audit_log(actor, role, "READ_CLINICAL_RECORD_NOT_FOUND", record_id, node_id, "NOT_FOUND")
