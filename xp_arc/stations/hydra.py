"""
The Hydra / Commis Chef — PATTERN RECOGNITION ENGINE.
Dragon Name: HYDRA (many heads — sees patterns from every angle)

Finds recurring patterns across the entity pool that no
individual station would catch. Shared registrars, naming
conventions, infrastructure fingerprints, clustering by
behavioral similarity.

The Hydra looks at the whole Hoard and asks: "what repeats?"

Use Cases:
    - Threat Hunting: Find domains using the same naming pattern
    - Competitive Intel: Identify competitors' subdomain strategies
    - Supply Chain: Detect shared dependencies across vendors
    - Academic Research: Find thematic clusters in citation graphs
    - Brand Monitoring: Spot imitation/typosquat patterns

Constitution: Operates under Garde Manger fallback.
"""

import re
from collections import defaultdict, Counter
from ..core.station import StationChef


class TheHydra(StationChef):
    """
    Pattern recognition across the entire entity pool.

    Detects:
    - Naming patterns (common prefixes, suffixes, structures)
    - Infrastructure patterns (shared TLDs, shared base domains)
    - Density anomalies (unusually clustered entities)
    - Structural fingerprints (subdomain depth distributions)
    """

    station_id = "hydra"
    name = "The Hydra"
    handles_types = ['_pattern_scan']
    sla_seconds = 120
    is_primary = True

    def run_pattern_scan(self) -> dict:
        """
        Full pattern analysis across the Hoard.
        Returns pattern report.
        """
        self.log("Pattern scan initiated — all heads active...")

        entities = self.pool.get_all_entities()
        domains = [e for e in entities if e['type'] == 'domain']
        domain_values = [e['value'] for e in domains]

        patterns = {}

        # 1. Prefix frequency (what subdomains are most common?)
        patterns['prefix_frequency'] = self._analyze_prefixes(domain_values)

        # 2. TLD distribution
        patterns['tld_distribution'] = self._analyze_tlds(domain_values)

        # 3. Subdomain depth distribution
        patterns['depth_distribution'] = self._analyze_depth(domain_values)

        # 4. Naming conventions (detect systematic naming)
        patterns['naming_conventions'] = self._detect_naming_patterns(domain_values)

        # 5. Base domain concentration
        patterns['base_domain_concentration'] = self._analyze_base_concentration(domain_values)

        # 6. Character analysis (average length, charset patterns)
        patterns['character_analysis'] = self._analyze_characters(domain_values)

        # Write notable findings
        total_patterns_found = 0
        for category, data in patterns.items():
            if isinstance(data, dict) and 'findings' in data:
                for finding in data['findings'][:5]:
                    self.pool.add_finding('info', self.station_id,
                                          f"Pattern [{category}]: {finding}",
                                          category)
                    total_patterns_found += 1

        self.log(f"  Pattern scan complete: {total_patterns_found} notable patterns found")

        self.pool._log_event('pattern_scan', self.station_id,
                             f"Scanned {len(domains)} domains. "
                             f"{total_patterns_found} patterns identified.")

        return {
            'domains_scanned': len(domains),
            'patterns': patterns,
            'total_findings': total_patterns_found,
        }

    def _analyze_prefixes(self, domains: list) -> dict:
        """Find the most common subdomain prefixes."""
        prefixes = Counter()
        for d in domains:
            parts = d.split('.')
            if len(parts) > 2:
                prefixes[parts[0]] += 1

        top = prefixes.most_common(20)
        findings = [f"'{p}' prefix used {c} times ({c/len(domains)*100:.1f}%)"
                    for p, c in top[:5] if c > 10]

        return {
            'top_prefixes': [{'prefix': p, 'count': c} for p, c in top],
            'unique_prefixes': len(prefixes),
            'findings': findings,
        }

    def _analyze_tlds(self, domains: list) -> dict:
        """TLD distribution analysis."""
        tlds = Counter()
        for d in domains:
            parts = d.split('.')
            tld = f".{parts[-1]}"
            if len(parts) > 2 and parts[-2] in ('co', 'ac', 'or', 'ne', 'go'):
                tld = f".{parts[-2]}.{parts[-1]}"
            tlds[tld] += 1

        top = tlds.most_common(20)
        dominant = top[0] if top else ('none', 0)
        concentration = dominant[1] / max(len(domains), 1)

        findings = []
        if concentration > 0.5:
            findings.append(f"TLD concentration: {dominant[0]} dominates with {concentration:.0%}")

        return {
            'distribution': [{'tld': t, 'count': c} for t, c in top],
            'unique_tlds': len(tlds),
            'dominant_tld': dominant[0],
            'concentration': round(concentration, 3),
            'findings': findings,
        }

    def _analyze_depth(self, domains: list) -> dict:
        """Subdomain depth distribution."""
        depths = Counter()
        for d in domains:
            depth = len(d.split('.')) - 2
            depths[depth] += 1

        findings = []
        deep = sum(c for d, c in depths.items() if d >= 3)
        if deep > 10:
            findings.append(f"{deep} domains have depth >= 3 (unusually nested)")

        return {
            'distribution': {str(d): c for d, c in sorted(depths.items())},
            'average_depth': sum(d * c for d, c in depths.items()) / max(len(domains), 1),
            'max_depth': max(depths.keys()) if depths else 0,
            'findings': findings,
        }

    def _detect_naming_patterns(self, domains: list) -> dict:
        """Detect systematic naming conventions."""
        # Look for numbered patterns: api1, api2, api3...
        numbered = defaultdict(list)
        for d in domains:
            match = re.match(r'^([a-z]+?)(\d+)\.', d)
            if match:
                base = match.group(1)
                numbered[base].append(d)

        # Look for region-prefixed patterns: us-east-*, eu-west-*
        regional = defaultdict(list)
        for d in domains:
            match = re.match(r'^(us|eu|ap|ca|sa|af|me|cn)[-_]', d)
            if match:
                region = match.group(1)
                regional[region].append(d)

        # Look for environment patterns: staging-*, dev-*, prod-*
        env_patterns = defaultdict(list)
        for d in domains:
            for env in ['staging', 'dev', 'prod', 'test', 'beta', 'sandbox']:
                if d.startswith(f'{env}-') or d.startswith(f'{env}.'):
                    env_patterns[env].append(d)

        findings = []
        for base, doms in sorted(numbered.items(), key=lambda x: -len(x[1]))[:3]:
            if len(doms) > 2:
                findings.append(f"Numbered series: '{base}' pattern ({len(doms)} instances)")

        for region, doms in sorted(regional.items(), key=lambda x: -len(x[1]))[:3]:
            if len(doms) > 5:
                findings.append(f"Regional pattern: '{region}-*' ({len(doms)} domains)")

        for env, doms in sorted(env_patterns.items(), key=lambda x: -len(x[1]))[:3]:
            if len(doms) > 3:
                findings.append(f"Environment pattern: '{env}-*' ({len(doms)} domains)")

        return {
            'numbered_series': {k: len(v) for k, v in numbered.items() if len(v) > 1},
            'regional_patterns': {k: len(v) for k, v in regional.items()},
            'environment_patterns': {k: len(v) for k, v in env_patterns.items()},
            'findings': findings,
        }

    def _analyze_base_concentration(self, domains: list) -> dict:
        """How concentrated is the pool around specific base domains?"""
        base_counts = Counter()
        for d in domains:
            parts = d.split('.')
            if len(parts) >= 2:
                base = '.'.join(parts[-2:])
                base_counts[base] += 1

        top = base_counts.most_common(15)
        total = len(domains)

        findings = []
        top_5_share = sum(c for _, c in top[:5]) / max(total, 1)
        if top_5_share > 0.3:
            findings.append(f"Top 5 base domains control {top_5_share:.0%} of all entities")

        return {
            'top_bases': [{'base': b, 'count': c, 'share': round(c/max(total,1), 3)}
                         for b, c in top],
            'unique_bases': len(base_counts),
            'top_5_concentration': round(top_5_share, 3),
            'findings': findings,
        }

    def _analyze_characters(self, domains: list) -> dict:
        """Character-level analysis."""
        lengths = [len(d) for d in domains]
        avg_len = sum(lengths) / max(len(lengths), 1)

        # Detect unusual characters
        has_numbers = sum(1 for d in domains if any(c.isdigit() for c in d.split('.')[0]))
        has_hyphens = sum(1 for d in domains if '-' in d.split('.')[0])

        findings = []
        if has_hyphens / max(len(domains), 1) > 0.2:
            findings.append(f"{has_hyphens} domains ({has_hyphens/len(domains)*100:.0f}%) use hyphens")

        return {
            'average_length': round(avg_len, 1),
            'min_length': min(lengths) if lengths else 0,
            'max_length': max(lengths) if lengths else 0,
            'with_numbers': has_numbers,
            'with_hyphens': has_hyphens,
            'findings': findings,
        }

    def process(self, entity_id, entity_type, entity_value):
        report = self.run_pattern_scan()
        return {
            'entity_type': '_pattern_scan',
            'entity_value': 'pattern_scan',
            'relationships': [],
            'confidence': 1.0,
            'notes': f"Scanned {report['domains_scanned']} domains. "
                     f"{report['total_findings']} patterns found.",
        }
