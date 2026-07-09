"""
Intelligence Pool — The constitutional ground of XP-Arc.

Single shared state surface. All entities flow through here.
SQLite state machine with full constitutional schema (v1.5).
"""

import sqlite3
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone


# ─── Module-level HMAC Key Store ─────────────────────────────────────────────

HMAC_KEY_FILE = "station_keys.json"

def _load_station_keys(path: str = HMAC_KEY_FILE) -> dict:
    """Load station HMAC keys from JSON file. Returns {} if not present."""
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def _save_station_keys(keys: dict, path: str = HMAC_KEY_FILE):
    """Persist station HMAC keys to JSON file."""
    with open(path, 'w') as f:
        json.dump(keys, f, indent=2)

def get_station_hmac_key(station_id: str, key_file: str = HMAC_KEY_FILE) -> str | None:
    """Retrieve a station's HMAC key from the key store file.

    Stations call this at startup to retrieve their persistent key.
    Returns None if the station has not been registered yet.
    """
    return _load_station_keys(key_file).get(station_id)

def register_station_with_key(station_id: str, name: str, handles_types: list,
                               is_primary: bool = True,
                               hmac_key: str = None,
                               key_file: str = HMAC_KEY_FILE) -> str:
    """Register a station and persist its HMAC key to key_file.

    Call this at system startup to get the station's key, then pass it
    to pool.register_station() for DB registration.
    Returns the HMAC key (generated or provided).
    """
    keys = _load_station_keys(key_file)
    if hmac_key is None:
        hmac_key = keys.get(station_id) or secrets.token_hex(32)
    keys[station_id] = hmac_key
    _save_station_keys(keys, key_file)
    return hmac_key


# ─── Constitutional Constants ─────────────────────────────────────────────────

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


# ─── Intelligence Pool ────────────────────────────────────────────────────────

# Cascade depth limit (CONSTITUTION Article VII, Section 7.3)
# Declared here so pool-level lineage verification can enforce it directly.
MAX_CASCADE_DEPTH = 5

