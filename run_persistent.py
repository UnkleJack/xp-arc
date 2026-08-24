#!/usr/bin/env python3
"""
XP-Arc Persistent Kitchen — Daemon Mode with WebSocket Telemetry.

Runs the brigade continuously, watching the pool for new entities and processing them.
Serves HTTP API for seed injection + WebSocket for real-time telemetry streaming.

Usage:  python3 run_persistent.py [options]

Options (environment variables can also be used):
  --db <path>           Path to SQLite DB (default: ./xp_arc.db)
  --port <int>          HTTP/WebSocket API port (default: 8089)
  --poll <seconds>      Pool poll interval (default: 0.5)
  --log-level <level>   Set Python logging level (DEBUG, INFO, WARNING)
  --no-watchdog         Disable the internal watchdog (use with care).

Environment overrides (take precedence over defaults):
  XP_ARC_DB, XP_ARC_PORT, XP_ARC_POLL

The script will print a short startup banner and then serve the API.
It can be run in foreground for debugging or background.

API Authentication: Set XP_ARC_API_KEY to enable Bearer token auth on all endpoints.

WebSocket Events (pushed on every cycle):
  {
    "event": "cycle_complete",
    "cycle": 42,
    "timestamp": "2026-08-09T14:30:00Z",
    "zorans": {"stability_quotient": 1.23, "primary_role_occupancy": 0.85, ...},
    "entities": {"total": 150, "completed": 120, "processing": 10, "raw": 5, "failed": 15},
    "stations": {"forager": {"processed": 50, "failed": 2}, ...},
    "findings": [...],
    "events": [...]
  }

Usage:
    python run_persistent.py                          # Default config
    python run_persistent.py --db /path/to/xp_arc.db  # Custom DB
    python run_persistent.py --poll 2                  # 2-second poll interval
    python run_persistent.py --port 8089               # Enable API on port
"""

import argparse
import asyncio
import json
import os
import secrets
import signal
import sys
import time
import logging
import threading
from pathlib import Path
from datetime import datetime, timezone
from typing import Set, Dict, Any, List
from aiohttp import web, WSMsgType

# Logging configuration
log_level = os.getenv('XP_ARC_LOG_LEVEL', 'INFO').upper()
log_file = os.getenv('XP_ARC_LOG')
handlers = [logging.StreamHandler()]
if log_file:
    handlers = [logging.FileHandler(log_file)]
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s',
    handlers=handlers,
)
logger = logging.getLogger('xp_arc')

from urllib.parse import urlparse

from xp_arc.core.pool import IntelligencePool
from xp_arc.core.network_guard import public_url
from xp_arc.core.executive import ExecutiveChef
from xp_arc.stations.forager import TheForager
from xp_arc.stations.analyst import TheAnalyst
from xp_arc.stations.librarian import TheLibrarian
from xp_arc.stations.cartographer import TheCartographer
from xp_arc.stations.hydra import TheHydra
from xp_arc.stations.salamander import TheSalamander
from xp_arc.stations.herald import TheHerald
from xp_arc.stations.dossier import TheDossier
from xp_arc.stations.warden import TheWarden
from xp_arc.stations.plongeur import ThePlongeur
from xp_arc.stations.sentinel import TheSentinel
from xp_arc.stations.chef_de_cuisine import ChefDeCuisine
from xp_arc.monitoring.zorans_law import ZoransLaw
from xp_arc.monitoring.spazzmatic import SpaZzMatiC


# API Key from environment (optional - if not set, auth is disabled)
API_KEY = os.environ.get("XP_ARC_API_KEY")


