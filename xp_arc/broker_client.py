"""
Broker Client — how stations and DRAGON interact with the Write Broker.

Station usage (enqueueing writes to Redis):
    from xp_arc.broker_client import StationClient
    client = StationClient("forager", station_key="...")
    client.add_entity("url", "https://example.com")
    client.transition_status(entity_id, "processing", station="forager")
    client.add_edge(source, "links_to", target)

DRAGON API-only mode (no local DuckDB — reads from Redis materialized view):
    from xp_arc.broker_client import BrokerMaterializedView
    view = BrokerMaterializedView()
    state = view.get_state()  # polls Redis at 500ms interval

Wait for write acknowledgment:
    ack = client.wait_ack(request_id, timeout=5.0)
    if ack and ack["ok"]:
        print("Write committed:", ack["data"])
    else:
        print("Write failed:", ack["error"])
"""

import json
import time
import uuid
from typing import Any

try:
    import redis
except ImportError:
    raise ImportError("redis package required: pip install redis")

import sys
sys.path.insert(0, '/Users/jadeddragon/xp-arc')

from xp_arc.core.authorization import compute_write_signature

DEFAULT_REDIS_HOST = "localhost"
DEFAULT_REDIS_PORT = 6379
DEFAULT_REDIS_QUEUE = "xp_arc:write_queue"
DEFAULT_REDIS_ACK_QUEUE = "xp_arc:write_ack"
DEFAULT_API_PORT = 8741
DEFAULT_POOL_STATE_KEY = "xp_arc:pool_state"


# ─── Station Client (enqueue signed writes to Redis) ─────────────────────────

