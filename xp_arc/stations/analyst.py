"""
The Analyst — Saucier.

Relationship inference. Builds edge graph from entity pool.
Examines domains and infers structural relationships.
Fallback: type-tagging only, no relationship inference.

Whitepaper Section 4.4, Station #2.
"""

import re
import urllib.request
from ..core.station import StationChef


class TheAnalyst(StationChef):
    """
    Processes domain entities: resolves basic metadata,
    infers relationships, and classifies domain types.
    """

    station_id = "analyst"
    name = "The Analyst"
    handles_types = ['domain']
    sla_seconds = 180

    # Known domain classifications
    CLASSIFICATIONS = {
        'github.com': 'code_hosting',
        'gitlab.com': 'code_hosting',
        'bitbucket.org': 'code_hosting',
        'stackoverflow.com': 'developer_community',
        'reddit.com': 'social_platform',
        'twitter.com': 'social_platform',
        'x.com': 'social_platform',
        'youtube.com': 'media_platform',
        'www.youtube.com': 'media_platform',
        'linkedin.com': 'professional_network',
        'medium.com': 'publishing_platform',
        'wikipedia.org': 'knowledge_base',
        'arxiv.org': 'academic',
        'news.ycombinator.com': 'tech_community',
        'lobste.rs': 'tech_community',
        'npmjs.com': 'package_registry',
        'pypi.org': 'package_registry',
        'aws.amazon.com': 'cloud_infrastructure',
        'cloud.google.com': 'cloud_infrastructure',
        'azure.microsoft.com': 'cloud_infrastructure',
    }

    def process(self, entity_id: int, entity_type: str, entity_value: str) -> dict:
        self.log(f"Analyzing domain: {entity_value}")

        classification = self._classify_domain(entity_value)
        relationships = []

        # Check for subdomain relationships
        parts = entity_value.split('.')
        if len(parts) > 2:
            parent_domain = '.'.join(parts[-2:])
            if parent_domain != entity_value:
                existing = self.pool.add_entity('domain', parent_domain)
                if existing:
                    self.pool.add_edge(entity_value, 'subdomain_of', parent_domain)
                    relationships.append(parent_domain)
                    self.log(f"  + Subdomain relationship: {entity_value} → {parent_domain}")

        # Attempt lightweight HTTP probe for additional intelligence
        probe_result = self._probe_domain(entity_value)

        confidence = 0.7 if classification != 'unknown' else 0.5
        if probe_result.get('reachable'):
            confidence += 0.15

        notes_parts = [f"Classification: {classification}"]
        if probe_result.get('redirect'):
            notes_parts.append(f"Redirects to: {probe_result['redirect']}")
        if probe_result.get('server'):
            notes_parts.append(f"Server: {probe_result['server']}")
        notes_parts.append(f"Reachable: {probe_result.get('reachable', False)}")

        return {
            'entity_type': 'domain',
            'entity_value': entity_value,
            'relationships': relationships,
            'confidence': min(confidence, 1.0),
            'notes': '. '.join(notes_parts),
        }

    def _classify_domain(self, domain: str) -> str:
        """Classify domain by known patterns."""
        # Exact match
        if domain in self.CLASSIFICATIONS:
            return self.CLASSIFICATIONS[domain]

        # Check if it's a subdomain of a known domain
        for known, classification in self.CLASSIFICATIONS.items():
            if domain.endswith(f".{known}"):
                return classification

        # TLD-based heuristics
        if domain.endswith('.gov'):
            return 'government'
        if domain.endswith('.edu'):
            return 'education'
        if domain.endswith('.mil'):
            return 'military'
        if domain.endswith('.org'):
            return 'organization'

        return 'unknown'

    def _probe_domain(self, domain: str) -> dict:
        """Lightweight HTTP probe. No deep scraping."""
        result = {'reachable': False, 'redirect': None, 'server': None}
        try:
            req = urllib.request.Request(
                f"https://{domain}",
                method='HEAD',
                headers={'User-Agent': 'Mozilla/5.0 (XP-Arc Analyst/0.2)'}
            )
            resp = urllib.request.urlopen(req, timeout=4)
            result['reachable'] = True
            result['server'] = resp.headers.get('Server', 'unknown')
            if resp.url != f"https://{domain}" and resp.url != f"https://{domain}/":
                result['redirect'] = resp.url
        except Exception:
            # Try HTTP as fallback
            try:
                req = urllib.request.Request(
                    f"http://{domain}",
                    method='HEAD',
                    headers={'User-Agent': 'Mozilla/5.0 (XP-Arc Analyst/0.2)'}
                )
                resp = urllib.request.urlopen(req, timeout=3)
                result['reachable'] = True
                result['server'] = resp.headers.get('Server', 'unknown')
            except Exception:
                pass
        return result
