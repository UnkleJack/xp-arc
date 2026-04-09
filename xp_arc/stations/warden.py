"""
The Warden / Rôtisseur — THREAT & RISK SCORING ENGINE.
Dragon Name: WARDEN

Assigns risk scores to every entity in the pool based on
configurable rule sets. TLD risk profiles, connection density,
classification patterns, anomaly indicators.

The Warden doesn't discover entities. It judges them.
Every entity gets a number between 0 and 100 that says
"how much should you worry about this?"

Use Cases:
    - OSINT: Flag high-risk domains in a target's infrastructure
    - Supply Chain: Score vendor domains by exposure risk
    - Due Diligence: Rate entities by trust signals
    - Vulnerability Mgmt: Prioritize by threat surface
    - Compliance: Flag entities that violate policy rules
"""

from collections import defaultdict
from ..core.station import StationChef


class TheWarden(StationChef):
    """
    Risk scoring engine. Every entity gets a threat score.

    Scoring factors:
    - TLD risk profile (.ru, .cn, .xyz = higher base risk)
    - Domain age heuristics (known vs unknown)
    - Connection density (too many or too few connections = flags)
    - Classification signals (government, security, finance = different profiles)
    - Aboyeur confidence (low confidence = higher risk)
    """

    station_id = "warden"
    name = "The Warden"
    handles_types = ['_risk_assessment']
    sla_seconds = 120
    is_primary = True

    # TLD risk tiers (0-30 base risk from TLD alone)
    TLD_RISK = {
        # Low risk — established, regulated
        '.gov': 5, '.mil': 5, '.edu': 8, '.int': 8,
        '.org': 12, '.com': 15, '.net': 15, '.co': 18,
        # Medium risk — regional, less regulated
        '.io': 20, '.ai': 18, '.dev': 15, '.app': 15,
        '.co.uk': 12, '.co.jp': 12, '.de': 12, '.fr': 12,
        # Higher risk — commonly abused TLDs
        '.xyz': 30, '.top': 30, '.tk': 35, '.ml': 35,
        '.ga': 35, '.cf': 35, '.buzz': 30, '.click': 28,
        '.ru': 25, '.cn': 22, '.su': 30,
    }

    # Classification risk modifiers
    CLASS_RISK = {
        'government': -10, 'education': -5, 'military': -10,
        'organization': -3, 'academic': -5,
        'cloud_infrastructure': 5, 'code_hosting': 0,
        'social_platform': 10, 'publishing_platform': 8,
        'package_registry': 3, 'developer_community': 0,
        'media_platform': 8, 'professional_network': 5,
        'tech_community': 3, 'knowledge_base': -3,
        'unknown': 15,
    }

    def run_risk_assessment(self) -> dict:
        """
        Score every entity in the pool.
        Returns assessment summary.
        """
        self.log("Running threat assessment across the Hoard...")

        entities = [dict(e) for e in self.pool.get_all_entities()]
        edges = [dict(e) for e in self.pool.get_all_edges()]

        # Build connection counts
        conn_count = defaultdict(int)
        for edge in edges:
            conn_count[edge['source']] += 1
            conn_count[edge['target']] += 1

        scores = []
        risk_distribution = defaultdict(int)
        high_risk = []
        critical = []

        for entity in entities:
            if entity['type'].startswith('_'):
                continue

            score = self._score_entity(entity, conn_count)
            scores.append(score)

            # Categorize
            risk_level = self._risk_level(score['total_risk'])
            risk_distribution[risk_level] += 1

            if score['total_risk'] >= 60:
                high_risk.append(score)
            if score['total_risk'] >= 80:
                critical.append(score)

        # Write high-risk findings
        for hr in critical[:20]:
            self.pool.add_finding(
                'warning', self.station_id,
                f"Critical risk ({hr['total_risk']}): {hr['entity'][:60]}",
                f"Factors: {', '.join(hr['factors'])}"
            )

        # Summary stats
        all_risks = [s['total_risk'] for s in scores]
        avg_risk = sum(all_risks) / max(len(all_risks), 1)
        median_risk = sorted(all_risks)[len(all_risks) // 2] if all_risks else 0

        self.log(f"  Assessed {len(scores)} entities")
        self.log(f"  Avg risk: {avg_risk:.1f} | Median: {median_risk}")
        self.log(f"  High risk: {len(high_risk)} | Critical: {len(critical)}")

        report = {
            'entities_assessed': len(scores),
            'average_risk': round(avg_risk, 1),
            'median_risk': median_risk,
            'distribution': dict(risk_distribution),
            'high_risk_count': len(high_risk),
            'critical_count': len(critical),
            'critical_entities': [{'entity': c['entity'], 'risk': c['total_risk'],
                                   'factors': c['factors']} for c in critical[:10]],
            'high_risk_entities': [{'entity': h['entity'], 'risk': h['total_risk']}
                                   for h in high_risk[:20]],
        }

        self.pool._log_event('risk_assessment', self.station_id,
                             f"Assessed {len(scores)} entities. "
                             f"Avg risk: {avg_risk:.1f}. "
                             f"Critical: {len(critical)}")

        return report

    def _score_entity(self, entity, conn_count) -> dict:
        """Calculate risk score for a single entity."""
        value = entity['value']
        risk = 0
        factors = []

        # 1. TLD base risk (0-35)
        tld_risk = 15  # default
        for tld, r in self.TLD_RISK.items():
            if value.endswith(tld):
                tld_risk = r
                break
        risk += tld_risk
        if tld_risk >= 25:
            factors.append(f'high_risk_tld({tld_risk})')

        # 2. Subdomain depth (deeper = more suspicious, 0-15)
        depth = len(value.split('.')) - 2
        depth_risk = min(depth * 5, 15)
        risk += depth_risk
        if depth_risk >= 10:
            factors.append(f'deep_subdomain(depth={depth})')

        # 3. Classification modifier (-10 to +15)
        notes = entity.get('notes', '') or ''
        cls = 'unknown'
        if 'Classification:' in notes:
            cls = notes.split('Classification:')[1].split('.')[0].strip()
        cls_risk = self.CLASS_RISK.get(cls, 10)
        risk += cls_risk
        if cls_risk >= 10:
            factors.append(f'unknown_classification')

        # 4. Connection density (0-15)
        connections = conn_count.get(value, 0)
        if connections == 0:
            # Isolated entity — no relationships mapped
            risk += 10
            factors.append('isolated_entity')
        elif connections > 50:
            # Extremely high connectivity — could be a hub or a collector
            risk += 5
            factors.append(f'high_connectivity({connections})')

        # 5. Confidence penalty (0-15)
        confidence = entity.get('confidence') or 0.5
        if confidence < 0.4:
            conf_risk = 15
            factors.append(f'low_confidence({confidence:.2f})')
        elif confidence < 0.6:
            conf_risk = 8
        else:
            conf_risk = 0
        risk += conf_risk

        # 6. Domain length heuristic (very long domains = suspicious, 0-10)
        if len(value) > 40:
            risk += 10
            factors.append(f'long_domain(len={len(value)})')
        elif len(value) > 30:
            risk += 5

        # Clamp to 0-100
        risk = max(0, min(100, risk))

        return {
            'entity': value,
            'entity_id': entity['id'],
            'total_risk': risk,
            'tld_risk': tld_risk,
            'factors': factors,
        }

    def _risk_level(self, score: int) -> str:
        if score >= 80:
            return 'critical'
        elif score >= 60:
            return 'high'
        elif score >= 40:
            return 'medium'
        elif score >= 20:
            return 'low'
        return 'minimal'

    def process(self, entity_id, entity_type, entity_value):
        report = self.run_risk_assessment()
        return {
            'entity_type': '_risk_assessment',
            'entity_value': 'threat_scoring',
            'relationships': [],
            'confidence': 1.0,
            'notes': f"Assessed {report['entities_assessed']} entities. "
                     f"Avg risk: {report['average_risk']}. "
                     f"Critical: {report['critical_count']}",
        }
