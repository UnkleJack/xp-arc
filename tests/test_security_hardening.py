"""
Security punch-list regressions.

Covers, in order:
  * RT-14 — MAX_SPAWN_PER_ENTITY: one process() could flood the pool.
  * RT-15 — MAX_SHARD_COUNT: one fracture could multiply without bound.
  * station_id injection — register_station() accepted any string as the HMAC
    write-auth lookup key and as a keystore component.
  * /ws auth bypass — auth_middleware unconditionally exempted '/ws', so the
    FULL live telemetry stream was readable without credentials even with
    XP_ARC_API_KEY set, while the REST surface it mirrors was protected.
  * /api/seed — no URL validation (an SSRF pivot into internal services) and no
    rate limiting.
  * GRC stations — shipped a hardcoded fallback credential in the source tree
    (the literal is assembled at runtime below so this file does not match its
    own scan).
"""

import os
import tempfile

import pytest

os.environ.setdefault('XP_ARC_DEV_MODE', '1')
os.environ.setdefault('XP_ARC_ABOYEUR_KEY', 'test-key')

from xp_arc.core.executive import ExecutiveChef  # noqa: E402
from xp_arc.core.fracture import FractureProtocol  # noqa: E402
from xp_arc.core.pool import (  # noqa: E402
    MAX_SHARD_COUNT, MAX_SPAWN_PER_ENTITY, IntelligencePool,
)
from xp_arc.core.sanitization import (  # noqa: E402
    sanitize_display_name, sanitize_station_id,
)
from xp_arc.core.station import StationChef  # noqa: E402


@pytest.fixture
def pool():
    with tempfile.TemporaryDirectory() as tmp:
        p = IntelligencePool(os.path.join(tmp, 'sec.db'))
        yield p
        p.close()


# ─── RT-14: entity flood ─────────────────────────────────────────────────────

class FloodStation(StationChef):
    station_id = 'flooder'
    name = 'Flood Station'
    handles_types = ['url']

    def __init__(self, pool, spawn_count):
        super().__init__(pool)
        self.spawn_count = spawn_count

    def process(self, entity_id, entity_type, entity_value):
        return {
            'entity_type': entity_type,
            'entity_value': entity_value,
            'relationships': [],
            'confidence': 0.9,
            'notes': 'flood',
            'spawn_targets': [
                {'ent_type': 'url', 'value': f'https://example.com/spawn/{i}'}
                for i in range(self.spawn_count)
            ],
        }


def test_spawn_flood_is_capped(pool):
    ex = ExecutiveChef(pool, verbose=False, max_entities=1)
    ex.register_station(FloodStation(pool, spawn_count=MAX_SPAWN_PER_ENTITY + 25))
    pool.add_entity('url', 'https://example.com/seed')

    ex.run_service()

    assert ex.summary()['spawn_created'] <= MAX_SPAWN_PER_ENTITY
    assert ex.summary()['spawn_blocked'] >= 25
    assert any(e['event_type'] == 'spawn_blocked_flood_limit'
               for e in pool.get_events(200))


def test_spawns_under_the_cap_are_untouched(pool):
    ex = ExecutiveChef(pool, verbose=False, max_entities=1)
    ex.register_station(FloodStation(pool, spawn_count=5))
    pool.add_entity('url', 'https://example.com/seed')

    ex.run_service()

    assert ex.summary()['spawn_created'] == 5
    assert ex.summary()['spawn_blocked'] == 0


# ─── RT-15: shard flood ──────────────────────────────────────────────────────

def test_shard_count_is_clamped(pool):
    eid = pool.add_entity('url', 'https://example.com/huge')
    pool.station_writer('executive').transition_status(eid, 'processing',
                                                       station='executive')

    shards = FractureProtocol(pool).create_shards(
        eid, 'url', 'https://example.com/huge', shard_count=5000
    )

    assert len(shards) == MAX_SHARD_COUNT
    assert any(e['event_type'] == 'shard_count_clamped'
               for e in pool.get_events(200))


def test_nonpositive_shard_count_is_refused(pool):
    eid = pool.add_entity('url', 'https://example.com/zero')
    pool.station_writer('executive').transition_status(eid, 'processing',
                                                       station='executive')

    assert FractureProtocol(pool).create_shards(
        eid, 'url', 'https://example.com/zero', shard_count=0) == []
    # Refused BEFORE the parent is moved to 'fractured', so it is not stranded.
    assert pool.get_entity(eid)['status'] == 'processing'


# ─── station_id injection ────────────────────────────────────────────────────

@pytest.mark.parametrize('bad', [
    'mcp_tool.name/v2', '../../etc/passwd', 'a' * 65, '', 'has space',
    'semi;colon', 'new\nline', 'quote"mark',
])
def test_malformed_station_ids_are_rejected(bad):
    with pytest.raises(ValueError):
        sanitize_station_id(bad)