class PersistentKitchen:
    """
    The kitchen that never closes.

    Polls the Intelligence Pool for raw entities, processes them
    through the brigade, and runs health checks on every cycle.
    Maintains WebSocket connections for real-time telemetry.
    """

    def __init__(self, db_path: str = "xp_arc.db", poll_interval: float = 0.5,
                 max_entities: int = 500):
        self.db_path = db_path
        self.poll_interval = poll_interval
        self.max_entities = max_entities
        self._running = False
        self._cycles = 0
        self._halt_vetoed = False
        self._halt_countdown = 0

        # WebSocket connections
        self._ws_connections: Set[web.WebSocketResponse] = set()

        # Initialize
        self.pool = IntelligencePool(db_path)
        self.executive = ExecutiveChef(self.pool, max_entities=max_entities, verbose=True)
        self.zorans = ZoransLaw(self.pool)
        self.spazz = SpaZzMatiC(self.pool, self.zorans)
        self.spazz.set_executive(self.executive)

        # Register stations
        self.forager = TheForager(self.pool, max_domains_per_target=5)
        self.analyst = TheAnalyst(self.pool)
        self.librarian = TheLibrarian(self.pool)
        self.cartographer = TheCartographer(self.pool)
        self.hydra = TheHydra(self.pool)
        self.salamander = TheSalamander(self.pool)
        self.herald = TheHerald(self.pool)
        self.dossier = TheDossier(self.pool)
        self.warden = TheWarden(self.pool)
        self.plongeur = ThePlongeur(self.pool)
        self.sentinel = TheSentinel(self.pool)
        # Escalation authority. CRITICAL: survives Brigade Compression.
        self.chef_de_cuisine = ChefDeCuisine(self.pool)

        for station in [self.forager, self.analyst, self.librarian, self.cartographer,
                        self.hydra, self.salamander, self.herald, self.dossier,
                        self.warden, self.plongeur, self.sentinel,
                        self.chef_de_cuisine]:
            self.executive.register_station(station)

    def start(self):
        """Start the persistent loop."""
        self._running = True
        print()
        print("╔══════════════════════════════════════════════╗")
        print("║    XP-ARC PERSISTENT KITCHEN — DAEMON MODE  ║")
        print("║         The kitchen never closes.            ║")
        print("╠══════════════════════════════════════════════╣")
        print(f"║  DB:    {self.db_path:<38s} ║")
        print(f"║  Poll:  {self.poll_interval}s{' ' * (36 - len(str(self.poll_interval)))} ║")
        print(f"║  Max:   {self.max_entities} entities{' ' * (29 - len(str(self.max_entities)))} ║")
        print("╚══════════════════════════════════════════════╝")
        print()
        logger.info("Persistent kitchen started – DB=%s, poll=%s, max=%s", self.db_path, self.poll_interval, self.max_entities)

        self.pool._log_event('daemon_start', 'persistent',
                             f"Persistent kitchen started. Poll: {self.poll_interval}s")
        # DRAGON must surface health immediately, even if this persisted Pool
        # contains no new raw entities for the first polling cycle.
        self.zorans.measure()
        self.spazz.run_review()
        self._export_dragon_state()

        try:
            while self._running:
                self._cycle()
                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            print("\n[PERSISTENT] Kitchen shutting down gracefully...")
            self._running = False

        self.pool._log_event('daemon_stop', 'persistent', 'Persistent kitchen stopped.')
        self.pool.close()
        print("[PERSISTENT] Kitchen closed. Pool saved.")

    def stop(self):
        self._running = False

    def _cycle(self):
        """One processing cycle."""
        import math

        # Check for raw entities
        raw = self.pool.get_next_raw()
        if not raw:
            # Still tick the veto window while idle
            if self._halt_countdown > 0:
                self._halt_countdown = max(0, self._halt_countdown - self.poll_interval)
                if self._halt_countdown == 0 and not self._halt_vetoed:
                    print("\n[SAFE HALT] Veto window expired. Initiating safe halt.")
                    self._running = False
            return

        self._cycles += 1
        now = datetime.now(timezone.utc).strftime('%H:%M:%S')
        print(f"\n[{now}] Cycle #{self._cycles} — processing raw entities")

        # Process all available raw entities
        self.executive.run_service()

        # Post-processing health checks every 5 cycles
        if self._cycles % 5 == 0:
            self.plongeur.run_sweep()
            self.sentinel.run_health_check()

        # Zoran + SpaZzMatiC every cycle
        self.zorans.measure()
        review = self.spazz.run_review()

        if review['safe_halt_recommended']:
            if not self._halt_vetoed:
                # Start 60-second veto window
                self._halt_countdown = 60
                print("\n[!!! SAFE HALT RECOMMENDED !!!]")
                print("[!!! 60-second veto window active !!!]")
                print("[!!! Call kitchen.stop() or Ctrl+C within 60s to veto !!!]")
                self.pool._log_event('safe_halt_warning', 'persistent',
                                     'SpaZzMatiC recommended safe halt — veto window started')
            else:
                # Already vetoed, halt now
                print("\n[SAFE HALT] Veto window expired. Initiating safe halt.")
                self._running = False
        elif self._halt_countdown > 0:
            # Recommendation cleared — cancel the window
            print("\n[SAFE HALT] Recommendation cleared. Veto window cancelled.")
            self._halt_countdown = 0

        # Decrement veto countdown if window is active
        if self._halt_countdown > 0:
            self._halt_countdown = max(0, self._halt_countdown - self.poll_interval)
            if self._halt_countdown > 0:
                print(f"[SAFE HALT] Veto window: {math.ceil(self._halt_countdown)}s remaining")
            elif not self._halt_vetoed:
                self._halt_vetoed = True
                self._running = False
                print("\n[SAFE HALT] Veto window expired. Initiating safe halt.")

        # Export state for DRAGON (static fallback) + push WebSocket telemetry
        self._export_dragon_state()
        self._push_websocket_telemetry()

    def _export_dragon_state(self):
        """Write current state to JSON for DRAGON consumption (static fallback)."""
        export = self.pool.export_state()
        export['zorans_latest'] = self.zorans.get_latest()
        export['daemon'] = {
            'running': self._running,
            'cycles': self._cycles,
            'poll_interval': self.poll_interval,
        }

        export_path = self.db_path.replace('.db', '_dragon.json')
        with open(export_path, 'w') as f:
            json.dump(export, f, indent=2, default=str)

    def _push_websocket_telemetry(self):
        """Build telemetry payload and push to all connected WebSocket clients."""
        if not self._ws_connections:
            return

        # Build telemetry payload
        zorans_latest = self.zorans.get_latest() or {}
        station_stats = {}
        for s in self.executive.stations:
            station_stats[s.station_id] = {
                'processed': s._tasks_processed,
                'failed': s._tasks_failed,
                'active': s.is_active,
                'is_primary': s.is_primary,
                'handles_types': s.handles_types,
            }

        # Entity counts by status
        all_entities = self.pool.get_all_entities()
        entity_counts = {}
        for e in all_entities:
            status = e['status']
            entity_counts[status] = entity_counts.get(status, 0) + 1

        # Recent findings
        findings = [dict(row) for row in self.pool.get_findings()]
        recent_findings = findings[:20] if findings else []

        # Recent events (last 50)
        events = [dict(row) for row in self.pool.get_events(50)]

        payload = {
            'event': 'cycle_complete',
            'cycle': self._cycles,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'zorans': zorans_latest,
            'entities': {
                'total': len(all_entities),
                **entity_counts,
            },
            'stations': station_stats,
            'spawn': {
                'created': self.executive._spawn_created,
                'blocked': self.executive._spawn_blocked,
            },
            'findings': recent_findings,
            'events': events,
            'safe_halt': {
                'recommended': self.spazz._safe_halt_recommended,
                'countdown': self._halt_countdown,
                'vetoed': self._halt_vetoed,
            },
        }

        # Push to all connected clients
        dead_connections = set()
        for ws in self._ws_connections:
            if not ws.closed:
                try:
                    # Use asyncio to send from sync context
                    asyncio.run_coroutine_threadsafe(
                        ws.send_str(json.dumps(payload, default=str)),
                        self._loop
                    )
                except Exception:
                    dead_connections.add(ws)
            else:
                dead_connections.add(ws)

        # Clean up dead connections
        for ws in dead_connections:
            self._ws_connections.discard(ws)

    # An operator-supplied seed is the one place untrusted input reaches the
    # pool directly, so it is validated before ingestion rather than trusted.
    MAX_SEED_URL_LEN = 2048

    def validate_seed_url(self, url: str) -> str | None:
        """Return a rejection reason, or None if the URL is acceptable.

        network_guard.public_url() is the same SSRF check the Forager uses when
        it fetches: it rejects private, loopback, link-local and reserved
        addresses, and the .test/.invalid/.example/.localhost suffixes. Reusing
        it here means the seed endpoint cannot be used to point the brigade at
        an internal service.
        """
        if not isinstance(url, str) or not url.strip():
            return 'url must be a non-empty string'
        url = url.strip()
        if len(url) > self.MAX_SEED_URL_LEN:
            return f'url exceeds {self.MAX_SEED_URL_LEN} characters'
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            return f'unsupported scheme {parsed.scheme!r}: only http and https are accepted'
        if not parsed.netloc:
            return 'url has no host'
        if not public_url(url):
            return 'host does not resolve to a public address (SSRF guard)'
        return None

    def seed(self, url: str) -> dict:
        """Inject a seed URL into the pool. Returns entity info."""
        reason = self.validate_seed_url(url)
        if reason:
            self.pool._log_event('seed_rejected', 'dragon_api',
                                 f"Seed rejected: {reason}", f"url={str(url)[:256]}")
            return {'status': 'rejected', 'url': url, 'reason': reason}
        url = url.strip()
        eid = self.pool.add_entity('url', url)
        if eid:
            return {'status': 'seeded', 'entity_id': eid, 'url': url}
        return {'status': 'duplicate', 'url': url}

    def register_ws(self, ws: web.WebSocketResponse):
        """Register a new WebSocket connection."""
        self._ws_connections.add(ws)
        logger.info(f"WebSocket connected. Total: {len(self._ws_connections)}")

    def unregister_ws(self, ws: web.WebSocketResponse):
        """Unregister a WebSocket connection."""
        self._ws_connections.discard(ws)
        logger.info(f"WebSocket disconnected. Total: {len(self._ws_connections)}")

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        """Set the event loop for cross-thread WebSocket sends."""
        self._loop = loop


