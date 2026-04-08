"""
The Sentinel — Poissonnier.

Anomaly detection. Monitors pool for unexpected patterns,
high-cardinality floods, status transition anomalies.
Fallback: alert-only mode.

Whitepaper Section 4.4, Station #5.
"""

from ..core.station import StationChef


class TheSentinel(StationChef):
    """
    Watches for anomalies. Does not process entities in the
    traditional sense — instead monitors pool health and writes
    findings.

    The Sentinel is a passive observer that becomes active
    when called by the Executive for pool health checks.
    """

    station_id = "sentinel"
    name = "The Sentinel"
    handles_types = ['_sentinel_check']  # Internal type, not from scraping
    sla_seconds = 30

    # Thresholds
    MAX_ENTITIES_WARNING = 400
    MAX_ENTITIES_CRITICAL = 480
    ORPHAN_THRESHOLD_SECONDS = 300
    HIGH_FAILURE_RATE = 0.3

    def __init__(self, pool):
        super().__init__(pool)
        self._checks_run = 0
        self._anomalies_found = 0

    def run_health_check(self) -> list:
        """
        Run all anomaly detection checks against current pool state.
        Returns list of findings.
        """
        self._checks_run += 1
        findings = []

        findings.extend(self._check_entity_flood())
        findings.extend(self._check_orphaned_entities())
        findings.extend(self._check_failure_rate())
        findings.extend(self._check_status_anomalies())

        self._anomalies_found += len(findings)

        for f in findings:
            self.pool.add_finding(f['severity'], self.station_id, f['message'], f.get('detail'))

        if findings:
            self.log(f"Health check: {len(findings)} anomalies detected")
        else:
            self.log("Health check: All clear")

        return findings

    def _check_entity_flood(self) -> list:
        """Detect Snowball DoS — too many entities."""
        findings = []
        count = self.pool.count_entities()

        if count >= self.MAX_ENTITIES_CRITICAL:
            findings.append({
                'severity': 'critical',
                'message': f"Entity flood: {count} entities (critical threshold: {self.MAX_ENTITIES_CRITICAL})",
                'detail': "Snowball may be unconstrained. Consider halting ingestion.",
            })
        elif count >= self.MAX_ENTITIES_WARNING:
            findings.append({
                'severity': 'warning',
                'message': f"Entity count high: {count} (warning threshold: {self.MAX_ENTITIES_WARNING})",
                'detail': "Approaching max_entities limit.",
            })

        return findings

    def _check_orphaned_entities(self) -> list:
        """Detect entities stuck in processing beyond SLA."""
        findings = []
        orphans = self.pool.get_orphaned_entities(self.ORPHAN_THRESHOLD_SECONDS)

        if orphans:
            for o in orphans:
                findings.append({
                    'severity': 'warning',
                    'message': f"Orphaned entity: {o['type']}:{o['value']} stuck in processing",
                    'detail': f"Station: {o['station']}, assigned_at: {o['assigned_at']}",
                })

        return findings

    def _check_failure_rate(self) -> list:
        """Detect high failure rates across the pipeline."""
        findings = []
        stats = self.pool.get_stats()

        total = sum(s['count'] for s in stats.values())
        failed = stats.get('failed', {}).get('count', 0)

        if total > 0:
            rate = failed / total
            if rate > self.HIGH_FAILURE_RATE:
                findings.append({
                    'severity': 'warning',
                    'message': f"High failure rate: {rate:.1%} ({failed}/{total} entities failed)",
                    'detail': "Check station health and input quality.",
                })

        return findings

    def _check_status_anomalies(self) -> list:
        """Check for entities in unexpected states."""
        findings = []

        # Entities stuck in pending_qa (should resolve quickly)
        pending_qa = self.pool.get_entities_by_status('pending_qa')
        if len(pending_qa) > 5:
            findings.append({
                'severity': 'warning',
                'message': f"{len(pending_qa)} entities stuck in pending_qa",
                'detail': "Aboyeur may be bottlenecked.",
            })

        return findings

    def process(self, entity_id: int, entity_type: str, entity_value: str) -> dict:
        """Internal process — triggers health check."""
        results = self.run_health_check()
        return {
            'entity_type': '_sentinel_check',
            'entity_value': 'health_check',
            'relationships': [],
            'confidence': 1.0,
            'notes': f"Found {len(results)} anomalies",
        }
