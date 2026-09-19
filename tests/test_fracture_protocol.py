'''Regression tests for the Fracture Protocol HMAC allowlist bug (fixed 2026-08-23).

Bug: FractureProtocol.create_shards() writes shard entities via
pool.add_entity(station_id='fracture_protocol', ...) with no HMAC key
registered for that station id. IntelligencePool._verify_write() only
allowed unkeyed writes from {'legacy_local', 'executive', 'aboyeur'}, so
'fracture_protocol' was never authorized and every shard insert silently
failed (add_entity returned None), making create_shards() always return [].
Because create_shards() transitions the parent to 'fractured' *before*
attempting shard writes, and 'fractured' can only advance to 'stitchable'
(which requires real shards to exist), every fracture permanently bricked
its parent entity. This was present since inception, not a regression.
'''
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

os.environ['XP_ARC_DEV_MODE'] = '1'
os.environ['XP_ARC_ABOYEUR_KEY'] = 'test-signing-key-for-unit-tests-only'

from xp_arc.core.pool import IntelligencePool
from xp_arc.core.fracture import FractureProtocol


def _fresh_pool():
    return IntelligencePool(":memory:")


def _processing_entity(pool, ent_type='complex_task', value='VeryLargeTaskData'):
    entity_id = pool.add_entity(ent_type, value)
    assert pool.transition_status(entity_id, 'processing') is True
    return entity_id


def test_fracture_protocol_writer_is_hmac_authorized():
    """'fracture_protocol' must be an authorized unkeyed writer, or every
    shard write silently fails HMAC verification."""
    pool = _fresh_pool()
    assert pool._verify_write('fracture_protocol', 'add_entity:shard:x:60', None) is True


def test_create_shards_actually_creates_shards():
    """The core regression: create_shards() must return real shard ids,
    not an empty list, when the write path is authorized correctly."""
    pool = _fresh_pool()
    parent_id = _processing_entity(pool)

    fp = FractureProtocol(pool)
    shard_ids = fp.create_shards(parent_id, 'complex_task', 'VeryLargeTaskData',
                                  shard_count=2, shard_type='shard')

    assert shard_ids != [], "create_shards() returned no shards — HMAC allowlist regressed"
    assert len(shard_ids) == 2

    for shard_id in shard_ids:
        shard = pool.get_entity(shard_id)
        assert shard is not None, f"shard {shard_id} was not actually persisted"
        assert shard['type'] == 'shard'
        assert shard['fracture_id'] is not None


def test_fractured_parent_is_not_permanently_stuck():
    """A parent that fractures successfully must have real shards to check
    completion against — proving it is NOT permanently bricked in
    'fractured' (which VALID_TRANSITIONS only allows to advance to
    'stitchable', and only once check_shard_completion sees real shards)."""
    pool = _fresh_pool()
    parent_id = _processing_entity(pool)

    fp = FractureProtocol(pool)
    shard_ids = fp.create_shards(parent_id, 'complex_task', 'VeryLargeTaskData',
                                  shard_count=2, shard_type='shard')
    parent = pool.get_entity(parent_id)
    assert parent['status'] == 'fractured'

    completion = fp.check_shard_completion(parent['fracture_id'])
    assert len(completion['shards']) == len(shard_ids) == 2, (
        "check_shard_completion sees no shards — parent would be permanently "
        "stuck in 'fractured' with no path to 'stitchable'"
    )