class StationClient:
    """
    Client used by stations to enqueue signed write requests to the Write Broker
    via Redis. The broker pops, verifies the signature, commits to DuckDB/SQLite,
    and enqueues an acknowledgment.

    Thread-safe for concurrent use by multiple station workers.
    """

    def __init__(self, station_id: str,
                   station_key: str | None,
                   redis_host: str = DEFAULT_REDIS_HOST,
                   redis_port: int = DEFAULT_REDIS_PORT,
                   queue_key: str = DEFAULT_REDIS_QUEUE,
                   ack_queue: str = DEFAULT_REDIS_ACK_QUEUE):
        self.station_id = station_id
        self.station_key = station_key
        self.r = redis.Redis(host=redis_host, port=redis_port,
                            decode_responses=True)
        self.queue_key = queue_key
        self.ack_queue = ack_queue

    def _enqueue(self, op: str, payload: dict) -> str:
        """Enqueue a signed write request. Returns request_id."""
        if self.station_key:
            signature = compute_write_signature(self.station_key, op, payload)
        else:
            signature = ""

        from xp_arc.broker import WriteRequest
        req = WriteRequest(
            op=op,
            payload=payload,
            station_id=self.station_id,
            signature=signature,
        )
        self.r.rpush(self.queue_key, req.to_json())
        return req.request_id

    # ─── Write Operations ────────────────────────────────────────────────────

    def add_entity(self, ent_type: str, value: str,
                     sla_seconds: int = 60,
                     parent_task_id: int = None) -> str:
        """Enqueue add_entity. Returns request_id."""
        return self._enqueue("add_entity", {
            "type": ent_type, "value": value,
            "sla_seconds": sla_seconds,
            "parent_task_id": parent_task_id,
        })

    def transition_status(self, entity_id: int, new_status: str,
                           station: str | None = None,
                           confidence: float | None = None,
                           notes: str | None = None) -> str:
        """Enqueue status transition. Returns request_id."""
        payload = {"entity_id": entity_id, "new_status": new_status}
        if station is not None:
            payload["station"] = station
        if confidence is not None:
            payload["confidence"] = confidence
        if notes is not None:
            payload["notes"] = notes
        return self._enqueue("transition_status", payload)

    def add_edge(self, source: str, relationship: str, target: str) -> str:
        """Enqueue add_edge. Returns request_id."""
        return self._enqueue("add_edge", {
            "source": source,
            "relationship": relationship,
            "target": target,
        })

    def set_aboyeur_signature(self, entity_id: int, signature: str) -> str:
        return self._enqueue("set_aboyeur_signature", {
            "entity_id": entity_id,
            "signature": signature,
        })

    def increment_rejection(self, entity_id: int) -> str:
        return self._enqueue("increment_rejection", {"entity_id": entity_id})

    def add_finding(self, severity: str, source: str,
                     message: str, detail: str = None) -> str:
        return self._enqueue("add_finding", {
            "severity": severity, "source": source,
            "message": message, "detail": detail,
        })

    def set_station_status(self, station_id: str, status: str) -> str:
        return self._enqueue("set_station_status", {
            "station_id": station_id, "status": status,
        })

    # ─── Acknowledgments ────────────────────────────────────────────────────

    def wait_ack(self, request_id: str, timeout: float = 5.0) -> dict | None:
        """
        Block waiting for acknowledgment of a specific request_id.
        Returns the ack dict or None on timeout.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            result = self.r.brpop(self.ack_queue, timeout=max(0.1, remaining))
            if result:
                _, raw = result
                ack = json.loads(raw)
                if ack["request_id"] == request_id:
                    return ack
        return None

    def drain_acks(self, timeout: float = 1.0, max_count: int = 100) -> list[dict]:
        """
        Drain all available acks (up to max_count) from the ack queue.
        Non-blocking within each pop.
        """
        acks = []
        for _ in range(max_count):
            result = self.r.brpop(self.ack_queue, timeout=0.05)
            if not result:
                break
            _, raw = result
            acks.append(json.loads(raw))
        return acks

    def get_queue_depth(self) -> int:
        """Return current queue depth (for monitoring)."""
        return self.r.llen(self.queue_key)


# ─── Broker Materialized View (DRAGON API-only mode) ──────────────────────────

class BrokerMaterializedView:
    """
    Reads the materialized view directly from Redis (written by the Write Broker).

    CONSTITUTION Article III, Section 3.5:
      "DRAGON polls this materialized view at 500ms — never the DuckDB file."

    Used when DRAGON runs without a local DuckDB (api-only broker mode).
    DRAGON polls GET /state on the broker's HTTP API, which reads from this view.
    """

    def __init__(self, redis_host: str = DEFAULT_REDIS_HOST,
                   redis_port: int = DEFAULT_REDIS_PORT,
                   state_key: str = DEFAULT_POOL_STATE_KEY):
        self.r = redis.Redis(host=redis_host, port=redis_port,
                            decode_responses=True)
        self.state_key = state_key

    def get_state(self) -> dict:
        """
        Retrieve the current materialized view from Redis.
        Returns full pool state or an empty shell if no state exists yet.
        """
        raw = self.r.get(self.state_key)
        if raw:
            return json.loads(raw)
        return {
            "meta": {
                "version": 0,
                "last_updated": 0,
                "stale_seconds": 999,
                "exported_at": None,
                "error": "No materialized view available — broker may not be running",
            },
            "entities": [],
            "edges": [],
            "stations": [],
            "findings": [],
            "events": [],
            "stats": {},
        }

    def get_version(self) -> int:
        """Return the current view version (increments on every write)."""
        raw = self.r.get(self.state_key)
        if not raw:
            return 0
        state = json.loads(raw)
        return state.get("meta", {}).get("version", 0)

    def is_stale(self, max_age_seconds: float = 5.0) -> bool:
        """Return True if the view hasn't been updated within max_age_seconds."""
        raw = self.r.get(self.state_key)
        if not raw:
            return True
        state = json.loads(raw)
        stale = state.get("meta", {}).get("stale_seconds", 999)
        return stale > max_age_seconds

    def ping_broker(self) -> bool:
        """Return True if the broker is responsive (via Redis ping)."""
        try:
            return self.r.ping()
        except Exception:
            return False


# ─── DRAGON HTTP API Client ───────────────────────────────────────────────────

class DragonAPIClient:
    """
    Lightweight HTTP client for DRAGON to poll the broker's API server.
    Wraps polling and handles stale view detection.
    """

    def __init__(self, host: str = "localhost",
                   port: int = DEFAULT_API_PORT):
        self.base_url = f"http://{host}:{port}"
        import urllib.request
        self._opener = urllib.request.urlopen

    def get_state(self) -> dict:
        """Fetch the current pool state from the broker API."""
        try:
            import json as _json
            resp = self._opener(f"{self.base_url}/state", timeout=2.0)
            body = resp.read()
            return _json.loads(body)
        except Exception as e:
            return {
                "meta": {"error": str(e)},
                "entities": [], "edges": [], "stations": [],
                "findings": [], "events": [], "stats": {},
            }

    def health(self) -> bool:
        """Return True if broker API is responsive."""
        try:
            self._opener(f"{self.base_url}/health", timeout=1.0)
            return True
        except Exception:
            return False