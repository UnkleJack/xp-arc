#!/usr/bin/env bash
# XP-Arc start.sh – convenience wrapper to launch the persistent daemon.
#
# Usage:   ./start.sh [options]
#
# Options are passed directly to `run_persistent.py`.
# Common flags:
#   --db <path>          Path to SQLite DB (default: ./xp_arc.db)
#   --port <int>         HTTP API port (default: 8089)
#   --poll <seconds>     Pool poll interval (default: 3)
#   --log-level <level>  Python logging level (DEBUG, INFO, WARNING)
#   --no-watchdog        Disable the internal watchdog (use with care).
#
# The script changes to its own directory, sets $DB based on $XP_ARC_DB
# (or defaults), and forwards all arguments.
#
# Example:
#   ./start.sh --port 9090
#   # Then query the API at http://localhost:9090/api/dragon
#
# For background execution you can use `nohup` or `&`:
#   nohup ./start.sh > start.log 2>&1 &
#
# For systemd installation see the installer output; the generated
# unit file points to this script.

cd "$(dirname "$0")"
DB="${XP_ARC_DB:-./xp_arc.db}"
python3 run_persistent.py --db "$DB" "$@"
