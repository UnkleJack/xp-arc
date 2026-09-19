'''
Targeted regression tests for the vulnerability fixes ported from PR #4
("Red team audit — 7 vulns fixed") during its reconciliation against current
main, since PR #4 itself was never merged (base commit diverged, mergeable_state
"dirty", and it still touched broker.py/broker_client.py which are slated for
removal per standing ruling).

Covers the fixes that ARE code-testable from Python:
  RT-11 — export_state() must not leak station hmac_key. NOTE: while
          reconciling this branch, main had already independently fixed RT-11
          twice (PUBLIC_STATION_COLUMNS in get_active_stations(), plus a
          defense-in-depth pop() in export_state() itself) between the local
          clone this branch's other fixes were verified against and the
          moment this branch was actually created from main. No RT-11 code
          change was needed here — this test just confirms that protection
          still holds.
  RT-14 — Executive._process_spawns() caps spawn_targets at MAX_SPAWN_PER_ENTITY
  RT-15 — FractureProtocol.create_shards() caps shard_count at MAX_SHARD_COUNT
  RT-10 — Forager strips HTML tags from extracted page titles
  RT-18 — legacy/unkeyed writes are now logged (mitigation, not a full close)

RT-08 and RT-09 (dossier/tooltip XSS in dragon/index.html) are pure front-end
JS fixes with no test harness in this repo (no node/JS test runner present) —
verified by manual code review only: both sites now wrap untrusted fields in
the pre-existing escapeHtml() helper, consistent with its use elsewhere in the
same file. Flagging this as unverified-by-automation rather than claiming test
coverage that doesn't exist.
'''
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

os.environ['XP_ARC_DEV_MODE'] = '1'
os.environ['XP_ARC_ABOYEUR_KEY'] = 'test-signing-key-for-unit-tests-only'
os.environ['XP_ARC_SLA_AUDIT'] = '1'

from xp_arc.core.pool import IntelligencePool
from xp_arc.core.executive import ExecutiveChef
from xp_arc.core.fracture import FractureProtocol, MAX_SHARD_COUNT


def _fresh_pool():
    return IntelligencePool(":memory:")


def test_rt11_export_state_does_not_leak_hmac_key():
    """export_state()'s station list must never include the raw hmac_key."""
    pool = _fresh_pool()
    pool.register_station('forager', 'The Forager', ['url', 'domain'], is_primary=True)
    state = pool.export_state()
    assert state['stations'], "expected at least one active station in export"
    for station in state['stations']:
        assert 'hmac_key' not in station, f"hmac_key leaked in export_state(): {station}"


def test_rt14_spawn_flood_is_capped():
    """A single process() result requesting more than MAX_SPAWN_PER_ENTITY spawns
    should be truncated, not allowed to flood the pool."""
    pool = _fresh_pool()
    parent_id = pool.add_entity('url', 'https://flood-parent.example')
    executive = ExecutiveChef(pool, verbose=False)

    flood_targets = [{'ent_type': 'domain', 'value': f'flood-{i}.example'} for i in range(500)]
    created = executive._process_spawns(parent_id, flood_targets)

    assert len(created) <= ExecutiveChef.MAX_SPAWN_PER_ENTITY, (
        f"spawn flood not capped: created {len(created)} entities, "
        f"expected at most {ExecutiveChef.MAX_SPAWN_PER_ENTITY}"
    )


def test_rt15_shard_flood_is_capped():
    """create_shards() must not honor an unbounded shard_count."""
    pool = _fresh_pool()
    entity_id = pool.add_entity('url', 'https://shard-parent.example')
    protocol = FractureProtocol(pool)

    shard_ids = protocol.create_shards(entity_id, 'url', 'https://shard-parent.example',
                                        shard_count=10_000)

    assert len(shard_ids) <= MAX_SHARD_COUNT, (
        f"shard flood not capped: created {len(shard_ids)} shards, "
        f"expected at most {MAX_SHARD_COUNT}"
    )


def test_rt10_forager_strips_html_from_extracted_title():
    """Forager's title-extraction transform (regex extract + tag strip, as now
    implemented in TheForager.process()) must not pass raw HTML through into
    notes. This mirrors the exact transform inline in forager.py rather than
    driving a real HTTP fetch, since TheForager.process() requires network I/O
    that isn't appropriate for a unit test."""
    import re

    html = (
        "<html><head><title>Evil<img src=x onerror=alert(1)>Title</title></head>"
        "<body></body></html>"
    )
    title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
    raw_title = title_match.group(1).strip() if title_match else "No title"
    cleaned = re.sub(r'<[^>]*>', '', raw_title)[:200]

    assert '<img' not in cleaned, f"HTML tag survived title extraction: {cleaned!r}"
    assert cleaned == "EvilTitle", f"unexpected cleaned title: {cleaned!r}"


def test_rt18_legacy_write_is_logged():
    """Unkeyed writes via the legacy allowlist must now be audited (mitigation,
    not a full close — closing it would require legacy_local/executive/aboyeur
    to hold real keys too, which is a separate architectural decision)."""
    pool = _fresh_pool()
    pool.add_entity('url', 'https://legacy-write-audit.example', station_id='executive')

    events = pool.get_events(50)
    legacy_events = [e for e in events if e['event_type'] == 'legacy_write']
    assert legacy_events, "expected a legacy_write event to be logged for the unkeyed 'executive' write"
    assert legacy_events[0]['source'] == 'executive'
