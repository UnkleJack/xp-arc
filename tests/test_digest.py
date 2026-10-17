"""
AI Agent Ecosystem Weekly digest — version labels, week window, rendering.

The digest must only print labels that can be read off the data. These tests
pin the cases that real registry data broke during development:

* a package shipping two major lines at once (Vercel's `ai` 6.x and 7.x), where
  comparing with the release published just before mislabels the older line;
* a fetch that keeps only five releases, so the true predecessor is unknown
  unless the fetcher records it from the full registry list;
* date-stamped `.dev` nightlies flooding the headlines;
* PyPI versions sorted as strings ("0.3.9" above "0.3.10").
"""

import asyncio
import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest

pytest.importorskip('yaml')
pytest.importorskip('httpx')

from xp_arc.competitive_intel.digest import (  # noqa: E402
    build_digest, iso_week_bounds, load_package_owners, render_markdown,
)
from xp_arc.competitive_intel.versioning import (  # noqa: E402
    classify, parse_version, predecessor,
)

SCHEMA = Path(__file__).resolve().parent.parent / 'sql' / 'competitive-gaps-schema.sql'


# ─── Version parsing and labels ──────────────────────────────────────────────

@pytest.mark.parametrize('lower,higher', [
    ('0.3.9', '0.3.10'),
    ('1.0.0a1', '1.0.0a2'),
    ('1.0.0b1', '1.0.0rc1'),
    ('1.0.0.dev3', '1.0.0a1'),
    ('1.0.0rc1', '1.0.0'),
    ('1.0.0', '1.0.0.post1'),
    ('7.0.0-beta.2', '7.0.0'),
    ('v2.0', '2.0.1'),
])
def test_version_ordering(lower, higher):
    assert parse_version(lower) < parse_version(higher)


def test_unparseable_version_is_none():
    assert parse_version('latest') is None
    assert parse_version('') is None


def test_predecessor_uses_version_order_not_publish_order():
    versions = ['3.0.130', '4.0.94', '4.0.95', '4.0.96', '3.0.129']
    assert predecessor('4.0.95', versions) == '4.0.94'
    assert predecessor('3.0.130', versions) == '3.0.129'
    assert predecessor('3.0.129', versions) is None


@pytest.mark.parametrize('version,previous,latest,label', [
    ('2.0.0', '1.9.3', '2.0.0', 'major'),
    ('1.5.0', '1.4.21', '1.5.0', 'minor'),
    ('1.5.1', '1.5.0', '1.5.1', 'patch'),
    ('0.14.9rc1', '0.14.8', '0.14.11', 'pre-release'),
    ('1.15.28.dev20261017', '1.15.28.dev20261016', '1.15.27', 'nightly'),
    ('6.0.309', '6.0.308', '7.0.143', 'maintenance'),
    ('0.1.0', None, '0.1.0', 'release'),
])
def test_classify(version, previous, latest, label):
    prev = parse_version(previous) if previous else None
    assert classify(parse_version(version), prev, parse_version(latest)) == label


def test_pre_release_of_new_major_does_not_make_current_line_maintenance():
    # langchain-community 1.0.0a1 exists, but 0.3.x is still the current line.
    assert classify(parse_version('0.3.10'), parse_version('0.3.9'),
                    parse_version('0.3.10')) == 'patch'


# ─── Week window ─────────────────────────────────────────────────────────────

def test_iso_week_bounds():
    label, start, end = iso_week_bounds('2026-W42')
    assert (label, start, end) == ('2026-W42', date(2026, 10, 12), date(2026, 10, 19))
    label, start, _ = iso_week_bounds(today=date(2026, 10, 17))
    assert label == '2026-W42' and start == date(2026, 10, 12)


# ─── Digest over a real schema ───────────────────────────────────────────────

@pytest.fixture
def db(tmp_path):
    path = tmp_path / 'gaps.db'
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA.read_text())
    conn.commit()
    conn.close()
    return path


def add_event(db, n, source, source_type, competitor, ts, title, url='', payload=None):
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO raw_events (id, source, source_type, competitor, fetched_at, timestamp, "
        "title, url, raw_payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (f'e{n}', source, source_type, competitor, ts, ts, title, url,
         json.dumps(payload or {})))
    conn.commit()
    conn.close()


def release(db, n, source, pkg, version, ts, previous='<absent>', latest=None,
            competitor='x'):
    payload = {'package': pkg, 'version': version}
    if previous != '<absent>':
        payload['previous_version'] = previous
        payload['latest_version'] = latest
    sep = '@' if source == 'npm' else ' '
    add_event(db, n, source, 'release', competitor, ts,
              f"{source} Release: {pkg}{sep}{version}", f"https://reg/{pkg}/{version}", payload)


def test_two_major_lines_are_labeled_correctly(db):
    release(db, 1, 'npm', 'ai', '7.0.143', '2026-10-16T20:10:00Z', '7.0.142', '7.0.143')
    release(db, 2, 'npm', 'ai', '6.0.309', '2026-10-16T19:00:00Z', '6.0.308', '7.0.143')
    d = build_digest(str(db), '2026-W42')
    labels = {r.version: r.label for r in d.releases}
    assert labels == {'7.0.143': 'patch', '6.0.309': 'maintenance'}


