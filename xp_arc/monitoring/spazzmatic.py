"""
SpaZzMatiC — Adversarial Review Authority.

Cold-eyes QA with no architectural bias toward XP-Arc.
SpaZzMatiC does not build. SpaZzMatiC breaks.

Rule-based adversarial monitor. No LLM dependency.
Deterministic. Verifiable. Traceable.

Constitution Article XIV.
"""


class SpaZzMatiC:
    """
    Independent adversarial review engine.

    Monitors:
    - Zoran's Law violations
    - Aboyeur rejection rate anomalies
    - Orphaned entities (stuck in processing)
    - Status transition violations (from event log)
    - Entity flood / Snowball runaway
    - Safe halt conditions

    Issues findings with severity classifications.
    Can recommend safe halt (60-second veto countdown).
    """

    # Constitutional thresholds
    SAFE_HALT_S_THRESHOLD = 0.5           # S < 0.5 sustained
    SAFE_HALT_SUSTAIN_COUNT = 2           # Must be violated for 2+ measurements
    ABOYEUR_REJECTION_ALARM = 0.10        # >10% rejection rate
    ROUTING_FAILURE_ALARM = 0.05          # >5% routing failures
    ENTITY_FLOOD_THRESHOLD = 450
    ORPHAN_ALARM_COUNT = 3                # 3+ orphans = concern

    def __init__(self, pool, zorans_law):
        self.pool = pool
        self.zorans_law = zorans_law
        self._reviews = 0
        self._safe_halt_recommended = False
        self._s_violation_streak = 0

    def run_review(self) -> dict:
        """
        Execute full adversarial review pass.

        Returns:
        {
            'findings': list of findings,
            'safe_halt_recommended': bool,
            'summary': str,
        }
        """
        self._reviews += 1
        findings = []

        findings.extend(self._review_zorans_law())
        findings.extend(self._review_aboyeur_health())
        findings.extend(self._review_pool_integrity())
        findings.extend(self._review_entity_flood())
        findings.extend(self._review_orphans())

        # Write findings to pool
        for f in findings:
            self.pool.add_finding(f['severity'], 'spazzmatic', f['message'], f.get('detail'))

        # Log the review
        self.pool._log_event('spazzmatic_review', 'spazzmatic',
                             f"Review #{self._reviews}: {len(findings)} findings. "
                             f"Safe halt: {self._safe_halt_recommended}")

        severity_counts = {}
        for f in findings:
            severity_counts[f['severity']] = severity_counts.get(f['severity'], 0) + 1

        summary_parts = [f"Review #{self._reviews}"]
        if not findings:
            summary_parts.append("No anomalies detected.")
        else:
            for sev, cnt in sorted(severity_counts.items()):
                summary_parts.append(f"{cnt} {sev}")

        return {
            'findings': findings,
            'safe_halt_recommended': self._safe_halt_recommended,
            'summary': ". ".join(summary_parts),
        }

    def _review_zorans_law(self) -> list:
        """Check Zoran's Law compliance."""
        findings = []
        measurement = self.zorans_law.get_latest()
        if not measurement:
            return findings

        s = measurement['stability_quotient']
        pro = measurement['primary_role_occupancy']

        # S < 0.5 sustained = safe halt candidate
        if s < self.SAFE_HALT_S_THRESHOLD:
            self._s_violation_streak += 1
            if self._s_violation_streak >= self.SAFE_HALT_SUSTAIN_COUNT:
                self._safe_halt_recommended = True
                findings.append({
                    'severity': 'critical',
                    'message': f"SAFE HALT RECOMMENDED: S={s:.3f} sustained below "
                               f"{self.SAFE_HALT_S_THRESHOLD} for "
                               f"{self._s_violation_streak} measurements",
                    'detail': "60-second veto window active. System should halt ingestion.",
                })
            else:
                findings.append({
                    'severity': 'warning',
                    'message': f"S={s:.3f} below distress threshold. "
                               f"Streak: {self._s_violation_streak}/{self.SAFE_HALT_SUSTAIN_COUNT}",
                })
        else:
            self._s_violation_streak = 0
            self._safe_halt_recommended = False

        # S < 1.0 = debt accumulating
        if 0.5 <= s < 1.0:
            findings.append({
                'severity': 'warning',
                'message': f"Cognitive debt accumulating: S={s:.3f}",
                'detail': "System correction rate not keeping pace with ingestion.",
            })

        # PRO check
        if pro < 0.70:
            findings.append({
                'severity': 'warning',
                'message': f"PRO={pro:.1%} below 70% threshold. Compression review needed.",
                'detail': f"Active: {measurement['active_stations']}, "
                          f"Primary: {measurement['primary_stations']}",
            })

        return findings

    def _review_aboyeur_health(self) -> list:
        """Check Aboyeur rejection rates."""
        findings = []

        # Get recent events to calculate rejection rate
        events = self.pool.get_events(100)
        rejections = sum(1 for e in events if e['event_type'] == 'aboyeur_rejection')
        approvals = sum(1 for e in events if e['event_type'] == 'aboyeur_approval')

        total = rejections + approvals
        if total > 0:
            rejection_rate = rejections / total
            if rejection_rate > self.ABOYEUR_REJECTION_ALARM:
                findings.append({
                    'severity': 'warning',
                    'message': f"Aboyeur rejection rate: {rejection_rate:.1%} "
                               f"(threshold: {self.ABOYEUR_REJECTION_ALARM:.0%})",
                    'detail': f"{rejections} rejections / {total} total verifications",
                })

        # Check for circuit breaker events
        circuit_breaks = sum(1 for e in events if e['event_type'] == 'aboyeur_circuit_break')
        if circuit_breaks > 0:
            findings.append({
                'severity': 'critical',
                'message': f"{circuit_breaks} Aboyeur circuit breaker(s) tripped",
                'detail': "Tasks have hit max_rejections. Chef de Cuisine escalation required.",
            })

        return findings

    def _review_pool_integrity(self) -> list:
        """Check for status transition violations in event log."""
        findings = []

        events = self.pool.get_events(200)
        violations = [e for e in events if e['event_type'] == 'status_violation']

        if violations:
            findings.append({
                'severity': 'critical',
                'message': f"{len(violations)} unauthorized status transitions detected",
                'detail': "; ".join(v['message'] for v in violations[:5]),
            })

        return findings

    def _review_entity_flood(self) -> list:
        """Check for Snowball runaway."""
        findings = []
        count = self.pool.count_entities()

        if count > self.ENTITY_FLOOD_THRESHOLD:
            findings.append({
                'severity': 'warning',
                'message': f"Entity count: {count} approaching system limit",
                'detail': "Snowball may be generating excessive entities.",
            })

        return findings

    def _review_orphans(self) -> list:
        """Check for orphaned entities."""
        findings = []
        orphans = self.pool.get_orphaned_entities()

        if len(orphans) >= self.ORPHAN_ALARM_COUNT:
            findings.append({
                'severity': 'warning',
                'message': f"{len(orphans)} orphaned entities detected",
                'detail': "Entities stuck in processing. Plongeur sweep recommended.",
            })

        return findings

    def format_report(self) -> str:
        """Human-readable adversarial review report."""
        result = self.run_review()
        lines = [
            "╔══════════════════════════════════════════════╗",
            "║   SpaZzMatiC — ADVERSARIAL REVIEW REPORT    ║",
            "╠══════════════════════════════════════════════╣",
        ]

        if result['safe_halt_recommended']:
            lines.append("║  ⚠ SAFE HALT RECOMMENDED                    ║")
            lines.append("║  60-second veto window active                ║")
            lines.append("╠══════════════════════════════════════════════╣")

        if not result['findings']:
            lines.append("║  No anomalies detected. System nominal.      ║")
        else:
            for f in result['findings']:
                sev = f['severity'].upper()
                msg = f['message'][:42]
                lines.append(f"║  [{sev}] {msg:<40s} ║")

        lines.append("╚══════════════════════════════════════════════╝")
        return "\n".join(lines)
