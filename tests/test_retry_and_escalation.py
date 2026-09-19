"""
Aboyeur retry budget and Chef de Cuisine escalation — Articles I 1.2 and V 5.5.

TWO DEFECTS PINNED HERE:

1. THE RETRY BUDGET NEVER RAN, FOR ANY ENTITY.
   Every entity carries rejection_count/max_rejections and Article I 1.2
   specifies a three-strike budget. But the Aboyeur's circuit breaker only
   transitions an entity to 'failed' once rejection_count REACHES
   max_rejections, and nothing anywhere re-processed a rejected entity. The
   Executive's "if not already failed, fail it" branch was therefore taken on
   strike one, every time. The budget was dead code.

   This was tracked for a long time as a shard-specific gap ("Article V 5.5
   shard retry driver missing"). It was never shard-specific — a shard is an
   ordinary entity, and every entity in the pool failed on its first rejection.

2. A DEAD SHARD STRANDED ITS PARENT FOREVER.
   create_shards() moves the parent to 'fractured' BEFORE creating shards, and
   'fractured' could only advance to 'stitchable', which requires every shard
   completed. One permanently-failed shard therefore bricked its parent with no
   exit and no escalation. Nothing called check_failed_shards() — the function
   did not exist on main.
"""

import json
import os
import tempfile

import pytest

os.environ.setdefault('XP_ARC_DEV_MODE', '1')
os.environ.setdefault('XP_ARC_ABOYEUR_KEY', 'test-key')

from xp_arc.core.executive import ExecutiveChef  # noqa: E402
from xp_arc.core.fracture import FractureProtocol  # noqa: E402
from xp_arc.core.pool import IntelligencePool  # noqa: E402
from xp_arc.core.station import StationChef  # noqa: E402
from xp_arc.stations.chef_de_cuisine import ChefDeCuisine  # noqa: E402


@pytest.fixture
def pool():
    with tempfile.TemporaryDirectory() as tmp:
        p = IntelligencePool(os.path.join(tmp, 'retry.db'))
        yield p
        p.close()


class FlakyStation(StationChef):
    """Emits output the Aboyeur rejects for the first `fail_times` attempts."""

    station_id = 'flaky'
    name = 'Flaky Station'
    handles_types = ['url']
    sla_seconds = 60

    def __init__(self, pool, fail_times=2):
        super().__init__(pool)
        self.fail_times = fail_times
        self.attempts = 0

    def process(self, entity_id, entity_type, entity_value):
        self.attempts += 1
        # Out-of-range confidence is a deterministic Aboyeur rejection that does
        # not depend on relationship semantics.
        confidence = 5.0 if self.attempts <= self.fail_times else 0.9
        return {
            'entity_type': entity_type,
            'entity_value': entity_value,
            'relationships': [],
            'confidence': confidence,
            'notes': f'attempt {self.attempts}',
        }


# ─── Retry budget ────────────────────────────────────────────────────────────

def test_entity_recovers_within_its_rejection_budget(pool):
    """Two rejections then success: the entity completes instead of failing."""
    ex = ExecutiveChef(pool, verbose=False)
    station = FlakyStation(pool, fail_times=2)
    ex.register_station(station)
    eid = pool.add_entity('url', 'https://example.com/retry')

    ex.run_service()

    entity = pool.get_entity(eid)
    assert station.attempts == 3, "handler was not re-invoked after rejection"
    assert entity['status'] == 'completed'
    assert entity['rejection_count'] == 2
    assert entity['aboyeur_signature'] is not None
    assert ex.summary()['retries'] == 2


def test_budget_exhaustion_still_fails_the_entity(pool):
    """The retry driver must not make failure unreachable."""
    ex = ExecutiveChef(pool, verbose=False)
    station = FlakyStation(pool, fail_times=99)
    ex.register_station(station)
    eid = pool.add_entity('url', 'https://example.com/doomed')

    ex.run_service()

    entity = pool.get_entity(eid)
    assert entity['status'] == 'failed'
    assert entity['rejection_count'] == entity['max_rejections'] == 3
    assert station.attempts == 3


def test_retry_is_bounded_by_hard_cap(pool):
    """An entity with an inflated budget still cannot spin forever."""
    ex = ExecutiveChef(pool, verbose=False)
    station = FlakyStation(pool, fail_times=9999)
    ex.register_station(station)
    eid = pool.add_entity('url', 'https://example.com/runaway')
    with pool.conn:
        pool.conn.execute(
            "UPDATE entities SET max_rejections = 100000 WHERE id = ?", (eid,)
        )

    ex.run_service()

    assert station.attempts <= ExecutiveChef.RETRY_HARD_CAP
    events = [e['event_type'] for e in pool.get_events(200)]
    assert 'retry_hard_cap' in events


