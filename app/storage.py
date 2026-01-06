from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict

from app.settings import get_settings

_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY: set[str] = set()


def _ensure_schema(conn: sqlite3.Connection, db_path: Path) -> None:
    db_key = str(db_path.resolve())
    with _SCHEMA_LOCK:
        if db_key in _SCHEMA_READY:
            return
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dedupe_key TEXT NOT NULL UNIQUE,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dedupe_key TEXT NOT NULL,
                ticket_id INTEGER,
                route_to TEXT,
                severity TEXT,
                notify INTEGER,
                group_id INTEGER,
                assignee_id INTEGER,
                slack_channel TEXT,
                summary TEXT,
                reason TEXT,
                tags TEXT,
                payload TEXT,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER,
                kind TEXT NOT NULL,
                dedupe_key TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                UNIQUE(kind, dedupe_key)
            )
            """
        )
        conn.commit()
        _SCHEMA_READY.add(db_key)


def _get_conn() -> sqlite3.Connection:
    settings = get_settings()
    db_path = Path(settings.DATABASE_PATH)
    conn = sqlite3.connect(db_path)
    _ensure_schema(conn, db_path)
    return conn


def make_dedupe_key(payload: Dict[str, Any]) -> str:
    ticket_id = payload.get("ticket_id")
    event_type = payload.get("type")
    priority = payload.get("priority")
    updated_at = payload.get("updated_at")
    event_id = payload.get("event_id")
    audit_id = payload.get("audit_id")

    def _norm(value: Any) -> str:
        return "" if value is None else str(value)

    base_parts = [_norm(ticket_id), _norm(event_type), _norm(priority)]
    extra_parts = [_norm(updated_at), _norm(event_id), _norm(audit_id)]
    if any(part for part in base_parts + extra_parts):
        parts = base_parts + [part for part in extra_parts if part]
        return "|".join(parts)

    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    return digest[:12]


def try_register_event(dedupe_key: str, payload: Dict[str, Any]) -> bool:
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    conn = _get_conn()
    try:
        with conn:
            conn.execute(
                "INSERT INTO events (dedupe_key, payload) VALUES (?, ?)",
                (dedupe_key, payload_json),
            )
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def save_decision(dedupe_key: str, payload: Dict[str, Any], decision: Dict[str, Any]) -> None:
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    tags = decision.get("tags")
    tags_json = json.dumps(tags, separators=(",", ":"), sort_keys=True) if tags is not None else None
    notify = 1 if decision.get("notify") else 0
    ticket_id = payload.get("ticket_id")
    try:
        ticket_id = int(ticket_id) if ticket_id is not None else None
    except (TypeError, ValueError):
        ticket_id = None
    conn = _get_conn()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO decisions (
                    dedupe_key,
                    ticket_id,
                    route_to,
                    severity,
                    notify,
                    group_id,
                    assignee_id,
                    slack_channel,
                    summary,
                    reason,
                    tags,
                    payload
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dedupe_key,
                    ticket_id,
                    decision.get("route_to"),
                    decision.get("severity"),
                    notify,
                    decision.get("group_id"),
                    decision.get("assignee_id"),
                    decision.get("slack_channel"),
                    decision.get("summary"),
                    decision.get("reason"),
                    tags_json,
                    payload_json,
                ),
            )
    finally:
        conn.close()


def has_notification(kind: str, dedupe_key: str) -> bool:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT 1 FROM notifications WHERE kind = ? AND dedupe_key = ? LIMIT 1",
            (kind, dedupe_key),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def mark_notification(kind: str, dedupe_key: str, ticket_id: int | None) -> None:
    conn = _get_conn()
    try:
        with conn:
            conn.execute(
                "INSERT OR IGNORE INTO notifications (ticket_id, kind, dedupe_key) VALUES (?, ?, ?)",
                (ticket_id, kind, dedupe_key),
            )
    finally:
        conn.close()


def fetch_recent_decisions(limit: int) -> list[Dict[str, Any]]:
    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
                id,
                dedupe_key,
                ticket_id,
                route_to,
                severity,
                notify,
                group_id,
                assignee_id,
                slack_channel,
                summary,
                reason,
                tags,
                payload,
                created_at
            FROM decisions
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        results: list[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            tags = item.get("tags")
            payload = item.get("payload")
            try:
                item["tags"] = json.loads(tags) if tags else None
            except json.JSONDecodeError:
                item["tags"] = tags
            try:
                item["payload"] = json.loads(payload) if payload else None
            except json.JSONDecodeError:
                item["payload"] = payload
            results.append(item)
        return results
    finally:
        conn.close()


def fetch_recent_events(limit: int) -> list[Dict[str, Any]]:
    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
                id,
                dedupe_key,
                payload,
                created_at
            FROM events
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        results: list[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            payload = item.get("payload")
            try:
                item["payload"] = json.loads(payload) if payload else None
            except json.JSONDecodeError:
                item["payload"] = payload
            results.append(item)
        return results
    finally:
        conn.close()


def fetch_latest_payload_for_ticket(ticket_id: int) -> Dict[str, Any] | None:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT payload FROM decisions WHERE ticket_id = ? ORDER BY id DESC LIMIT 1",
            (ticket_id,),
        ).fetchone()
        if not row:
            return None
        payload_json = row[0]
        if not payload_json:
            return None
        try:
            return json.loads(payload_json)
        except json.JSONDecodeError:
            return None
    finally:
        conn.close()


def generate_metrics_csv() -> str:
    conn = _get_conn()
    try:
        total_events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        total_decisions = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
        total_notifications = conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0]

        route_rows = conn.execute(
            "SELECT route_to, COUNT(*) AS count FROM decisions GROUP BY route_to ORDER BY count DESC"
        ).fetchall()
        severity_rows = conn.execute(
            "SELECT severity, COUNT(*) AS count FROM decisions GROUP BY severity ORDER BY count DESC"
        ).fetchall()

        lines = [
            "metric,value",
            f"total_events,{total_events}",
            f"total_decisions,{total_decisions}",
            f"total_notifications,{total_notifications}",
        ]

        lines.append("")
        lines.append("decisions_by_route_to,count")
        for route_to, count in route_rows:
            route_label = "" if route_to is None else str(route_to)
            lines.append(f"{route_label},{count}")

        lines.append("")
        lines.append("decisions_by_severity,count")
        for severity, count in severity_rows:
            severity_label = "" if severity is None else str(severity)
            lines.append(f"{severity_label},{count}")

        return "\n".join(lines) + "\n"
    finally:
        conn.close()
