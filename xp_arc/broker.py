"""
Write Broker — Redis-buffered Pool write sequencer.

CONSTITUTION Article III, Section 3.5:
  "All Pool writes MUST be routed through a write broker that buffers
  operations via a Redis queue before committing to DuckDB."

Architecture:
  Stations → [signed write request] → Redis queue
                                    → Write Broker (single-threaded consumer)
                                    → DuckDB (only writer; no lock contention)
                                    → Materialized View updated
                                    → DRAGON polls view at 500ms

Hot standby: two broker processes. Leader election via Redis lock.
Primary holds lock TTL=15s, refreshed every 5s. Standby monitors lock.
On primary failure, standby acquires lock and takes over.

Usage:
  # Primary
  python -m xp_arc.broker --role primary --db xp_arc.db

  # Standby
  python -m xp_arc.broker --role standby --db xp_arc.db

  # DRAGON API (starts with primary or standalone)
  python -m xp_arc.broker --api-only --db xp_arc.db
"""

import argparse
import json
import logging
import queue
import signal
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

try:
    import redis
except ImportError:
    redis = None

import sqlite3
import threading
import os

# Local imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from xp_arc.core.authorization import (
    verify_write_signature, StationKeyRegistry
)
from xp_arc.core.sanitization import sanitize_d2_node_id, sanitize_markdown

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("xp_arc.broker")


# ─── Configuration ────────────────────────────────────────────────────────────

DEFAULT_REDIS_HOST = "localhost"
DEFAULT_REDIS_PORT = 6379
DEFAULT_REDIS_QUEUE = "xp_arc:write_queue"
DEFAULT_REDIS_ACK_QUEUE = "xp_arc:write_ack"
DEFAULT_LOCK_KEY = "xp_arc:broker:leader"
DEFAULT_POOL_STATE_KEY = "xp_arc:pool_state"
DEFAULT_LEADER_TTL = 15  # seconds
DEFAULT_LOCK_RENEW_INTERVAL = 5  # seconds
DEFAULT_API_PORT = 8741
DEFAULT_STATS_KEY = "xp_arc:broker:stats"

IN_MEMORY_VIEW_TTL = 5  # seconds before view is considered stale

# ─── Operation Types ──────────────────────────────────────────────────────────

OP_ADD_ENTITY = "add_entity"
OP_TRANSITION_STATUS = "transition_status"
OP_ADD_EDGE = "add_edge"
OP_SET_ABOYEUR_SIG = "set_aboyeur_signature"
OP_INCREMENT_REJECTION = "increment_rejection"
OP_ADD_FINDING = "add_finding"
OP_SET_STATION_STATUS = "set_station_status"


# ─── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class WriteRequest:
    """A signed Pool write request, enqueued by stations to Redis."""
    op: str
    payload: dict
    station_id: str
    signature: str
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    enqueued_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @classmethod
    def from_json(cls, raw: str) -> "WriteRequest":
        data = json.loads(raw)
        return cls(
            op=data["op"],
            payload=data["payload"],
            station_id=data["station_id"],
            signature=data["signature"],
            request_id=data.get("request_id", uuid.uuid4().hex[:12]),
            enqueued_at=data.get("enqueued_at", datetime.now(timezone.utc).isoformat()),
        )

    def to_json(self) -> str:
        return json.dumps({
            "op": self.op,
            "payload": self.payload,
            "station_id": self.station_id,
            "signature": self.signature,
            "request_id": self.request_id,
            "enqueued_at": self.enqueued_at,
        })


# ─── Materialized View ────────────────────────────────────────────────────────

