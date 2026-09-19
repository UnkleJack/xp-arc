"""
Competitive Gap Analyst — the pool station that consumes bridged gaps.

The bridge injects 'competitive_gap' entities onto the pass. Without a station
that handles that type, the Executive marks every one of them unhandled and
fails it, so the bridge alone proves nothing. This is the other half.

It is an ordinary StationChef: registered with the pool, HMAC-signed writes,
output gated by the Aboyeur like any other labor. That is the whole point of
bridging — competitive findings become first-class pool citizens rather than
rows in a private database nobody else can see.

The analysis is deliberately rule-based rather than LLM-backed. This station's
job in the acceptance run is to prove the PLUMBING carries real competitive data
end to end under real constitutional constraints. A model call would add an
external dependency, a failure mode, and a cost to a path whose purpose is to
demonstrate the protocol, not to be clever.
"""

import json

from ..core.station import StationChef

# Gap types that bear directly on XP-Arc's stated differentiation. A gap in a
# competitor's QA-enforcement or auditability story is strategically louder for
# XP-Arc than a pricing gap, because that is the ground XP-Arc claims.
STRATEGIC_GAP_TYPES = {
    'missing_integration': 'interoperability',
    'performance': 'throughput',
    'dx': 'developer experience',
    'lockin': 'openness',
    'pricing': 'commercial',
    'feature': 'capability',
}

SEVERITY_CONFIDENCE = {
    'critical': 0.95,
    'high': 0.85,
    'medium': 0.7,
    'low': 0.55,
}


class CompetitiveGapAnalyst(StationChef):
    """Turns a bridged competitive gap into a scored, signed pool finding."""

    station_id = 'competitive_gap_analyst'
    name = 'Competitive Gap Analyst'
    handles_types = ['competitive_gap']
    sla_seconds = 180
    is_primary = True

    def process(self, entity_id: int, entity_type: str, entity_value: str) -> dict:
        try:
            gap = json.loads(entity_value)
        except (json.JSONDecodeError, TypeError):
            # Malformed input is reported honestly at low confidence rather than
            # guessed at. The Aboyeur will still gate it.
            return {
                'entity_type': entity_type,
                'entity_value': entity_value,
                'relationships': [],
                'confidence': 0.1,
                'notes': 'Gap payload was not valid JSON and could not be analyzed.',
            }

        severity = str(gap.get('severity', 'medium')).lower()
        gap_type = str(gap.get('gap_type', 'other')).lower()
        competitor = gap.get('competitor', 'unknown')
        dimension = STRATEGIC_GAP_TYPES.get(gap_type, 'general')
        confidence = SEVERITY_CONFIDENCE.get(severity, 0.6)

        assessment = (
            f"{competitor}: {dimension} gap ({gap_type}, severity {severity}). "
            f"{gap.get('description', 'No description recorded.')}"
        )

        if severity in ('critical', 'high'):
            self.pool.add_finding(
                'high' if severity == 'high' else 'critical',
                self.station_id,
                f"Competitive gap — {competitor} / {gap_type}",
                assessment,
            )

        self.log(assessment)

        # entity_type and entity_value are echoed back unchanged: the Aboyeur
        # verifies both against the payload_hash sealed at ingestion and rejects
        # any station that rewrites the entity it was handed.
        return {
            'entity_type': entity_type,
            'entity_value': entity_value,
            'relationships': self._relationships(gap),
            'confidence': confidence,
            'notes': assessment,
        }

    @staticmethod
    def _relationships(gap: dict) -> list:
        """Relationships are plain strings — the Aboyeur rejects non-str elements."""
        rels = []
        competitor = gap.get('competitor')
        if competitor:
            rels.append(f"competitor:{competitor}")
        gap_type = gap.get('gap_type')
        if gap_type:
            rels.append(f"gap_type:{gap_type}")
        for url in (gap.get('evidence_urls') or [])[:5]:
            if isinstance(url, str) and url.strip():
                rels.append(f"evidence:{url.strip()}")
        return rels
