#!/usr/bin/env python3
"""
XP-Arc Batch Runner — Processes the next 1000 raw entities.

Designed to be called by a cron job every 10 minutes.
Picks up raw entities, runs them through the full brigade
(with HTTP probes), and exports state for DRAGON.

Usage:
    python3 batch_run.py                    # Process next 1000
    python3 batch_run.py --batch-size 500   # Custom batch size
    python3 batch_run.py --status           # Just print current stats
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from xp_arc.core.pool import IntelligencePool
from xp_arc.core.executive import ExecutiveChef
from xp_arc.stations.forager import TheForager
from xp_arc.stations.analyst import TheAnalyst
from xp_arc.stations.sentinel import TheSentinel
from xp_arc.stations.plongeur import ThePlongeur
from xp_arc.stations.cartographer import TheCartographer
from xp_arc.stations.auditor import TheAuditor
from xp_arc.monitoring.zorans_law import ZoransLaw
from xp_arc.monitoring.spazzmatic import SpaZzMatiC

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dragon_hoard.db')
EXPORT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dragon', 'pool_state.json')
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'batch_log.txt')


def log(msg):
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_PATH, 'a') as f:
        f.write(line + '\n')


def get_status():
    pool = IntelligencePool(DB_PATH)
    stats = pool.get_stats()
    total = pool.count_entities()
    raw = stats.get('raw', {}).get('count', 0)
    completed = stats.get('completed', {}).get('count', 0)
    failed = stats.get('failed', {}).get('count', 0)
    edges = len(pool.get_all_edges())
    pool.close()
    return {
        'total': total, 'raw': raw, 'completed': completed,
        'failed': failed, 'edges': edges,
        'progress': f"{completed}/{total} ({completed/max(total,1)*100:.1f}%)",
    }


def run_batch(batch_size=1000):
    log(f"═══ BATCH RUN START — Processing up to {batch_size} entities ═══")

    pool = IntelligencePool(DB_PATH)
    stats_before = pool.get_stats()
    raw_before = stats_before.get('raw', {}).get('count', 0)

    if raw_before == 0:
        log("No raw entities remaining. Hoard fully processed.")
        pool.close()
        return

    log(f"Raw entities waiting: {raw_before}")

    # Set up brigade — HTTP probes enabled (2s timeout for batch efficiency)
    executive = ExecutiveChef(pool, max_entities=batch_size, verbose=False)
    zorans = ZoransLaw(pool)

    forager = TheForager(pool, max_domains_per_target=3, timeout=2)
    analyst = TheAnalyst(pool)
    # Override probe timeout for batch efficiency
    original_probe = analyst._probe_domain
    def fast_probe(domain):
        import urllib.request
        result = {'reachable': False, 'redirect': None, 'server': None}
        try:
            req = urllib.request.Request(
                f"https://{domain}", method='HEAD',
                headers={'User-Agent': 'Mozilla/5.0 (XP-Arc Basilisk/0.2)'}
            )
            resp = urllib.request.urlopen(req, timeout=2)
            result['reachable'] = True
            result['server'] = resp.headers.get('Server', 'unknown')
            if resp.url != f"https://{domain}" and resp.url != f"https://{domain}/":
                result['redirect'] = resp.url
        except Exception:
            pass
        return result
    analyst._probe_domain = fast_probe

    executive.register_station(forager)
    executive.register_station(analyst)

    # Process
    t_start = time.time()
    summary = executive.run_service()
    t_elapsed = time.time() - t_start

    # Post-processing
    sentinel = TheSentinel(pool)
    plongeur = ThePlongeur(pool)
    plongeur.run_sweep()
    sentinel.run_health_check()

    # Zoran measurement
    measurement = zorans.measure()

    # Stats after
    stats_after = pool.get_stats()
    completed_after = stats_after.get('completed', {}).get('count', 0)
    raw_after = stats_after.get('raw', {}).get('count', 0)
    completed_before = stats_before.get('completed', {}).get('count', 0)
    batch_completed = completed_after - completed_before

    log(f"Batch complete: {batch_completed} entities processed in {t_elapsed:.1f}s")
    log(f"  Rate: {batch_completed/max(t_elapsed,1):.1f} entities/sec")
    log(f"  Remaining raw: {raw_after}")
    log(f"  Total completed: {completed_after}")
    log(f"  Zoran S={measurement['stability_quotient']:.3f} PRO={measurement['primary_role_occupancy']:.0%}")
    log(f"  Aboyeur: {summary['aboyeur']['approvals']} approved, {summary['aboyeur']['rejections']} rejected")

    # Export for DRAGON (every batch updates the dashboard)
    export = pool.export_state()
    export['zorans_latest'] = measurement
    export['batch_info'] = {
        'last_batch_time': datetime.now(timezone.utc).isoformat(),
        'last_batch_size': batch_completed,
        'last_batch_duration': round(t_elapsed, 1),
        'remaining_raw': raw_after,
    }

    os.makedirs(os.path.dirname(EXPORT_PATH), exist_ok=True)
    with open(EXPORT_PATH, 'w') as f:
        json.dump(export, f, indent=2, default=str)

    log(f"DRAGON export updated: {EXPORT_PATH}")
    log(f"═══ BATCH RUN COMPLETE ═══")
    log("")

    pool.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch-size', type=int, default=1000)
    parser.add_argument('--status', action='store_true')
    args = parser.parse_args()

    if args.status:
        s = get_status()
        print(json.dumps(s, indent=2))
        return

    run_batch(args.batch_size)


if __name__ == '__main__':
    main()
