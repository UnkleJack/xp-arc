"""
The Dossier Station — Garde Manger.

The final assembly node. Aggregates all intelligence from the Pool
into a unified, multi-point OSINT Dossier. 

Triggered for 'dossier' entity types.
"""

from datetime import datetime, timezone
import json
from ..core.station import StationChef


class TheDossier(StationChef):
    """
    Orchestrates the synthesis of individual entities into a 
    structured intelligence report.
    """

    station_id = "dossier"
    name = "The Dossier"
    handles_types = ['dossier_request']
    sla_seconds = 300

    def process(self, entity_id: int, entity_type: str, entity_value: str) -> dict:
        """
        Processes a dossier request by gathering all connected entities.
        """
        self.log(f"Assembling dossier for target: {entity_value}")
        
        # 1. Gather all related entities from the pool
        # This implementation looks for everything connected to the target value
        target = entity_value
        related_entities = self._gather_intelligence(target)
        
        # 2. Format the Dossier
        dossier_md = self._generate_markdown(target, related_entities)
        
        # 3. Write finding
        self.pool.add_finding(
            'info', self.station_id,
            f"Dossier Complete: {target}",
            dossier_md[:500] + "..."
        )

        # 4. Write dossier_report back to the pool (Article III shared state)
        report_value = f"REPORT-{target}"
        eid = self.writer.add_entity(
            'dossier_report',
            report_value,
            sla_seconds=300,
        )
        if eid:
            self.writer.transition_status(eid, 'processing', station=self.station_id)
            qa_result = self.submit_for_qa(eid, {
                'entity_type': 'dossier_report',
                'entity_value': report_value,
                'relationships': [target],
                'confidence': 1.0,
                'notes': dossier_md,
            })
            if qa_result['approved']:
                self.writer.add_edge(target, 'has_dossier', report_value)

        return {
            'entity_type': 'dossier_report',
            'entity_value': report_value,
            'relationships': [target],
            'confidence': 1.0,
            'notes': dossier_md,
        }

    def _gather_intelligence(self, target: str) -> dict:
        """Query the pool for all data points related to the target."""
        intelligence = {
            'target': target,
            'identities': [],
            'infrastructure': [],
            'presence': [],
            'risk_factors': [],
            'audit_trail': []
        }
        
        # Get edges related to target
        edges = self.pool.get_all_edges()
        connected_values = set()
        for edge in edges:
            if edge['source'] == target:
                connected_values.add(edge['target'])
            elif edge['target'] == target:
                connected_values.add(edge['source'])
        
        # Get actual entity details for connected values
        all_entities = self.pool.get_all_entities()
        for ent in all_entities:
            # Skip the request itself and uncompleted/raw entities
            if ent['type'] in ('dossier_request', 'dossier_report'):
                continue
            if ent['value'] in connected_values or ent['value'] == target:
                data_point = {
                    'type': ent['type'],
                    'value': ent['value'],
                    'notes': ent['notes'],
                    'confidence': ent['confidence'],
                    'station': ent['station'],
                    'signature': ent['aboyeur_signature']
                }
                
                # Sort into categories based on station/type
                if ent['type'] == 'domain':
                    intelligence['infrastructure'].append(data_point)
                elif ent['station'] in ('hydra', 'cartographer'):
                    intelligence['presence'].append(data_point)
                elif ent['station'] == 'warden':
                    intelligence['risk_factors'].append(data_point)
                else:
                    intelligence['identities'].append(data_point)
                
                # Audit trail only records completed work by valid stations
                if ent['status'] == 'completed' and ent['station'] and ent['station'] != 'none':
                    intelligence['audit_trail'].append({
                        'station': ent['station'],
                        'signature': ent['aboyeur_signature'],
                        'timestamp': ent['completed_at']
                    })
                
        return intelligence

    def _generate_markdown(self, target: str, intel: dict) -> str:
        """Synthesize data into a professional OSINT dossier."""
        lines = [
            f"# OSINT INTELLIGENCE DOSSIER: {target}",
            f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "---",
            "## 1. Executive Summary",
            f"Comprehensive intelligence gathering completed for target `{target}`.",
            f"Total data points captured: {len(intel['audit_trail'])}",
            ""
        ]
        
        if intel['infrastructure']:
            lines.append("## 2. Infrastructure & Technical Footprint")
            for item in intel['infrastructure']:
                lines.append(f"- **{item['value']}** ({item['type']})")
                if item['notes']:
                    lines.append(f"  - *Notes:* {item['notes']}")
            lines.append("")

        if intel['presence']:
            lines.append("## 3. Digital Presence & Social Mapping")
            for item in intel['presence']:
                lines.append(f"- **{item['value']}**")
                lines.append(f"  - *Source:* {item['station']}")
            lines.append("")

        if intel['risk_factors']:
            lines.append("## 4. Risk Assessment & Legal Flags")
            for item in intel['risk_factors']:
                lines.append(f"### [!] RISK: {item['value']}")
                lines.append(f"- {item['notes']}")
            lines.append("")

        lines.append("## 5. Constitutional Audit Trail")
        lines.append("| Station | Completed At | Aboyeur Signature |")
        lines.append("| :--- | :--- | :--- |")
        for log in intel['audit_trail']:
            lines.append(f"| {log['station']} | {log['timestamp']} | `{log['signature']}` |")
        
        lines.append("\n---")
        lines.append("*End of Dossier - XP ARC Protocol v1.4*")
        
        return "\n".join(lines)