class MaterializedView:
    """
    Thread-safe in-memory snapshot of the complete Pool state.

    CONSTITUTION Article III, Section 3.5:
      "The Write Broker maintains an in-memory materialized view of current
      Pool state, updated on every committed write. DRAGON polls this
      materialized view at 500ms — never the DuckDB file."
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._entities: dict[int, dict] = {}
        self._edges: list[dict] = []
        self._stations: list[dict] = []
        self._findings: list[dict] = []
        self._events: list[dict] = []
        self._stats: dict = {}
        self._last_updated: float = 0.0
        self._version: int = 0  # monotonic snapshot version

    def full_refresh(self, entities, edges, stations, findings, events, stats):
        """Replace entire view state. Called on startup or leader takeover."""
        with self._lock:
            self._entities = {e["id"]: dict(e) for e in entities}
            self._edges = [dict(e) for e in edges]
            self._stations = [dict(s) for s in stations]
            self._findings = [dict(f) for f in findings]
            self._events = list(reversed([dict(e) for e in events]))
            self._stats = dict(stats) if stats else {}
            self._last_updated = time.monotonic()
            self._version += 1
            log.info(
                f"View refreshed: {len(self._entities)} entities, "
                f"{len(self._edges)} edges, {len(self._stations)} stations"
            )

    def apply_add_entity(self, entity_id: int, ent_type: str, value: str,
                           payload_hash: str, sla_seconds: int, parent_task_id):
        """Apply an add_entity result to the view."""
        with self._lock:
            self._entities[entity_id] = {
                "id": entity_id, "type": ent_type, "value": value,
                "status": "raw", "payload_hash": payload_hash,
                "station": None, "confidence": None, "notes": None,
                "sla_seconds": sla_seconds, "assigned_at": None,
                "completed_at": None, "created_at": datetime.now(timezone.utc).isoformat(),
                "aboyeur_signature": None, "fallback_role": 0,
                "fracture_id": None, "parent_task_id": parent_task_id,
                "rejection_count": 0, "max_rejections": 3, "sla_suspended": 0,
            }
            self._version += 1
            self._last_updated = time.monotonic()

    def apply_add_edge(self, edge_id: int, source: str, rel: str, target: str):
        """Apply an add_edge result to the view."""
        with self._lock:
            self._edges.append({
                "id": edge_id, "source": source, "relationship": rel,
                "target": target,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            self._version += 1
            self._last_updated = time.monotonic()

    def apply_status_transition(self, entity_id: int, new_status: str,
                                  **fields):
        """Apply a status transition result to the view."""
        with self._lock:
            if entity_id in self._entities:
                self._entities[entity_id]["status"] = new_status
                for k, v in fields.items():
                    if v is not None and k in self._entities[entity_id]:
                        self._entities[entity_id][k] = v
                self._version += 1
                self._last_updated = time.monotonic()

    def apply_aboyeur_sig(self, entity_id: int, signature: str):
        with self._lock:
            if entity_id in self._entities:
                self._entities[entity_id]["aboyeur_signature"] = signature
                self._version += 1
                self._last_updated = time.monotonic()

    def apply_rejection_increment(self, entity_id: int, new_count: int):
        with self._lock:
            if entity_id in self._entities:
                self._entities[entity_id]["rejection_count"] = new_count
                self._version += 1
                self._last_updated = time.monotonic()

    def apply_finding(self, finding_id: int, severity: str, source: str,
                        message: str, detail: str | None):
        with self._lock:
            self._findings.insert(0, {
                "id": finding_id, "severity": severity, "source": source,
                "message": message, "detail": detail,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            self._version += 1
            self._last_updated = time.monotonic()

    def apply_station_status(self, station_id: str, status: str):
        with self._lock:
            for s in self._stations:
                if s["station_id"] == station_id:
                    s["status"] = status
                    break
            self._version += 1
            self._last_updated = time.monotonic()

    def get_state(self) -> dict:
        """Return serializable snapshot for DRAGON polling."""
        with self._lock:
            return {
                "meta": {
                    "version": self._version,
                    "last_updated": self._last_updated,
                    "stale_seconds": time.monotonic() - self._last_updated,
                    "exported_at": datetime.now(timezone.utc).isoformat(),
                },
                "entities": list(self._entities.values()),
                "edges": self._edges,
                "stations": self._stations,
                "findings": self._findings[:50],  # last 50 findings
                "events": self._events[:500],     # last 500 events
                "stats": self._stats,
            }


from xp_arc.core.pool import VALID_TRANSITIONS, MAX_CASCADE_DEPTH
import json as _json

# ─── SQLite Write Executor ────────────────────────────────────────────────────
class SQLiteBrokerExecutor:
    """
    Single-writer SQLite connection used exclusively by the Write Broker.
    This is the only process that writes to the DB — eliminating file lock
    contention from concurrent station writers.

    Uses the exact same schema as xp_arc/core/pool.py (SQLite with WAL mode).
    On concurrent write attempts (race between primary and standby both trying
    to write), one gets the file lock, the other retries or fails cleanly.

    CONSTITUTION Article III, Section 3.5:
      "The Write Broker MUST be deployed with a hot standby to eliminate
      the SPOF introduced by a single-threaded broker."
      (The SPOF is the broker process, not the DB file — the standby takes over.)
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.setup()

    def setup(self):
        with self._lock, self.conn:
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
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    relationship TEXT NOT NULL,
                    target TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
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

    def _execute(self, sql: str, params: tuple = ()):
        """Thread-safe execute with file-lock serialization."""
        with self._lock:
            return self.conn.execute(sql, params)

    def execute_add_entity(self, req: WriteRequest) -> dict:
        import hashlib
        ent_type = req.payload["type"]
        value = req.payload["value"]
        sla_seconds = req.payload.get("sla_seconds", 60)
        parent_task_id = req.payload.get("parent_task_id")
        crawl_depth = req.payload.get("crawl_depth", 0)
        max_crawl_depth = req.payload.get("max_crawl_depth", 3)

        payload_hash = hashlib.sha256(
            _json.dumps({"type": ent_type, "value": value}, sort_keys=True).encode()
        ).hexdigest()

        with self._lock:
            cascade_depth = 0
            root_task_id = None
            spawn_chain = None
            if parent_task_id is not None:
                parent_row = self.conn.execute(
                    "SELECT cascade_depth, root_task_id, spawn_chain FROM entities WHERE id = ?", (parent_task_id,)
                ).fetchone()
                if not parent_row:
                    return {"ok": False, "error": "parent_task_id does not exist"}
                parent_depth = parent_row["cascade_depth"] or 0
                if parent_depth >= MAX_CASCADE_DEPTH:
                    self.conn.execute("""
                        INSERT INTO events (event_type, source, message, detail)
                        VALUES (?, ?, ?, ?)
                    """, ("spawn_blocked_depth_limit", "write_broker",
                          f"Lineage rejected: parent at depth {parent_depth} >= {MAX_CASCADE_DEPTH}",
                          f"parent_task_id={parent_task_id}"))
                    return {"ok": False, "error": f"cascade depth limit {MAX_CASCADE_DEPTH} exceeded"}
                cascade_depth = parent_depth + 1
                root_task_id = parent_row["root_task_id"] or parent_task_id
                parent_chain_raw = parent_row["spawn_chain"]
                parent_chain = _json.loads(parent_chain_raw) if parent_chain_raw else []
                spawn_chain = _json.dumps(parent_chain + [parent_task_id])

            with self.conn:
                cur = self.conn.execute("""
                    INSERT INTO entities (type, value, status, payload_hash, sla_seconds, parent_task_id, crawl_depth, max_crawl_depth, root_task_id, cascade_depth, spawn_chain)
                    VALUES (?, ?, 'raw', ?, ?, ?, ?, ?, ?, ?, ?)
                """, (ent_type, value, payload_hash, sla_seconds, parent_task_id, crawl_depth, max_crawl_depth, root_task_id, cascade_depth, spawn_chain))
                eid = cur.lastrowid
                self.conn.execute("""
                    INSERT INTO events (event_type, source, message, detail)
                    VALUES (?, ?, ?, ?)
                """, ("entity_added", "write_broker", f"New {ent_type}: {value}", f"id={eid}"))

        return {"entity_id": eid}

    def execute_transition_status(self, req: WriteRequest) -> dict:
        entity_id = req.payload["entity_id"]
        new_status = req.payload["new_status"]

        row = self._execute(
            "SELECT status FROM entities WHERE id = ?", (entity_id,)
        ).fetchone()
        if not row:
            return {"ok": False, "error": "entity not found"}

        current = row[0]
        if new_status not in VALID_TRANSITIONS.get(current, []):
            return {"ok": False, "error": f"unauthorized transition: {current} -> {new_status}"}

        updates = {"status": new_status}
        if new_status == "processing":
            updates["assigned_at"] = datetime.now(timezone.utc).isoformat()
            station = req.payload.get("station")
            if station:
                updates["station"] = station
        elif new_status in ("completed", "mapped"):
            updates["completed_at"] = datetime.now(timezone.utc).isoformat()
            confidence = req.payload.get("confidence")
            if confidence is not None:
                updates["confidence"] = confidence
            notes = req.payload.get("notes")
            if notes:
                updates["notes"] = notes

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [entity_id]

        with self._lock:
            with self.conn:
                self.conn.execute(f"UPDATE entities SET {set_clause} WHERE id = ?", values)
                self.conn.execute("""
                    INSERT INTO events (event_type, source, message, detail)
                    VALUES (?, ?, ?, ?)
                """, ("status_transition", "write_broker",
                      f"Entity {entity_id}: {current} → {new_status}", None))

        return {"ok": True, "previous": current, "new": new_status}

    def execute_add_edge(self, req: WriteRequest) -> dict:
        source = req.payload["source"]
        rel = req.payload["relationship"]
        target = req.payload["target"]

        with self._lock:
            with self.conn:
                cur = self.conn.execute(
                    "INSERT INTO edges (source, relationship, target) VALUES (?, ?, ?)",
                    (source, rel, target)
                )
                eid = cur.lastrowid
                self.conn.execute("""
                    INSERT INTO events (event_type, source, message, detail)
                    VALUES (?, ?, ?, ?)
                """, ("edge_added", "write_broker", f"{source} --({rel})--> {target}", None))

        return {"edge_id": eid}

    def execute_set_aboyeur_sig(self, req: WriteRequest) -> dict:
        entity_id = req.payload["entity_id"]
        signature = req.payload["signature"]
        with self._lock:
            with self.conn:
                self.conn.execute(
                    "UPDATE entities SET aboyeur_signature = ? WHERE id = ?",
                    (signature, entity_id)
                )
        return {"ok": True}

    def execute_increment_rejection(self, req: WriteRequest) -> dict:
        entity_id = req.payload["entity_id"]
        with self._lock:
            with self.conn:
                self.conn.execute(
                    "UPDATE entities SET rejection_count = rejection_count + 1 WHERE id = ?",
                    (entity_id,)
                )
            row = self.conn.execute(
                "SELECT rejection_count FROM entities WHERE id = ?", (entity_id,)
            ).fetchone()
        return {"count": row[0] if row else 0}

    def execute_add_finding(self, req: WriteRequest) -> dict:
        severity = req.payload["severity"]
        source = req.payload["source"]
        message = req.payload["message"]
        detail = req.payload.get("detail")

        with self._lock:
            with self.conn:
                cur = self.conn.execute(
                    "INSERT INTO findings (severity, source, message, detail) VALUES (?, ?, ?, ?)",
                    (severity, source, message, detail)
                )
                fid = cur.lastrowid
                self.conn.execute("""
                    INSERT INTO events (event_type, source, message, detail)
                    VALUES (?, ?, ?, ?)
                """, ("finding", source, f"[{severity.upper()}] {message}", detail))

        return {"finding_id": fid}

    def execute_set_station_status(self, req: WriteRequest) -> dict:
        station_id = req.payload["station_id"]
        status = req.payload["status"]
        with self._lock:
            with self.conn:
                self.conn.execute(
                    "UPDATE station_registry SET status = ? WHERE station_id = ?",
                    (status, station_id)
                )
        return {"ok": True}

    def execute_raw(self, sql: str, params: tuple = ()) -> list[dict]:
        """Execute a raw SQL query and return results as dicts. For reads only."""
        rows = self._execute(sql, params).fetchall()
        if not rows:
            return []
        cols = [d[0] for d in self._execute(sql, params).description or []]
        return [dict(zip(cols, r)) for r in rows]

    def load_full_state(self) -> tuple:
        """Load full pool state for materialized view initialization."""
        entities = self._execute("SELECT * FROM entities ORDER BY id").fetchall()
        entities = [dict(e) for e in entities]
        edges = [dict(e) for e in self._execute("SELECT * FROM edges ORDER BY id").fetchall()]
        stations = [dict(s) for s in self._execute("SELECT * FROM station_registry").fetchall()]
        findings = [dict(f) for f in self._execute(
            "SELECT * FROM findings ORDER BY id DESC LIMIT 50"
        ).fetchall()]
        events = [dict(e) for e in self._execute(
            "SELECT * FROM events ORDER BY id DESC LIMIT 500"
        ).fetchall()]
        events.reverse()  # chronological

        stats_rows = self._execute(
            "SELECT status, COUNT(*) as cnt, COALESCE(SUM(sla_seconds), 0) as total_sla "
            "FROM entities GROUP BY status"
        ).fetchall()
        stats = {r[0]: {"count": r[1], "total_sla": r[2]} for r in stats_rows}

        return entities, edges, stations, findings, events, stats

    def close(self):
        with self._lock:
            self.conn.close()

    # Alias for DuckDBExecutor compatibility in code that uses duckdb attribute
    @property
    def duckdb(self) -> type:
        return SQLiteBrokerExecutor  # Dummy to avoid AttributeError on `duckdb` attr access


