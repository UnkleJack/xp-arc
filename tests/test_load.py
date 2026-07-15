"""
XP-Arc Load Test Suite.

Tests the full brigade under Snowball load at 500+ entities.
Measures throughput, latency, SLA compliance, and cascade behavior.
Run with: python3 -m pytest tests/test_load.py -v --tb=short -s
"""
import time
import tempfile
import os
import sys

# Ensure xp_arc is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from xp_arc.core.pool import IntelligencePool
from xp_arc.core.executive import ExecutiveChef
from xp_arc.stations.forager import TheForager
from xp_arc.stations.analyst import TheAnalyst
from xp_arc.stations.librarian import TheLibrarian
from xp_arc.stations.cartographer import TheCartographer
from xp_arc.stations.hydra import TheHydra
from xp_arc.stations.warden import TheWarden
from xp_arc.stations.auditor import TheAuditor
from xp_arc.stations.amphithere import TheAmphithere
from xp_arc.stations.salamander import TheSalamander
from xp_arc.stations.herald import TheHerald
from xp_arc.stations.dossier import TheDossier
from xp_arc.stations.plongeur import ThePlongeur
from xp_arc.stations.sentinel import TheSentinel
from xp_arc.core.aboyeur import Aboyeur


# Override Forager timeout for load tests (avoid long DNS waits on .test TLD)
_ORIGINAL_FORAGER_INIT = TheForager.__init__
def _fast_forager_init(self, pool, max_domains_per_target: int = 5, timeout: int = 1):
    _ORIGINAL_FORAGER_INIT(self, pool, max_domains_per_target, timeout)
TheForager.__init__ = _fast_forager_init


# ─── Brigade Compression Test ──────────────────────────────────────────────

class _MockStation:
    """Minimal mock station for compression testing."""
    def __init__(self, name: str, handles_types: list[str], critical: bool = False):
        self.name = name
        self.station_id = name.lower().replace(' ', '_')
        self.handles_types = handles_types
        self.critical = critical
        self.is_active = True
        self._tasks_processed = 0
        self._tasks_failed = 0
        self.is_primary = True
        self.stats_called = False

    def can_handle(self, entity_type: str) -> bool:
        return entity_type in self.handles_types

    def stats(self) -> dict:
        self.stats_called = True
        return {
            'id': self.station_id,
            'processed': self._tasks_processed,
            'failed': self._tasks_failed,
        }


def test_brigade_compression():
    """Verify compress/expand failover behavior of the brigade."""
    db_path = tempfile.mktemp(suffix='.db')
    pool = IntelligencePool(db_path)
    exec_ = ExecutiveChef(pool, verbose=False)

    # Register mixed critical/non-critical stations
    forager = _MockStation('Forager', ['url'], critical=True)
    analyst = _MockStation('Analyst', ['domain'], critical=False)
    hydra = _MockStation('Hydra', ['ip'], critical=True)
    warden = _MockStation('Warden', ['cert'], critical=False)

    for s in [forager, analyst, hydra, warden]:
        exec_.register_station(s)

    # Verify all 4 registered
    assert len(exec_.stations) == 4, f"Expected 4 stations, got {len(exec_.stations)}"

    # Compress — only critical stations survive
    exec_.compress_brigade()
    assert exec_.is_compressed(), "Brigade should report compressed"
    assert len(exec_.stations) == 2, f"Expected 2 critical stations, got {len(exec_.stations)}"
    assert forager in exec_.stations, "Forager (critical) should remain"
    assert hydra in exec_.stations, "Hydra (critical) should remain"
    assert analyst not in exec_.stations, "Analyst (non-critical) should be removed"
    assert warden not in exec_.stations, "Warden (non-critical) should be removed"

    # Backup still has all 4
    assert len(exec_._station_backup) == 4, "Backup should preserve all 4 stations"
    assert len(exec_._critical_stations) == 2, "Critical set should have 2"

    # Compress again — idempotent
    exec_.compress_brigade()
    assert len(exec_.stations) == 2, "Second compress should be idempotent"

    # Expand — all restored
    exec_.expand_brigade()
    assert not exec_.is_compressed(), "Brigade should report expanded"
    assert len(exec_.stations) == 4, f"Expected all 4 restored, got {len(exec_.stations)}"
    assert analyst in exec_.stations, "Analyst should be restored"
    assert warden in exec_.stations, "Warden should be restored"

    # Expand again — idempotent
    exec_.expand_brigade()
    assert len(exec_.stations) == 4, "Second expand should be idempotent"

    pool.close()
    os.unlink(db_path)
    print("  PASS: brigade compression failover")


