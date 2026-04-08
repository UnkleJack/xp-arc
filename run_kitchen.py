#!/usr/bin/env python3
"""
XP-Arc Kitchen Runner — CLI Entry Point.

Seeds the Intelligence Pool, starts the brigade, runs QA,
monitors health, and exports state for DRAGON.

Usage:
    python run_kitchen.py                              # Default 5-target spread
    python run_kitchen.py https://example.com          # Custom seeds
    python run_kitchen.py --db myrun.db https://a.com  # Custom DB path
    python run_kitchen.py --export-only                # Re-export existing DB
"""

import argparse
import json
import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from xp_arc.core.pool import IntelligencePool
from xp_arc.core.executive import ExecutiveChef
from xp_arc.stations.forager import TheForager
from xp_arc.stations.analyst import TheAnalyst
from xp_arc.stations.sentinel import TheSentinel
from xp_arc.stations.plongeur import ThePlongeur
from xp_arc.monitoring.zorans_law import ZoransLaw
from xp_arc.monitoring.spazzmatic import SpaZzMatiC


# Default targets — the original 5-target spread
DEFAULT_TARGETS = [
    "https://news.ycombinator.com",
    "https://github.com/unklejack",
    "https://lobste.rs",
    "https://httpbin.org/html",
    "https://en.wikipedia.org/wiki/Kitchen_brigade_system",
]


def run_kitchen(targets: list, db_path: str = "xp_arc.db",
                max_entities: int = 500, verbose: bool = True) -> dict:
    """
    Full pipeline execution.

    1. Initialize pool + stations
    2. Seed targets
    3. Run Executive (routing + Aboyeur QA)
    4. Run Plongeur sweep
    5. Run Sentinel health check
    6. Measure Zoran's Law
    7. Run SpaZzMatiC adversarial review
    8. Export state for DRAGON

    Returns: export dict
    """

    print("╔══════════════════════════════════════════════╗")
    print("║          XP-ARC — KITCHEN RUNNER v0.2       ║")
    print("║     Exponential Architecture Protocol       ║")
    print("╚══════════════════════════════════════════════╝")
    print()

    # ─── Initialize ───
    pool = IntelligencePool(db_path)
    executive = ExecutiveChef(pool, max_entities=max_entities, verbose=verbose)
    zorans = ZoransLaw(pool)
    spazz = SpaZzMatiC(pool, zorans)

    # ─── Register Stations ───
    forager = TheForager(pool, max_domains_per_target=5)
    analyst = TheAnalyst(pool)
    sentinel = TheSentinel(pool)
    plongeur = ThePlongeur(pool)

    executive.register_station(forager)
    executive.register_station(analyst)

    print(f"\n[KITCHEN] Seeding {len(targets)} targets...\n")

    # ─── Seed Pool ───
    for url in targets:
        eid = pool.add_entity('url', url)
        if eid:
            print(f"  [POOL] + Seed: {url}")
        else:
            print(f"  [POOL] ~ Already in pool: {url}")

    # ─── Run Brigade ───
    print()
    summary = executive.run_service()

    # ─── Post-Processing ───
    print("\n" + "─" * 60)
    print("  POST-PROCESSING")
    print("─" * 60)

    # Plongeur sweep
    print()
    plongeur.run_sweep()

    # Sentinel health check
    print()
    sentinel.run_health_check()

    # Zoran's Law measurement
    print()
    print(zorans.format_report())

    # SpaZzMatiC adversarial review
    print()
    print(spazz.format_report())

    # ─── Print Corkboard ───
    print("\n" + "=" * 60)
    print("  THE CORKBOARD")
    print("=" * 60)

    entities = pool.get_all_entities()
    print(f"\n[ ENTITIES ({len(entities)}) ]")
    for e in entities[:30]:
        status_icon = {
            'completed': '✓',
            'failed': '✗',
            'raw': '○',
            'processing': '◑',
            'pending_qa': '◐',
        }.get(e['status'], '?')
        sig = f" sig:{e['aboyeur_signature'][:12]}..." if e['aboyeur_signature'] else ""
        print(f"  {status_icon} [{e['type'].upper():>8}] {e['value'][:50]:<50} "
              f"({e['status']}){sig}")

    if len(entities) > 30:
        print(f"  ... and {len(entities) - 30} more")

    edges = pool.get_all_edges()
    print(f"\n[ EDGES ({len(edges)}) ]")
    for edge in edges[:20]:
        print(f"  {edge['source'][:40]} --({edge['relationship']})--> {edge['target']}")

    if len(edges) > 20:
        print(f"  ... and {len(edges) - 20} more")

    # ─── Aboyeur Stats ───
    print(f"\n[ ABOYEUR ]")
    astats = summary['aboyeur']
    print(f"  Verifications: {astats['verifications']}")
    print(f"  Approved: {astats['approvals']} ({astats['approval_rate']:.0%})")
    print(f"  Rejected: {astats['rejections']} ({astats['rejection_rate']:.0%})")

    # ─── Export for DRAGON ───
    export = pool.export_state()

    # Add summary data
    export['summary'] = summary
    export['zorans_latest'] = zorans.get_latest()

    export_path = db_path.replace('.db', '_dragon.json')
    with open(export_path, 'w') as f:
        json.dump(export, f, indent=2, default=str)

    print(f"\n[DRAGON] State exported to: {export_path}")
    print(f"[DRAGON] {len(entities)} entities, {len(edges)} edges, "
          f"{len(export['findings'])} findings, {len(export['events'])} events")

    pool.close()
    return export


def main():
    parser = argparse.ArgumentParser(
        description="XP-Arc Kitchen Runner — Multi-Agent Intelligence Pipeline"
    )
    parser.add_argument('targets', nargs='*', help='Seed URLs (default: 5-target spread)')
    parser.add_argument('--db', default='xp_arc.db', help='Database path (default: xp_arc.db)')
    parser.add_argument('--max-entities', type=int, default=500, help='Max entities (default: 500)')
    parser.add_argument('--quiet', action='store_true', help='Suppress verbose output')
    parser.add_argument('--export-only', action='store_true', help='Re-export existing DB without running pipeline')

    args = parser.parse_args()
    targets = args.targets or DEFAULT_TARGETS

    if args.export_only:
        pool = IntelligencePool(args.db)
        export = pool.export_state()
        export_path = args.db.replace('.db', '_dragon.json')
        with open(export_path, 'w') as f:
            json.dump(export, f, indent=2, default=str)
        print(f"Exported to {export_path}")
        pool.close()
        return

    run_kitchen(
        targets=targets,
        db_path=args.db,
        max_entities=args.max_entities,
        verbose=not args.quiet,
    )


if __name__ == '__main__':
    main()