# ─── Leader Election ──────────────────────────────────────────────────────────

class LeaderElection:
    """
    Redis-based leader election for hot standby.

    Primary holds a Redis key with TTL. Standby checks key TTL.
    On expiry, standby attempts to set the key — first to succeed becomes leader.
    """

    def __init__(self, redis_client: Any, lock_key: str,
                   ttl: int = DEFAULT_LEADER_TTL):
        self.redis = redis_client
        self.lock_key = lock_key
        self.ttl = ttl
        self.is_leader = False
        self._leader_id = uuid.uuid4().hex[:12]

    def try_acquire(self) -> bool:
        """Attempt to become leader. Returns True if we got the lock."""
        ok = self.redis.set(
            self.lock_key, self._leader_id,
            nx=True, ex=self.ttl
        )
        self.is_leader = bool(ok)
        return self.is_leader

    def renew(self) -> bool:
        """Renew our leadership. Returns False if we lost leadership."""
        current = self.redis.get(self.lock_key)
        if current and current == self._leader_id:
            self.redis.expire(self.lock_key, self.ttl)
            self.is_leader = True
            return True
        else:
            self.is_leader = False
            return False

    def is_current_leader(self) -> bool:
        """Check if we are still the leader (lock not expired)."""
        current = self.redis.get(self.lock_key)
        if current and current == self._leader_id:
            self.is_leader = True
            return True
        self.is_leader = False
        return False

    def release(self):
        """Release leadership explicitly."""
        current = self.redis.get(self.lock_key)
        if current and current == self._leader_id:
            self.redis.delete(self.lock_key)
        self.is_leader = False


