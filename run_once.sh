#!/usr/bin/env bash
# XP-Arc run_once.sh – one‑shot execution wrapper.
#
# Usage:   ./run_once.sh [options]
#
# Options are passed directly to `run_kitchen.py`.
# Common flags:
#   --db <path>          Path to SQLite DB (default: ./xp_arc.db)
#   --export-only        Export pool state without running stations.
#   --quiet              Suppress progress output.
#   --dry-run            Validate pipeline without writing results.
#
# The script changes to its own directory, sets $DB based on $XP_ARC_DB 
# (or defaults), and forwards all arguments.
#
# Example:
#   ./run_once.sh --db myrun.db https://example.com
#
# For a full list of flags see `python3 run_kitchen.py --help`.

cd "$(dirname "$0")"
DB="${XP_ARC_DB:-./xp_arc.db}"
python3 run_kitchen.py --db "$DB" "$@"