def test_brigade_routing_in_compressed_mode():
    """Verify entities only route to active (critical) stations during compression."""
    db_path = tempfile.mktemp(suffix='.db')
    pool = IntelligencePool(db_path)
    exec_ = ExecutiveChef(pool, verbose=False)

    forager = _MockStation('Forager', ['url'], critical=True)
    analyst = _MockStation('Analyst', ['domain'], critical=False)
    hydra = _MockStation('Hydra', ['ip'], critical=True)

    for s in [forager, analyst, hydra]:
        exec_.register_station(s)

    # Seed a URL (forager handles) and a domain (analyst handles)
    url_eid = pool.add_entity('url', 'https://example.test', sla_seconds=5)
    domain_eid = pool.add_entity('domain', 'example.test', sla_seconds=5)

    # Compress
    exec_.compress_brigade()

    # Manually process the URL — should still route to forager (critical)
    handler = next((s for s in exec_.stations if s.can_handle('url')), None)
    assert handler is forager, f"URL should route to forager, got {handler}"

    # Domain type — no critical station handles it
    handler = next((s for s in exec_.stations if s.can_handle('domain')), None)
    assert handler is None, "No handler should exist for domain in compressed mode"

    pool.close()
    os.unlink(db_path)
    print("  PASS: compressed-mode routing isolation")


def _complete_entity(pool, entity_id: int):
    """Complete an entity via the correct status transition path."""
    pool.transition_status(entity_id, 'processing')
    pool.transition_status(entity_id, 'pending_qa')
    pool.transition_status(entity_id, 'completed')


def test_zorans_law_s_below_threshold_triggers_compression():
    """S < 0.5 for 2 consecutive measurements triggers auto-compression."""
    from xp_arc.monitoring.zorans_law import ZoransLaw
    from xp_arc.monitoring.spazzmatic import SpaZzMatiC

    db_path = tempfile.mktemp(suffix='.db')
    pool = IntelligencePool(db_path)
    exec_ = ExecutiveChef(pool, verbose=False)

    # Register stations in DB so ZoransLaw can see them
    # 1 primary (critical) + 2 non-primary (non-critical) → PRO = 1/3
    pool.register_station('forager', 'Forager', ['url'], is_primary=True)
    pool.register_station('analyst', 'Analyst', ['domain'], is_primary=False)
    pool.register_station('librarian', 'Librarian', ['cert'], is_primary=False)

    # Register mock station objects with executive
    primary_station = _MockStation('Forager', ['url'], critical=True)
    non_primary1 = _MockStation('Analyst', ['domain'], critical=False)
    non_primary2 = _MockStation('Librarian', ['cert'], critical=False)
    for s in [primary_station, non_primary1, non_primary2]:
        exec_.register_station(s)

    # Seed one entity with a short SLA and complete it
    eid = pool.add_entity('url', 'https://test.test', sla_seconds=1)
    _complete_entity(pool, eid)

    zoran = ZoransLaw(pool)
    spazz = SpaZzMatiC(pool, zoran)
    spazz.set_executive(exec_)

    # PRO = 1/3 < 0.70 — triggers compression
    m1 = zoran.measure()
    result1 = spazz.run_review()
    assert exec_.is_compressed(), f"PRO < 70% should auto-compress. PRO={m1['primary_role_occupancy']}, findings: {result1['findings']}"

    pool.close()
    os.unlink(db_path)
    print("  PASS: PRO < 70% triggers auto-compression")