# ─── HTTP + WebSocket Handlers ───

async def ws_handler(request: web.Request):
    """WebSocket endpoint for real-time telemetry."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    kitchen = request.app['kitchen']
    kitchen.register_ws(ws)

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    if data.get('type') == 'ping':
                        await ws.send_str(json.dumps({'type': 'pong', 'timestamp': datetime.now(timezone.utc).isoformat()}))
                except json.JSONDecodeError:
                    pass
            elif msg.type == WSMsgType.ERROR:
                logger.warning(f"WebSocket error: {ws.exception()}")
    finally:
        kitchen.unregister_ws(ws)

    return ws


async def health_handler(request: web.Request):
    """Health check endpoint."""
    kitchen = request.app['kitchen']
    measurement = kitchen.zorans.get_latest() or {}
    return web.json_response({
        'status': 'running' if kitchen._running else 'stopped',
        'cycles': kitchen._cycles,
        'zorans': measurement,
        'entities': kitchen.pool.count_entities(),
        'ws_connections': len(kitchen._ws_connections),
    })


async def dragon_handler(request: web.Request):
    """Full pool state for DRAGON dashboard."""
    kitchen = request.app['kitchen']
    export = kitchen.pool.export_state()
    export['zorans_latest'] = kitchen.zorans.get_latest()
    return web.json_response(export)


async def entities_handler(request: web.Request):
    """All entities."""
    kitchen = request.app['kitchen']
    entities = [dict(row) for row in kitchen.pool.get_all_entities()]
    return web.json_response({'entities': entities})


async def edges_handler(request: web.Request):
    """All edges."""
    kitchen = request.app['kitchen']
    edges = [dict(row) for row in kitchen.pool.get_all_edges()]
    return web.json_response({'edges': edges})


async def findings_handler(request: web.Request):
    """All findings."""
    kitchen = request.app['kitchen']
    findings = [dict(row) for row in kitchen.pool.get_findings()]
    return web.json_response({'findings': findings})


async def events_handler(request: web.Request):
    """Recent events."""
    kitchen = request.app['kitchen']
    events = [dict(row) for row in kitchen.pool.get_events(200)]
    return web.json_response({'events': events})


async def seed_handler(request: web.Request):
    """Inject a seed URL. Authenticated (via middleware), rate limited, validated."""
    allowed, retry_after = SEED_RATE_LIMITER.allow(client_key(request))
    if not allowed:
        return web.json_response(
            {'error': 'Rate limit exceeded', 'retry_after': retry_after},
            status=429, headers={'Retry-After': str(retry_after)},
        )

    try:
        data = await request.json()
    except (json.JSONDecodeError, ValueError):
        return web.json_response({'error': 'Invalid JSON'}, status=400)

    if not isinstance(data, dict):
        return web.json_response({'error': 'Body must be a JSON object'}, status=400)

    url = data.get('url')
    if not url:
        return web.json_response({'error': 'Missing "url" field'}, status=400)

    kitchen = request.app['kitchen']
    result = kitchen.seed(url)
    if result['status'] == 'rejected':
        return web.json_response(result, status=400)
    return web.json_response(result)


async def metrics_handler(request: web.Request):
    """Prometheus-compatible metrics."""
    kitchen = request.app['kitchen']
    total = kitchen.pool.count_entities()
    completed = len([e for e in kitchen.pool.get_all_entities() if e['status'] == 'completed'])
    metrics_text = f"xp_arc_entities_total {total}\nxp_arc_entities_completed {completed}\n"
    return web.Response(text=metrics_text, content_type='text/plain; version=0.0.4')


class RateLimiter:
    """Fixed-window per-client limiter for write endpoints.

    Deliberately simple and in-process: this guards a single-machine daemon
    against an unattended script hammering /api/seed, not against a distributed
    attacker. A real deployment behind a reverse proxy should rate limit there
    too. Windows are pruned on access so the dict cannot grow without bound.
    """

    def __init__(self, max_requests: int = 30, window_seconds: float = 60.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict = {}
        self._lock = threading.Lock()

    def allow(self, client: str) -> tuple:
        """Return (allowed, retry_after_seconds)."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            for key in [k for k, v in self._hits.items() if not v or v[-1] < cutoff]:
                del self._hits[key]
            hits = [t for t in self._hits.get(client, []) if t >= cutoff]
            if len(hits) >= self.max_requests:
                self._hits[client] = hits
                return False, max(1, int(hits[0] + self.window_seconds - now) + 1)
            hits.append(now)
            self._hits[client] = hits
            return True, 0


