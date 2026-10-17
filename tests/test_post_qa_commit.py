"""
Station side effects are committed only after QA — 2026-07-14 audit CRITICAL-5
and MEDIUM-4.

CRITICAL-5: stations used to write child entities and edges inside process(),
before the Aboyeur saw the output. A rejected task left its children and edges
in the graph. Stations now return them as spawn_targets/edges, and the
Executive commits them only after approval.

MEDIUM-4: the Forager only wrote a links_to edge when the child domain was new,
so a domain linked from a second page lost that provenance edge. Edges are now
declared independently of entity dedup, and the Pool skips exact duplicates.
"""

import os
import tempfile

import pytest

os.environ.setdefault('XP_ARC_DEV_MODE', '1')
os.environ.setdefault('XP_ARC_ABOYEUR_KEY', 'test-key')

from xp_arc.core.executive import ExecutiveChef  # noqa: E402
from xp_arc.core.pool import IntelligencePool  # noqa: E402
from xp_arc.core.station import StationChef  # noqa: E402


@pytest.fixture
def pool():
    with tempfile.TemporaryDirectory() as tmp:
        p = IntelligencePool(os.path.join(tmp, 'postqa.db'))
        yield p
        p.close()


class LinkingStation(StationChef):
    """Declares one child domain and one edge per URL; optionally always rejected."""

    station_id = 'linker'
    name = 'Linking Station'
    handles_types = ['url']
    sla_seconds = 60

    def __init__(self, pool, reject=False, target='shared.example'):
        super().__init__(pool)
        self.reject = reject
        self.target = target

    def process(self, entity_id, entity_type, entity_value):
        return {
            'entity_type': entity_type,
            'entity_value': entity_value,
            'relationships': [self.target],
            # Out-of-range confidence is a deterministic Aboyeur rejection.
            'confidence': 5.0 if self.reject else 0.9,
            'notes': 'linked',
            'spawn_targets': [{'ent_type': 'domain', 'value': self.target}],
            'edges': [{'source': entity_value, 'relationship': 'links_to',
                       'target': self.target}],
        }


def _run(pool, station, *urls):
    executive = ExecutiveChef(pool, verbose=False)
    executive.register_station(station)
    for url in urls:
        pool.add_entity('url', url)
    return executive.run_service()


def _edges(pool):
    return [(e['source'], e['relationship'], e['target']) for e in pool.get_all_edges()]


def test_rejected_output_leaves_no_children_or_edges(pool):
    _run(pool, LinkingStation(pool, reject=True), 'https://a.example')

    assert pool.get_entity(1)['status'] == 'failed'
    domains = [e for e in pool.get_all_entities() if e['type'] == 'domain']
    assert domains == [], "a rejected task must not leave child entities behind"
    assert _edges(pool) == [], "a rejected task must not leave edges behind"


def test_approved_output_commits_children_and_edges(pool):
    _run(pool, LinkingStation(pool), 'https://a.example')

    assert pool.get_entity(1)['status'] == 'completed'
    child = next(e for e in pool.get_all_entities() if e['type'] == 'domain')
    assert child['value'] == 'shared.example'
    assert child['parent_task_id'] == 1
    assert child['cascade_depth'] == 1
    assert _edges(pool) == [('https://a.example', 'links_to', 'shared.example')]


def test_second_parent_keeps_its_provenance_edge(pool):
    _run(pool, LinkingStation(pool), 'https://a.example', 'https://b.example')

    domains = [e for e in pool.get_all_entities() if e['type'] == 'domain']
    assert len(domains) == 1, "the shared domain is still one entity"
    assert sorted(_edges(pool)) == [
        ('https://a.example', 'links_to', 'shared.example'),
        ('https://b.example', 'links_to', 'shared.example'),
    ]


def test_identical_edge_is_not_duplicated(pool):
    writer = pool.station_writer('executive')
    assert writer.add_edge('x.example', 'links_to', 'y.example') is True
    assert writer.add_edge('x.example', 'links_to', 'y.example') is False
    assert len(_edges(pool)) == 1


def test_edge_flood_is_capped(pool):
    class Flooder(LinkingStation):
        def process(self, entity_id, entity_type, entity_value):
            out = super().process(entity_id, entity_type, entity_value)
            out['spawn_targets'] = []
            out['edges'] = [{'source': entity_value, 'relationship': 'links_to',
                             'target': f'd{i}.example'}
                            for i in range(ExecutiveChef.MAX_EDGES_PER_ENTITY + 25)]
            return out

    summary = _run(pool, Flooder(pool), 'https://a.example')
    assert summary['edges_created'] == ExecutiveChef.MAX_EDGES_PER_ENTITY
    assert len(_edges(pool)) == ExecutiveChef.MAX_EDGES_PER_ENTITY


def test_malformed_edges_are_skipped(pool):
    class Sloppy(LinkingStation):
        def process(self, entity_id, entity_type, entity_value):
            out = super().process(entity_id, entity_type, entity_value)
            out['spawn_targets'] = []
            out['edges'] = [{'source': entity_value},
                            {'source': '', 'relationship': 'r', 'target': 't'},
                            'not-a-dict']
            return out

    _run(pool, Sloppy(pool), 'https://a.example')
    assert pool.get_entity(1)['status'] == 'completed'
    assert _edges(pool) == []


# ─── The stations themselves no longer write inside process() ───────────────

def _graph_size(pool):
    return len(pool.get_all_entities()), len(pool.get_all_edges())


def test_analyst_process_writes_nothing(pool, monkeypatch):
    from xp_arc.stations.analyst import TheAnalyst
    analyst = TheAnalyst(pool)
    monkeypatch.setattr(analyst, '_probe_domain', lambda d: {'reachable': False})
    eid = pool.add_entity('domain', 'docs.example.com')
    before = _graph_size(pool)

    out = analyst.process(eid, 'domain', 'docs.example.com')

    assert _graph_size(pool) == before
    assert out['spawn_targets'] == [{'ent_type': 'domain', 'value': 'example.com'}]
    assert out['edges'] == [{'source': 'docs.example.com', 'relationship': 'subdomain_of',
                             'target': 'example.com'}]


def test_meta_stations_defer_edges_under_the_executive(pool):
    from xp_arc.stations.cartographer import TheCartographer
    from xp_arc.stations.salamander import TheSalamander
    writer = pool.station_writer('executive')
    for value in ('WWW.Example.com', 'example.com', 'a.example', 'b.example'):
        pool.add_entity('domain', value)
    writer.add_edge('a.example', 'links_to', 'b.example')
    writer.add_edge('b.example', 'links_to', 'example.com')
    before = _graph_size(pool)

    declared = {}
    for station in (TheSalamander(pool), TheCartographer(pool)):
        out = station.process(0, station.handles_types[0], 'sweep')
        declared[station.station_id] = out['edges']

    assert _graph_size(pool) == before
    assert {'source': 'WWW.Example.com', 'relationship': 'normalizes_to',
            'target': 'example.com'} in declared['salamander']
