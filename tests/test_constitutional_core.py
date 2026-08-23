"""Regression tests for the canonical XP-Arc core and DRAGON export contract."""

import os

os.environ.setdefault("XP_ARC_ABOYEUR_KEY", "test-signing-key-for-unit-tests-only")
os.environ.setdefault("XP_ARC_DEV_MODE", "1")

from xp_arc.core.aboyeur import Aboyeur
from xp_arc.core.executive import ExecutiveChef
from xp_arc.core.pool import IntelligencePool
from xp_arc.core.station import StationChef
from xp_arc.stations.forager import TheForager


class SpawnStation(StationChef):
    station_id = "spawn_station"
    name = "Spawn Station"
    handles_types = ["seed"]

    def process(self, entity_id, entity_type, entity_value):
        return {
            "entity_type": entity_type,
            "entity_value": entity_value,
            "confidence": 0.95,
            "relationships": [],
            "notes": "Verified seed that requests one child.",
            "spawn_targets": [{"ent_type": "child", "value": "child-1"}],
        }


class ChildStation(StationChef):
    station_id = "child_station"
    name = "Child Station"
    handles_types = ["child"]

    def process(self, entity_id, entity_type, entity_value):
        return {
            "entity_type": entity_type,
            "entity_value": entity_value,
            "confidence": 0.9,
            "relationships": [],
            "notes": "Verified spawned child.",
        }


def _pool():
    return IntelligencePool(":memory:")


def test_pool_blocks_unsigned_completion_and_uses_sqlite_timestamps():
    pool = _pool()
    pool.register_station("test_station", "Test Station", ["url"])
    writer = pool.station_writer("test_station")
    entity_id = writer.add_entity("url", "https://example.com")

    assert writer.transition_status(entity_id, "processing", station="test_station")
    assert writer.transition_status(entity_id, "pending_qa")
    assert not writer.transition_status(entity_id, "completed")

    blocked = pool.get_entity(entity_id)
    assert blocked["status"] == "pending_qa"
    assert blocked["assigned_at"] is not None
    assert "T" not in blocked["assigned_at"]

    aboyeur = Aboyeur(pool)
    result = aboyeur.validate_and_sign(
        entity_id,
        "test_station",
        {
            "entity_type": "url",
            "entity_value": "https://example.com",
            "confidence": 0.9,
            "relationships": [],
            "notes": "Valid completion.",
        },
    )
    assert result["approved"]
    assert writer.transition_status(entity_id, "completed", station="test_station")

    completed = pool.get_entity(entity_id)
    assert completed["aboyeur_signature"].startswith("ABOY-")
    assert completed["completed_at"] is not None
    assert "T" not in completed["completed_at"]


def test_seed_lineage_is_initialized_inside_the_pool_transaction():
    pool = _pool()
    entity_id = pool.add_entity("url", "https://example.com")
    entity = pool.get_entity(entity_id)

    assert entity["root_task_id"] == entity_id
    assert entity["parent_task_id"] is None
    assert entity["cascade_depth"] == 0


def test_snowball_spawn_uses_verified_parent_lineage():
    pool = _pool()
    executive = ExecutiveChef(pool, max_entities=5, verbose=False)
    executive.register_station(SpawnStation(pool))
    executive.register_station(ChildStation(pool))

    root_id = pool.add_entity("seed", "root-1")
    executive.run_service()

    root = pool.get_entity(root_id)
    child_rows = [row for row in pool.get_all_entities() if row["type"] == "child"]
    assert root["status"] == "completed"
    assert root["aboyeur_signature"].startswith("ABOY-")
    assert len(child_rows) == 1

    child = child_rows[0]
    assert child["status"] == "completed"
    assert child["aboyeur_signature"].startswith("ABOY-")
    assert child["parent_task_id"] == root_id
    assert child["root_task_id"] == root_id
    assert child["cascade_depth"] == 1
    assert child["spawn_chain"] == f"[{root_id}]"


def test_malformed_url_is_a_contained_station_refusal():
    pool = _pool()
    executive = ExecutiveChef(pool, max_entities=1, verbose=False)
    executive.register_station(TheForager(pool, timeout=1))

    entity_id = pool.add_entity("url", "ftp://not-allowed.example")
    executive.run_service()

    entity = pool.get_entity(entity_id)
    assert entity["status"] == "failed"
    assert entity["refusal_reason"] == "malformed_url: input did not pass URL validation"
    assert entity["aboyeur_signature"] is None


def test_dragon_export_has_a_total_read_only_contract():
    pool = _pool()
    entity_id = pool.add_entity("url", "https://example.com")
    state = pool.export_state()

    assert state["entities"][0]["id"] == entity_id
    assert state["dossiers"] == []
    assert state["topology"]["clusters"]["count"] == 0
    assert state["audit"]["overall"]["all_checks_passed"] is True
    assert state["audit"]["zero_drop"]["zero_drop_verified"] is True


class FracturingStation(StationChef):
    station_id = "fracturing_station"
    name = "Fracturing Station"
    handles_types = ["complex_task"]

    def process(self, entity_id, entity_type, entity_value):
        from xp_arc.core.fracture import FractureRequest

        raise FractureRequest("bounded constitutional test fracture", shard_count=2, shard_type="shard")


class ShardStation(StationChef):
    station_id = "shard_station"
    name = "Shard Station"
    handles_types = ["shard"]

    def process(self, entity_id, entity_type, entity_value):
        return {
            "entity_type": entity_type,
            "entity_value": entity_value,
            "confidence": 1.0,
            "relationships": [],
            "notes": "Verified shard output.",
        }


def test_fracture_stitches_only_after_signed_shards():
    pool = _pool()
    executive = ExecutiveChef(pool, max_entities=10, verbose=False)
    executive.register_station(FracturingStation(pool))
    executive.register_station(ShardStation(pool))

    parent_id = pool.add_entity("complex_task", "oversized-work-item")
    executive.run_service()

    entities = [dict(row) for row in pool.get_all_entities()]
    parent = next(entity for entity in entities if entity["id"] == parent_id)
    shards = [entity for entity in entities if entity["type"] == "shard"]
    stitched = [
        entity
        for entity in entities
        if entity["type"] == "complex_task" and entity["id"] != parent_id
    ]

    assert parent["status"] == "completed"
    assert parent["aboyeur_signature"].startswith("ABOY-")
    assert len(shards) == 2
    assert all(shard["status"] == "completed" for shard in shards)
    assert all(shard["aboyeur_signature"].startswith("ABOY-") for shard in shards)
    assert len(stitched) == 1
    assert stitched[0]["status"] == "completed"
    assert stitched[0]["aboyeur_signature"].startswith("ABOY-")


def test_real_minimum_viable_brigade_survives_compression():
    from xp_arc.stations.analyst import TheAnalyst
    from xp_arc.stations.librarian import TheLibrarian
    from xp_arc.stations.plongeur import ThePlongeur
    from xp_arc.stations.sentinel import TheSentinel

    pool = _pool()
    executive = ExecutiveChef(pool, max_entities=1, verbose=False)
    critical_stations = [TheForager(pool), TheAnalyst(pool), TheSentinel(pool), ThePlongeur(pool)]
    noncritical_station = TheLibrarian(pool)
    for station in [*critical_stations, noncritical_station]:
        executive.register_station(station)

    executive.compress_brigade()

    active_ids = {station.station_id for station in executive.stations}
    assert {station.station_id for station in critical_stations}.issubset(active_ids)
    assert noncritical_station.station_id not in active_ids
    assert any(station.can_handle("url") for station in executive.stations)
    assert executive.aboyeur is not None