SEED_RATE_LIMITER = RateLimiter(max_requests=30, window_seconds=60.0)


def client_key(request: web.Request) -> str:
    """Identify the caller for rate limiting. Peer address, not a spoofable header."""
    peer = request.transport.get_extra_info('peername') if request.transport else None
    if isinstance(peer, tuple) and peer:
        return str(peer[0])
    return request.remote or 'unknown'


def check_auth(request: web.Request) -> bool:
    """Check Bearer token auth if API_KEY is configured."""
    if not API_KEY:
        return True
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer ') and secrets.compare_digest(auth_header[7:], API_KEY):
        return True
    # Browsers cannot set an Authorization header on a WebSocket handshake, so
    # /ws additionally accepts the key as a query parameter. Same secret, same
    # constant-time comparison — this is a transport accommodation, not a
    # weaker check.
    if request.path == '/ws':
        token = request.query.get('token', '')
        if token and secrets.compare_digest(token, API_KEY):
            return True
    return False


@web.middleware
async def cors_middleware(request: web.Request, handler):
    """Allow local DRAGON files and same-machine tools to read the observation API."""
    response = await handler(request)
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Authorization, Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response


@web.middleware
async def auth_middleware(request: web.Request, handler):
    """Middleware to enforce API key auth on protected routes.

    Only /api/health is unauthenticated, and only because a liveness probe must
    work without credentials; it returns no pool data.

    Previously this also exempted '/ws' and '/metrics' unconditionally. /ws
    streams the FULL pool telemetry payload, so that exemption meant setting
    XP_ARC_API_KEY protected the REST surface while leaving a complete live feed
    of the same data open to anyone who could reach the port — directly
    contradicting this module's own docstring. /metrics leaks entity counts.
    Both are now gated. When XP_ARC_API_KEY is unset, auth is disabled
    everywhere exactly as before, so this changes nothing for local dev.
    """
    if request.path == '/api/health':
        return await handler(request)
    if not check_auth(request):
        return web.json_response({'error': 'Unauthorized - invalid or missing Bearer token'}, status=401)
    return await handler(request)