def test_retries_are_logged(pool):
    ex = ExecutiveChef(pool, verbose=False)
    ex.register_station(FlakyStation(pool, fail_times=1))
    pool.add_entity('url', 'https://example.com/logged')

    ex.run_service()

    assert any(e['event_type'] == 'qa_retry' for e in pool.get_events(200))


# ─── Fracture escalation ─────────────────────────────────────────────────────

def _strand_a_fracture(pool):
    """Build a fracture whose shards are all permanently dead."""
    parent_id = pool.add_entity('url', 'https://example.com/complex')
    writer = pool.station_writer('executive')
    writer.transition_status(parent_id, 'processing', station='executive')

    fracture = FractureProtocol(pool)
    shard_ids = fracture.create_shards(parent_id, 'url',
                                       'https://example.com/complex', 3)
    assert shard_ids, "fracture produced no shards"

    for sid in shard_ids:
        with pool.conn:
            pool.conn.execute(
                """UPDATE entities
                   SET status = 'failed', rejection_count = max_rejections
                   WHERE id = ?""",
                (sid,),
            )
    return parent_id, shard_ids


def test_stranded_fracture_is_detected(pool):
    parent_id, shard_ids = _strand_a_fracture(pool)
    entity = pool.get_entity(shard_ids[0])

    report = FractureProtocol(pool).check_failed_shards(entity['fracture_id'])

    assert report['stranded'] is True
    assert report['parent_id'] == parent_id
    assert sorted(report['failed_shards']) == sorted(shard_ids)


def test_shard_with_budget_remaining_is_not_stranded(pool):
    """A failed shard that can still retry is live work, not a dead end."""
    parent_id = pool.add_entity('url', 'https://example.com/pending')
    writer = pool.station_writer('executive')
    writer.transition_status(parent_id, 'processing', station='executive')
    fracture = FractureProtocol(pool)
    shard_ids = fracture.create_shards(parent_id, 'url',
                                       'https://example.com/pending', 2)
    with pool.conn:
        pool.conn.execute(
            "UPDATE entities SET status='failed', rejection_count=1 WHERE id = ?",
            (shard_ids[0],),
        )
    entity = pool.get_entity(shard_ids[0])

    report = fracture.check_failed_shards(entity['fracture_id'])

    assert report['stranded'] is False
    assert shard_ids[0] in report['pending_shards']


def test_stranded_parent_is_released_and_escalated(pool):
    """The parent leaves 'fractured' and an escalation entity is published."""
    ex = ExecutiveChef(pool, verbose=False)
    parent_id, shard_ids = _strand_a_fracture(pool)
    assert pool.get_entity(parent_id)['status'] == 'fractured'

    escalated = ex._check_stranded_fracture(shard_ids[0])

    assert escalated is True
    assert pool.get_entity(parent_id)['status'] == 'failed'
    escalations = [e for e in pool.get_all_entities() if e['type'] == 'escalation']
    assert len(escalations) == 1
    payload = json.loads(escalations[0]['value'])
    assert payload['kind'] == 'stranded_fracture'
    assert payload['parent_entity_id'] == parent_id


def test_chef_de_cuisine_rules_on_the_escalation(pool):
    """End to end: stranded fracture -> escalation entity -> Chef ruling."""
    ex = ExecutiveChef(pool, verbose=False)
    chef = ChefDeCuisine(pool)
    ex.register_station(chef)
    _, shard_ids = _strand_a_fracture(pool)
    ex._check_stranded_fracture(shard_ids[0])

    ex.run_service()

    rulings = [e for e in pool.get_all_entities() if e['type'] == 'escalation']
    assert rulings and rulings[0]['status'] == 'completed'
    assert rulings[0]['aboyeur_signature'] is not None
    findings = [f for f in pool.get_findings() if f['source'] == 'chef_de_cuisine']
    assert findings, "Chef de Cuisine recorded no finding"


def test_chef_de_cuisine_survives_brigade_compression(pool):
    """Escalation authority must not be compressed away in degraded mode."""
    ex = ExecutiveChef(pool, verbose=False)
    ex.register_station(FlakyStation(pool, fail_times=0))
    ex.register_station(ChefDeCuisine(pool))

    ex.compress_brigade()

    assert ex.is_compressed()
    assert any(isinstance(s, ChefDeCuisine) for s in ex.stations)


def test_chef_records_unknown_escalation_kinds(pool):
    """An unrecognized escalation is surfaced, never silently dropped."""
    chef = ChefDeCuisine(pool)

    out = chef.process(1, 'escalation', json.dumps({'kind': 'something_new'}))

    assert out['confidence'] == 0.5
    assert any(f['severity'] == 'high' for f in pool.get_findings())