@pytest.mark.parametrize('good', [
    'aboyeur', 'chef_de_cuisine', 'competitive-intel-bridge', 'A2A_agent_01',
])
def test_conforming_station_ids_pass_through_unchanged(good):
    assert sanitize_station_id(good) == good


def test_pool_refuses_to_register_a_malformed_station_id(pool):
    with pytest.raises(ValueError):
        pool.register_station('evil id/../x', 'Evil', ['url'])
    assert not any(s['station_id'] == 'evil id/../x'
                   for s in pool.get_active_stations())


def test_display_names_are_sanitized_not_rejected(pool):
    pool.register_station('tidy_station', 'Tidy\x00 Station\x1b', ['url'])

    row = [s for s in pool.get_active_stations()
           if s['station_id'] == 'tidy_station'][0]
    assert row['name'] == 'Tidy Station'
    assert sanitize_display_name('x' * 500) == 'x' * 128


# ─── DRAGON API surface ──────────────────────────────────────────────────────

def test_ws_and_metrics_are_no_longer_auth_exempt():
    """Only the credential-free liveness probe may bypass auth."""
    import run_persistent
    src = run_persistent.__file__
    with open(src) as fh:
        body = fh.read()

    assert "if request.path in ('/ws', '/api/health', '/metrics')" not in body
    assert "if request.path == '/api/health':" in body


def test_websocket_accepts_the_key_as_a_query_parameter(monkeypatch):
    """Browsers cannot set headers on a WS handshake; same secret either way."""
    import run_persistent

    monkeypatch.setattr(run_persistent, 'API_KEY', 'super-secret')

    class FakeRequest:
        def __init__(self, path, headers=None, query=None):
            self.path = path
            self.headers = headers or {}
            self.query = query or {}

    assert run_persistent.check_auth(
        FakeRequest('/ws', query={'token': 'super-secret'})) is True
    assert run_persistent.check_auth(
        FakeRequest('/ws', query={'token': 'wrong'})) is False
    assert run_persistent.check_auth(FakeRequest('/ws')) is False
    # The query-param path is scoped to /ws only.
    assert run_persistent.check_auth(
        FakeRequest('/api/dragon', query={'token': 'super-secret'})) is False
    assert run_persistent.check_auth(
        FakeRequest('/api/dragon',
                    headers={'Authorization': 'Bearer super-secret'})) is True


@pytest.mark.parametrize('url,reason_fragment', [
    ('http://127.0.0.1:8080/admin', 'public'),
    ('http://localhost/', 'public'),
    ('http://169.254.169.254/latest/meta-data/', 'public'),
    ('file:///etc/passwd', 'scheme'),
    ('javascript:alert(1)', 'scheme'),
    ('ftp://example.com/x', 'scheme'),
    ('', 'non-empty'),
    ('https://' + 'a' * 3000 + '.com', 'exceeds'),
])
def test_seed_urls_are_validated(url, reason_fragment):
    import run_persistent

    kitchen = run_persistent.PersistentKitchen.__new__(
        run_persistent.PersistentKitchen)
    reason = run_persistent.PersistentKitchen.validate_seed_url(kitchen, url)

    assert reason is not None, f'{url!r} was accepted'
    assert reason_fragment in reason


def test_seed_rate_limiter_blocks_a_burst():
    from run_persistent import RateLimiter

    limiter = RateLimiter(max_requests=3, window_seconds=60)

    assert [limiter.allow('1.2.3.4')[0] for _ in range(3)] == [True] * 3
    allowed, retry_after = limiter.allow('1.2.3.4')
    assert allowed is False
    assert retry_after >= 1
    # Limits are per client, not global.
    assert limiter.allow('5.6.7.8')[0] is True


# ─── Credentials in the source tree ──────────────────────────────────────────

def test_no_hardcoded_grc_fallback_token_anywhere_in_the_tree():
    # Assembled rather than written literally: a scan for a credential string
    # must not be tripped by the scanner's own source.
    needle = 'dev-token' + '-change-in-' + 'production'
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    offenders = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in {'.git', '__pycache__', '.pytest_cache',
                                    'build', 'dist', '.venv'}]
        for name in filenames:
            if not name.endswith(('.py', '.md', '.toml', '.yml', '.yaml')):
                continue
            path = os.path.join(dirpath, name)
            try:
                with open(path, encoding='utf-8', errors='ignore') as fh:
                    if needle in fh.read():
                        offenders.append(os.path.relpath(path, root))
            except OSError:
                continue
    assert offenders == [], f'hardcoded fallback credential present in {offenders}'


def test_grc_stations_refuse_to_start_without_a_token(pool, monkeypatch):
    monkeypatch.delenv('XP_ARC_CISO_TOKEN', raising=False)
    from xp_arc.stations.grc_commis import GRCCommis
    from xp_arc.stations.grc_supervisor import GRCSupervisor

    for cls in (GRCSupervisor, GRCCommis):
        with pytest.raises(RuntimeError, match='XP_ARC_CISO_TOKEN'):
            cls(pool)
