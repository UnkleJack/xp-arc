#!/usr/bin/env python3
"""
Competitive-intel acceptance run — the end-to-end gate.

This is the run Dragon set as the bar before any marketing push: a REAL
workload, against REAL external sources, carried the whole way through the
constitutional pipeline. Nothing in XP-Arc had ever done that. Every prior
integration test used a stub engine or a localhost server the test itself
started, which proves the code runs but not that the protocol works.

The gate, in order:

    1. FETCH      real competitive events from live public sources
    2. DETECT     gaps from those events
    3. SNAPSHOT   per-competitor point-in-time state
    4. BRIDGE     republish gaps into the Intelligence Pool as entities
    5. ROUTE      the Executive dispatches them to CompetitiveGapAnalyst
    6. ABOYEUR    every completed entity carries a QA signature
    7. ZORAN      stability is measured over the run
    8. DRAGON     the result is present in the exported dashboard state

Each stage asserts. A stage that cannot run says so and fails the gate rather
than being skipped quietly — a green run that silently skipped the network is
worse than a red one.

Usage:
    XP_ARC_ABOYEUR_KEY=... python3.12 scripts/competitive_acceptance_run.py
    ... --offline     use gaps already in the competitive DB, skip the network
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from xp_arc.competitive_intel import (  # noqa: E402
    CompetitiveGapAnalyst, CompetitiveIntelBridge, CompetitiveIntelStation,
    load_all_configs,
)
from xp_arc.core.executive import ExecutiveChef  # noqa: E402
from xp_arc.core.pool import IntelligencePool  # noqa: E402
from xp_arc.monitoring.zorans_law import ZoransLaw  # noqa: E402
from xp_arc.stations.chef_de_cuisine import ChefDeCuisine  # noqa: E402


class GateFailure(AssertionError):
    """A stage of the acceptance gate did not pass."""


def gate(number, label, condition, detail):
    status = 'PASS' if condition else 'FAIL'
    print(f"  [{status}] Gate {number}: {label}")
    print(f"         {detail}")
    if not condition:
        raise GateFailure(f"Gate {number} ({label}): {detail}")


def banner(text):
    print()
    print("=" * 72)
    print(f"  {text}")
    print("=" * 72)


async def run(args):
    if not os.environ.get('XP_ARC_ABOYEUR_KEY'):
        print("XP_ARC_ABOYEUR_KEY is not set. The Aboyeur refuses to construct "
              "without a signing key, which is correct — set it and re-run.")
        return 2

    banner("XP-ARC COMPETITIVE-INTEL ACCEPTANCE RUN")

    config = load_all_configs(
        str(PROJECT_ROOT / 'config' / 'competitive-intelligence-station.yaml'),
        str(PROJECT_ROOT / 'config' / 'competitive-watchlist.yaml'),
    )
    intel = CompetitiveIntelStation(config)
    await intel.init_database()

    # ─── 1. FETCH ────────────────────────────────────────────────────────────
    banner("STAGE 1 — FETCH (live external sources)")
    if args.offline:
        print("  --offline: skipping the network fetch.")
        events_fetched = None
    else:
        await intel.fetch_all_sources()
        conn = intel.get_connection()
        try:
            events_fetched = conn.execute(
                "SELECT COUNT(*) AS c FROM raw_events").fetchone()['c']
        finally:
            conn.close()
        gate(1, "Real events fetched from live sources", events_fetched > 0,
             f"{events_fetched} raw events in the competitive database")

    # ─── 2. DETECT ───────────────────────────────────────────────────────────
    banner("STAGE 2 — DETECT (gap analysis)")
    if not args.offline:
        await intel.detect_all()
    gaps = await intel.query_gaps(status='open')
    gate(2, "Gaps detected from real events", len(gaps) > 0,
         f"{len(gaps)} open gaps available to publish")

    # ─── 3. SNAPSHOT ─────────────────────────────────────────────────────────
    banner("STAGE 3 — SNAPSHOT (competitor state)")
    await intel.snapshot_all_competitors()
    conn = intel.get_connection()
    try:
        snapshots = conn.execute(
            "SELECT COUNT(*) AS c FROM competitor_snapshots").fetchone()['c']
    finally:
        conn.close()
    gate(3, "Competitor snapshots recorded (was a no-op stub)", snapshots > 0,
         f"{snapshots} snapshot rows written")

    # ─── 4. BRIDGE ───────────────────────────────────────────────────────────
    banner("STAGE 4 — BRIDGE (competitive DB -> Intelligence Pool)")
    db_path = str(PROJECT_ROOT / args.pool_db)
    for stale in (db_path, db_path + '.station_keys.json.enc'):
        if os.path.exists(stale) and args.fresh:
            os.remove(stale)

    pool = IntelligencePool(db_path)
    bridge = CompetitiveIntelBridge(pool, intel)
    published = await bridge.publish_gaps(status='open')
    gate(4, "Gaps published into the pool as signed entities", len(published) > 0,
         f"{len(published)} entities created, {bridge.stats['skipped_duplicate']} "
         f"already present, {bridge.stats['truncated']} truncated by cap")

    # ─── 5. ROUTE ────────────────────────────────────────────────────────────
    banner("STAGE 5 — ROUTE (Executive -> CompetitiveGapAnalyst)")
    executive = ExecutiveChef(pool, max_entities=500, verbose=args.verbose)
    executive.register_station(CompetitiveGapAnalyst(pool))
    executive.register_station(ChefDeCuisine(pool))
    summary = executive.run_service()

    entities = [dict(e) for e in pool.get_all_entities()
                if e['type'] == 'competitive_gap']
    completed = [e for e in entities if e['status'] == 'completed']
    gate(5, "Every bridged gap was routed and completed",
         len(entities) > 0 and len(completed) == len(entities),
         f"{len(completed)}/{len(entities)} completed, "
         f"{summary['unhandled']} unhandled, {summary['retries']} retries")

    # ─── 6. ABOYEUR ──────────────────────────────────────────────────────────
    banner("STAGE 6 — ABOYEUR (mandatory QA seal)")
    unsigned = [e for e in completed if not e['aboyeur_signature']]
    gate(6, "Every completed entity carries an Aboyeur signature",
         completed and not unsigned,
         f"{len(completed)} signed, {len(unsigned)} unsigned")
    if completed:
        print(f"         sample signature: {completed[0]['aboyeur_signature'][:32]}...")

    # ─── 7. ZORAN ────────────────────────────────────────────────────────────
    banner("STAGE 7 — ZORAN'S LAW (stability measurement)")
    zorans = ZoransLaw(pool)
    measurement = zorans.measure()
    print(zorans.format_report())
    gate(7, "Stability measured over the run",
         measurement['stability_quotient'] is not None
         and pool.get_zorans_history(),
         f"S={measurement['stability_quotient']} "
         f"state={measurement['system_state']} "
         f"window={measurement['window_seconds']}s")

    # ─── 8. DRAGON ───────────────────────────────────────────────────────────
    banner("STAGE 8 — DRAGON (visible in exported dashboard state)")
    export = pool.export_state()
    export['summary'] = summary
    export['zorans_latest'] = zorans.get_latest()
    out = PROJECT_ROOT / args.export
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, 'w') as fh:
        json.dump(export, fh, indent=2, default=str)

    exported_gaps = [e for e in export['entities'] if e['type'] == 'competitive_gap']
    leaked_keys = [s for s in export['stations'] if 'hmac_key' in s]
    gate(8, "Competitive gaps present in DRAGON export", len(exported_gaps) > 0,
         f"{len(exported_gaps)} gap entities in {out.name}")
    gate('8b', "No station HMAC key leaked into the export (RT-11)",
         not leaked_keys, f"{len(leaked_keys)} stations exposing a key")

    banner("ACCEPTANCE GATE PASSED")
    print(f"  events fetched : {events_fetched if events_fetched is not None else 'skipped (offline)'}")
    print(f"  gaps published : {len(published)}")
    print(f"  entities sealed: {len(completed)}")
    print(f"  findings       : {len(export['findings'])}")
    print(f"  S              : {measurement['stability_quotient']}")
    print(f"  DRAGON export  : {out}")
    pool.close()
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true',
                        help='Skip the live fetch and use gaps already stored')
    parser.add_argument('--pool-db', default='data/competitive/acceptance_pool.db')
    parser.add_argument('--export', default='data/competitive/acceptance_dragon.json')
    parser.add_argument('--fresh', action='store_true',
                        help='Delete the acceptance pool DB before running')
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args()

    try:
        return asyncio.run(run(args))
    except GateFailure as exc:
        banner("ACCEPTANCE GATE FAILED")
        print(f"  {exc}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