def test_out_of_week_events_are_excluded(db):
    release(db, 1, 'npm', 'ai', '7.0.143', '2026-10-16T20:10:00Z', '7.0.142', '7.0.143')
    release(db, 2, 'npm', 'ai', '7.0.100', '2026-10-01T10:00:00Z', '7.0.99', '7.0.143')
    d = build_digest(str(db), '2026-W42')
    assert [r.version for r in d.releases] == ['7.0.143']


def test_richer_duplicate_row_wins(db):
    # Same release stored by an old fetch (no predecessor) and a new one.
    release(db, 1, 'npm', 'ai', '7.0.143', '2026-10-16T20:10:00Z')
    release(db, 2, 'npm', 'ai', '7.0.143', '2026-10-16T20:10:00Z', '7.0.142', '7.0.143')
    d = build_digest(str(db), '2026-W42')
    assert len(d.releases) == 1
    assert d.releases[0].label == 'patch' and d.releases[0].previous == '7.0.142'


def test_legacy_rows_without_predecessor_are_not_guessed(db):
    # Only one version known, no registry predecessor recorded: say nothing.
    release(db, 1, 'npm', 'ai', '4.0.95', '2026-10-16T20:10:00Z')
    d = build_digest(str(db), '2026-W42')
    assert d.releases[0].label == 'release'


def test_watchlist_owner_mapping(db, tmp_path):
    watchlist = tmp_path / 'watchlist.yaml'
    watchlist.write_text(
        "competitors:\n"
        "  - id: vercel_ai\n    name: Vercel AI SDK\n    npm_packages: [ai]\n"
    )
    release(db, 1, 'npm', 'ai', '7.0.143', '2026-10-16T20:10:00Z', '7.0.142', '7.0.143',
            competitor='vercel-ai')
    d = build_digest(str(db), '2026-W42', owners=load_package_owners(str(watchlist)))
    assert d.releases[0].competitor == 'vercel_ai'


def test_render_headlines_and_rollups(db):
    release(db, 1, 'npm', '@langchain/langgraph', '1.5.0', '2026-10-15T10:00:00Z',
            '1.4.21', '1.5.1', competitor='langgraph')
    for day in (14, 15, 16, 17):
        release(db, 10 + day, 'pypi', 'crewai', f'1.15.28.dev202610{day}',
                f'2026-10-{day}T03:00:00Z', f'1.15.28.dev202610{day - 1}', '1.15.27',
                competitor='crewai')
    add_event(db, 50, 'website', 'blog_post', 'langgraph', '2026-10-13T09:00:00Z',
              'Blog: Shipping 1.5', 'https://blog/1.5')
    add_event(db, 51, 'hackernews', 'story', 'hackernews', '2026-10-13T12:00:00Z',
              'HN: Agents in production', 'https://hn/1')

    text = render_markdown(build_digest(str(db), '2026-W42'),
                           {'langgraph': 'LangGraph', 'crewai': 'CrewAI'})

    headlines = text.split('## Headlines')[1].split('## By project')[0]
    assert 'minor (from 1.4.21)' in headlines
    assert 'dev2026' not in headlines, 'nightlies must not reach the headlines'
    assert '`crewai` (PyPI): 4 nightly builds' in text
    assert '`@langchain/langgraph` (npm)' in text
    assert 'Blog: [Shipping 1.5](https://blog/1.5)' in text
    assert '## On Hacker News' in text
    assert '**5 releases** across **2 projects**' in text


def test_empty_week_renders(db):
    text = render_markdown(build_digest(str(db), '2026-W42'))
    assert 'No major, minor or pre-release versions this week.' in text
    assert 'No events collected for this week.' in text


# ─── Fetcher: PyPI ordering and predecessor recording ───────────────────────

def test_pypi_fetcher_keeps_newest_by_upload_time_and_records_predecessor():
    from xp_arc.competitive_intel.fetchers import PyPIFetcher

    def files(day):
        return [{'upload_time_iso_8601': f'2026-10-{day:02d}T00:00:00Z'}]

    registry = {
        'info': {'version': '0.3.10', 'summary': 's'},
        'releases': {'0.3.1': files(1), '0.3.2': files(2), '0.3.3': files(3),
                     '0.3.8': files(8), '0.3.9': files(9), '0.3.10': files(10),
                     '0.4.0a1': []},
    }

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return registry

    class FakeClient:
        async def get(self, url):
            return FakeResponse()

    class FakeStation:
        config = {}

    fetcher = PyPIFetcher(FakeStation())
    fetcher.client = FakeClient()
    events = asyncio.run(fetcher._fetch_package('pkg'))

    versions = [e['raw_payload']['version'] for e in events]
    assert versions == ['0.3.10', '0.3.9', '0.3.8', '0.3.3', '0.3.2']
    first = events[0]['raw_payload']
    assert first['previous_version'] == '0.3.9'
    assert first['latest_version'] == '0.3.10'
