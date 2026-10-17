"""
Weekly ecosystem digest built straight from collected raw_events.

Every label in the digest is a fact that can be read off the data:

* Releases are classified by comparing version numbers, not by keyword
  matching: major / minor / patch, pre-release, or maintenance (a release on an
  older line while a newer line already exists).
* Blog posts and Hacker News stories are listed as what they are.

Nothing here infers sentiment, pricing changes, or "gaps". That is
deliberate: the detection engine's keyword categories are not reliable enough
to publish, so the digest does not use them.
"""

import json
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from .versioning import SIGNIFICANCE, Version, classify, parse_version

def iso_week_bounds(week: Optional[str] = None, today: Optional[date] = None):
    """Return (label, start, end) for an ISO week like '2026-W42' (default: current)."""
    if week:
        year, num = week.upper().split('-W')
        start = date.fromisocalendar(int(year), int(num), 1)
    else:
        today = today or datetime.now(timezone.utc).date()
        start = today - timedelta(days=today.isoweekday() - 1)
    end = start + timedelta(days=7)
    iso = start.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}", start, end


def _parse_ts(text: str) -> Optional[datetime]:
    if not text:
        return None
    try:
        ts = datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


@dataclass
class ReleaseItem:
    competitor: str
    package: str
    version: str
    label: str
    timestamp: datetime
    url: str
    source: str
    previous: Optional[str] = None


@dataclass
class Digest:
    week: str
    start: date
    end: date
    releases: List[ReleaseItem] = field(default_factory=list)
    posts: List[dict] = field(default_factory=list)
    stories: List[dict] = field(default_factory=list)
    sources_seen: Dict[str, int] = field(default_factory=dict)


ROUTINE = ('patch', 'maintenance', 'nightly')
ECOSYSTEM = {'pypi': 'PyPI', 'npm': 'npm', 'github': 'GitHub'}


def _load_watchlist(watchlist_path: str) -> list:
    try:
        with open(watchlist_path) as f:
            return (yaml.safe_load(f) or {}).get('competitors', [])
    except OSError:
        return []


def load_competitor_names(watchlist_path: str) -> Dict[str, str]:
    return {c['id']: c.get('name', c['id']) for c in _load_watchlist(watchlist_path) if 'id' in c}


def load_package_owners(watchlist_path: str) -> Dict[Tuple[str, str], str]:
    """Map (source, package) to the watchlist competitor that publishes it."""
    owners = {}
    for c in _load_watchlist(watchlist_path):
        for pkg in c.get('pypi_packages') or []:
            owners.setdefault(('pypi', pkg), c['id'])
        for pkg in c.get('npm_packages') or []:
            owners.setdefault(('npm', pkg), c['id'])
    return owners


def build_digest(db_path: str, week: Optional[str] = None,
                 today: Optional[date] = None,
                 owners: Optional[Dict[Tuple[str, str], str]] = None) -> Digest:
    """Read raw_events and assemble the digest for one ISO week.

    owners maps (source, package) to a watchlist competitor id; packages not in
    it keep the competitor id the fetcher assigned.
    """
    owners = owners or {}
    label, start, end = iso_week_bounds(week, today)
    lo = datetime.combine(start, datetime.min.time(), timezone.utc)
    hi = datetime.combine(end, datetime.min.time(), timezone.utc)
    digest = Digest(week=label, start=start, end=end)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT source, source_type, competitor, timestamp, title, url, raw_payload "
        "FROM raw_events"
    ).fetchall()
    conn.close()

    # Every known version per package, from all history, so each release in
    # the week can be compared with its true predecessor.
    versions_by_pkg: Dict[Tuple[str, str], Dict[str, Version]] = defaultdict(dict)
    release_rows = []
    seen_ids: Dict[Tuple[str, str, str], int] = {}
    for row in rows:
        ts = _parse_ts(row['timestamp'])
        in_week = ts is not None and lo <= ts < hi
        if in_week:
            digest.sources_seen[row['source']] = digest.sources_seen.get(row['source'], 0) + 1

        if row['source_type'] == 'release':
            try:
                payload = json.loads(row['raw_payload'] or '{}')
            except json.JSONDecodeError:
                payload = {}
            package = payload.get('package') or row['competitor']
            ver_text = payload.get('version') or row['title'].rsplit(' ', 1)[-1].split('@')[-1]
            parsed = parse_version(ver_text)
            if parsed:
                versions_by_pkg[(row['source'], package)][ver_text] = parsed
            key = (row['source'], package, ver_text)
            if in_week:
                if key not in seen_ids:
                    seen_ids[key] = len(release_rows)
                    release_rows.append((row, package, ver_text, parsed, ts, payload))
                elif 'previous_version' in payload and \
                        'previous_version' not in release_rows[seen_ids[key]][5]:
                    # Same release fetched again by a newer fetcher: keep the richer row.
                    release_rows[seen_ids[key]] = (row, package, ver_text, parsed, ts, payload)
        elif in_week and row['source'] == 'website':
            digest.posts.append({'competitor': row['competitor'], 'timestamp': ts,
                                 'title': re.sub(r'^Blog:\s*', '', row['title']),
                                 'url': row['url']})
        elif in_week and row['source'] == 'hackernews':
            digest.stories.append({'timestamp': ts, 'url': row['url'],
                                   'title': re.sub(r'^HN:\s*', '', row['title'])})

    for row, package, ver_text, parsed, ts, payload in release_rows:
        known = versions_by_pkg[(row['source'], package)]
        label_ = 'release'
        prev_text = None
        if parsed:
            if 'previous_version' in payload:
                # The fetcher saw the registry's full version list: trust it.
                prev_text = payload.get('previous_version')
                latest = parse_version(payload.get('latest_version') or '')
                newest_final = latest if latest and not latest.is_pre else parsed
            else:
                # Older rows: fall back to the versions this database has seen.
                # A missing predecessor then means "not collected", so the
                # release is left unlabeled rather than guessed.
                ordered = sorted(known.items(), key=lambda kv: kv[1])
                finals = [v for _, v in ordered if not v.is_pre]
                newest_final = finals[-1] if finals else ordered[-1][1]
                idx = [t for t, _ in ordered].index(ver_text)
                prev_text = ordered[idx - 1][0] if idx > 0 else None
            prev = parse_version(prev_text) if prev_text else None
            label_ = classify(parsed, prev, newest_final)
        digest.releases.append(ReleaseItem(
            competitor=owners.get((row['source'], package), row['competitor']),
            package=package, version=ver_text,
            label=label_, timestamp=ts, url=row['url'] or '', source=row['source'],
            previous=prev_text,
        ))

    digest.releases.sort(key=lambda r: (SIGNIFICANCE[r.label], -r.timestamp.timestamp()))
    digest.posts.sort(key=lambda p: p['timestamp'], reverse=True)
    digest.stories.sort(key=lambda s: s['timestamp'], reverse=True)
    return digest


