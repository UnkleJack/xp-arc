#!/usr/bin/env python3
"""
XP-Arc Competitive Intelligence Station
Main entry point for the competitive intelligence agent.
"""

import asyncio
import argparse
import sys
import os
from pathlib import Path
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from competitive_intel.station import CompetitiveIntelStation
from competitive_intel.config import load_config


async def main():
    parser = argparse.ArgumentParser(description="XP-Arc Competitive Intelligence Station")
    parser.add_argument("command", choices=[
        "run", "fetch", "detect", "report", "snapshot", "query", "health", "init-db"
    ], help="Command to execute")
    parser.add_argument("--config", default="config/competitive-intelligence-station.yaml", help="Config file path")
    parser.add_argument("--watchlist", default="config/competitive-watchlist.yaml", help="Watchlist file path")
    parser.add_argument("--source", help="Specific source to run (for fetch/detect)")
    parser.add_argument("--competitor", help="Specific competitor to query")
    parser.add_argument("--week", help="Week for report (YYYY-WNN)")
    parser.add_argument("--since", help="Since timestamp for query (ISO8601)")
    parser.add_argument("--severity", choices=["critical", "high", "medium", "low"], help="Filter by severity")
    parser.add_argument("--status", choices=["open", "investigating", "prototyping", "shipped", "wont_fix"], help="Filter gaps by status")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon (for scheduled runs)")
    parser.add_argument("--dry-run", action="store_true", help="Dry run - no database writes")

    args = parser.parse_args()

    # Load configuration
    config = load_config(args.config, args.watchlist)

    # Initialize station
    station = CompetitiveIntelStation(config, dry_run=args.dry_run)

    try:
        if args.command == "init-db":
            await station.init_database()
            print("Database initialized successfully")

        elif args.command == "fetch":
            if args.source:
                await station.fetch_source(args.source)
            else:
                await station.fetch_all_sources()

        elif args.command == "detect":
            if args.source:
                await station.detect_source(args.source)
            else:
                await station.detect_all()

        elif args.command == "run":
            if args.daemon:
                await station.run_daemon()
            else:
                await station.run_once()

        elif args.command == "report":
            await station.generate_weekly_report(args.week)

        elif args.command == "snapshot":
            if args.competitor:
                await station.snapshot_competitor(args.competitor)
            else:
                await station.snapshot_all_competitors()

        elif args.command == "query":
            results = await station.query_gaps(
                competitor=args.competitor,
                status=args.status,
                severity=args.severity,
                since=args.since
            )
            for r in results:
                print(r)

        elif args.command == "health":
            health = await station.check_source_health()
            for h in health:
                print(f"{h['source']}: SNR={h['snr']:.2%}, Errors={h['errors']}, Muted={h['muted']}")

    except KeyboardInterrupt:
        print("\nInterrupted")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if os.getenv("XP_ARC_DEBUG"):
            raise
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())