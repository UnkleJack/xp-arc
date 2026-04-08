"""
The Librarian — Patissier.

Dossier generation. Groups completed entities by seed origin,
synthesizes intelligence reports, identifies gaps, and writes
structured dossiers back to the pool.

The Librarian doesn't discover new entities. It reads what
the brigade already found and tells you what it means.
"""

import json
from ..core.station import StationChef


class TheLibrarian(StationChef):
    """
    Generates intelligence dossiers from completed entities.

    For each seed URL, the Librarian:
    - Gathers all entities connected by edges
    - Classifies the seed's ecosystem (tech stack, affiliations, geography)
    - Identifies intelligence gaps (unresolved domains, low-confidence entities)
    - Writes a structured dossier as a new entity
    """

    station_id = "librarian"
    name = "The Librarian"
    handles_types = ['_dossier_request']
    sla_seconds = 120
    is_primary = True

    def generate_dossiers(self) -> list:
        """
        Generate dossiers for all seed URLs.
        Returns list of dossier dicts.
        """
        self.log("Compiling intelligence dossiers...")
        dossiers = []

        entities = self.pool.get_all_entities()
        edges = self.pool.get_all_edges()

        # Index entities by value for fast lookup (convert Row to dict)
        entity_index = {e['value']: dict(e) for e in entities}
        entities = [dict(e) for e in entities]

        # Build adjacency lists from edges
        outgoing = {}  # source -> [(rel, target), ...]
        incoming = {}  # target -> [(rel, source), ...]
        for edge in edges:
            src, rel, tgt = edge['source'], edge['relationship'], edge['target']
            outgoing.setdefault(src, []).append((rel, tgt))
            incoming.setdefault(tgt, []).append((rel, src))

        # Find seed URLs (type='url')
        seeds = [e for e in entities if e['type'] == 'url']

        for seed in seeds:
            seed_value = seed['value']
            dossier = self._build_dossier(seed, entity_index, outgoing, incoming, entities)
            dossiers.append(dossier)

            # Write dossier as entity
            dossier_json = json.dumps(dossier, default=str)
            eid = self.pool.add_entity(
                '_dossier',
                f"dossier:{seed_value}",
                sla_seconds=120,
            )
            if eid:
                self.pool.transition_status(eid, 'processing', station=self.station_id)
                self.pool.transition_status(eid, 'pending_qa')
                self.pool.transition_status(eid, 'completed',
                                            station=self.station_id,
                                            confidence=dossier['confidence'],
                                            notes=dossier_json[:500])
                self.pool.add_edge(seed_value, 'has_dossier', f"dossier:{seed_value}")

        self.log(f"Generated {len(dossiers)} dossiers")
        return dossiers

    def _build_dossier(self, seed, entity_index, outgoing, incoming, all_entities) -> dict:
        """Build a structured dossier for a single seed."""
        seed_value = seed['value']

        # Get directly connected entities
        direct_connections = outgoing.get(seed_value, [])
        connected_domains = []
        for rel, target in direct_connections:
            ent = entity_index.get(target, {})
            connected_domains.append({
                'value': target,
                'relationship': rel,
                'type': ent.get('type', 'unknown'),
                'confidence': ent.get('confidence', 0),
                'classification': self._extract_classification(ent.get('notes', '')),
                'station': ent.get('station', 'unknown'),
            })

        # Get 2nd-degree connections
        second_degree = []
        seen = {seed_value}
        for _, first_hop in direct_connections:
            seen.add(first_hop)
            for rel2, second_hop in outgoing.get(first_hop, []):
                if second_hop not in seen:
                    seen.add(second_hop)
                    ent2 = entity_index.get(second_hop, {})
                    second_degree.append({
                        'value': second_hop,
                        'path': f"{seed_value} -> {first_hop} -> {second_hop}",
                        'relationship_chain': f"links_to -> {rel2}",
                        'type': ent2.get('type', 'unknown'),
                    })

        # Classify the ecosystem
        classifications = {}
        for conn in connected_domains:
            cls = conn.get('classification', 'unknown')
            classifications[cls] = classifications.get(cls, 0) + 1

        # Identify gaps
        low_confidence = [c for c in connected_domains if c['confidence'] < 0.5]
        unsigned = [dict(e) for e in all_entities
                    if e['value'] in [c['value'] for c in connected_domains]
                    and not e['aboyeur_signature']]

        # Calculate dossier confidence
        if connected_domains:
            avg_conf = sum(c['confidence'] for c in connected_domains) / len(connected_domains)
        else:
            avg_conf = 0.0

        return {
            'seed_url': seed_value,
            'seed_status': seed['status'],
            'seed_notes': seed.get('notes', ''),
            'direct_connections': len(connected_domains),
            'second_degree_connections': len(second_degree),
            'total_reach': len(connected_domains) + len(second_degree),
            'ecosystem_breakdown': classifications,
            'top_connections': connected_domains[:10],
            'hidden_connections': second_degree[:10],
            'intelligence_gaps': {
                'low_confidence_count': len(low_confidence),
                'unsigned_count': len(unsigned),
                'low_confidence_entities': [c['value'] for c in low_confidence[:5]],
            },
            'confidence': round(avg_conf, 3),
        }

    def _extract_classification(self, notes: str) -> str:
        """Extract classification from analyst notes."""
        if 'Classification:' in notes:
            parts = notes.split('Classification:')
            if len(parts) > 1:
                cls = parts[1].split('.')[0].strip()
                return cls
        return 'unclassified'

    def process(self, entity_id, entity_type, entity_value):
        dossiers = self.generate_dossiers()
        return {
            'entity_type': '_dossier_request',
            'entity_value': 'dossier_generation',
            'relationships': [],
            'confidence': 1.0,
            'notes': f"Generated {len(dossiers)} dossiers",
        }
