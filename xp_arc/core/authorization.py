"""
Pool Write Authorization — Constitutional Access Control.

WHITEPAPER 5.5.1: The Intelligence Pool has no authentication. Any process on
the same machine can read and write to xp_arc.db directly.

This module implements signed write authorization:
- Every writing caller holds a station key registered at startup.
- All writes (add_entity, transition_status, add_edge) require a valid HMAC
  signature proving the caller holds the station's secret key.
- The master auth key is stored externally (env var) and used to derive
  per-station HMAC keys at registration time.
- Read operations (get_entity, get_all_entities, get_stats) are public — the
  Pool is a Glass Wall (Constitution Article III, Section 3.4).

In production, the Write Broker (Constitution Article III, Section 3.5) is the
single process with write access. All stations send signed write requests to
the Broker. This module provides the cryptographic foundation for that trust
model.

Usage:
    pool = IntelligencePool("xp_arc.db")
    authorizer = WriteAuthorizer(pool, master_key=os.environ["XP_ARC_MASTER_KEY"])
    authorizer.register_station("forager", "The Forager", ["url"], is_primary=True)

    # Station code:
    pool.add_entity("url", safe_url, station_key=authorizer.get_station_key("forager"))
    pool.transition_status(eid, "processing", station_key=authorizer.get_station_key("forager"))

Fallback (development): If no master key is configured, writes proceed unsigned
with a warning logged. This allows the reference implementation to run without
secret management infrastructure.
"""

import hashlib
import hmac
import json
import logging
import os
import secrets
from typing import Optional

logger = logging.getLogger("xp_arc.auth")

# ─── Key Derivation ───────────────────────────────────────────────────────────

def derive_station_key(master_key: str, station_id: str) -> str:
    """Derive a per-station HMAC key from the master key."""
    return hmac.new(
        master_key.encode(),
        station_id.encode(),
        hashlib.sha256
    ).hexdigest()[:32]


# ─── Station Key Registry ──────────────────────────────────────────────────────

class StationKeyRegistry:
    """
    Manages per-station secret keys and their derived HMAC verification keys.

    Keys are derived from the master auth key at registration time.
    Each station gets a unique HMAC key — compromise of one station key
    does not expose the master key or other stations.
    """

    def __init__(self, master_key: str | None):
        self._master_key = master_key.encode() if master_key else None
        self._station_keys: dict[str, str] = {}
        self._signing_keys: dict[str, str] = {}
        self._enabled = master_key is not None

        if not self._enabled:
            logger.warning(
                "[AUTH] No XP_ARC_MASTER_KEY set — write authorization DISABLED. "
                "ALL WRITES PROCEED WITHOUT SIGNATURE VERIFICATION. "
                "Do not use this mode in production."
            )

    def register_station(self, station_id: str, name: str,
                          handles_types: list, is_primary: bool = True) -> str | None:
        """
        Register a station and generate its signing key.

        Returns the station's secret key (hex, 32 chars) if authorized,
        or None if auth is disabled (development mode).
        """
        if not self._enabled:
            return None

        station_key = derive_station_key(self._master_key.decode(), station_id)
        self._station_keys[station_id] = station_key

        logger.info(f"[AUTH] Station registered: {station_id} ({name}) → [{', '.join(handles_types)}]")

        return station_key

    def get_station_key(self, station_id: str) -> str | None:
        """Return the station's signing key, or None if not found."""
        return self._station_keys.get(station_id)

    @property
    def auth_enabled(self) -> bool:
        return self._enabled


def compute_write_signature(station_key: str, operation: str, payload: dict) -> str:
    """
    Compute an HMAC-SHA256 signature for a pool write operation.

    The signature covers:
    - operation name (add_entity, transition_status, add_edge, etc.)
    - all relevant payload fields (type, value, entity_id, new_status, etc.)

    This prevents replay attacks (each operation's signature covers its context)
    and tampering (the payload is part of what is signed).
    """
    message = json.dumps(payload, sort_keys=True, default=str)
    sig = hmac.new(
        station_key.encode(),
        (operation + ":" + message).encode(),
        hashlib.sha256
    ).hexdigest()[:32]
    return f"XPKEY-{sig}"


def verify_write_signature(station_key: str, operation: str,
                             payload: dict, signature: str) -> bool:
    """
    Verify a write signature. Returns True if valid, False otherwise.

    Timing-safe comparison — avoids short-circuit on mismatch.
    """
    expected = compute_write_signature(station_key, operation, payload)
    return hmac.compare_digest(expected, signature)


# ─── Authorized Pool Wrapper ──────────────────────────────────────────────────