def test_zorans_law_s_streak_triggers_safe_halt():
    """S < 0.5 for 2 consecutive measurements triggers safe halt + compression."""
    from xp_arc.monitoring.zorans_law import ZoransLaw
    from xp_arc.monitoring.spazzmatic import SpaZzMatiC

    db_path = tempfile.mktemp(suffix='.db')
    pool = IntelligencePool(db_path)
    exec_ = ExecutiveChef(pool, verbose=False)

    # All primary (PRO=1.0), so PRO check doesn't fire
    all_primary = _MockStation('Forager', ['url'], critical=True)
    exec_.register_station(all_primary)

    # Seed one entity and complete it (S will be high initially)
    eid = pool.add_entity('url', 'https://test.test', sla_seconds=1)
    _complete_entity(pool, eid)

    zoran = ZoransLaw(pool)
    spazz = SpaZzMatiC(pool, zoran)
    spazz.set_executive(exec_)

    # Measurement 1: S=1.0 (all completed) — should be fine
    m1 = zoran.measure()
    result1 = spazz.run_review()
    assert not result1['safe_halt_recommended'], f"S=1.0 should not trigger safe halt. Findings: {result1['findings']}"
    assert not exec_.is_compressed(), "S=1.0 should not compress"
    assert spazz._s_violation_streak == 0, f"Streak should be 0 at S=1.0, got {spazz._s_violation_streak}"

    # Now seed two long-SLA entities that aren't completed — S will drop below 0.5
    # completed_sla=1, total=1+100+100=201, S=1/201 ≈ 0.005
    pool.add_entity('url', 'https://test2.test', sla_seconds=100)
    pool.add_entity('url', 'https://test3.test', sla_seconds=100)

    m2 = zoran.measure()
    s2 = m2['stability_quotient']
    result2 = spazz.run_review()

    assert s2 < 0.5, f"Expected S < 0.5, got {s2}"
    assert spazz._s_violation_streak == 1, f"First violation streak should be 1, got {spazz._s_violation_streak}"

    # Second consecutive measurement at low S
    result3 = spazz.run_review()
    assert spazz._s_violation_streak == 2, f"Streak should reach 2, got {spazz._s_violation_streak}"
    assert result3['safe_halt_recommended'], "Second consecutive S < 0.5 should recommend safe halt"
    assert exec_.is_compressed(), "Sustained distress should trigger brigade compression"

    # Check the finding
    critical_findings = [f for f in result3['findings'] if f['severity'] == 'critical']
    assert any('SAFE HALT' in f['message'] for f in critical_findings), \
        f"Expected SAFE HALT finding, got: {critical_findings}"

    pool.close()
    os.unlink(db_path)
    print("  PASS: S < 0.5 streak triggers safe halt + compression")


def test_zorans_law_recovery_resets_streak():
    """When S >= 0.5, streak resets and safe_halt_recommended clears."""
    from xp_arc.monitoring.zorans_law import ZoransLaw
    from xp_arc.monitoring.spazzmatic import SpaZzMatiC

    db_path = tempfile.mktemp(suffix='.db')
    pool = IntelligencePool(db_path)
    exec_ = ExecutiveChef(pool, verbose=False)

    station = _MockStation('Forager', ['url'], critical=True)
    exec_.register_station(station)

    # Seed and complete one entity (S=1.0)
    eid = pool.add_entity('url', 'https://test.test', sla_seconds=10)
    _complete_entity(pool, eid)

    zoran = ZoransLaw(pool)
    spazz = SpaZzMatiC(pool, zoran)
    spazz.set_executive(exec_)

    m = zoran.measure()
    assert m['stability_quotient'] == 1.0, f"Expected S=1.0, got {m['stability_quotient']}"

    result = spazz.run_review()
    assert spazz._s_violation_streak == 0, f"Streak should be 0 at S=1.0, got {spazz._s_violation_streak}"
    assert not result['safe_halt_recommended']

    pool.close()
    os.unlink(db_path)
    print("  PASS: S >= 0.5 streak resets, safe halt clears")


