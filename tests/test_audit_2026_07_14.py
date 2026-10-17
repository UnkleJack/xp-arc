"""
Regression tests for the remaining 2026-07-14 audit findings.

MEDIUM-5: the Constitution (Article X 10.4) requires every output to record the
prompt_version used; the schema had no such column.

HIGH-3: safe halt stopped the processing loop, but POST /api/seed kept
accepting work during the halt and its veto window.

CRITICAL-5 and MEDIUM-4 are covered in test_post_qa_commit.py.
"""

import os
import sqlite3
import tempfile

import pytest

os.environ.setdefault('XP_ARC_DEV_MODE', '1')
os.environ.setdefault('XP_ARC_ABOYEUR_KEY', 'test-key')

from xp_arc.core.executive import ExecutiveChef  # noqa: E402
from xp_arc.core.pool import IntelligencePool  # noqa: E402
from xp_arc.core.station import StationChef  # noqa: E402


@pytest.fixture
def tmpdir_path():
    with tempfile.TemporaryDirectory() as tmp:
        yield tmp


class EchoStation(StationChef):
    station_id = 'echo'
    name = 'Echo Station'
    handles_types = ['url']

    def __init__(self, pool, version_override=None):
        super().__init__(pool)
        self.version_override = version_override

    def process(self, entity_id, entity_type, entity_value):
        out = {'entity_type': entity_type, 'entity_value': entity_value,
               'relationships': [], 'confidence': 0.9, 'notes': 'ok'}
        if self.version_override:
            out['prompt_version'] = self.version_override
        return out


def _complete_one(pool, station):
    executive = ExecutiveChef(pool, verbose=False)
    executive.register_station(station)
    eid = pool.add_entity('url', 'https://a.example')
    executive.run_service()
    return pool.get_entity(eid)


# ─── MEDIUM-5: prompt_version ────────────────────────────────────────────────

def test_completed_output_records_station_prompt_version(tmpdir_path):
    pool = IntelligencePool(os.path.join(tmpdir_path, 'pv.db'))
    entity = _complete_one(pool, EchoStation(pool))
    assert entity['status'] == 'completed'
    assert entity['prompt_version'] == 'rules-v1'
    pool.close()


def test_output_can_override_prompt_version(tmpdir_path):
    pool = IntelligencePool(os.path.join(tmpdir_path, 'pv.db'))
    entity = _complete_one(pool, EchoStation(pool, version_override='pack-2026.10'))
    assert entity['prompt_version'] == 'pack-2026.10'
    pool.close()


def test_existing_pool_gains_prompt_version_column(tmpdir_path):
    """A database created before the column existed is migrated on open."""
    path = os.path.join(tmpdir_path, 'old.db')
    pool = IntelligencePool(path)
    pool.close()
    conn = sqlite3.connect(path)
    conn.execute("ALTER TABLE entities DROP COLUMN prompt_version")
    conn.commit()
    conn.close()

    pool = IntelligencePool(path)
    cols = {r['name'] for r in pool.conn.execute("PRAGMA table_info(entities)")}
    assert 'prompt_version' in cols
    pool.close()


# ─── HIGH-3: safe halt refuses ingestion ─────────────────────────────────────

@pytest.fixture
def kitchen(tmpdir_path):
    import run_persistent
    k = run_persistent.PersistentKitchen(os.path.join(tmpdir_path, 'halt.db'))
    yield k
    k.pool.close()


def test_seed_refused_after_safe_halt(kitchen):
    kitchen._enter_safe_halt()
    result = kitchen.seed('https://example.com')
    assert result['status'] == 'halted'
    assert kitchen.pool.get_all_entities() == []


def test_seed_refused_during_veto_window(kitchen):
    kitchen._halt_countdown = 30
    result = kitchen.seed('https://example.com')
    assert result['status'] == 'halted'
    assert 'veto window' in result['reason']


def test_safe_halt_is_logged_once(kitchen):
    kitchen._enter_safe_halt()
    kitchen._enter_safe_halt()
    halts = [e for e in kitchen.pool.get_events(200) if e['event_type'] == 'safe_halt']
    assert len(halts) == 1


# ─── HIGH-5: descendants walk the whole subtree, by integer ID ──────────────

def test_descendants_include_grandchildren_and_not_lookalike_ids(tmpdir_path):
    pool = IntelligencePool(os.path.join(tmpdir_path, 'tree.db'))
    root = pool.add_entity('url', 'https://root.example')
    child = pool.add_entity('domain', 'child.example', parent_task_id=root)
    grandchild = pool.add_entity('domain', 'grand.example', parent_task_id=child)
    # Pad IDs so that an unrelated entity gets an ID containing root's digit.
    for i in range(12):
        pool.add_entity('url', f'https://pad{i}.example')
    unrelated = pool.add_entity('domain', 'other.example')

    ids = {row['id'] for row in pool.get_descendants(root)}
    assert ids == {child, grandchild}
    assert unrelated not in ids
    pool.close()


# ─── MEDIUM-2: dossiers cite only completed, signed entities ────────────────

def test_dossier_ignores_unapproved_entities(tmpdir_path):
    from xp_arc.stations.dossier import TheDossier
    pool = IntelligencePool(os.path.join(tmpdir_path, 'dossier.db'))
    pool.add_entity('domain', 'raw-neighbor.example')
    pool.station_writer('executive').add_edge(
        'target.example', 'links_to', 'raw-neighbor.example')

    intel = TheDossier(pool)._gather_intelligence('target.example')
    cited = [p['value'] for bucket in ('infrastructure', 'presence', 'identities',
                                       'risk_factors') for p in intel[bucket]]
    assert 'raw-neighbor.example' not in cited
    pool.close()
