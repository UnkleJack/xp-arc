"""RT-11 regression tests: station HMAC keys must never leave the Pool.

The HMAC key is the write-auth secret for a station. Anyone holding it can
forge authenticated writes into the Intelligence Pool, defeating Article III's
Glass Wall (bounded mutability) entirely.

Before this fix, `get_active_stations()` was `SELECT *` on station_registry,
which includes the `hmac_key` column. Two live exfiltration paths resulted:

  1. `export_state()` -> served verbatim by the DRAGON HTTP API
     (`/api/dragon`, `/api/pool`, `/pool_state.json`) to any client.
  2. SpaZzMatiC's Gemini review path -> the station rows are interpolated into
     the prompt sent to an external LLM API.

These tests pin both the source query and the export boundary.
"""

import pytest

from xp_arc.core.pool import IntelligencePool


@pytest.fixture()
def pool(tmp_path):
    p = IntelligencePool(str(tmp_path / "rt11.db"))
    p.register_station("forager", "The Forager", ["url"], is_primary=True)
    p.register_station("analyst", "The Analyst", ["domain"], is_primary=True)
    yield p
    p.close()


def test_registered_stations_actually_have_keys(pool):
    """Guard the guard: if keys stopped existing, the leak tests would pass
    vacuously and prove nothing."""
    assert pool.get_station_key("forager"), "expected a real HMAC key to exist"
    assert pool.get_station_key("analyst")


def test_get_active_stations_excludes_hmac_key(pool):
    rows = pool.get_active_stations()
    assert rows, "expected active stations"
    for row in rows:
        assert "hmac_key" not in row.keys(), (
            "get_active_stations() must not return the hmac_key column"
        )


def test_export_state_contains_no_hmac_key_field(pool):
    export = pool.export_state()
    assert export["stations"], "expected stations in export"
    for station in export["stations"]:
        assert "hmac_key" not in station, (
            "export_state() leaked the hmac_key field to the DRAGON surface"
        )


def test_export_state_does_not_contain_key_material_anywhere(pool):
    """Serialize the whole export and assert no real key value appears in it,
    regardless of which field it might hide in."""
    import json

    keys = [pool.get_station_key("forager"), pool.get_station_key("analyst")]
    blob = json.dumps(pool.export_state(), default=str)
    for key in keys:
        assert key and key not in blob, (
            "a station HMAC key appeared in the serialized DRAGON export"
        )


def test_station_registry_still_stores_the_key(pool):
    """The key must remain retrievable internally — this fix hides it from
    external surfaces, it does not disable HMAC auth."""
    key = pool.get_station_key("forager")
    assert key
    # And it must still verify a correctly-signed write.
    import hashlib
    import hmac as hmac_mod

    payload = "add_entity:url:https://example.com:60"
    mac = hmac_mod.new(key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    assert pool._verify_write("forager", payload, mac) is True
    assert pool._verify_write("forager", payload, "deadbeef") is False
