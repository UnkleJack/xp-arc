"""
Zoran's Law regression tests — Article VIII.

THE DEFECT THESE PIN:

    S = SUM(sla_seconds of completed) / SUM(sla_seconds of ALL ingested)

Every completed task is also an ingested task, so the numerator was a strict
subset of the denominator and S could never exceed 1.0. Article VIII 8.1
defines HEALTHY as S > 1.0 — an unreachable state. A brigade that ingested ten
tasks and completed all ten scored exactly 1.0, "equilibrium / watch closely",
which was the best score the system could physically produce.

`test_old_cumulative_formula_cannot_exceed_one` reproduces that bound directly
against the same pool data the fixed code reads, so the regression is pinned by
demonstration rather than by assertion about code that no longer exists.

The fix applies Article VIII 8.4's rolling window, making S a RATE ratio:
SLA-seconds drained per window over SLA-seconds arriving per window. S > 1 then
means the brigade is paying down backlog, which is what the Constitution says
healthy means.
"""

import os
import tempfile

import pytest

os.environ.setdefault('XP_ARC_DEV_MODE', '1')
os.environ.setdefault('XP_ARC_ABOYEUR_KEY', 'test-key')

from xp_arc.core.pool import IntelligencePool  # noqa: E402
from xp_arc.monitoring.zorans_law import ZoransLaw  # noqa: E402


@pytest.fixture
def pool():
    with tempfile.TemporaryDirectory() as tmp:
        p = IntelligencePool(os.path.join(tmp, 'zorans.db'))
        yield p
        p.close()


def _insert(pool, ident, sla, *, age_seconds=0, status='raw',
            completed_age_seconds=None, sla_suspended=0):
    """Insert an entity directly with controlled timestamps.

    Direct SQL is deliberate: these tests need to place work at specific points
    in time relative to the rolling window, which the ordinary write path
    (correctly) will not allow — timestamps are DB-generated per Article 3.3.
    """
    with pool.conn:
        cur = pool.conn.execute(
            """INSERT INTO entities (type, value, status, payload_hash, sla_seconds,
                                     sla_suspended, created_at, completed_at)
               VALUES ('url', ?, ?, 'x', ?, ?, datetime('now', ?), ?)""",
            (
                f'https://example.com/{ident}', status, sla, sla_suspended,
                f'-{age_seconds} seconds',
                None if completed_age_seconds is None else None,
            ),
        )
        eid = cur.lastrowid
        if completed_age_seconds is not None:
            pool.conn.execute(
                "UPDATE entities SET completed_at = datetime('now', ?) WHERE id = ?",
                (f'-{completed_age_seconds} seconds', eid),
            )
    return eid


# ─── The reproduction ────────────────────────────────────────────────────────

def test_old_cumulative_formula_cannot_exceed_one(pool):
    """The pre-fix formula, applied to a perfectly healthy pool, is capped at 1.0."""
    for i in range(10):
        _insert(pool, i, 60, status='completed', completed_age_seconds=0)

    stats = pool.get_stats()
    completed_sla = stats.get('completed', {}).get('total_sla', 0)
    ingested_sla = sum(v.get('total_sla', 0) for v in stats.values())
    old_s = completed_sla / ingested_sla

    # Ten in, ten out, nothing failed, nothing queued: the healthiest a brigade
    # can be. The old formula calls it "equilibrium", never "healthy".
    assert old_s == 1.0
    assert not old_s > ZoransLaw.THRESHOLDS['healthy']


def test_healthy_state_is_reachable_after_fix(pool):
    """Same drained backlog, windowed rate ratio: S > 1.0, state healthy."""
    # Ingested well before the window opened, completed inside it.
    for i in range(10):
        _insert(pool, i, 60, age_seconds=600, status='completed',
                completed_age_seconds=0)

    m = ZoransLaw(pool).measure()

    assert m['stability_quotient'] > 1.0
    assert m['system_state'].startswith('healthy')
    assert m['completed_sla_in_window'] == 600
    assert m['ingested_sla_in_window'] == 0


# ─── Directional behavior ────────────────────────────────────────────────────

