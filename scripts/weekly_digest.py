#!/usr/bin/env python3
"""
Weekly job: collect fresh data, then write the AI Agent Ecosystem Weekly digest.

Runs each step as a subprocess with a timeout, records every run in
data/competitive/job_runs.db, and exits non-zero if the digest could not be
produced. Collection errors from individual sources do not fail the job: the
digest's coverage section reports which sources returned data.

Usage (from the repository root):
    python scripts/weekly_digest.py                 # current ISO week
    python scripts/weekly_digest.py --week 2026-W42
    python scripts/weekly_digest.py --skip-fetch    # rebuild from stored data

Cron (Mondays 08:07 local):
    7 8 * * 1  cd /path/to/xp-arc && .venv/bin/python scripts/weekly_digest.py

Set XP_ARC_ALERT_WEBHOOK to POST a JSON alert when the job fails.
"""

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_DB = ROOT / "data" / "competitive" / "job_runs.db"
STEP_TIMEOUT = 900


def log_run(step: str, status: str, output: str, duration_ms: int) -> None:
    LOG_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(LOG_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS job_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            step TEXT NOT NULL,
            status TEXT NOT NULL,
            output TEXT,
            duration_ms INTEGER,
            ran_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("INSERT INTO job_runs (step, status, output, duration_ms) VALUES (?, ?, ?, ?)",
                 (step, status, output[-5000:], duration_ms))
    conn.commit()
    conn.close()


def alert(message: str) -> None:
    url = os.environ.get("XP_ARC_ALERT_WEBHOOK")
    if not url:
        return
    body = json.dumps({"text": message[:500]}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)  # nosec B310 - operator-configured webhook
    except Exception as exc:  # an alert failure must not mask the job result
        print(f"[weekly_digest] alert failed: {exc}", file=sys.stderr)


def run_step(name: str, args: list) -> bool:
    cmd = [sys.executable, "-m", "xp_arc.competitive_intel.station_main", *args]
    print(f"[weekly_digest] {name}: {' '.join(args)}")
    start = time.monotonic()
    try:
        result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                                timeout=STEP_TIMEOUT)
        output = (result.stdout + "\n" + result.stderr).strip()
        status = "SUCCESS" if result.returncode == 0 else "FAIL"
    except subprocess.TimeoutExpired:
        output, status = f"timed out after {STEP_TIMEOUT}s", "TIMEOUT"
    duration_ms = int((time.monotonic() - start) * 1000)
    log_run(name, status, output, duration_ms)
    print(f"[weekly_digest] {name}: {status} in {duration_ms} ms")
    if status != "SUCCESS":
        print(output[-2000:], file=sys.stderr)
    return status == "SUCCESS"


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect data and write the weekly digest")
    parser.add_argument("--week", help="ISO week, e.g. 2026-W42 (default: current week)")
    parser.add_argument("--output-dir", default="reports/digest")
    parser.add_argument("--skip-fetch", action="store_true",
                        help="Do not collect; rebuild the digest from stored data")
    args = parser.parse_args()

    if not run_step("init-db", ["init-db"]):
        alert("XP-Arc weekly digest: database init failed")
        return 1
    if not args.skip_fetch and not run_step("collect", ["run"]):
        # Keep going: a partial collection still yields a useful digest.
        alert("XP-Arc weekly digest: collection failed; digest built from stored data")

    digest_args = ["digest", "--output-dir", args.output_dir]
    if args.week:
        digest_args += ["--week", args.week]
    if not run_step("digest", digest_args):
        alert("XP-Arc weekly digest: digest generation failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
