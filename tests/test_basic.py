"""
Basic unit tests for xp_arc core modules.
"""
import sys
import os

# Ensure the project root is on the import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from xp_arc.core.pool import IntelligencePool


def _fresh_pool():
    """Return a new in-memory pool (no shared state between tests)."""
    return IntelligencePool()  # defaults to :memory:


def test_intelligence_pool_add_and_get_raw():
    """An entity added as 'raw' should be returned by get_next_raw."""
    pool = _fresh_pool()
    pool.add_entity('url', 'https://example.com')
    row = pool.get_next_raw()
    assert row is not None, "No raw entity returned"
    assert row['type'] == 'url'
    assert row['value'] == 'https://example.com'
    assert row['status'] == 'raw'


def test_intelligence_pool_mark_completed():
    """Marking an entity completed should remove it from the raw queue."""
    pool = _fresh_pool()
    pool.add_entity('domain', 'example.com')
    row = pool.get_next_raw()
    assert row is not None
    entity_id = row['id']
    pool.mark_status(entity_id, 'completed')
    assert pool.get_next_raw() is None, "Entity should no longer be raw after completion"


def test_intelligence_pool_add_edge():
    """add_edge should not raise for valid inputs."""
    pool = _fresh_pool()
    pool.add_edge('https://example.com', 'links_to', 'example.org')


def test_intelligence_pool_duplicate_entity():
    """Duplicate entities should not raise — pool should be idempotent."""
    pool = _fresh_pool()
    pool.add_entity('url', 'https://dup.com')
    try:
        pool.add_entity('url', 'https://dup.com')
    except Exception as e:
        assert False, f"Duplicate entity raised unexpectedly: {e}"


def test_intelligence_pool_payload_hash_sealed():
    """Payload hash should be set at ingestion and be a 64-char hex string."""
    pool = _fresh_pool()
    pool.add_entity('url', 'https://hash-check.com')
    row = pool.get_next_raw()
    assert row is not None
    assert row['payload_hash'] is not None
    assert len(row['payload_hash']) == 64, "Expected SHA-256 hex digest (64 chars)"


def test_intelligence_pool_count():
    """count_entities should reflect added entities."""
    pool = _fresh_pool()
    pool.add_entity('url', 'https://a.com')
    pool.add_entity('url', 'https://b.com')
    assert pool.count_entities() == 2
