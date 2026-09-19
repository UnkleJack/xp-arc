"""
Competitive Intelligence Bridge — the dual-path connector.

CompetitiveIntelStation is deliberately NOT a pool station. It has its own
private SQLite database, its own async fetch/detect pipeline, and its own CLI,
and Dragon's ruling was to keep that standalone path working exactly as it does
today. Rewriting it into a StationChef would have meant either breaking the CLI
or dragging the pool's synchronous write contract into an async fetcher.

So this is the second path: a thin adapter that READS the competitive database
and REPUBLISHES its findings into the Intelligence Pool as ordinary entities,
where they get everything pool citizenship provides — HMAC-signed writes, the
mandatory Aboyeur gate, lineage, Zoran measurement, and DRAGON visibility.

Direction of travel is one-way by design: competitive DB -> pool. The bridge
never writes back into the competitive database, so the standalone tool cannot
be corrupted by pool state.

CONCURRENCY: this bridge is NOT concurrent-safe and is deliberately not marked
concurrent_safe. It reads a database written by a separate process on its own
schedule. Run it between scans, not during one.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from ..core.sanitization import sanitize_station_id

logger = logging.getLogger(__name__)

# One scan must not be able to flood the pool. This is the bridge's own cap and
# is independent of the Executive's MAX_SPAWN_PER_ENTITY — the bridge publishes
# root entities directly, so it is not covered by the spawn path's limit.
MAX_GAPS_PER_SCAN = 50

# Gap severity -> SLA seconds. Zoran's Law weights by cognitive labor
# expectation, so a critical gap must carry more weight than a cosmetic one or
# the stability metric misreads a backlog of serious findings as healthy.
SEVERITY_SLA = {
    'critical': 300,
    'high': 180,
    'medium': 120,
    'low': 60,
}
DEFAULT_SLA = 120

# Severity ordering for "most important first" truncation.
SEVERITY_RANK = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}


class CompetitiveIntelBridge:
    """Republishes competitive-intel gaps into the Intelligence Pool."""

    station_id = 'competitive_intel_bridge'
    name = 'Competitive Intel Bridge'

    # Not a StationChef: this does not handle a type off the pass, it injects
    # work onto it. It registers for a write key and nothing else.
    concurrent_safe = False

    def __init__(self, pool, intel_station, max_gaps: int = MAX_GAPS_PER_SCAN):
        self.pool = pool
        self.intel_station = intel_station
        self.max_gaps = max_gaps
        self.station_id = sanitize_station_id(self.station_id)
        pool.register_station(self.station_id, self.name, ['competitive_gap'],
                              is_primary=False)
        self.writer = pool.station_writer(self.station_id)
        self._published = 0
        self._skipped_duplicate = 0
        self._truncated = 0

    # ─── Publication ─────────────────────────────────────────────────────────

    async def publish_gaps(self, status: Optional[str] = 'open',
                           since: Optional[str] = None) -> List[int]:
        """Read gaps from the competitive DB and publish them into the pool.

        Returns the ids of the entities created. Gaps already present in the
        pool are skipped — add_entity() returns None on the UNIQUE(type, value)
        collision, which is the pool's own idempotency guarantee, so re-running
        the bridge after a scan does not duplicate work.
        """
        gaps = await self.intel_station.query_gaps(status=status, since=since)
        return self.publish_gap_records(gaps)

    def publish_gap_records(self, gaps: List[Dict[str, Any]]) -> List[int]:
        """Synchronous core, separated so it can be tested without an event loop."""
        gaps = self._prioritize_and_cap(gaps)
        created = []

        for gap in gaps:
            value = self._gap_to_entity_value(gap)
            sla = SEVERITY_SLA.get(str(gap.get('severity', '')).lower(), DEFAULT_SLA)
            eid = self.writer.add_entity(
                ent_type='competitive_gap',
                value=value,
                sla_seconds=sla,
            )
            if eid:
                created.append(eid)
                self._published += 1
            else:
                self._skipped_duplicate += 1

        self.pool._log_event(
            'competitive_gaps_published', self.station_id,
            f"Published {len(created)} competitive gaps into the pool "
            f"({self._skipped_duplicate} already present).",
            f"truncated={self._truncated}, cap={self.max_gaps}"
        )
        return created

    def _prioritize_and_cap(self, gaps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Cap the batch, dropping the LEAST severe gaps rather than the tail.

        A naive [:max] would discard by database order, which could throw away
        critical findings while keeping cosmetic ones.
        """
        ordered = sorted(
            gaps,
            key=lambda g: (
                SEVERITY_RANK.get(str(g.get('severity', '')).lower(), 99),
                -int(g.get('frequency') or 0),
            ),
        )
        if len(ordered) > self.max_gaps:
            self._truncated = len(ordered) - self.max_gaps
            logger.warning(
                "Capping competitive gap publication at %d; dropping %d "
                "lowest-severity gaps this scan.", self.max_gaps, self._truncated
            )
            self.pool._log_event(
                'competitive_gaps_truncated', self.station_id,
                f"{len(ordered)} gaps exceeded MAX_GAPS_PER_SCAN={self.max_gaps}; "
                f"{self._truncated} lowest-severity gaps not published this scan."
            )
            ordered = ordered[:self.max_gaps]
        return ordered

    @staticmethod
    def _gap_to_entity_value(gap: Dict[str, Any]) -> str:
        """Render a gap row as a stable, deterministic entity value.

        Determinism matters: the pool keys uniqueness on (type, value) and seals
        a payload_hash at ingestion, so the same gap must serialize identically
        on every scan or it will be republished as a new entity each time.
        sort_keys plus a fixed field set gives that.
        """
        evidence = gap.get('evidence_urls')
        if isinstance(evidence, str):
            try:
                evidence = json.loads(evidence)
            except (json.JSONDecodeError, TypeError):
                evidence = [evidence] if evidence else []
        return json.dumps({
            'gap_id': gap.get('id'),
            'competitor': gap.get('competitor'),
            'gap_type': gap.get('gap_type'),
            'description': gap.get('description'),
            'severity': gap.get('severity'),
            'evidence_urls': evidence or [],
            'first_seen': gap.get('first_seen'),
        }, sort_keys=True)

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            'station_id': self.station_id,
            'published': self._published,
            'skipped_duplicate': self._skipped_duplicate,
            'truncated': self._truncated,
            'concurrent_safe': self.concurrent_safe,
        }