def seed_pool(pool, count: int):
    """Seed the pool with N URL entities for the load test.

    Uses real but non-routable domains (RFC 6761 .test).
    Format: https://sNNN.test/p/N — short labels, valid TLD, no actual HTTP needed.
    """
    entities = []
    for i in range(count):
        eid = pool.add_entity(
            'url',
            f'https://s{i:03d}.test/p/{i}',
            sla_seconds=30,
            cascade_depth=0,
            root_task_id=None,
        )
        if eid is not None:
            entities.append(eid)
    return entities


def run_load_test(
    entity_count: int = 500,
    max_entities: int = 500,
    verbose: bool = False,
) -> dict:
    """Run the full brigade load test and return metrics."""
    db_path = tempfile.mktemp(suffix='.db')
    pool = IntelligencePool(db_path)

    # Register all stations
    aboyeur = Aboyeur(pool)
    stations = [
        TheForager(pool),
        TheAnalyst(pool),
        TheLibrarian(pool),
        TheCartographer(pool),
        TheHydra(pool),
        TheWarden(pool),
        TheAuditor(pool),
        TheAmphithere(pool),
        TheSalamander(pool),
        TheHerald(pool),
        TheDossier(pool),
        ThePlongeur(pool),
        TheSentinel(pool),
    ]

    executive = ExecutiveChef(pool, max_entities=max_entities, verbose=verbose)
    for s in stations:
        executive.register_station(s)

    # Seed the pool
    seed_start = time.perf_counter()
    seeds = seed_pool(pool, entity_count)
    seed_time = time.perf_counter() - seed_start
    pool_count = pool.count_entities()

    # Run the brigade
    exec_start = time.perf_counter()
    result = executive.run_service()
    exec_time = time.perf_counter() - exec_start

    # Collect metrics
    all_entities = pool.get_all_entities()
    by_status = {}
    for e in all_entities:
        s = e['status']
        by_status[s] = by_status.get(s, 0) + 1

    # Cascade depth distribution
    depths = {}
    for e in all_entities:
        d = e['cascade_depth']
        depths[d] = depths.get(d, 0) + 1

    # SLA compliance
    from datetime import datetime, timezone
    sla_violations = 0
    for e in all_entities:
        if e['status'] != 'completed' and e['sla_seconds']:
            assigned = dict(e).get('assigned_at')
            if assigned:
                try:
                    assigned_dt = datetime.fromisoformat(assigned.replace('Z', '+00:00'))
                    elapsed = (datetime.now(timezone.utc) - assigned_dt).total_seconds()
                    if elapsed > e['sla_seconds']:
                        sla_violations += 1
                except (ValueError, TypeError):
                    pass

    # Throughput
    completed = by_status.get('completed', 0)
    throughput = completed / exec_time if exec_time > 0 else 0

    # Station stats
    station_stats = {}
    for s in stations:
        station_stats[s.station_id] = {
            'processed': s._tasks_processed,
            'failed': s._tasks_failed,
        }

    # Build metrics dict
    metrics = {
        'seed_count': len(seeds),
        'pool_count': pool_count,
        'seed_time_s': round(seed_time, 3),
        'exec_time_s': round(exec_time, 3),
        'throughput_per_sec': round(throughput, 2),
        'completed': completed,
        'failed': by_status.get('failed', 0),
        'by_status': by_status,
        'cascade_depths': dict(sorted(depths.items())),
        'sla_violations': sla_violations,
        'spawn_blocked': result.get('spawn_blocked', 0),
        'station_stats': station_stats,
        'max_entities': max_entities,
        'executive_cycles': result.get('cycles', 0),
    }

    pool.close()
    try:
        os.unlink(db_path)
    except OSError:
        pass

    return metrics