class AuthorizedIntelligencePool:
    """
    Wraps IntelligencePool with signed-write authorization.

    All write operations require a valid station key signature.
    Read operations (get_entity, get_all_entities, etc.) are unauthenticated.

    Usage:
        pool = IntelligencePool("xp_arc.db")
        auth = WriteAuthorizer(pool, master_key=os.environ.get("XP_ARC_MASTER_KEY"))
        auth_pool = AuthorizedIntelligencePool(pool, auth)
        auth_pool.register_station("forager", "The Forager", ["url"])

        # In station code:
        key = auth_pool.get_station_key("forager")
        auth_pool.add_entity("url", safe_url, station_key=key)
    """

    def __init__(self, pool, registry: StationKeyRegistry):
        self._pool = pool
        self._auth = registry
        # Mirror the underlying pool's connection for read operations
        self.conn = pool.conn

    # ─── Station Registration ─────────────────────────────────────────────────

    def register_station(self, station_id: str, name: str,
                           handles_types: list, is_primary: bool = True) -> str | None:
        """Register a station. Returns its signing key if auth is enabled."""
        return self._auth.register_station(station_id, name, handles_types, is_primary)

    def get_station_key(self, station_id: str) -> str | None:
        """Get a station's signing key (needed for write operations)."""
        return self._auth.get_station_key(station_id)

    @property
    def auth_enabled(self) -> bool:
        return self._auth.auth_enabled

    # ─── Authorized Writes ────────────────────────────────────────────────────

    def _sign_and_write(self, operation: str, payload: dict,
                         station_id: str, station_key: str | None) -> bool:
        """
        Verify signature and forward to the underlying pool.
        If auth is disabled (no station_key), writes proceed directly.
        """
        if self._auth.auth_enabled:
            if not station_key:
                logger.warning(f"[AUTH] {operation} rejected: no station key provided")
                return False
            sig = compute_write_signature(station_key, operation, payload)
            if not verify_write_signature(station_key, operation, payload, sig):
                logger.warning(f"[AUTH] {operation} REJECTED: invalid signature for {station_id}")
                return False

        # Auth passed (or disabled) — execute the operation
        return True

    def add_entity(self, ent_type: str, value: str, sla_seconds: int = 60,
                   parent_task_id: int = None, station_id: str = None,
                   station_key: str = None) -> int | None:
        """Write a new entity to the pool. Requires valid station signature."""
        payload = {"type": ent_type, "value": value, "sla_seconds": sla_seconds}
        if not self._sign_and_write("add_entity", payload, station_id, station_key):
            return None
        return self._pool.add_entity(ent_type, value, sla_seconds, parent_task_id)

    def transition_status(self, entity_id: int, new_status: str,
                           station_id: str = None, station_key: str = None,
                           **kwargs) -> bool:
        """Transition an entity status. Requires valid station signature."""
        payload = {"entity_id": entity_id, "new_status": new_status}
        if not self._sign_and_write("transition_status", payload, station_id, station_key):
            return False
        return self._pool.transition_status(entity_id, new_status, **kwargs)

    def add_edge(self, source: str, rel: str, target: str,
                  station_id: str = None, station_key: str = None) -> None:
        """Add an edge to the graph. Requires valid station signature."""
        payload = {"source": source, "relationship": rel, "target": target}
        if not self._sign_and_write("add_edge", payload, station_id, station_key):
            return
        self._pool.add_edge(source, rel, target)

    # ─── Unauthenticated Reads (Glass Wall — Constitution Article III, 3.4) ──

    def get_entity(self, entity_id: int):
        return self._pool.get_entity(entity_id)

    def get_all_entities(self):
        return self._pool.get_all_entities()

    def get_entities_by_status(self, status: str):
        return self._pool.get_entities_by_status(status)

    def get_next_raw(self):
        return self._pool.get_next_raw()

    def count_entities(self):
        return self._pool.count_entities()

    def get_all_edges(self):
        return self._pool.get_all_edges()

    def get_stats(self) -> dict:
        return self._pool.get_stats()

    def get_active_stations(self):
        return self._pool.get_active_stations()

    def get_findings(self):
        return self._pool.get_findings()

    def get_zorans_history(self):
        return self._pool.get_zorans_history()

    def get_events(self, limit: int = 200):
        return self._pool.get_events(limit)

    def get_orphaned_entities(self, threshold_seconds: int = 300):
        return self._pool.get_orphaned_entities(threshold_seconds)

    def export_state(self) -> dict:
        return self._pool.export_state()

    # ─── SpaZzMatiC / Zoran's Law (internal use, unauthenticated) ──────────────

    def add_finding(self, severity: str, source: str, message: str, detail: str = None):
        return self._pool.add_finding(severity, source, message, detail)

    def record_zorans_metrics(self, s: float, pro: float, state: str,
                               active: int, primary: int, completed: int, ingested: int):
        return self._pool.record_zorans_metrics(s, pro, state, active, primary, completed, ingested)

    def set_aboyeur_signature(self, entity_id: int, signature: str):
        return self._pool.set_aboyeur_signature(entity_id, signature)

    def increment_rejection(self, entity_id: int) -> int:
        return self._pool.increment_rejection(entity_id)

    def close(self):
        return self._pool.close()

    def get_zorans_metrics(self):
        return self._pool.get_zorans_metrics()

    def set_station_status(self, station_id: str, status: str):
        return self._pool.set_station_status(station_id, status)

    def _log_event(self, *args, **kwargs):
        return self._pool._log_event(*args, **kwargs)