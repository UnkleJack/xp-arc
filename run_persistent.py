#!/usr/bin/env python3
"""
XP-Arc Persistent Kitchen — Daemon Mode.

Runs the brigade continuously, watching the pool for new
raw entities and processing them as they arrive. Designed
to run as a background service on Zo.Computer.

The kitchen never closes.

Usage:
    python run_persistent.py                          # Default config
    python run_persistent.py --db /path/to/xp_arc.db  # Custom DB
    python run_persistent.py --poll 2                  # 2-second poll interval
    python run_persistent.py --port 8089               # Enable seed API on port

Environment:
    XP_ARC_DB       — Database path (default: xp_arc.db)
    XP_ARC_POLL     — Poll interval seconds (default: 3)
    XP_ARC_PORT     — HTTP port for seed injection API (default: disabled)
    XP_ARC_MAX      — Max entities before auto-halt (default: 500)
"""

import argparse
import json
import os
import signal
import sys
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from xp_arc.core.pool import IntelligencePool
from xp_arc.core.executive import ExecutiveChef
from xp_arc.stations.forager import TheForager
from xp_arc.stations.analyst import TheAnalyst
from xp_arc.stations.sentinel import TheSentinel
from xp_arc.stations.plongeur import ThePlongeur
from xp_arc.monitoring.zorans_law import ZoransLaw
from xp_arc.monitoring.spazzmatic import SpaZzMatiC


class PersistentKitchen:
    """
    The kitchen that never closes.

    Polls the Intelligence Pool for raw entities, processes them
    through the brigade, and runs health checks on every cycle.
    """

    def __init__(self, db_path: str = "xp_arc.db", poll_interval: float = 3.0,
                 max_entities: int = 500):
        self.db_path = db_path
        self.poll_interval = poll_interval
        self.max_entities = max_entities
        self._running = False
        self._cycles = 0

        # Initialize
        self.pool = IntelligencePool(db_path)
        self.executive = ExecutiveChef(self.pool, max_entities=max_entities, verbose=True)
        self.zorans = ZoransLaw(self.pool)
        self.spazz = SpaZzMatiC(self.pool, self.zorans)

        # Register stations
        self.forager = TheForager(self.pool, max_domains_per_target=5)
        self.analyst = TheAnalyst(self.pool)
        self.sentinel = TheSentinel(self.pool)
        self.plongeur = ThePlongeur(self.pool)

        self.executive.register_station(self.forager)
        self.executive.register_station(self.analyst)

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

        self.pool._log_event('daemon_start', 'persistent',
                             f"Persistent kitchen started. Poll: {self.poll_interval}s")

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
        # Check for raw entities
        raw = self.pool.get_next_raw()
        if not raw:
            return  # Nothing to do

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
            print("\n[!!! SAFE HALT RECOMMENDED !!!]")
            print("[!!! 60-second veto window active !!!]")
            self.pool._log_event('safe_halt_warning', 'persistent',
                                 'SpaZzMatiC recommended safe halt')

        # Export state for DRAGON
        self._export_dragon_state()

    def _export_dragon_state(self):
        """Write current state to JSON for DRAGON consumption."""
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

    def seed(self, url: str) -> dict:
        """Inject a seed URL into the pool. Returns entity info."""
        eid = self.pool.add_entity('url', url)
        if eid:
            return {'status': 'seeded', 'entity_id': eid, 'url': url}
        return {'status': 'duplicate', 'url': url}


# ─── Seed Injection HTTP API ───

class SeedAPIHandler(BaseHTTPRequestHandler):
    """Minimal HTTP API for injecting seeds and reading pool state."""

    kitchen = None  # Set by main()

    def do_GET(self):
        if self.path == '/api/dragon' or self.path == '/api/pool':
            # Serve full pool state
            export = self.kitchen.pool.export_state()
            export['zorans_latest'] = self.kitchen.zorans.get_latest()
            self._json_response(export)

        elif self.path == '/api/health':
            measurement = self.kitchen.zorans.get_latest() or {}
            self._json_response({
                'status': 'running' if self.kitchen._running else 'stopped',
                'cycles': self.kitchen._cycles,
                'zorans': measurement,
                'entities': self.kitchen.pool.count_entities(),
            })

        elif self.path == '/api/entities':
            entities = [dict(row) for row in self.kitchen.pool.get_all_entities()]
            self._json_response({'entities': entities})

        elif self.path == '/api/edges':
            edges = [dict(row) for row in self.kitchen.pool.get_all_edges()]
            self._json_response({'edges': edges})

        elif self.path == '/api/findings':
            findings = [dict(row) for row in self.kitchen.pool.get_findings()]
            self._json_response({'findings': findings})

        elif self.path == '/api/events':
            events = [dict(row) for row in self.kitchen.pool.get_events(200)]
            self._json_response({'events': list(reversed(events))})

        else:
            self._json_response({'error': 'Not found', 'endpoints': [
                '/api/dragon', '/api/health', '/api/entities',
                '/api/edges', '/api/findings', '/api/events',
                'POST /api/seed {"url": "https://..."}',
            ]}, status=404)

    def do_POST(self):
        if self.path == '/api/seed':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            try:
                data = json.loads(body)
                url = data.get('url')
                if not url:
                    self._json_response({'error': 'Missing "url" field'}, status=400)
                    return
                result = self.kitchen.seed(url)
                self._json_response(result)
            except json.JSONDecodeError:
                self._json_response({'error': 'Invalid JSON'}, status=400)
        else:
            self._json_response({'error': 'Not found'}, status=404)

    def _json_response(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2, default=str).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def log_message(self, format, *args):
        # Suppress default logging, use pool events instead
        pass


def main():
    parser = argparse.ArgumentParser(
        description="XP-Arc Persistent Kitchen — Daemon Mode"
    )
    parser.add_argument('--db', default=os.environ.get('XP_ARC_DB', 'xp_arc.db'),
                        help='Database path')
    parser.add_argument('--poll', type=float,
                        default=float(os.environ.get('XP_ARC_POLL', '3')),
                        help='Poll interval in seconds')
    parser.add_argument('--max-entities', type=int,
                        default=int(os.environ.get('XP_ARC_MAX', '500')),
                        help='Max entities before auto-halt')
    parser.add_argument('--port', type=int,
                        default=int(os.environ.get('XP_ARC_PORT', '0')),
                        help='HTTP API port (0=disabled)')
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

    # Start HTTP API if port specified
    if args.port > 0:
        SeedAPIHandler.kitchen = kitchen
        server = HTTPServer(('0.0.0.0', args.port), SeedAPIHandler)
        api_thread = threading.Thread(target=server.serve_forever, daemon=True)
        api_thread.start()
        print(f"[API] Seed injection API running on port {args.port}")
        print(f"[API] DRAGON endpoint: http://localhost:{args.port}/api/dragon")
        print(f"[API] Seed endpoint:   POST http://localhost:{args.port}/api/seed")
        print()

    # Handle SIGTERM gracefully
    def handle_sigterm(signum, frame):
        print("\n[PERSISTENT] SIGTERM received. Shutting down...")
        kitchen.stop()

    signal.signal(signal.SIGTERM, handle_sigterm)

    # Start the persistent loop
    kitchen.start()


if __name__ == '__main__':
    main()
