#!/usr/bin/env python3
"""Run a bounded live XP-Arc resilience proof for the canonical core and DRAGON.

The run contains one real public success target and controlled curveballs that
must be contained as terminal failures. It is intentionally small: production
load testing remains deterministic in the test suite, while this script proves
that the actual outbound and observability path works on a local machine.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from xp_arc.core.executive import ExecutiveChef
from xp_arc.core.pool import IntelligencePool
from xp_arc.monitoring.spazzmatic import SpaZzMatiC
from xp_arc.monitoring.zorans_law import ZoransLaw
from xp_arc.stations import TheAnalyst, TheForager, ThePlongeur, TheSentinel


LIVE_SUCCESS = "https://example.com"
LIVE_HTTP_FAILURE = "https://httpbin.org/status/404"
LIVE_REDIRECT = "https://httpbin.org/redirect/2"
MALFORMED_URL = "ftp://not-allowed.example"
PRIVATE_ADDRESS = "http://127.0.0.1"
DEPTH_LIMITED_URL = "https://example.org"


def configure_brigade(pool: IntelligencePool) -> tuple[ExecutiveChef, ZoransLaw, SpaZzMatiC]:
    executive = ExecutiveChef(pool, max_entities=30, verbose=True)
    executive.register_station(TheForager(pool, max_domains_per_target=3, timeout=5))
    executive.register_station(TheAnalyst(pool))
    zorans = ZoransLaw(pool)
    spazz = SpaZzMatiC(pool, zorans)
    spazz.set_executive(executive)
    return executive, zorans, spazz


def seed_adversarial_pool(pool: IntelligencePool) -> dict[str, int | None]:
    """Seed one real success and a deliberately awkward but bounded failure set."""
    seeds = {
        "live_success": pool.add_entity("url", LIVE_SUCCESS),
        "live_http_failure": pool.add_entity("url", LIVE_HTTP_FAILURE),
        "live_redirect": pool.add_entity("url", LIVE_REDIRECT),
        "malformed": pool.add_entity("url", MALFORMED_URL),
        "private_address": pool.add_entity("url", PRIVATE_ADDRESS),
        "depth_limited": pool.add_entity(
            "url", DEPTH_LIMITED_URL, crawl_depth=1, max_crawl_depth=1
        ),
    }
    # Idempotency must suppress duplicate raw work without creating a second row.
    seeds["duplicate_live_success"] = pool.add_entity("url", LIVE_SUCCESS)
    return seeds


def run(db_path: str, export_path: str | None = None) -> dict:
    if not os.environ.get("XP_ARC_ABOYEUR_KEY"):
        raise RuntimeError("XP_ARC_ABOYEUR_KEY must be set before running the acceptance proof")

    pool = IntelligencePool(db_path)
    executive, zorans, spazz = configure_brigade(pool)
    seeds = seed_adversarial_pool(pool)
    summary = executive.run_service()

    plongeur = ThePlongeur(pool)
    sentinel = TheSentinel(pool)
    sweep = plongeur.run_sweep()
    health = sentinel.run_health_check()
    zoran = zorans.measure()
    review = spazz.run_review()

    entities = [dict(entity) for entity in pool.get_all_entities()]
    failures = [entity for entity in entities if entity["status"] == "failed"]
    completed = [entity for entity in entities if entity["status"] == "completed"]
    all_terminal = all(entity["status"] in {"completed", "failed"} for entity in entities)
    signed_completed = all(entity["aboyeur_signature"] for entity in completed)
    refused = {entity["value"]: entity["refusal_reason"] for entity in failures}

    required_refusals = {
        MALFORMED_URL: "malformed_url",
        PRIVATE_ADDRESS: "outbound_fetch_failed",
        DEPTH_LIMITED_URL: "crawl_depth_limit",
    }
    refusal_checks = {
        value: bool(refused.get(value) and reason in refused[value])
        for value, reason in required_refusals.items()
    }
    report = {
        "seeds": seeds,
        "summary": summary,
        "post_processing": {"sweep": sweep, "health": health, "zorans": zoran, "spazzmatic": review},
        "entities": entities,
        "assertions": {
            "duplicate_suppressed": seeds["duplicate_live_success"] is None,
            "all_terminal": all_terminal,
            "completed_are_signed": signed_completed,
            "controlled_refusals": refusal_checks,
            "at_least_one_live_completion": bool(completed),
            "at_least_one_live_network_failure": any(
                entity["value"] in {LIVE_HTTP_FAILURE, LIVE_REDIRECT}
                and entity["status"] == "failed"
                for entity in entities
            ),
        },
    }
    report["passed"] = all(
        [
            report["assertions"]["duplicate_suppressed"],
            report["assertions"]["all_terminal"],
            report["assertions"]["completed_are_signed"],
            all(report["assertions"]["controlled_refusals"].values()),
            report["assertions"]["at_least_one_live_completion"],
            report["assertions"]["at_least_one_live_network_failure"],
        ]
    )

    export = pool.export_state()
    export["zorans_latest"] = zorans.get_latest()
    export["acceptance_report"] = report
    resolved_export = Path(export_path or db_path.replace(".db", "_dragon.json"))
    resolved_export.write_text(json.dumps(export, indent=2, default=str), encoding="utf-8")
    pool.close()

    print(json.dumps(report, indent=2, default=str))
    print(f"DRAGON export: {resolved_export}")
    if not report["passed"]:
        raise SystemExit(1)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the bounded live XP-Arc resilience proof")
    parser.add_argument("--db", default="xp_arc_acceptance.db", help="SQLite database path")
    parser.add_argument("--export", default=None, help="Optional DRAGON export path")
    args = parser.parse_args()
    run(args.db, args.export)


if __name__ == "__main__":
    main()
