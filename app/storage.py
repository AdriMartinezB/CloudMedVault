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
