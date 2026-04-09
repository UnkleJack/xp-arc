"""
The Herald / Aboyeur de Salle — ALERT & NOTIFICATION ENGINE.
Dragon Name: HERALD (the dragon's roar — announces what matters)

Configurable alert rules that fire when pool state matches
conditions. The Herald watches the Hoard and roars when
something demands attention.

Rules are defined as simple Python-evaluable conditions
against pool state. When a rule triggers, the Herald
writes an alert to findings and can be wired to external
notification systems (Telegram, webhooks, etc).

Use Cases:
    - Real-Time Monitoring: Alert when new entity types appear
    - Compliance: Alert when .gov domains are found in the pool
    - Security: Alert when risk scores exceed thresholds
    - Operations: Alert when Zoran S drops below threshold
    - Business: Alert when entity count hits milestones

Constitution: Independent monitoring authority.
"""

from datetime import datetime, timezone
from ..core.station import StationChef


class TheHerald(StationChef):
    """
    Alert and notification engine.

    Evaluates configurable rules against pool state
    and fires alerts when conditions are met.
    """

    station_id = "herald"
    name = "The Herald"
    handles_types = ['_alert_check']
    sla_seconds = 30
    is_primary = True

    def __init__(self, pool, rules: list = None):
        super().__init__(pool)
        self._alerts_fired = 0
        self._checks_run = 0
        self.rules = rules or self._default_rules()
        self._triggered_rules = set()  # Avoid repeated alerts

    def _default_rules(self) -> list:
        """Default alert rules for XP-Arc monitoring."""
        return [
            {
                'id': 'entity_milestone_1k',
                'name': 'Entity Milestone (1K)',
                'description': 'Entity count crossed 1,000',
                'severity': 'info',
                'check': lambda stats, pool: stats.get('completed', {}).get('count', 0) >= 1000,
            },
            {
                'id': 'entity_milestone_10k',
                'name': 'Entity Milestone (10K)',
                'description': 'Entity count crossed 10,000',
                'severity': 'info',
                'check': lambda stats, pool: stats.get('completed', {}).get('count', 0) >= 10000,
            },
            {
                'id': 'entity_milestone_30k',
                'name': 'Entity Milestone (30K)',
                'description': 'Entity count crossed 30,000',
                'severity': 'info',
                'check': lambda stats, pool: stats.get('completed', {}).get('count', 0) >= 30000,
            },
            {
                'id': 'high_failure_rate',
                'name': 'High Failure Rate',
                'description': 'More than 5% of entities failed processing',
                'severity': 'critical',
                'check': lambda stats, pool: (
                    stats.get('failed', {}).get('count', 0) /
                    max(sum(v.get('count', 0) for v in stats.values()), 1)
                ) > 0.05,
            },
            {
                'id': 'gov_domains_detected',
                'name': 'Government Domains Detected',
                'description': 'Government (.gov) domains found in the Hoard',
                'severity': 'info',
                'check': lambda stats, pool: any(
                    e['value'].endswith('.gov')
                    for e in pool.get_entities_by_status('completed')[:1000]
                ),
            },
            {
                'id': 'edu_domains_detected',
                'name': 'Education Domains Detected',
                'description': 'Education (.edu) domains found in the Hoard',
                'severity': 'info',
                'check': lambda stats, pool: any(
                    e['value'].endswith('.edu')
                    for e in pool.get_entities_by_status('completed')[:1000]
                ),
            },
            {
                'id': 'raw_backlog',
                'name': 'Raw Entity Backlog',
                'description': 'More than 1,000 raw entities waiting to be processed',
                'severity': 'warning',
                'check': lambda stats, pool: stats.get('raw', {}).get('count', 0) > 1000,
            },
            {
                'id': 'zero_failures',
                'name': 'Perfect Run',
                'description': 'Zero failures across all processing',
                'severity': 'info',
                'check': lambda stats, pool: (
                    stats.get('failed', {}).get('count', 0) == 0 and
                    stats.get('completed', {}).get('count', 0) > 100
                ),
            },
            {
                'id': 'large_cluster_detected',
                'name': 'Large Cluster Detected',
                'description': 'A cluster with 100+ connected entities exists',
                'severity': 'info',
                'check': lambda stats, pool: len(pool.get_all_edges()) > 100,
            },
        ]

    def run_alert_check(self) -> dict:
        """
        Evaluate all rules against current pool state.
        Returns alert report.
        """
        self._checks_run += 1
        self.log(f"Alert check #{self._checks_run} — evaluating {len(self.rules)} rules...")

        stats = self.pool.get_stats()
        alerts_fired = []

        for rule in self.rules:
            rule_id = rule['id']

            # Skip already-triggered one-time alerts
            if rule_id in self._triggered_rules:
                continue

            try:
                triggered = rule['check'](stats, self.pool)
            except Exception as e:
                self.log(f"  Rule '{rule_id}' error: {e}")
                continue

            if triggered:
                self._triggered_rules.add(rule_id)
                self._alerts_fired += 1

                alert = {
                    'rule_id': rule_id,
                    'name': rule['name'],
                    'description': rule['description'],
                    'severity': rule['severity'],
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                }
                alerts_fired.append(alert)

                # Write to findings
                self.pool.add_finding(
                    rule['severity'], self.station_id,
                    f"ALERT: {rule['name']} — {rule['description']}",
                    f"Rule: {rule_id}"
                )

                self.log(f"  [{rule['severity'].upper()}] {rule['name']}")

        if not alerts_fired:
            self.log("  No new alerts triggered.")

        report = {
            'check_number': self._checks_run,
            'rules_evaluated': len(self.rules),
            'alerts_fired': len(alerts_fired),
            'total_alerts_lifetime': self._alerts_fired,
            'alerts': alerts_fired,
            'active_triggers': list(self._triggered_rules),
        }

        if alerts_fired:
            self.pool._log_event('herald_alert', self.station_id,
                                 f"Check #{self._checks_run}: {len(alerts_fired)} alerts fired. "
                                 f"{', '.join(a['name'] for a in alerts_fired)}")

        return report

    def add_rule(self, rule_id: str, name: str, description: str,
                 severity: str, check_fn):
        """Add a custom alert rule at runtime."""
        self.rules.append({
            'id': rule_id,
            'name': name,
            'description': description,
            'severity': severity,
            'check': check_fn,
        })

    def process(self, entity_id, entity_type, entity_value):
        report = self.run_alert_check()
        return {
            'entity_type': '_alert_check',
            'entity_value': 'alert_check',
            'relationships': [],
            'confidence': 1.0,
            'notes': f"Check #{report['check_number']}: "
                     f"{report['alerts_fired']} alerts fired.",
        }
