#!/usr/bin/env python3
"""
Benchmark the one‑shot pipeline.

Usage:
    python benchmark.py [--iterations N] [--db path] [targets...]

The script runs `run_kitchen.py` repeatedly, measures wall‑clock time for each run,
and prints mean/median/min/max timings.
"""

import argparse, subprocess, time, statistics, sys, os

def run_once(db, targets):
    cmd = [sys.executable, 'run_kitchen.py', '--db', db] + targets
    start = time.time()
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return time.time() - start

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--iterations', type=int, default=5, help='Number of runs to average')
    p.add_argument('--db', default='xp_arc.db', help='Database path')
    p.add_argument('targets', nargs='*', help='Target URLs (optional)')
    args = p.parse_args()

    timings = []
    for i in range(args.iterations):
        t = run_once(args.db, args.targets)
        timings.append(t)
        print(f'Run {i+1}/{args.iterations}: {t:.3f}s')

    print('\n=== Benchmark summary ===')
    print(f'Mean:   {statistics.mean(timings):.3f}s')
    print(f'Median: {statistics.median(timings):.3f}s')
    print(f'Min:    {min(timings):.3f}s')
    print(f'Max:    {max(timings):.3f}s')

if __name__ == '__main__':
    main()