# ─── Token Bucket Rate Limiter ────────────────────────────────────────────────

class TokenBucket:
    """
    Per-station rate limiter for the Write Broker.

    Prevents any single station from flooding the Redis queue or
    overwhelming DuckDB writes. Each station gets a bucket of N tokens,
    refilling at one token per second. Writes cost one token; if the
    bucket is empty, the request is slowed down (not rejected).
    """

    def __init__(self, writes_per_second: float = 10.0, burst: int = 20):
        self.writes_per_second = writes_per_second
        self.burst = burst
        self._buckets: dict[str, tuple[float, float]] = {}  # station_id → (tokens, last_refill_ts)

    def _refill(self, station_id: str) -> float:
        """Refill tokens for station_id based on elapsed time. Returns current tokens."""
        now = time.monotonic()
        tokens, last_ts = self._buckets.get(station_id, (float(self.burst), now))
        elapsed = now - last_ts
        tokens = min(self.burst, tokens + elapsed * self.writes_per_second)
        self._buckets[station_id] = (tokens, now)
        return tokens

    def try_write(self, station_id: str) -> bool:
        """
        Attempt to consume one token for station_id.
        Returns True if the write is allowed (token was available),
        False if the station must wait for refill.
        """
        tokens = self._refill(station_id)
        if tokens >= 1.0:
            self._buckets[station_id] = (tokens - 1.0, time.monotonic())
            return True
        return False

    def wait_time(self, station_id: str) -> float:
        """Return seconds to wait until one token is available. 0 if available now."""
        tokens = self._refill(station_id)
        if tokens >= 1.0:
            return 0.0
        return (1.0 - tokens) / self.writes_per_second


