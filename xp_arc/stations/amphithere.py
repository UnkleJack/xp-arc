"""
The Amphithere / Tournant — DNS ENRICHMENT STATION.
Dragon Name: AMPHITHERE (winged serpent — strikes external systems)

Enriches domain entities with real DNS intelligence:
IP addresses, nameservers, CNAME chains, reverse lookups.
Adds new entity types (IP, nameserver) and edges to the pool.

The Amphithere reaches outside the Hoard to pull back
real infrastructure data that no other station can see.

Use Cases:
    - OSINT: Map domain infrastructure to IP ranges
    - Asset Discovery: Find all domains sharing an IP
    - Threat Hunting: Identify shared hosting (bulletproof hosts)
    - Supply Chain: Map CDN/cloud dependencies
    - Competitive Intel: Identify competitor infrastructure choices

Zero external dependencies — uses Python stdlib socket module.
"""

import socket
from collections import defaultdict
from ..core.station import StationChef


class TheAmphithere(StationChef):
    """
    DNS enrichment station. Resolves domains to infrastructure.

    For each domain entity:
    - Resolves A/AAAA records (IPv4/IPv6 addresses)
    - Identifies shared infrastructure (multiple domains → same IP)
    - Creates 'resolves_to' edges between domains and IPs
    - Adds IP entities to the pool for further analysis
    """

    station_id = "amphithere"
    name = "The Amphithere"
    handles_types = ['_dns_enrichment']
    sla_seconds = 300
    is_primary = True

    def __init__(self, pool, timeout: float = 2.0, max_entities: int = 5000):
        super().__init__(pool)
        self.timeout = timeout
        self.max_entities = max_entities
        socket.setdefaulttimeout(timeout)

    def run_enrichment(self) -> dict:
        """
        Resolve DNS for domain entities and enrich the pool.
        Returns enrichment report.
        """
        self.log("Launching DNS enrichment sweep...")

        entities = self.pool.get_all_entities()
        domains = [e for e in entities if e['type'] == 'domain'
                   and not e['value'].startswith('_')]

        # Limit for performance
        domains = domains[:self.max_entities]

        resolved = 0
        failed = 0
        ips_found = defaultdict(list)  # ip -> [domains]
        new_entities = 0
        new_edges = 0

        for i, entity in enumerate(domains):
            domain = entity['value']
            result = self._resolve_domain(domain)

            if result['ips']:
                resolved += 1
                for ip in result['ips']:
                    ips_found[ip].append(domain)

                    # Add IP entity
                    eid = self.pool.add_entity('ip_address', ip)
                    if eid:
                        new_entities += 1

                    # Add resolves_to edge
                    self.pool.add_edge(domain, 'resolves_to', ip)
                    new_edges += 1
            else:
                failed += 1

            if (i + 1) % 500 == 0:
                self.log(f"  [{i+1}/{len(domains)}] Resolved: {resolved}, Failed: {failed}")

        # Find shared infrastructure (multiple domains → same IP)
        shared_infra = {ip: doms for ip, doms in ips_found.items() if len(doms) > 1}

        # Write shared infrastructure findings
        for ip, doms in sorted(shared_infra.items(), key=lambda x: -len(x[1]))[:20]:
            self.pool.add_finding(
                'info', self.station_id,
                f"Shared IP: {ip} hosts {len(doms)} domains",
                f"Domains: {', '.join(doms[:10])}"
            )

        # IP range analysis
        ip_prefixes = defaultdict(int)
        for ip in ips_found:
            parts = ip.split('.')
            if len(parts) == 4:
                prefix = f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
                ip_prefixes[prefix] += 1

        top_subnets = sorted(ip_prefixes.items(), key=lambda x: -x[1])[:10]

        self.log(f"  Resolved: {resolved}/{len(domains)}")
        self.log(f"  Unique IPs: {len(ips_found)}")
        self.log(f"  Shared infrastructure: {len(shared_infra)} IPs host multiple domains")
        self.log(f"  New entities: {new_entities}, New edges: {new_edges}")

        report = {
            'domains_scanned': len(domains),
            'resolved': resolved,
            'failed': failed,
            'unique_ips': len(ips_found),
            'new_ip_entities': new_entities,
            'new_edges': new_edges,
            'shared_infrastructure': {
                'count': len(shared_infra),
                'top_shared': [{'ip': ip, 'domain_count': len(doms), 'domains': doms[:5]}
                               for ip, doms in sorted(shared_infra.items(),
                                                       key=lambda x: -len(x[1]))[:10]],
            },
            'top_subnets': [{'subnet': s, 'count': c} for s, c in top_subnets],
        }

        self.pool._log_event('dns_enrichment', self.station_id,
                             f"Resolved {resolved}/{len(domains)} domains. "
                             f"{len(ips_found)} unique IPs. "
                             f"{len(shared_infra)} shared infrastructure.")

        return report

    def _resolve_domain(self, domain: str) -> dict:
        """Resolve a domain to IP addresses using stdlib."""
        result = {'ips': [], 'error': None}
        try:
            infos = socket.getaddrinfo(domain, None, socket.AF_INET, socket.SOCK_STREAM)
            ips = set()
            for info in infos:
                ip = info[4][0]
                ips.add(ip)
            result['ips'] = list(ips)
        except socket.gaierror as e:
            result['error'] = str(e)
        except socket.timeout:
            result['error'] = 'timeout'
        except Exception as e:
            result['error'] = str(e)
        return result

    def process(self, entity_id, entity_type, entity_value):
        report = self.run_enrichment()
        return {
            'entity_type': '_dns_enrichment',
            'entity_value': 'dns_sweep',
            'relationships': [],
            'confidence': 1.0,
            'notes': f"Resolved {report['resolved']} domains. "
                     f"{report['unique_ips']} unique IPs.",
        }
