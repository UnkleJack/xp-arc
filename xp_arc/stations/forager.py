"""
The Forager — Garde Manger.

Raw intelligence acquisition. Seeds → DOM extraction → entity writes.
Fallback: passive pool reader, surfaces unhandled entities for human review.

Whitepaper Section 4.4, Station #1.
"""

import re
import urllib.request
from ..core.station import StationChef


class TheForager(StationChef):
    """
    Scrapes target URLs, extracts domains, writes new entities
    back to the pool. This is the Snowball's ignition switch.
    """

    station_id = "forager"
    name = "The Forager"
    handles_types = ['url']
    sla_seconds = 60

    def __init__(self, pool, max_domains_per_target: int = 5, timeout: int = 8):
        super().__init__(pool)
        self.max_domains_per_target = max_domains_per_target
        self.timeout = timeout

    def process(self, entity_id: int, entity_type: str, entity_value: str) -> dict:
        self.log(f"Foraging target DOM: {entity_value}")
        extracted_domains = []

        try:
            req = urllib.request.Request(
                entity_value,
                headers={'User-Agent': 'Mozilla/5.0 (XP-Arc Forager/0.2)'}
            )
            html = urllib.request.urlopen(req, timeout=self.timeout).read().decode('utf-8', errors='ignore')

            # Extract domains from links
            all_domains = set(re.findall(r'href="https?://([^/"\']+)', html))

            # Filter: external only, skip self-references
            source_domain = re.findall(r'https?://([^/]+)', entity_value)
            source_domain = source_domain[0] if source_domain else ""

            count = 0
            for d in all_domains:
                # Basic input sanitization (Whitepaper 5.5.2)
                if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$', d):
                    continue
                if d == source_domain or d.endswith(f".{source_domain}"):
                    continue
                if count >= self.max_domains_per_target:
                    break

                new_id = self.pool.add_entity('domain', d)
                if new_id:
                    self.pool.add_edge(entity_value, 'links_to', d)
                    self.log(f"  + Extracted domain: {d}")
                    extracted_domains.append(d)
                    count += 1

            # Extract page title
            title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
            title = title_match.group(1).strip()[:200] if title_match else "No title"

            self.log(f"  Foraged {len(extracted_domains)} domains from: {entity_value}")

            return {
                'entity_type': 'url',
                'entity_value': entity_value,
                'relationships': extracted_domains,
                'confidence': 0.85,
                'notes': f"Title: {title}. Extracted {len(extracted_domains)} external domains.",
            }

        except Exception as e:
            self.log(f"  Failed to forage {entity_value}: {e}")
            return {
                'entity_type': 'url',
                'entity_value': entity_value,
                'relationships': [],
                'confidence': 0.2,
                'notes': f"Forage failed: {str(e)}",
            }