def create_app(kitchen: PersistentKitchen) -> web.Application:
    """Create the single-machine dashboard and observation API host."""
    app = web.Application(middlewares=[cors_middleware, auth_middleware])
    app['kitchen'] = kitchen
    dragon_dir = Path(__file__).resolve().parent / 'dragon'

    async def dashboard_handler(_request: web.Request):
        return web.FileResponse(dragon_dir / 'index.html')

    async def start_kitchen(_app: web.Application):
        kitchen.set_loop(asyncio.get_running_loop())
        worker = threading.Thread(target=kitchen.start, name='xp-arc-kitchen', daemon=True)
        _app['kitchen_worker'] = worker
        worker.start()

    async def stop_kitchen(app_to_stop: web.Application):
        kitchen.stop()
        worker = app_to_stop.get('kitchen_worker')
        if worker:
            worker.join(timeout=max(5, kitchen.poll_interval * 4))

    app.on_startup.append(start_kitchen)
    app.on_shutdown.append(stop_kitchen)
    app.router.add_get('/', dashboard_handler)
    app.router.add_static('/dragon', dragon_dir)
    app.router.add_get('/ws', ws_handler)
    app.router.add_get('/api/health', health_handler)
    app.router.add_get('/api/dragon', dragon_handler)
    app.router.add_get('/api/pool', dragon_handler)
    app.router.add_get('/api/entities', entities_handler)
    app.router.add_get('/api/edges', edges_handler)
    app.router.add_get('/api/findings', findings_handler)
    app.router.add_get('/api/events', events_handler)
    app.router.add_post('/api/seed', seed_handler)
    app.router.add_get('/metrics', metrics_handler)
    app.router.add_get('/pool_state.json', dragon_handler)
    return app


