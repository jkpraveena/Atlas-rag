"""SQLite audit trail for every ask() call and eval run -- same
zero-infrastructure philosophy as this author's other projects."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List, Optional

from src.models import AskResult, EvalRunSummary

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "rag_history.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS queries (
    query_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    question TEXT NOT NULL,
    chunking_strategy TEXT NOT NULL,
    used_hybrid INTEGER NOT NULL,
    generation_provider TEXT NOT NULL,
    composite_confidence REAL NOT NULL,
    total_latency_ms REAL NOT NULL,
    result_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_queries_timestamp ON queries(timestamp);

CREATE TABLE IF NOT EXISTS eval_runs (
    run_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    chunking_strategy TEXT NOT NULL,
    pass_rate REAL NOT NULL,
    result_json TEXT NOT NULL
);
"""


def _connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    return conn


def save_query(result: AskResult, db_path: Path = DB_PATH) -> None:
    conn = _connect(db_path)
    with conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO queries
                (query_id, timestamp, question, chunking_strategy, used_hybrid,
                 generation_provider, composite_confidence, total_latency_ms, result_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.query_id, result.timestamp.isoformat(), result.question,
                result.chunking_strategy.value, int(result.used_hybrid),
                result.generation_provider, result.confidence.composite,
                result.total_latency_ms, result.model_dump_json(),
            ),
        )
    conn.close()


def get_query(query_id: str, db_path: Path = DB_PATH) -> Optional[AskResult]:
    conn = _connect(db_path)
    row = conn.execute("SELECT result_json FROM queries WHERE query_id = ?", (query_id,)).fetchone()
    conn.close()
    return AskResult.model_validate_json(row[0]) if row else None


def list_recent_queries(n: int = 50, db_path: Path = DB_PATH) -> List[AskResult]:
    conn = _connect(db_path)
    rows = conn.execute("SELECT result_json FROM queries ORDER BY timestamp DESC LIMIT ?", (n,)).fetchall()
    conn.close()
    return [AskResult.model_validate_json(r[0]) for r in rows]


def save_eval_run(summary: EvalRunSummary, db_path: Path = DB_PATH) -> None:
    conn = _connect(db_path)
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO eval_runs (run_id, timestamp, chunking_strategy, pass_rate, result_json) VALUES (?, ?, ?, ?, ?)",
            (summary.run_id, summary.timestamp.isoformat(), summary.chunking_strategy.value, summary.pass_rate, summary.model_dump_json()),
        )
    conn.close()


def list_recent_eval_runs(n: int = 20, db_path: Path = DB_PATH) -> List[EvalRunSummary]:
    conn = _connect(db_path)
    rows = conn.execute("SELECT result_json FROM eval_runs ORDER BY timestamp DESC LIMIT ?", (n,)).fetchall()
    conn.close()
    return [EvalRunSummary.model_validate_json(r[0]) for r in rows]


def count_queries(db_path: Path = DB_PATH) -> int:
    conn = _connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM queries").fetchone()[0]
    conn.close()
    return count
