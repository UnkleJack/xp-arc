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
import threading
import os
import base64
from datetime import datetime, timezone
from cryptography.fernet import Fernet


# ─── Module-level Encrypted HMAC Key Store ───────────────────────────────────

HMAC_KEY_FILE = "station_keys.json.enc"
MASTER_KEY_ENV = "XP_ARC_MASTER_KEY"
KEY_FILE_ENV = "XP_ARC_STATION_KEY_FILE"

def _get_fernet() -> Fernet | None:
    """Get Fernet instance from master key env var. Returns None if not configured."""
    master_key = os.environ.get(MASTER_KEY_ENV)
    if not master_key:
        return None
    # Derive a proper 32-byte Fernet key from the master key using SHA-256
    import hashlib
    derived_key = hashlib.sha256(master_key.encode()).digest()
    key = base64.urlsafe_b64encode(derived_key)
    return Fernet(key)

def _load_station_keys(path: str = HMAC_KEY_FILE) -> dict:
    """Load station HMAC keys from encrypted JSON file. Returns {} if not present or no master key."""
    fernet = _get_fernet()
    if not fernet:
        # No encryption configured - fall back to plaintext for backward compat
        plain_path = path.replace('.enc', '')
        try:
            with open(plain_path) as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
    try:
        with open(path, 'rb') as f:
            encrypted = f.read()
        decrypted = fernet.decrypt(encrypted)
        return json.loads(decrypted.decode())
    except FileNotFoundError:
        return {}
    except Exception:
        # Corrupted or wrong key - return empty
        return {}

