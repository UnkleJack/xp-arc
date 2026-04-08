"""
Intelligence Pool — The constitutional ground of XP-Arc.

Single shared state surface. All entities flow through here.
SQLite state machine with full constitutional schema (v1.4).
"""

import sqlite3
import hashlib
import json
import time
from datetime import datetime, timezone


# Constitutional status transitions (Article III, Section 3.2)
VALID_TRANSITIONS = {
    'raw': ['processing'],
    'processing': ['pending_qa', 'failed', 'fractured'],
    'pending_qa': ['completed', 'failed'],
    'failed': ['processing'],  # retry
    'fractured': ['stitchable'],
    'stitchable': ['mapped', 'failed'],
    'mapped': ['completed', 'failed'],
    'completed': [],  # terminal
}

STATION_DEFAULTS_SLA = {
    'chef_de_cuisine': 300,
    'sous_chef': 120,
    'expeditor': 30,
    'saucier': 180,
    'garde_manger': 60,
    'patissier': 60,
    'commis': 120,
    'plongeur': 45,
}


def compute_payload_hash(entity_type: str, entity_value: str) -> str:
    """SHA-256 of the entity payload at ingestion. Immutable once sealed."""
    payload = json.dumps({'type': entity_type, 'value': entity_value}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


class IntelligencePool:
    """
    The Pass. Every dish moves through it. Nothing reaches the guest
    without crossing it.

    SQLite-backed state machine. Persistent. Auditable.
    """

    def __init__(self, db_path="xp_arc.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._event_log = []  # In-memory event buffer for DRAGON
        self.setup()

    def setup(self):
        with self.conn:
            # Entities — Article III
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL,
                    value TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'raw',
                    payload_hash TEXT NOT NULL,
                    station TEXT,
                    confidence REAL,
                    notes TEXT,
                    sla_seconds INTEGER DEFAULT 60,
                    assigned_at TEXT,
                    completed_at TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    aboyeur_signature TEXT,
                    fallback_role INTEGER DEFAULT 0,
                    fracture_id TEXT,
                    parent_task_id INTEGER,
                    rejection_count INTEGER DEFAULT 0,
                    max_rejections INTEGER DEFAULT 3,
                    sla_suspended INTEGER DEFAULT 0,
                    UNIQUE(type, value)
                )
            """)

            # Edges — relationship graph
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    relationship TEXT NOT NULL,
                    target TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)

            # Station registry
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS station_registry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    station_id TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    handles_types TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    is_primary INTEGER DEFAULT 1,
                    registered_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)

            # SpaZzMatiC findings
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS findings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    severity TEXT NOT NULL,
                    source TEXT NOT NULL,
                    message TEXT NOT NULL,
                    detail TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)

            # Zoran's Law metrics history
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS zorans_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stability_quotient REAL NOT NULL,
                    primary_role_occupancy REAL NOT NULL,
                    system_state TEXT NOT NULL,
                    active_stations INTEGER,
                    primary_stations INTEGER,
                    tasks_completed INTEGER,
                    tasks_ingested INTEGER,
                    measured_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)

            # Pipeline events log (for DRAGON timeline)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    message TEXT NOT NULL,
                    detail TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)

    # ─── Entity Operations ───

    def add_entity(self, ent_type: str, value: str, sla_seconds: int = 60,
                   parent_task_id: int = None) -> int | None:
        """Write a new raw entity to the pool. Returns entity ID or None if duplicate."""
        payload_hash = compute_payload_hash(ent_type, value)
        try:
            with self.conn:
                cur = self.conn.execute("""
                    INSERT INTO entities (type, value, status, payload_hash, sla_seconds, parent_task_id)
                    VALUES (?, ?, 'raw', ?, ?, ?)
                """, (ent_type, value, payload_hash, sla_seconds, parent_task_id))
                eid = cur.lastrowid
                self._log_event('entity_added', 'pool', f"New {ent_type}: {value}", f"id={eid}")
                return eid
        except sqlite3.IntegrityError:
            return None

    def transition_status(self, entity_id: int, new_status: str, station: str = None,
                          confidence: float = None, notes: str = None) -> bool:
        """
        Atomic status transition with constitutional validation.
        Unauthorized transitions are rejected.
        """
        row = self.conn.execute(
            "SELECT status FROM entities WHERE id = ?", (entity_id,)
        ).fetchone()

        if not row:
            return False

        current = row['status']
        if new_status not in VALID_TRANSITIONS.get(current, []):
            self._log_event('status_violation', 'pool',
                            f"Unauthorized transition: {current} → {new_status}",
                            f"entity_id={entity_id}")
            return False

        updates = {"status": new_status}
        if new_status == 'processing':
            updates["assigned_at"] = datetime.now(timezone.utc).isoformat()
            if station:
                updates["station"] = station
        elif new_status in ('completed', 'mapped'):
            updates["completed_at"] = datetime.now(timezone.utc).isoformat()
        if confidence is not None:
            updates["confidence"] = confidence
        if notes:
            updates["notes"] = notes

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [entity_id]

        with self.conn:
            self.conn.execute(
                f"UPDATE entities SET {set_clause} WHERE id = ?", values
            )

        self._log_event('status_transition', station or 'pool',
                        f"Entity {entity_id}: {current} → {new_status}")
        return True

    def set_aboyeur_signature(self, entity_id: int, signature: str):
        with self.conn:
            self.conn.execute(
                "UPDATE entities SET aboyeur_signature = ? WHERE id = ?",
                (signature, entity_id)
            )

    def increment_rejection(self, entity_id: int) -> int:
        """Increment rejection count. Returns new count."""
        with self.conn:
            self.conn.execute(
                "UPDATE entities SET rejection_count = rejection_count + 1 WHERE id = ?",
                (entity_id,)
            )
        row = self.conn.execute(
            "SELECT rejection_count, max_rejections FROM entities WHERE id = ?",
            (entity_id,)
        ).fetchone()
        return row['rejection_count'] if row else 0

    def get_next_raw(self):
        """Get next unprocessed entity."""
        return self.conn.execute(
            "SELECT * FROM entities WHERE status = 'raw' ORDER BY id LIMIT 1"
        ).fetchone()

    def get_entity(self, entity_id: int):
        return self.conn.execute(
            "SELECT * FROM entities WHERE id = ?", (entity_id,)
        ).fetchone()

    def get_entities_by_status(self, status: str):
        return self.conn.execute(
            "SELECT * FROM entities WHERE status = ?", (status,)
        ).fetchall()

    def get_all_entities(self):
        return self.conn.execute(
            "SELECT * FROM entities ORDER BY id"
        ).fetchall()

    def count_entities(self):
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM entities").fetchone()
        return row['cnt']

    # ─── Edge Operations ───

    def add_edge(self, source: str, rel: str, target: str):
        with self.conn:
            self.conn.execute(
                "INSERT INTO edges (source, relationship, target) VALUES (?, ?, ?)",
                (source, rel, target)
            )
        self._log_event('edge_added', 'pool', f"{source} --({rel})--> {target}")

    def get_all_edges(self):
        return self.conn.execute(
            "SELECT * FROM edges ORDER BY id"
        ).fetchall()

    # ─── Station Registry ───

    def register_station(self, station_id: str, name: str, handles_types: list,
                         is_primary: bool = True):
        types_str = json.dumps(handles_types)
        try:
            with self.conn:
                self.conn.execute("""
                    INSERT OR REPLACE INTO station_registry
                    (station_id, name, handles_types, is_primary)
                    VALUES (?, ?, ?, ?)
                """, (station_id, name, types_str, int(is_primary)))
        except sqlite3.IntegrityError:
            pass

    def get_active_stations(self):
        return self.conn.execute(
            "SELECT * FROM station_registry WHERE status = 'active'"
        ).fetchall()

    def set_station_status(self, station_id: str, status: str):
        with self.conn:
            self.conn.execute(
                "UPDATE station_registry SET status = ? WHERE station_id = ?",
                (status, station_id)
            )

    # ─── Findings (SpaZzMatiC) ───

    def add_finding(self, severity: str, source: str, message: str, detail: str = None):
        with self.conn:
            self.conn.execute(
                "INSERT INTO findings (severity, source, message, detail) VALUES (?, ?, ?, ?)",
                (severity, source, message, detail)
            )
        self._log_event('finding', source, f"[{severity.upper()}] {message}")

    def get_findings(self):
        return self.conn.execute(
            "SELECT * FROM findings ORDER BY id DESC"
        ).fetchall()

    # ─── Zoran Metrics ───

    def record_zorans_metrics(self, s: float, pro: float, state: str,
                              active: int, primary: int, completed: int, ingested: int):
        with self.conn:
            self.conn.execute("""
                INSERT INTO zorans_metrics
                (stability_quotient, primary_role_occupancy, system_state,
                 active_stations, primary_stations, tasks_completed, tasks_ingested)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (s, pro, state, active, primary, completed, ingested))

    def get_zorans_history(self):
        return self.conn.execute(
            "SELECT * FROM zorans_metrics ORDER BY id"
        ).fetchall()

    # ─── Events ───

    def _log_event(self, event_type: str, source: str, message: str, detail: str = None):
        with self.conn:
            self.conn.execute(
                "INSERT INTO events (event_type, source, message, detail) VALUES (?, ?, ?, ?)",
                (event_type, source, message, detail)
            )

    def get_events(self, limit: int = 200):
        return self.conn.execute(
            "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()

    # ─── Orphan Detection (for Plongeur) ───

    def get_orphaned_entities(self, threshold_seconds: int = 300):
        """Entities stuck in processing beyond their SLA."""
        return self.conn.execute("""
            SELECT * FROM entities
            WHERE status = 'processing'
            AND assigned_at IS NOT NULL
            AND sla_suspended = 0
            AND (julianday('now') - julianday(assigned_at)) * 86400 > sla_seconds
        """).fetchall()

    # ─── Stats for Zoran's Law ───

    def get_stats(self) -> dict:
        """Aggregate pool statistics."""
        rows = self.conn.execute("""
            SELECT status, COUNT(*) as cnt,
                   COALESCE(SUM(sla_seconds), 0) as total_sla
            FROM entities GROUP BY status
        """).fetchall()

        stats = {}
        for r in rows:
            stats[r['status']] = {'count': r['cnt'], 'total_sla': r['total_sla']}
        return stats

    # ─── Export for DRAGON ───

    def export_state(self) -> dict:
        """Full pool state export as JSON-serializable dict."""
        entities = [dict(row) for row in self.get_all_entities()]
        edges = [dict(row) for row in self.get_all_edges()]
        stations = [dict(row) for row in self.get_active_stations()]
        findings = [dict(row) for row in self.get_findings()]
        zorans = [dict(row) for row in self.get_zorans_history()]
        events = [dict(row) for row in self.get_events(500)]

        stats = self.get_stats()

        return {
            'meta': {
                'exported_at': datetime.now(timezone.utc).isoformat(),
                'db_path': self.db_path,
                'version': '0.2.0',
                'protocol': 'XP-Arc',
            },
            'entities': entities,
            'edges': edges,
            'stations': stations,
            'findings': findings,
            'zorans_metrics': zorans,
            'events': list(reversed(events)),  # chronological
            'stats': {k: dict(v) if isinstance(v, sqlite3.Row) else v for k, v in stats.items()},
        }

    def close(self):
        self.conn.close()