def test_draining_faster_than_arriving_scores_above_one(pool):
    """600 SLA-seconds drained against 120 arriving is S = 5.0."""
    for i in range(10):
        _insert(pool, f'old{i}', 60, age_seconds=600, status='completed',
                completed_age_seconds=5)
    for i in range(2):
        _insert(pool, f'new{i}', 60, age_seconds=1)

    m = ZoransLaw(pool).measure()

    assert m['stability_quotient'] == pytest.approx(5.0)
    assert m['system_state'].startswith('healthy')


def test_arriving_faster_than_draining_scores_below_one(pool):
    """Backlog growing: S < 1.0, debt accumulating.

    Ten tasks arrive in the window and seven of them drain inside it, so
    S = 420/600 = 0.7 — below equilibrium but above the 0.5 distress floor.
    """
    for i in range(3):
        _insert(pool, f'new{i}', 60, age_seconds=1)
    for i in range(7):
        _insert(pool, f'done{i}', 60, age_seconds=1, status='completed',
                completed_age_seconds=0)

    m = ZoransLaw(pool).measure()

    assert m['stability_quotient'] == pytest.approx(0.7)
    assert 'debt_accumulating' in m['system_state']


def test_distress_below_half(pool):
    for i in range(10):
        _insert(pool, f'new{i}', 60, age_seconds=1)

    m = ZoransLaw(pool).measure()

    assert m['stability_quotient'] == 0.0
    assert 'distress' in m['system_state']


def test_idle_window_is_equilibrium_not_distress(pool):
    """Nothing in, nothing out. An idle brigade is not a failing one."""
    _insert(pool, 'ancient', 60, age_seconds=9999, status='completed',
            completed_age_seconds=9999)

    m = ZoransLaw(pool).measure()

    assert m['stability_quotient'] == 1.0
    assert m['system_state'].startswith('equilibrium')


def test_s_is_capped_at_finite_ceiling(pool):
    """Zero arrivals must not produce infinity in the stored metrics."""
    for i in range(50):
        _insert(pool, i, 3600, age_seconds=600, status='completed',
                completed_age_seconds=0)

    m = ZoransLaw(pool).measure()

    assert m['stability_quotient'] == ZoransLaw.S_MAX
    assert m['stability_quotient'] != float('inf')


# ─── Windowing rules (Article VIII 8.4) ──────────────────────────────────────

def test_work_outside_the_window_is_excluded(pool):
    """A task completed ten minutes ago does not prop up the current window."""
    _insert(pool, 'stale', 60, age_seconds=1200, status='completed',
            completed_age_seconds=1200)
    _insert(pool, 'fresh', 60, age_seconds=1)

    flow = pool.windowed_sla_flow(60)

    assert flow['completed_sla'] == 0
    assert flow['ingested_sla'] == 60


def test_sla_suspended_excluded_from_both_sides(pool):
    """Suspended tasks accrue no debt, so they are neither arrivals nor drains."""
    _insert(pool, 'suspended-in', 60, age_seconds=1, sla_suspended=1)
    _insert(pool, 'suspended-out', 60, age_seconds=1, status='completed',
            completed_age_seconds=0, sla_suspended=1)
    _insert(pool, 'live', 60, age_seconds=1)

    flow = pool.windowed_sla_flow(60)

    assert flow['ingested_sla'] == 60
    assert flow['completed_sla'] == 0


def test_window_floor_is_enforced(pool):
    """Article VIII 8.4 sets a 10 second minimum window."""
    assert pool.windowed_sla_flow(1)['window_seconds'] == 10
    assert pool.windowed_sla_flow(0)['window_seconds'] == 10
    assert ZoransLaw(pool, window_seconds=2).window_seconds == 10
    assert ZoransLaw(pool).window_seconds == 60


def test_measurement_is_recorded_and_rederivable(pool):
    """A stored metrics row must carry the window that produced it."""
    for i in range(3):
        _insert(pool, i, 60, age_seconds=600, status='completed',
                completed_age_seconds=0)

    z = ZoransLaw(pool)
    m = z.measure()

    assert m['window_seconds'] == 60
    assert m['lifetime_ingested'] == 3
    history = pool.get_zorans_history()
    assert len(history) == 1
    assert history[0]['stability_quotient'] == m['stability_quotient']