def main():
    parser = argparse.ArgumentParser(
        description="XP-Arc Persistent Kitchen — Daemon Mode with WebSocket Telemetry"
    )
    parser.add_argument('--db', default=os.environ.get('XP_ARC_DB', 'xp_arc.db'),
                        help='Database path')
    parser.add_argument('--poll', type=float,
                        default=float(os.environ.get('XP_ARC_POLL', '0.5')),
                        help='Poll interval in seconds')
    parser.add_argument('--max-entities', type=int,
                        default=int(os.environ.get('XP_ARC_MAX', '500')),
                        help='Max entities before auto-halt')
    parser.add_argument('--port', type=int,
                        default=int(os.environ.get('XP_ARC_PORT', '8089')),
                        help='HTTP/WebSocket API port (0=disabled)')
    parser.add_argument('--host', default=os.environ.get('XP_ARC_HOST', '127.0.0.1'),
                        help='Bind address for the observation API. Defaults to '
                             '127.0.0.1 (loopback only). Set to 0.0.0.0 to accept '
                             'external connections — do that ONLY behind a trusted '
                             'network boundary and with XP_ARC_API_KEY set. '
                             'Containers need 0.0.0.0 for published ports to reach '
                             'the daemon; the container boundary is the isolation.')
    parser.add_argument('--seeds', nargs='*', help='Initial seed URLs')

    args = parser.parse_args()

    kitchen = PersistentKitchen(
        db_path=args.db,
        poll_interval=args.poll,
        max_entities=args.max_entities,
    )

    # Seed initial URLs if provided
    if args.seeds:
        for url in args.seeds:
            result = kitchen.seed(url)
            print(f"  [SEED] {result['status']}: {url}")

    # The dashboard server owns the asyncio event loop; the kitchen runs in a
    # dedicated worker so polling never starves the HTTP or WebSocket surface.
    if args.port > 0:
        app = create_app(kitchen)
        shown = 'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host
        print(f"[API] Bind address:        {args.host}:{args.port}")
        if args.host == '0.0.0.0' and not API_KEY:  # nosec B104 - operator opt-in, warned
            print("[API] *** WARNING: bound to all interfaces with XP_ARC_API_KEY "
                  "unset. Every endpoint, including the /ws telemetry stream, is "
                  "unauthenticated. ***")
        print(f"[API] DRAGON dashboard:     http://{shown}:{args.port}/")
        print(f"[API] WebSocket telemetry: ws://{shown}:{args.port}/ws")
        print(f"[API] DRAGON endpoint:     http://{shown}:{args.port}/api/dragon")
        print(f"[API] Seed endpoint:       POST http://{shown}:{args.port}/api/seed")
        print(f"[API] Health endpoint:     http://{shown}:{args.port}/api/health")
        print()
        web.run_app(app, host=args.host, port=args.port)
        return

    # Without the local observation server, retain a foreground CLI mode.
    signal.signal(signal.SIGTERM, lambda _signum, _frame: kitchen.stop())
    kitchen.start()


if __name__ == '__main__':
    main()