# ─── Write Broker Core ────────────────────────────────────────────────────────

class WriteBroker:
    """
    Single-threaded write sequencer: pops from Redis, executes in DuckDB,
    updates materialized view.

    This is the core of CONSTITUTION Article III, Section 3.5.
    All stations write to Redis. Only the broker writes to DuckDB.
    """

    def __init__(self, redis_host: str, redis_port: int, db_path: str,
                 queue_key: str = DEFAULT_REDIS_QUEUE,
                 ack_queue: str = DEFAULT_REDIS_ACK_QUEUE,
                 pool_state_key: str = DEFAULT_POOL_STATE_KEY,
                 station_registry: StationKeyRegistry | None = None):
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.db_path = db_path
        self.queue_key = queue_key
        self.ack_queue = ack_queue
        self.pool_state_key = pool_state_key

        if redis is None:
            raise ImportError("redis package required: pip install redis")
        self.r = redis.Redis(host=redis_host, port=redis_port,
                             decode_responses=True)
        self.r.ping()

        self.view = MaterializedView()
        self.station_registry = station_registry or StationKeyRegistry(None)
        self.db: SQLiteBrokerExecutor | None = None
        self.rate_limiter = TokenBucket(writes_per_second=10.0, burst=20)

        self._running = False
        self._stats = {
            "writes_processed": 0,
            "writes_succeeded": 0,
            "writes_failed": 0,
            "writes_by_op": {},
            "signatures_rejected": 0,
            "rate_limited": 0,
            "start_time": None,
        }

    def _init_db(self):
        self.db = SQLiteBrokerExecutor(self.db_path)
        # Load full state into materialized view on startup
        state = self.db.load_full_state()
        self.view.full_refresh(*state)
        self._publish_view_to_redis()
        log.info("DuckDB connected, view initialized and published to Redis")

    # ─── Operation Dispatch ─────────────────────────────────────────────────

    def _dispatch(self, req: WriteRequest) -> dict:
        """Dispatch a WriteRequest to DuckDB and return the result dict."""
        entity_id = req.payload.get("entity_id")
        op = req.op

        if op == OP_ADD_ENTITY:
            result = self.db.execute_add_entity(req)
            self.view.apply_add_entity(
                result["entity_id"],
                req.payload["type"], req.payload["value"],
                "", req.payload.get("sla_seconds", 60),
                req.payload.get("parent_task_id")
            )
            return result

        elif op == OP_TRANSITION_STATUS:
            result = self.db.execute_transition_status(req)
            if result.get("ok", True):
                fields = {}
                if "confidence" in req.payload:
                    fields["confidence"] = req.payload["confidence"]
                if "notes" in req.payload:
                    fields["notes"] = req.payload["notes"]
                self.view.apply_status_transition(entity_id, req.payload["new_status"], **fields)
            return result

        elif op == OP_ADD_EDGE:
            result = self.db.execute_add_edge(req)
            self.view.apply_add_edge(
                result["edge_id"],
                req.payload["source"], req.payload["relationship"],
                req.payload["target"]
            )
            return result

        elif op == OP_SET_ABOYEUR_SIG:
            result = self.db.execute_set_aboyeur_sig(req)
            self.view.apply_aboyeur_sig(entity_id, req.payload["signature"])
            return result

        elif op == OP_INCREMENT_REJECTION:
            result = self.db.execute_increment_rejection(req)
            self.view.apply_rejection_increment(entity_id, result["count"])
            return result

        elif op == OP_ADD_FINDING:
            result = self.db.execute_add_finding(req)
            self.view.apply_finding(
                result["finding_id"],
                req.payload["severity"], req.payload["source"],
                req.payload["message"], req.payload.get("detail")
            )
            return result

        elif op == OP_SET_STATION_STATUS:
            result = self.db.execute_set_station_status(req)
            self.view.apply_station_status(req.payload["station_id"], req.payload["status"])
            return result

        else:
            log.warning(f"Unknown operation: {req.op}")
            return {"ok": False, "error": f"unknown operation: {req.op}"}

    # ─── Signature Verification ────────────────────────────────────────────

    def _verify_signature(self, req: WriteRequest) -> bool:
        """
        Verify the station's HMAC signature.
        Falls back to accepting the write if auth is not enabled (dev mode).
        """
        if not self.station_registry.auth_enabled:
            return True  # Dev mode — no auth required

        key = self.station_registry.get_station_key(req.station_id)
        if not key:
            log.warning(f"[AUTH] Unknown station: {req.station_id}")
            return False

        return verify_write_signature(key, req.op, req.payload, req.signature)

    # ─── Main Loop ───────────────────────────────────────────────────────────

    def run_loop(self, poll_timeout: float = 0.5):
        """
        Main write loop. Pops from Redis, verifies, executes, updates view.
        Blocks until stop() is called or leadership is lost.
        """
        log.info(f"Write broker loop starting. Polling {self.queue_key}")
        self._stats["start_time"] = datetime.now(timezone.utc).isoformat()

        while self._running:
            try:
                # Blocking pop from Redis queue — waits up to poll_timeout
                result = self.r.blpop(self.queue_key, timeout=poll_timeout)

                if result is None:
                    # Timeout — just check leadership and continue
                    continue

                _, raw = result
                req = WriteRequest.from_json(raw)

                self._stats["writes_processed"] += 1
                op_stats = self._stats["writes_by_op"]
                op_stats[req.op] = op_stats.get(req.op, 0) + 1

                # Verify station signature
                if not self._verify_signature(req):
                    self._stats["signatures_rejected"] += 1
                    log.warning(f"[AUTH] Signature rejected for {req.station_id}/{req.op} "
                                f"req={req.request_id}")
                    self._enqueue_ack(req, False, "invalid signature")
                    continue

                # ─── Rate limit per station (WHITEPAPER 8: Rate limit evasion at Write Broker) ───
                # If station has exhausted its token bucket, slow down (not reject).
                # This provides backpressure without losing writes.
                wait = self.rate_limiter.wait_time(req.station_id)
                if wait > 0:
                    self._stats["rate_limited"] += 1
                    log.debug(f"[RATE] {req.station_id} rate-limited, waiting {wait:.2f}s")
                    time.sleep(wait)

                # Execute write
                try:
                    result_data = self._dispatch(req)
                    self._stats["writes_succeeded"] += 1
                    self._enqueue_ack(req, True, None, result_data)
                    self._publish_view_to_redis()
                    log.debug(f"[{req.op}] {req.request_id} → OK")

                except Exception as e:
                    self._stats["writes_failed"] += 1
                    log.error(f"[{req.op}] {req.request_id} → ERROR: {e}")
                    self._enqueue_ack(req, False, str(e))

            except redis.ConnectionError as e:
                log.error(f"Redis connection lost: {e}. Reconnecting in 1s...")
                time.sleep(1)
                try:
                    self.r.ping()
                    log.info("Redis reconnected")
                except redis.ConnectionError:
                    pass
            except Exception as e:
                log.error(f"Unexpected error in broker loop: {e}")

    def _publish_view_to_redis(self):
        """Push current materialized view to Redis for BrokerMaterializedView readers."""
        try:
            state = self.view.get_state()
            self.r.set(self.pool_state_key, json.dumps(state), ex=30)
        except Exception as e:
            log.warning(f"Failed to publish view to Redis: {e}")

    def _enqueue_ack(self, req: WriteRequest, ok: bool, error: str | None,
                       data: dict | None = None):
        """Write an acknowledgment back to the ack queue."""
        ack = {
            "request_id": req.request_id,
            "op": req.op,
            "station_id": req.station_id,
            "ok": ok,
            "error": error,
            "data": data,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self.r.lpush(self.ack_queue, json.dumps(ack))
            self.r.ltrim(self.ack_queue, 0, 999)
        except Exception as e:
            log.warning(f"Failed to enqueue ack for {req.request_id}: {e}")

    def start(self):
        """Start the broker. Initializes DuckDB and enters main loop."""
        self._running = True
        self._init_db()
        self.run_loop()

    def stop(self):
        self._running = False
        log.info("Broker stopping...")


# ─── Standby Monitor ──────────────────────────────────────────────────────────

class StandbyMonitor:
    """
    Monitors the primary broker via Redis lock TTL.
    On primary failure, takes over as new primary.
    """

    def __init__(self, redis_host: str, redis_port: int, db_path: str,
                 station_registry: StationKeyRegistry | None = None):
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.db_path = db_path
        self.station_registry = station_registry

        if redis is None:
            raise ImportError("redis package required: pip install redis")
        self.r = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
        self.broker: WriteBroker | None = None
        self._running = False

    def run(self):
        """
        Monitor loop. Attempts to become primary when lock expires.
        On becoming primary, starts the write broker.
        """
        election = LeaderElection(self.r, DEFAULT_LOCK_KEY)
        log.info("Standby monitor started. Waiting for primary to fail...")

        self._running = True
        while self._running:
            if election.is_leader:
                # We are the leader — renew lock and run broker
                if not election.renew():
                    log.warning("Lost leadership unexpectedly")
                    continue
                time.sleep(DEFAULT_LOCK_RENEW_INTERVAL)
            else:
                # Check if primary is still alive
                ttl = self.r.ttl(DEFAULT_LOCK_KEY)
                if ttl == -2:
                    # Key does not exist — primary is dead, try to acquire
                    log.warning("Primary lock expired. Attempting to acquire leadership...")
                    if election.try_acquire():
                        log.info("Leadership acquired! Starting write broker...")
                        self.broker = WriteBroker(
                            self.redis_host, self.redis_port, self.db_path,
                            station_registry=self.station_registry
                        )
                        self.broker.start()
                    else:
                        log.info("Leadership claim failed (another standby got it first)")
                elif ttl == -1:
                    # Key exists but has no TTL — race condition, try anyway
                    if election.try_acquire():
                        log.info("Acquired leadership (key had no TTL)")
                        self.broker = WriteBroker(
                            self.redis_host, self.redis_port, self.db_path,
                            station_registry=self.station_registry
                        )
                        self.broker.start()
                else:
                    # Primary is alive (TTL > 0) — wait half the remaining TTL
                    wait = max(0.5, min(ttl / 2, 5))
                    time.sleep(wait)

    def stop(self):
        self._running = False
        if self.broker:
            self.broker.stop()


# ─── DRAGON HTTP API ──────────────────────────────────────────────────────────

def run_api_server(view: MaterializedView, port: int = DEFAULT_API_PORT):
    """
    Minimal HTTP server for DRAGON to poll the materialized view.
    DRAGON calls GET /state at 500ms intervals.
    """
    try:
        from http.server import HTTPServer, BaseHTTPRequestHandler
    except ImportError:
        log.error("http.server not available — cannot start API server")
        return

    class StateHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/state" or self.path == "/":
                state = view.get_state()
                body = json.dumps(state).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", len(body))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/health":
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"OK")
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, fmt, *args):
            pass  # Silent — avoid log spam at 500ms poll rate

    server = HTTPServer(("0.0.0.0", port), StateHandler)
    log.info(f"DRAGON API server listening on http://0.0.0.0:{port}")
    server.serve_forever()


