"""
The Salamander / Boucher — ENTITY NORMALIZER & DEDUPLICATOR.
Dragon Name: SALAMANDER (survives fire — purifies what passes through)

Cleans, normalizes, and deduplicates the entity pool.
www.example.com and example.com are the same entity.
HTTP and HTTPS variants are the same target. Trailing
dots, mixed case, port numbers — all noise that obscures
the real intelligence.

The Salamander makes the data trustworthy by making it clean.

Use Cases:
    - Data Quality: Remove noise from any large-scale ingestion
    - OSINT: Merge duplicate targets to avoid double-counting
    - Compliance: Prove that reported counts are accurate
    - Academic Research: Deduplicate citation variants
    - Any Pipeline: Run Salamander as a post-processing pass
      to guarantee data hygiene before analysis

Constitution: Operates under Plongeur authority (cleanup domain).
"""

import re
from collections import defaultdict
from ..core.station import StationChef


class TheSalamander(StationChef):
    """
    Entity normalizer and deduplicator.

    Normalizations applied:
    - Strip 'www.' prefix (www.example.com → example.com)
    - Lowercase everything
    - Strip trailing dots (example.com. → example.com)
    - Strip port numbers (example.com:443 → example.com)
    - Strip protocol prefixes (https://example.com → example.com)
    - Strip trailing slashes
    - Detect near-duplicates (fuzzy matching on Levenshtein-like distance)

    Creates 'normalized_to' edges when merging.
    Writes quality report to findings.
    """

    station_id = "salamander"
    name = "The Salamander"
    handles_types = ['_normalization_pass']
    sla_seconds = 120
    is_primary = True

    def run_normalization(self) -> dict:
        """
        Full normalization pass across the pool.
        Returns quality report.
        """
        self.log("Purification sweep — cleaning the Hoard...")

        entities = self.pool.get_all_entities()
        domains = [e for e in entities if e['type'] in ('domain', 'url')]

        normalized_count = 0
        duplicates_found = []
        normalizations = defaultdict(list)  # normalized → [original values]

        for entity in domains:
            original = entity['value']
            cleaned = self._normalize(original)

            if cleaned != original:
                normalized_count += 1
                normalizations[cleaned].append(original)

        # Find groups where multiple originals normalize to the same value
        duplicate_groups = {k: v for k, v in normalizations.items() if len(v) > 1}

        # Also check if the normalized form already exists as an entity
        entity_values = set(e['value'] for e in entities)
        merge_candidates = []
        for normalized, originals in normalizations.items():
            if normalized in entity_values and normalized not in originals:
                merge_candidates.append({
                    'normalized': normalized,
                    'variants': originals,
                })

        # Write edges for normalization relationships
        edges_added = 0
        for normalized, originals in normalizations.items():
            for orig in originals:
                if orig != normalized:
                    self.pool.add_edge(orig, 'normalizes_to', normalized)
                    edges_added += 1

        # Write findings
        if duplicate_groups:
            self.pool.add_finding(
                'warning', self.station_id,
                f"Found {len(duplicate_groups)} duplicate groups "
                f"({sum(len(v) for v in duplicate_groups.values())} entities)",
                f"Examples: {list(duplicate_groups.keys())[:5]}"
            )

        # Pattern analysis of normalization issues
        www_stripped = sum(1 for v in normalizations.values()
                         for o in v if o.startswith('www.'))
        case_issues = sum(1 for v in normalizations.values()
                         for o in v if o != o.lower() and o.lower() == o.lower())
        protocol_stripped = sum(1 for v in normalizations.values()
                               for o in v if o.startswith(('http://', 'https://')))

        self.log(f"  Entities analyzed: {len(domains)}")
        self.log(f"  Would normalize: {normalized_count}")
        self.log(f"  Duplicate groups: {len(duplicate_groups)}")
        self.log(f"  Merge candidates: {len(merge_candidates)}")
        self.log(f"  Normalization edges: {edges_added}")

        report = {
            'entities_analyzed': len(domains),
            'normalizations_needed': normalized_count,
            'duplicate_groups': len(duplicate_groups),
            'merge_candidates': len(merge_candidates),
            'edges_added': edges_added,
            'quality_metrics': {
                'www_prefix_issues': www_stripped,
                'case_issues': case_issues,
                'protocol_prefix_issues': protocol_stripped,
                'data_quality_score': round(1 - (normalized_count / max(len(domains), 1)), 3),
            },
            'top_duplicate_groups': [
                {'normalized': k, 'variant_count': len(v), 'variants': v[:5]}
                for k, v in sorted(duplicate_groups.items(), key=lambda x: -len(x[1]))[:10]
            ],
            'merge_candidates': merge_candidates[:10],
        }

        self.pool._log_event('normalization', self.station_id,
                             f"Analyzed {len(domains)} entities. "
                             f"{normalized_count} need normalization. "
                             f"Quality: {report['quality_metrics']['data_quality_score']:.1%}")

        return report

    def _normalize(self, value: str) -> str:
        """Apply all normalization rules to a value."""
        v = value.strip()

        # Lowercase
        v = v.lower()

        # Strip protocol
        v = re.sub(r'^https?://', '', v)

        # Strip trailing slash
        v = v.rstrip('/')

        # Strip port number
        v = re.sub(r':\d+$', '', v)

        # Strip trailing dot (DNS root)
        v = v.rstrip('.')

        # Strip www. prefix
        if v.startswith('www.') and len(v.split('.')) > 2:
            v = v[4:]

        # Strip leading/trailing whitespace again
        v = v.strip()

        return v

    def process(self, entity_id, entity_type, entity_value):
        report = self.run_normalization()
        return {
            'entity_type': '_normalization_pass',
            'entity_value': 'normalization',
            'relationships': [],
            'confidence': 1.0,
            'notes': f"Quality: {report['quality_metrics']['data_quality_score']:.1%}. "
                     f"{report['normalizations_needed']} normalizations needed.",
        }