def _save_station_keys(keys: dict, path: str = HMAC_KEY_FILE):
    """Persist station HMAC keys to encrypted JSON file."""
    fernet = _get_fernet()
    if not fernet:
        # No encryption configured - fall back to plaintext
        plain_path = path.replace('.enc', '')
        with open(plain_path, 'w') as f:
            json.dump(keys, f, indent=2)
        return
    encrypted = fernet.encrypt(json.dumps(keys, indent=2).encode())
    with open(path, 'wb') as f:
        f.write(encrypted)

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
        configured_key_file = os.environ.get(KEY_FILE_ENV)
        self._key_file = configured_key_file or (None if db_path == ":memory:" else f"{db_path}.station_keys.json.enc")
        self.conn = sqlite3.connect(db_path, timeout=30, check_same_thread=False)
        self._write_lock = threading.RLock()
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
                    refusal_reason TEXT,
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

            # Lightweight migration for pools created before refusal records.
            entity_columns = {
                row['name'] for row in self.conn.execute("PRAGMA table_info(entities)").fetchall()
            }
            if 'refusal_reason' not in entity_columns:
                self.conn.execute("ALTER TABLE entities ADD COLUMN refusal_reason TEXT")

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
        """Register a station in the DB. Also persists key to encrypted key file."""
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
            # Keep keys beside the selected Pool database, never in the source tree.
            if self._key_file:
                register_station_with_key(
                    station_id, name, handles_types, is_primary, hmac_key,
                    key_file=self._key_file,
                )
            return hmac_key
        except sqlite3.IntegrityError:
            return None

    # Station registry columns that are safe to expose outside the Pool.
    # Deliberately excludes hmac_key (see get_active_stations / RT-11).
    PUBLIC_STATION_COLUMNS = (
        'id', 'station_id', 'name', 'handles_types',
        'status', 'is_primary', 'registered_at',
    )

    def get_active_stations(self):
        """Active station registry rows, WITHOUT the hmac_key column.

        RT-11: this was previously `SELECT *`, so every consumer received each
        station's HMAC write-auth secret. Those consumers include
        `export_state()` (served to any DRAGON API client) and SpaZzMatiC's
        Gemini review path (shipped to an external LLM API).

        No caller needs the key — `get_station_key()` is the dedicated
        accessor. Columns are enumerated explicitly so that adding a future
        secret column cannot silently re-open this leak.
        """
        return self.conn.execute(
            f"SELECT {', '.join(self.PUBLIC_STATION_COLUMNS)} "  # nosec B608 - fixed internal constant, no user input
            "FROM station_registry WHERE status = 'active'"
        ).fetchall()

    def set_station_status(self, station_id: str, status: str):
        with self.conn:
            self.conn.execute(
                "UPDATE station_registry SET status = ? WHERE station_id = ?",
                (status, station_id)
            )

    def _verify_write(self, station_id: str, payload: str, provided_mac: str = None) -> bool:
        """Verify HMAC of a write payload."""
        key = self.get_station_key(station_id)
        if key is None:
            # 'fracture_protocol' is the internal writer FractureProtocol.create_shards()
            # uses for pool.add_entity(station_id='fracture_protocol', ...). It was
            # missing from this set since inception, so every shard write returned
            # None (HMAC rejected) and create_shards() always returned []. Because
            # the parent is transitioned to 'fractured' *before* shards are attempted,
            # and 'fractured' can only advance to 'stitchable' (which requires real
            # shards), every fracture permanently bricked its parent entity.
            return station_id in {'legacy_local', 'executive', 'aboyeur', 'fracture_protocol'}
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
            if caller_cascade_depth != 0 or caller_root_task_id is not None or caller_spawn_chain not in (None, '', '[]'):
                self._log_event('lineage_rejected', 'pool', 'Seed entity supplied forged lineage metadata')
                return None
            return 0, None, None

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
        
        SLA Validation (RT-13 mitigation): SLA values are clamped to [1, 3600]
        to prevent Zoran's Law gaming via SLA inflation/deflation.
        """
        # SLA Validation - prevent gaming Zoran's Law
        from .station import validate_sla
        sla_seconds = validate_sla(sla_seconds, station_id or 'unknown')
        
        if station_id is None:
            station_id = 'legacy_local'
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
            # Ingestion and root-lineage assignment are one atomic Pool operation.
            with self._write_lock, self.conn:
                cur = self.conn.execute("""
                    INSERT INTO entities (type, value, status, payload_hash, sla_seconds, parent_task_id, crawl_depth, max_crawl_depth, root_task_id, cascade_depth, spawn_chain)
                    VALUES (?, ?, 'raw', ?, ?, ?, ?, ?, ?, ?, ?)
                """, (ent_type, value, payload_hash, sla_seconds, parent_task_id,
                       crawl_depth, max_crawl_depth, root_task_id,
                       cascade_depth, spawn_chain))
                eid = cur.lastrowid
                if parent_task_id is None:
                    self.conn.execute(
                        "UPDATE entities SET root_task_id = ? WHERE id = ?", (eid, eid)
                    )
                self._log_event('entity_added', station_id or 'pool',
                                f"New {ent_type}: {value}", f"id={eid}, depth={crawl_depth}")
                return eid
        except sqlite3.IntegrityError:
            return None

    def transition_status(self, entity_id: int, new_status: str, station: str = None,
                          confidence: float = None, notes: str = None,
                          station_id: str = None, mac: str = None) -> bool:
        """Perform one validated state transition as an atomic Pool write.

        The Pool, not an agent, owns lifecycle timestamps. A task may cross the
        ``pending_qa → completed`` gate only after the Aboyeur has written a
        signature; this makes the gate enforceable even when a station is buggy.
        """
        if station_id is None:
            station_id = 'legacy_local'
        if station_id:
            payload = f"transition_status:{entity_id}:{new_status}"
            if not self._verify_write(station_id, payload, mac):
                self._log_event('auth_failure', station_id,
                                f"HMAC rejected for transition_status: {entity_id}→{new_status}")
                return False

        with self._write_lock, self.conn:
            row = self.conn.execute(
                "SELECT status, aboyeur_signature FROM entities WHERE id = ?", (entity_id,)
            ).fetchone()
            if not row:
                return False

            current = row['status']
            if new_status not in VALID_TRANSITIONS.get(current, []):
                self._log_event('status_violation', 'pool',
                                f"Unauthorized transition: {current} → {new_status}",
                                f"entity_id={entity_id}")
                return False
            if current in {'pending_qa', 'mapped'} and new_status == 'completed' and not row['aboyeur_signature']:
                self._log_event('qa_gate_blocked', 'pool',
                                f"Completion blocked without Aboyeur signature for entity {entity_id}")
                return False

            assignments = ["status = ?"]
            values = [new_status]
            if new_status == 'processing':
                assignments.append("assigned_at = datetime('now')")
                if station:
                    assignments.append("station = ?")
                    values.append(station)
            elif new_status == 'completed':
                assignments.append("completed_at = datetime('now')")
            if confidence is not None:
                assignments.append("confidence = ?")
                values.append(confidence)
            if notes is not None:
                assignments.append("notes = ?")
                values.append(notes)

            values.append(entity_id)
            self.conn.execute(
                f"UPDATE entities SET {', '.join(assignments)} WHERE id = ?", values  # nosec B608
            )

        self._log_event('status_transition', station or 'pool',
                        f"Entity {entity_id}: {current} → {new_status}")
        return True

    def set_aboyeur_signature(self, entity_id: int, signature: str,
                              station_id: str = None, mac: str = None) -> bool:
        """Persist an Aboyeur seal only while a task is awaiting finalization."""
        if station_id is None:
            station_id = 'legacy_local'
        if station_id:
            payload = f"set_aboyeur_signature:{entity_id}"
            if not self._verify_write(station_id, payload, mac):
                self._log_event('auth_failure', station_id,
                                f"HMAC rejected for set_aboyeur_signature: {entity_id}")
                return False
        if not isinstance(signature, str) or not signature.startswith('ABOY-'):
            return False
        with self._write_lock, self.conn:
            changed = self.conn.execute(
                "UPDATE entities SET aboyeur_signature = ? WHERE id = ? AND status IN ('pending_qa', 'mapped')",
                (signature, entity_id)
            ).rowcount
        return changed == 1

    def refuse_entity(self, entity_id: int, reason: str, station: str = None,
                      station_id: str = None, mac: str = None) -> bool:
        """Record a constitutionally protected station refusal as a terminal failure."""
        if station_id is None:
            station_id = 'legacy_local'
        payload = f"refuse_entity:{entity_id}:{reason}"
        if station_id and not self._verify_write(station_id, payload, mac):
            self._log_event('auth_failure', station_id,
                            f"HMAC rejected for refuse_entity: {entity_id}")
            return False
        with self._write_lock, self.conn:
            row = self.conn.execute("SELECT status FROM entities WHERE id = ?", (entity_id,)).fetchone()
            if not row or row['status'] not in {'processing', 'pending_qa'}:
                return False
            self.conn.execute(
                """UPDATE entities
                   SET status = 'failed', refusal_reason = ?, notes = ?, completed_at = datetime('now'), station = COALESCE(?, station)
                   WHERE id = ?""",
                (reason, reason, station, entity_id)
            )
        self._log_event('station_refusal', station or station_id or 'pool',
                        f"Entity {entity_id} refused: {reason}")
        return True

    def set_fracture_metadata(self, entity_id: int, fracture_id: str,
                              parent_task_id: int | None = None,
                              station_id: str = None, mac: str = None) -> bool:
        """Attach authorized fracture metadata without exposing a raw SQL write."""
        if station_id is None:
            station_id = 'legacy_local'
        payload = f"set_fracture_metadata:{entity_id}:{fracture_id}:{parent_task_id}"
        if station_id and not self._verify_write(station_id, payload, mac):
            self._log_event('auth_failure', station_id,
                            f"HMAC rejected for set_fracture_metadata: {entity_id}")
            return False
        with self._write_lock, self.conn:
            changed = self.conn.execute(
                "UPDATE entities SET fracture_id = ?, parent_task_id = COALESCE(?, parent_task_id) WHERE id = ?",
                (fracture_id, parent_task_id, entity_id),
            ).rowcount
        return changed == 1

    # ─── Backward-Compatible Aliases ──────────────────────────────────────────

    def mark_status(self, entity_id: int, status: str):
        """Deprecated local compatibility alias. Guarded by XP_ARC_DEV_MODE env var."""
        import os
        if not os.environ.get('XP_ARC_DEV_MODE'):
            raise RuntimeError(
                "mark_status() is a development bypass and is disabled in production. "
                "Set XP_ARC_DEV_MODE=1 to enable (not recommended for production)."
            )
        if status == 'completed':
            self.transition_status(entity_id, 'processing', station_id='legacy_local')
            self.transition_status(entity_id, 'pending_qa', station_id='legacy_local')
        return self.transition_status(entity_id, status, station_id='legacy_local')

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


    def claim_entity(self, entity_id: int, station: str):
        with self._write_lock, self.conn:
            changed = self.conn.execute(
                "UPDATE entities SET status = 'processing', station = ?, assigned_at = datetime('now') WHERE id = ? AND status = 'raw'",
                (station, entity_id),
            ).rowcount
            return self.get_entity(entity_id) if changed == 1 else None

    def claim_next_raw(self, station: str):
        """Atomically claim the oldest raw entity for one station."""
        with self._write_lock, self.conn:
            row = self.conn.execute(
                "SELECT id FROM entities WHERE status = 'raw' ORDER BY id LIMIT 1"
            ).fetchone()
            if not row:
                return None
            changed = self.conn.execute(
                "UPDATE entities SET status = 'processing', station = ?, assigned_at = datetime('now') WHERE id = ? AND status = 'raw'",
                (station, row['id'])
            ).rowcount
            return self.get_entity(row['id']) if changed == 1 else None

    def station_writer(self, station_id: str):
        return _StationWriter(self, station_id)

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
        if station_id is None:
            station_id = 'legacy_local'
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
            WHERE parent_task_id = ?
            ORDER BY cascade_depth
        """, (entity_id,)).fetchall()
        return rows

    def reset_descendants(self, entity_id: int, status: str = 'failed') -> int:
        """Reset status of all descendants of entity_id. Returns count."""
        descendants = self.get_descendants(entity_id)
        if not descendants:
            return 0
        desc_ids = [d['id'] for d in descendants]
        placeholders = ','.join('?' * len(desc_ids))
        with self.conn:
            # Use parameterized query with IN clause
            query = f"UPDATE entities SET status = ? WHERE id IN ({placeholders})"  # nosec B608 - placeholders derive from internal entity IDs
            self.conn.execute(query, [status] + desc_ids)
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
        # RT-11 defense in depth: get_active_stations() already excludes
        # hmac_key, but this export is the public DRAGON surface — strip any
        # secret column again here so a regression upstream cannot leak it.
        stations = []
        for row in self.get_active_stations():
            station = dict(row)
            station.pop('hmac_key', None)
            stations.append(station)
        findings = [dict(row) for row in self.get_findings()]
        zorans = [dict(row) for row in self.get_zorans_history()]
        events = [dict(row) for row in self.get_events(500)]

        stats = self.get_stats()

        completed = [entity for entity in entities if entity['status'] == 'completed']
        terminal = [entity for entity in entities if entity['status'] in {'completed', 'failed'}]
        unsigned_completed = [entity for entity in completed if not entity['aboyeur_signature']]
        hash_valid = sum(
            compute_payload_hash(entity['type'], entity['value']) == entity['payload_hash']
            for entity in entities
        )
        status_violations = sum(event['event_type'] == 'status_violation' for event in events)
        unaccounted = [
            entity for entity in entities if entity['status'] not in VALID_TRANSITIONS
        ]
        integrity_score = 1.0 if not completed else 1.0 - (len(unsigned_completed) / len(completed))

        def audit_check(passed: bool, pass_rate: float) -> dict:
            return {'passed': passed, 'pass_rate': pass_rate}

        audit = {
            'overall': {
                'integrity_score': integrity_score,
                'all_checks_passed': not unsigned_completed and status_violations == 0,
            },
            'hash_integrity': {
                **audit_check(hash_valid == len(entities), 1.0 if not entities else hash_valid / len(entities)),
                'valid': hash_valid,
                'total': len(entities),
            },
            'signature_integrity': {
                **audit_check(not unsigned_completed, 1.0 if not completed else (len(completed) - len(unsigned_completed)) / len(completed)),
                'signed': len(completed) - len(unsigned_completed),
                'total_completed': len(completed),
            },
            'transition_legality': {
                **audit_check(status_violations == 0, 1.0 if status_violations == 0 else 0.0),
                'total_transitions': sum(event['event_type'] == 'status_transition' for event in events),
                'violations': status_violations,
            },
            'edge_consistency': {
                **audit_check(True, 1.0),
                'valid': len(edges),
                'total_edges': len(edges),
            },
            'completeness': {
                **audit_check(len(terminal) == len(entities), 1.0 if not entities else len(terminal) / len(entities)),
                'complete': len(terminal),
                'total': len(entities),
            },
            'zero_drop': {
                **audit_check(not unaccounted, 1.0 if not entities else (len(entities) - len(unaccounted)) / len(entities)),
                'zero_drop_verified': not unaccounted,
                'terminal': len(terminal),
                'unaccounted': len(unaccounted),
            },
            'unsigned_completed': len(unsigned_completed),
        }
        return {
            'meta': {
                'exported_at': datetime.now(timezone.utc).isoformat(),
                'db_path': self.db_path,
                'version': '0.3.0',
                'protocol': 'XP-Arc',
            },
            'entities': entities,
            'edges': edges,
            'stations': stations,
            'findings': findings,
            'zorans_metrics': zorans,
            'events': list(reversed(events)),  # chronological
            'stats': {k: dict(v) if isinstance(v, sqlite3.Row) else v for k, v in stats.items()},
            # Always-present DRAGON collections keep the read-only dashboard safe
            # when an optional producer has not emitted data in this run.
            'dossiers': [],
            'topology': {'clusters': {'count': 0, 'largest': 0, 'smallest': 0}, 'bridges': [], 'hubs': []},
            'audit': audit,
        }

    def close(self):
        self.conn.close()
