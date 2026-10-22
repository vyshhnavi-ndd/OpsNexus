"""Small local SQLite store for dashboard data requests.

This is independent of Exasol: requests are user workflow records, not source
or staging data. Set OPSNEXUS_REQUEST_DB to select a writable database path.
"""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


PRIORITIES = {"low": "Low", "medium": "Medium", "high": "High", "urgent": "Urgent"}


def _connect(database_path: str | Path) -> sqlite3.Connection:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        """CREATE TABLE IF NOT EXISTS data_requests (
            id TEXT PRIMARY KEY,
            dataset TEXT NOT NULL,
            reason TEXT NOT NULL,
            priority TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending',
            created_at TEXT NOT NULL
        )"""
    )
    return connection


def list_requests(database_path: str | Path, limit: int = 200) -> list[dict]:
    with closing(_connect(database_path)) as connection:
        rows = connection.execute(
            "SELECT id, dataset, reason, priority, status, created_at "
            "FROM data_requests ORDER BY created_at DESC, id DESC LIMIT ?",
            (max(1, min(int(limit), 200)),),
        ).fetchall()
    return [dict(row) for row in rows]


def create_request(database_path: str | Path, dataset: str, reason: str, priority: str) -> dict:
    normalized_priority = PRIORITIES.get(priority.strip().casefold())
    dataset, reason = dataset.strip(), reason.strip()
    if not dataset or len(dataset) > 200:
        raise ValueError("dataset must contain 1 to 200 characters")
    if not reason or len(reason) > 4000:
        raise ValueError("reason must contain 1 to 4000 characters")
    if not normalized_priority:
        raise ValueError("priority must be Low, Medium, High, or Urgent")

    record = {
        "id": f"REQ-{uuid.uuid4().hex[:12].upper()}",
        "dataset": dataset,
        "reason": reason,
        "priority": normalized_priority,
        "status": "Pending",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    with closing(_connect(database_path)) as connection:
        with connection:
            connection.execute(
                "INSERT INTO data_requests (id, dataset, reason, priority, status, created_at) "
                "VALUES (:id, :dataset, :reason, :priority, :status, :created_at)",
                record,
            )
    return record