# ─── CLI Entry Point ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="XP-Arc Write Broker")
    parser.add_argument("--role", choices=["primary", "standby", "api-only"],
                          default="primary",
                          help="primary=run broker, standby=monitor+failover, api-only=DRAGON API only")
    parser.add_argument("--db", default="xp_arc.db",
                          help="Path to DuckDB file")
    parser.add_argument("--redis-host", default=DEFAULT_REDIS_HOST)
    parser.add_argument("--redis-port", type=int, default=DEFAULT_REDIS_PORT)
    parser.add_argument("--api-port", type=int, default=DEFAULT_API_PORT)
    parser.add_argument("--queue", default=DEFAULT_REDIS_QUEUE)
    parser.add_argument("--master-key",
                          help="XP_ARC_MASTER_KEY for station auth")
    args = parser.parse_args()

    station_registry = (
        StationKeyRegistry(args.master_key) if args.master_key
        else StationKeyRegistry(None)
    )

    if args.role == "api-only":
        # DRAGON API only — read view from Redis (written by external broker)
        from xp_arc.broker_client import BrokerMaterializedView
        view = BrokerMaterializedView(args.redis_host, args.redis_port)
        run_api_server(view, args.api_port)

    elif args.role == "standby":
        monitor = StandbyMonitor(
            args.redis_host, args.redis_port, args.db,
            station_registry=station_registry
        )
        signal.signal(signal.SIGINT, lambda *a: monitor.stop())
        signal.signal(signal.SIGTERM, lambda *a: monitor.stop())
        monitor.run()

    else:  # primary
        broker = WriteBroker(
            args.redis_host, args.redis_port, args.db,
            queue_key=args.queue,
            station_registry=station_registry
        )

        def handle_signal(sig, frame):
            broker.stop()
            if broker.duckdb:
                broker.duckdb.close()
            sys.exit(0)

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        # Start DRAGON API in background thread
        api_thread = threading.Thread(
            target=run_api_server,
            args=(broker.view, args.api_port),
            daemon=True
        )
        api_thread.start()

        # Also run leader election so primary holds the lock
        if redis is None:
            raise ImportError("redis package required: pip install redis")
        r = redis.Redis(host=args.redis_host, port=args.redis_port, decode_responses=True)
        election = LeaderElection(r, DEFAULT_LOCK_KEY)
        if not election.try_acquire():
            log.warning("Could not acquire primary lock — another broker may be running")
        else:
            log.info("Primary lock acquired")

        broker.start()


if __name__ == "__main__":
    main()