def _pkg(r: ReleaseItem) -> str:
    return f"`{r.package}` ({ECOSYSTEM.get(r.source, r.source)})"


def _display_name(cid: str, names: Dict[str, str]) -> str:
    return names.get(cid) or cid.replace('_', ' ').replace('-', ' ').title()


def _release_line(r: ReleaseItem) -> str:
    since = f" (from {r.previous})" if r.previous else ""
    return f"{_pkg(r)} [{r.version}]({r.url}) — {r.label}{since}"


def render_markdown(digest: Digest, names: Optional[Dict[str, str]] = None) -> str:
    names = names or {}

    def display(cid: str) -> str:
        return _display_name(cid, names)

    end_inclusive = digest.end - timedelta(days=1)
    projects = sorted({r.competitor for r in digest.releases} |
                      {p['competitor'] for p in digest.posts})

    out = [
        f"# AI Agent Ecosystem Weekly — {digest.week}",
        f"*{digest.start:%b %d} – {end_inclusive:%b %d, %Y}*",
        "",
        f"**{len(digest.releases)} releases** across **{len(projects)} projects**, "
        f"**{len(digest.posts)} blog posts**, **{len(digest.stories)} Hacker News stories**.",
        "",
    ]

    headlines = [r for r in digest.releases if r.label in ('major', 'minor', 'pre-release')]
    out.append("## Headlines")
    if headlines:
        for r in headlines:
            out.append(f"- **{display(r.competitor)}**: {_release_line(r)}")
    else:
        out.append("- No major, minor or pre-release versions this week.")
    out.append("")

    out.append("## By project")
    for cid in projects:
        rel = [r for r in digest.releases if r.competitor == cid]
        posts = [p for p in digest.posts if p['competitor'] == cid]
        out.append(f"### {display(cid)}")
        for r in (r for r in rel if r.label not in ROUTINE):
            out.append(f"- {_release_line(r)}")
        routine = defaultdict(list)
        for r in rel:
            if r.label in ROUTINE:
                routine[(r.source, r.package, r.label)].append(r)
        for (_, _, kind), items in sorted(routine.items(), key=lambda kv: (kv[0][1], kv[0][0],
                                                                          SIGNIFICANCE[kv[0][2]])):
            newest = max(items, key=lambda r: r.timestamp)
            noun = 'build' if kind == 'nightly' else 'release'
            count = f"{len(items)} {kind} {noun}{'s' if len(items) > 1 else ''}"
            out.append(f"- {_pkg(newest)}: {count}, latest [{newest.version}]({newest.url})")
        for p in posts:
            out.append(f"- Blog: [{p['title']}]({p['url']})")
        out.append("")

    if digest.stories:
        out.append("## On Hacker News")
        for s in digest.stories:
            out.append(f"- [{s['title']}]({s['url']})")
        out.append("")

    out.append("## Coverage and method")
    if digest.sources_seen:
        seen = ", ".join(f"{k} ({v})" for k, v in sorted(digest.sources_seen.items()))
        out.append(f"- Sources with data this week: {seen}.")
    else:
        out.append("- No events collected for this week.")
    out.append("- Release labels come from comparing each version with the previous "
               "version of the same package in its registry. *Maintenance* means a release "
               "on an older major line while a newer one exists; *nightly* means a `.dev` "
               "build. Release notes are not read or summarized.")
    out.append("- Blog posts are listed from each project's configured feed, unfiltered.")
    out.append("")
    return "\n".join(out)


def write_digest(db_path: str, output_dir: str, watchlist_path: str,
                 week: Optional[str] = None) -> Path:
    digest = build_digest(db_path, week, owners=load_package_owners(watchlist_path))
    text = render_markdown(digest, load_competitor_names(watchlist_path))
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{digest.week}.md"
    path.write_text(text)
    return path
