"""
Competitive-intel bridge and analyst — pool integration.

CompetitiveIntelStation is standalone by ruling: its own async pipeline, its own
private SQLite database, its own CLI, none of it touching the pool. That path is
preserved byte-for-byte. The bridge is the second path — it reads that database
and republishes gaps into the Intelligence Pool, where they become ordinary
entities subject to HMAC write auth, the Aboyeur gate, lineage and Zoran.

These tests exercise the bridge and the analyst WITHOUT network access, so CI
covers the integration deterministically. The live end-to-end gate against real
external sources is scripts/competitive_acceptance_run.py.
"""

import json
import os
import tempfile

import pytest

os.environ.setdefault('XP_ARC_DEV_MODE', '1')
os.environ.setdefault('XP_ARC_ABOYEUR_KEY', 'test-key')

from xp_arc.competitive_intel.analyst import CompetitiveGapAnalyst  # noqa: E402
from xp_arc.competitive_intel.bridge import (  # noqa: E402
    MAX_GAPS_PER_SCAN, SEVERITY_SLA, CompetitiveIntelBridge,
)
from xp_arc.core.executive import ExecutiveChef  # noqa: E402
from xp_arc.core.pool import IntelligencePool  # noqa: E402


@pytest.fixture
def pool():
    with tempfile.TemporaryDirectory() as tmp:
        p = IntelligencePool(os.path.join(tmp, 'bridge.db'))
        yield p
        p.close()


class FakeIntelStation:
    """Stands in for CompetitiveIntelStation's read surface."""

    def __init__(self, gaps):
        self._gaps = gaps

    async def query_gaps(self, competitor=None, status=None, severity=None,
                         since=None):
        return list(self._gaps)


def _gap(i, severity='high', competitor='langgraph', gap_type='dx'):
    return {
        'id': i,
        'competitor': competitor,
        'gap_type': gap_type,
        'description': f'Gap number {i}',
        'severity': severity,
        'evidence_urls': json.dumps([f'https://example.com/evidence/{i}']),
        'first_seen': '2026-08-01T00:00:00Z',
        'frequency': 1,
    }


# ─── Publication ─────────────────────────────────────────────────────────────

def test_gaps_become_pool_entities(pool):
    bridge = CompetitiveIntelBridge(pool, FakeIntelStation([_gap(1), _gap(2)]))

    created = bridge.publish_gap_records([_gap(1), _gap(2)])

    assert len(created) == 2
    entities = [e for e in pool.get_all_entities() if e['type'] == 'competitive_gap']
    assert len(entities) == 2
    assert all(e['status'] == 'raw' for e in entities)


def test_republishing_the_same_gap_is_idempotent(pool):
    """A gap that persists across scans must not multiply in the pool."""
    bridge = CompetitiveIntelBridge(pool, FakeIntelStation([]))

    first = bridge.publish_gap_records([_gap(1)])
    second = bridge.publish_gap_records([_gap(1)])

    assert len(first) == 1
    assert second == []
    assert bridge.stats['skipped_duplicate'] == 1


def test_severity_maps_to_sla_weight(pool):
    """Zoran weights by SLA, so a critical gap must outweigh a cosmetic one."""
    bridge = CompetitiveIntelBridge(pool, FakeIntelStation([]))

    bridge.publish_gap_records([
        _gap(1, severity='critical'), _gap(2, severity='low'),
    ])

    by_sla = {e['sla_seconds'] for e in pool.get_all_entities()}
    assert SEVERITY_SLA['critical'] in by_sla
    assert SEVERITY_SLA['low'] in by_sla


def test_scan_is_capped_and_drops_least_severe_first(pool):
    """MAX_GAPS_PER_SCAN must not throw away critical findings."""
    bridge = CompetitiveIntelBridge(pool, FakeIntelStation([]))
    gaps = [_gap(i, severity='low') for i in range(MAX_GAPS_PER_SCAN + 10)]
    gaps.append(_gap(9999, severity='critical'))

    created = bridge.publish_gap_records(gaps)

    assert len(created) == MAX_GAPS_PER_SCAN
    assert bridge.stats['truncated'] == 11
    published = [json.loads(e['value']) for e in pool.get_all_entities()]
    assert any(g['severity'] == 'critical' for g in published), \
        "the critical gap was dropped by the cap"
    assert any(e['event_type'] == 'competitive_gaps_truncated'
               for e in pool.get_events(200))


def test_bridge_is_not_marked_concurrent_safe(pool):
    """It reads a database another process writes on its own schedule."""
    bridge = CompetitiveIntelBridge(pool, FakeIntelStation([]))
    assert bridge.concurrent_safe is False


def test_bridge_writes_are_hmac_signed(pool):
    """The bridge holds a station key like any other pool writer."""
    bridge = CompetitiveIntelBridge(pool, FakeIntelStation([]))
    assert pool.get_station_key(bridge.station_id)


# ─── Analyst ─────────────────────────────────────────────────────────────────

def test_analyst_completes_a_bridged_gap_with_a_signature(pool):
    """The whole in-process path: bridge -> Executive -> analyst -> Aboyeur."""
    bridge = CompetitiveIntelBridge(pool, FakeIntelStation([]))
    bridge.publish_gap_records([_gap(1, severity='critical')])
    ex = ExecutiveChef(pool, verbose=False)
    ex.register_station(CompetitiveGapAnalyst(pool))

    ex.run_service()

    entity = [e for e in pool.get_all_entities()
              if e['type'] == 'competitive_gap'][0]
    assert entity['status'] == 'completed'
    assert entity['aboyeur_signature'].startswith('ABOY-')
    assert ex.summary()['unhandled'] == 0


def test_severe_gaps_raise_findings(pool):
    bridge = CompetitiveIntelBridge(pool, FakeIntelStation([]))
    bridge.publish_gap_records([_gap(1, severity='critical'),
                                _gap(2, severity='low')])
    ex = ExecutiveChef(pool, verbose=False)
    ex.register_station(CompetitiveGapAnalyst(pool))

    ex.run_service()

    findings = [f for f in pool.get_findings()
                if f['source'] == 'competitive_gap_analyst']
    assert len(findings) == 1
    assert findings[0]['severity'] == 'critical'


def test_analyst_reports_malformed_payloads_honestly(pool):
    """Unparseable input gets low confidence, not an invented analysis."""
    analyst = CompetitiveGapAnalyst(pool)

    out = analyst.process(1, 'competitive_gap', 'not json at all')

    assert out['confidence'] == 0.1
    assert 'not valid JSON' in out['notes']
    assert out['entity_value'] == 'not json at all'


def test_analyst_relationships_are_strings(pool):
    """The Aboyeur rejects any relationship element that is not a str."""
    analyst = CompetitiveGapAnalyst(pool)

    out = analyst.process(1, 'competitive_gap', json.dumps({
        'competitor': 'crewai', 'gap_type': 'lockin', 'severity': 'high',
        'description': 'x', 'evidence_urls': ['https://example.com/a'],
    }))

    assert all(isinstance(r, str) for r in out['relationships'])
    assert 'competitor:crewai' in out['relationships']