class IntelligencePool:
    """
    The Pass. Every dish moves through it. Nothing reaches the guest
    without crossing it.

    SQLite-backed state machine. Persistent. Auditable.
    HMAC write authentication for all station writes (v0.2 hardening).
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
                    crawl_depth INTEGER DEFAULT 0,
                    max_crawl_depth INTEGER DEFAULT 3,
                    root_task_id INTEGER,
                    cascade_depth INTEGER DEFAULT 0,
                    spawn_chain TEXT,
                    UNIQUE(type, value)
                )
            """)

            # Add cascade lineage columns if they don't exist (migration)
            try:
                self.conn.execute("SELECT root_task_id FROM entities LIMIT 1")
            except sqlite3.OperationalError:
                self.conn.execute("ALTER TABLE entities ADD COLUMN root_task_id INTEGER")
                self.conn.execute("ALTER TABLE entities ADD COLUMN cascade_depth INTEGER DEFAULT 0")
                self.conn.execute("ALTER TABLE entities ADD COLUMN spawn_chain TEXT")

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
                    hmac_key TEXT,
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

    # ─── Station Registry ───────────────────────────────────────────────────────

    def get_station_key(self, station_id: str) -> str | None:
        """Return HMAC key for a station, or None if not registered."""
        row = self.conn.execute(
            "SELECT hmac_key FROM station_registry WHERE station_id = ?",
            (station_id,)
        ).fetchone()
        return row['hmac_key'] if row else None

    def register_station(self, station_id: str, name: str, handles_types: list,
                         is_primary: bool = True, hmac_key: str = None):
        """Register a station in the DB. Use register_station_with_key() at
        startup to persist the key to the key file for station retrieval."""
        types_str = json.dumps(handles_types)
        if hmac_key is None:
            existing = self.get_station_key(station_id)
            hmac_key = existing or secrets.token_hex(32)
        try:
            with self.conn:
                self.conn.execute("""
                    INSERT OR REPLACE INTO station_registry
                    (station_id, name, handles_types, is_primary, hmac_key)
                    VALUES (?, ?, ?, ?, ?)
                """, (station_id, name, types_str, int(is_primary), hmac_key))
            return hmac_key
        except sqlite3.IntegrityError:
            return None

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

    def _verify_write(self, station_id: str, payload: str, provided_mac: str = None) -> bool:
        """Verify HMAC of write payload. Returns True if valid, False otherwise.

        Station with key + no MAC = reject (security enforcement).
        Station with key + valid MAC = allow.
        Station with no key = allow (backward compat during onboarding).
        """
        key = self.get_station_key(station_id)
        if key is None:
            return True  # no key registered — backward compat
        if provided_mac is None:
            return False  # station has key but provided no MAC — reject
        expected = hmac.new(
            key.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, provided_mac)

    # ─── Entity Operations ──────────────────────────────────────────────────────

    def _verify_and_compute_lineage(self, parent_task_id: int | None,
                                     caller_cascade_depth: int,
                                     caller_root_task_id: int | None,
                                     caller_spawn_chain: str | None) -> tuple[int, int, str] | None:
        """Verify and compute correct lineage for a new entity.

        Returns (cascade_depth, root_task_id, spawn_chain) tuple if allowed,
        or None if the spawn should be rejected due to depth limit exceeded.

        For child entities (parent_task_id set): lineage is computed from the
        actual parent entity in the DB, NOT from caller-provided values.
        This prevents stations from spoofing lineage to bypass cascade limits.

        For seed entities (parent_task_id is None or self-referential): caller
        values are preserved (this is the normal seed creation path).
        """
        if parent_task_id is None:
            # Seed entity — caller knows the full lineage context
            return caller_cascade_depth, caller_root_task_id, caller_spawn_chain

        # Child entity — verify against actual parent in DB
        parent = self.get_entity(parent_task_id)
        if parent is None:
            # No such parent entity — reject
            self._log_event('lineage_rejected', 'pool',
                            f"No valid parent entity {parent_task_id} for child entity",
                            "parent_task_id does not exist in pool")
            return None

        parent_depth = parent['cascade_depth']
        parent_root = parent['root_task_id']

        # Check cascade depth limit
        if parent_depth >= MAX_CASCADE_DEPTH:
            self._log_event(
                'spawn_blocked_depth_limit', 'pool',
                f"Lineage rejected: parent at depth {parent_depth} >= {MAX_CASCADE_DEPTH}",
                f"parent_task_id={parent_task_id}"
            )
            return None

        # Build spawn chain from parent's chain
        parent_chain_raw = parent['spawn_chain']
        if parent_chain_raw:
            try:
                parent_chain = json.loads(parent_chain_raw)
            except (json.JSONDecodeError, TypeError):
                parent_chain = []
        else:
            parent_chain = []
        new_chain = parent_chain + [parent_task_id]

        computed_depth = parent_depth + 1
        computed_root = parent_root if parent_root else parent_task_id

        return computed_depth, computed_root, json.dumps(new_chain)

    def add_entity(self, ent_type: str, value: str, sla_seconds: int = 60,
                   parent_task_id: int = None,
                   crawl_depth: int = 0,
                   max_crawl_depth: int = 3,
                   root_task_id: int = None,
                   cascade_depth: int = 0,
                   spawn_chain: str = None,
                   station_id: str = None,
                   mac: str = None) -> int | None:
        """Write a new raw entity to the pool. HMAC auth required if station has a key.

        Lineage verification (CONSTITUTION Article VII, Section 7.4):
        For child entities (parent_task_id set), lineage is computed from the
        actual parent entity in the DB — stations cannot spoof cascade_depth
        or root_task_id to bypass the depth limit.
        """
        if station_id:
            payload = f"add_entity:{ent_type}:{value}:{sla_seconds}"
            if not self._verify_write(station_id, payload, mac):
                self._log_event('auth_failure', station_id,
                                f"HMAC rejected for add_entity: {ent_type}:{value}")
                return None

        # Verify and compute lineage from actual parent
        lineage = self._verify_and_compute_lineage(
            parent_task_id, cascade_depth, root_task_id, spawn_chain
        )
        if lineage is None:
            return None
        cascade_depth, root_task_id, spawn_chain = lineage

        payload_hash = compute_payload_hash(ent_type, value)
        try:
            with self.conn:
                cur = self.conn.execute("""
                    INSERT INTO entities (type, value, status, payload_hash, sla_seconds, parent_task_id, crawl_depth, max_crawl_depth, root_task_id, cascade_depth, spawn_chain)
                    VALUES (?, ?, 'raw', ?, ?, ?, ?, ?, ?, ?, ?)
                """, (ent_type, value, payload_hash, sla_seconds, parent_task_id,
                       crawl_depth, max_crawl_depth, root_task_id,
                       cascade_depth, spawn_chain))
                eid = cur.lastrowid
                self._log_event('entity_added', station_id or 'pool',
                                f"New {ent_type}: {value}", f"id={eid}, depth={crawl_depth}")
                return eid
        except sqlite3.IntegrityError:
            return None

    def transition_status(self, entity_id: int, new_status: str, station: str = None,
                          confidence: float = None, notes: str = None,
                          station_id: str = None, mac: str = None) -> bool:
        """Atomic status transition with constitutional validation. HMAC auth if station has key."""
        if station_id:
            payload = f"transition_status:{entity_id}:{new_status}"
            if not self._verify_write(station_id, payload, mac):
                self._log_event('auth_failure', station_id,
                                f"HMAC rejected for transition_status: {entity_id}→{new_status}")
                return False

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

    def set_aboyeur_signature(self, entity_id: int, signature: str,
                              station_id: str = None, mac: str = None):
        if station_id:
            payload = f"set_aboyeur_signature:{entity_id}"
            if not self._verify_write(station_id, payload, mac):
                self._log_event('auth_failure', station_id,
                                f"HMAC rejected for set_aboyeur_signature: {entity_id}")
                return
        with self.conn:
            self.conn.execute(
                "UPDATE entities SET aboyeur_signature = ? WHERE id = ?",
                (signature, entity_id)
            )

    # ─── Backward-Compatible Aliases ──────────────────────────────────────────

    def mark_status(self, entity_id: int, status: str):
        """Alias for transition_status without HMAC auth.

        DEPRECATED: Use transition_status() with station_id and mac for
        authenticated writes. This alias exists for backward compatibility
        with existing tests and callers that don't yet use HMAC auth.
        """
        return self.transition_status(entity_id, status)

    def increment_rejection(self, entity_id: int, station_id: str = None, mac: str = None) -> int:
        if station_id:
            payload = f"increment_rejection:{entity_id}"
            if not self._verify_write(station_id, payload, mac):
                self._log_event('auth_failure', station_id,
                                f"HMAC rejected for increment_rejection: {entity_id}")
                return 0
        with self.conn:
            self.conn.execute(
                "UPDATE entities SET rejection_count = rejection_count + 1 WHERE id = ?",
                (entity_id,)
            )
        row = self.conn.execute(
            "SELECT rejection_count FROM entities WHERE id = ?", (entity_id,)
        ).fetchone()
        return row['rejection_count'] if row else 0

    def get_next_raw(self, max_depth: int = None):
        """Get next unprocessed entity. If max_depth is set, only return entities whose
        crawl_depth is strictly below max_crawl_depth (depth-gated entities)."""
        if max_depth is not None:
            return self.conn.execute("""
                SELECT * FROM entities
                WHERE status = 'raw'
                  AND crawl_depth < max_crawl_depth
                ORDER BY id LIMIT 1
            """).fetchone()
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

    # ─── Edge Operations ────────────────────────────────────────────────────────

    def add_edge(self, source: str, rel: str, target: str,
                 station_id: str = None, mac: str = None):
        if station_id:
            payload = f"add_edge:{source}:{rel}:{target}"
            if not self._verify_write(station_id, payload, mac):
                self._log_event('auth_failure', station_id,
                                f"HMAC rejected for add_edge: {source}--({rel})-->{target}")
                return
        with self.conn:
            self.conn.execute(
                "INSERT INTO edges (source, relationship, target) VALUES (?, ?, ?)",
                (source, rel, target)
            )
        self._log_event('edge_added', station_id or 'pool', f"{source} --({rel})--> {target}")

    def get_all_edges(self):
        return self.conn.execute(
            "SELECT * FROM edges ORDER BY id"
        ).fetchall()

    # ─── Findings (SpaZzMatiC) ─────────────────────────────────────────────────

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

    # ─── Zoran Metrics ────────────────────────────────────────────────────────────

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

    # ─── Events ─────────────────────────────────────────────────────────────────

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

    # ─── Descendant Tracking (for GC cleanup) ─────────────────────────────────

    def get_descendants(self, entity_id: int) -> list:
        """Return all entities that have entity_id anywhere in their spawn_chain."""
        rows = self.conn.execute("""
            SELECT id, type, value, status, cascade_depth, spawn_chain
            FROM entities
            WHERE spawn_chain LIKE ?
               OR parent_task_id = ?
            ORDER BY cascade_depth
        """, (f'%{entity_id}%', entity_id)).fetchall()
        return rows

    def reset_descendants(self, entity_id: int, status: str = 'failed') -> int:
        """Reset status of all descendants of entity_id. Returns count."""
        descendants = self.get_descendants(entity_id)
        if not descendants:
            return 0
        desc_ids = [d['id'] for d in descendants]
        placeholders = ','.join('?' * len(desc_ids))
        with self.conn:
            self.conn.execute(
                f"UPDATE entities SET status = ? WHERE id IN ({placeholders})",
                [status] + desc_ids
            )
        self._log_event('descendants_reset', 'pool',
                        f"Reset {len(desc_ids)} descendants of entity {entity_id} to {status}")
        return len(descendants)

    # ─── Orphan Detection (for Plongeur) ───────────────────────────────────────

    def get_orphaned_entities(self, threshold_seconds: int = 300):
        """Entities stuck in processing beyond their SLA."""
        return self.conn.execute("""
            SELECT * FROM entities
            WHERE status = 'processing'
            AND assigned_at IS NOT NULL
            AND sla_suspended = 0
            AND (julianday('now') - julianday(assigned_at)) * 86400 > sla_seconds
        """).fetchall()

    # ─── Spawn / Cascade Lineage ───────────────────────────────────────────────

    def get_lineage_depth(self, entity_id: int) -> int:
        """Trace parent_task_id chain to root. Returns number of levels (0 = root)."""
        depth = 0
        current = entity_id
        visited = set()
        while True:
            if current in visited:
                break  # cycle guard
            visited.add(current)
            row = self.conn.execute(
                "SELECT parent_task_id FROM entities WHERE id = ?", (current,)
            ).fetchone()
            if not row or row['parent_task_id'] is None:
                break
            depth += 1
            current = row['parent_task_id']
        return depth

    def get_root_task_id(self, entity_id: int) -> int | None:
        """Trace parent_task_id chain to root. Returns root entity ID."""
        current = entity_id
        visited = set()
        while True:
            if current in visited:
                break
            visited.add(current)
            row = self.conn.execute(
                "SELECT parent_task_id FROM entities WHERE id = ?", (current,)
            ).fetchone()
            if not row or row['parent_task_id'] is None:
                return current  # current is the root
            current = row['parent_task_id']
        return None  # cycle

    def get_spawn_chain(self, entity_id: int) -> list[int]:
        """Return the full ancestor chain from root to this entity as a list of IDs."""
        chain = []
        current = entity_id
        visited = set()
        while True:
            if current in visited:
                break
            visited.add(current)
            row = self.conn.execute(
                "SELECT parent_task_id FROM entities WHERE id = ?", (current,)
            ).fetchone()
            if not row:
                break
            chain.append(current)
            if row['parent_task_id'] is None:
                break
            current = row['parent_task_id']
        chain.reverse()
        return chain

    # ─── Stats for Zoran's Law ─────────────────────────────────────────────────

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

    # ─── Export for DRAGON ─────────────────────────────────────────────────────

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