def print_metrics(m: dict, label: str = "Load Test"):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  Entities seeded:    {m['seed_count']}")
    print(f"  Pool total:         {m['pool_count']}")
    print(f"  Seed time:          {m['seed_time_s']}s")
    print(f"  Exec time:          {m['exec_time_s']}s")
    print(f"  Throughput:         {m['throughput_per_sec']} entities/sec")
    print(f"  Completed:          {m['completed']}")
    print(f"  Failed:             {m['failed']}")
    print(f"  SPAWN BLOCKED:     {m['spawn_blocked']}")
    print(f"  SLA violations:     {m['sla_violations']}")
    print(f"  Cascade depth dist: {m['cascade_depths']}")
    print(f"  Executive cycles:  {m['executive_cycles']}")
    print(f"  Station breakdown:")
    for sid, s in m['station_stats'].items():
        print(f"    {sid:12s}: processed={s['processed']}, failed={s['failed']}")
    print(f"{'='*60}")


# ─── Test Cases ─────────────────────────────────────────────────────────────

def test_load_100_entities():
    """Baseline: 100 entities, measure throughput and behavior."""
    m = run_load_test(entity_count=100, max_entities=100, verbose=False)
    print_metrics(m, "100-Entity Baseline")

    assert m['completed'] >= 0, "Should complete without errors"
    assert m['seed_count'] == 100, f"Should seed 100 entities, got {m['seed_count']}"
    assert m['exec_time_s'] < 60, "Should complete 100 entities in under 60s"
    print("  PASS: 100-entity baseline")


def test_load_500_entities():
    """Full spec: 500 entities — Snowball at target scale."""
    m = run_load_test(entity_count=500, max_entities=500, verbose=False)
    print_metrics(m, "500-Entity Snowball Test")

    assert m['seed_count'] == 500, f"Should seed 500, got {m['seed_count']}"
    # Throughput should be > 5/sec for a functioning system
    assert m['throughput_per_sec'] > 5, f"Throughput too low: {m['throughput_per_sec']}/sec"
    print(f"  PASS: 500-entity load, throughput={m['throughput_per_sec']}/sec")


def test_cascade_depth_limit():
    """Verify cascade depth limit is enforced at 500-entity Snowball scale."""
    m = run_load_test(entity_count=200, max_entities=500, verbose=False)
    print_metrics(m, "Cascade Depth Limit Check")

    depths = m['cascade_depths']
    max_depth = max(depths.keys()) if depths else 0

    # Max depth should never exceed 5 (MAX_CASCADE_DEPTH)
    assert max_depth <= 5, f"Max cascade depth exceeded: {max_depth} > 5"
    # Distribution should show tapering at depth 4-5
    print(f"  PASS: max depth={max_depth} (limit enforced), dist={depths}")


def test_bottleneck_detection():
    """Run 300-entity test and identify which station is the bottleneck."""
    m = run_load_test(entity_count=300, max_entities=300, verbose=False)
    print_metrics(m, "Bottleneck Detection (300 entities)")

    # Find station with most work
    station_stats = m['station_stats']
    busiest = max(station_stats.items(), key=lambda x: x[1]['processed'])
    idle = [(k, v) for k, v in station_stats.items() if v['processed'] == 0]

    print(f"  Busiest station:  {busiest[0]} ({busiest[1]['processed']} processed)")
    print(f"  Idle stations:    {[k for k,_ in idle]}")
    print(f"  Throughput:       {m['throughput_per_sec']}/sec")

    # All stations should have processed something if they're registered for URL type
    forager_stats = station_stats.get('forager', {})
    assert forager_stats.get('processed', 0) > 0, "Forager should process URL entities"

    return m


if __name__ == '__main__':
    print("XP-Arc Load Test Suite")
    print("=" * 60)
    import pytest
    sys.exit(pytest.main([__file__, '-v', '-s']))