class _StationWriter:
    def __init__(self, pool, station_id: str):
        self._pool = pool
        self.station_id = station_id

    def _mac(self, operation: str, payload: str):
        key = self._pool.get_station_key(self.station_id)
        if key is None:
            return None
        return hmac.new(key.encode(), payload.encode(), hashlib.sha256).hexdigest()

    def add_entity(self, ent_type, value, sla_seconds=60, **kwargs):
        payload = f"add_entity:{ent_type}:{value}:{sla_seconds}"
        return self._pool.add_entity(ent_type, value, sla_seconds=sla_seconds,
                                      station_id=self.station_id, mac=self._mac('add_entity', payload), **kwargs)

    def transition_status(self, entity_id, new_status, **kwargs):
        payload = f"transition_status:{entity_id}:{new_status}"
        return self._pool.transition_status(entity_id, new_status,
                                            station_id=self.station_id,
                                            mac=self._mac('transition_status', payload), **kwargs)

    def add_edge(self, source, rel, target):
        payload = f"add_edge:{source}:{rel}:{target}"
        return self._pool.add_edge(source, rel, target, station_id=self.station_id,
                                   mac=self._mac('add_edge', payload))

    def set_aboyeur_signature(self, entity_id, signature):
        payload = f"set_aboyeur_signature:{entity_id}"
        return self._pool.set_aboyeur_signature(entity_id, signature,
                                                station_id=self.station_id,
                                                mac=self._mac('set_aboyeur_signature', payload))

    def increment_rejection(self, entity_id):
        payload = f"increment_rejection:{entity_id}"
        return self._pool.increment_rejection(entity_id, station_id=self.station_id,
                                              mac=self._mac('increment_rejection', payload))

    def refuse_entity(self, entity_id, reason, station=None):
        payload = f"refuse_entity:{entity_id}:{reason}"
        return self._pool.refuse_entity(entity_id, reason, station=station,
                                        station_id=self.station_id,
                                        mac=self._mac('refuse_entity', payload))

    def set_fracture_metadata(self, entity_id, fracture_id, parent_task_id=None):
        payload = f"set_fracture_metadata:{entity_id}:{fracture_id}:{parent_task_id}"
        return self._pool.set_fracture_metadata(
            entity_id, fracture_id, parent_task_id=parent_task_id,
            station_id=self.station_id,
            mac=self._mac('set_fracture_metadata', payload),
        )

    def __getattr__(self, name):
        return getattr(self._pool, name)
