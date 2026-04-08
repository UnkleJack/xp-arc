"""
Zoran's Law — Stability and Equilibrium.

S > 1: System self-heals. Correction rate outpaces informational decay.
PRO >= 70%: Brigade is operating within primary roles.

Constitution Article VIII.
"""


class ZoransLaw:
    """
    Computes and monitors the Stability Quotient (S) and
    Primary Role Occupancy (PRO).

    S = Σ(sla_seconds for completed tasks) / Σ(sla_seconds for ingested tasks)
    PRO = agents_in_primary_role / total_active_agents

    Weighted by cognitive labor expectation (sla_seconds), not raw task count.
    """

    # Article VIII, Section 8.2
    THRESHOLDS = {
        'healthy': 1.0,      # S > 1.0
        'equilibrium': 1.0,  # S == 1.0
        'debt': 1.0,         # S < 1.0
        'distress': 0.5,     # S < 0.5
    }

    PRO_MINIMUM = 0.70  # 70% primary role occupancy

    def __init__(self, pool):
        self.pool = pool
        self._measurements = []

    def measure(self) -> dict:
        """
        Take a measurement of current system stability.
        Records to pool and returns the measurement.
        """
        stats = self.pool.get_stats()
        stations = self.pool.get_active_stations()

        # ─── Stability Quotient (S) ───
        # Weighted by sla_seconds
        completed_sla = stats.get('completed', {}).get('total_sla', 0)
        total_ingested_sla = sum(v.get('total_sla', 0) for v in stats.values())

        if total_ingested_sla > 0:
            s = completed_sla / total_ingested_sla
        else:
            s = 1.0  # No tasks = healthy by default

        # ─── Primary Role Occupancy (PRO) ───
        total_active = len(stations)
        primary_count = sum(1 for st in stations if st['is_primary'])

        if total_active > 0:
            pro = primary_count / total_active
        else:
            pro = 1.0

        # ─── Determine System State ───
        if s > self.THRESHOLDS['healthy']:
            state = 'healthy'
        elif s == self.THRESHOLDS['equilibrium']:
            state = 'equilibrium'
        elif s >= self.THRESHOLDS['distress']:
            state = 'debt_accumulating'
        else:
            state = 'distress'

        # PRO check
        if pro < self.PRO_MINIMUM:
            state = f"{state}+compression_review"

        tasks_completed = stats.get('completed', {}).get('count', 0)
        tasks_ingested = sum(v.get('count', 0) for v in stats.values())

        measurement = {
            'stability_quotient': round(s, 4),
            'primary_role_occupancy': round(pro, 4),
            'system_state': state,
            'active_stations': total_active,
            'primary_stations': primary_count,
            'tasks_completed': tasks_completed,
            'tasks_ingested': tasks_ingested,
        }

        # Record to pool
        self.pool.record_zorans_metrics(
            s=measurement['stability_quotient'],
            pro=measurement['primary_role_occupancy'],
            state=measurement['system_state'],
            active=measurement['active_stations'],
            primary=measurement['primary_stations'],
            completed=measurement['tasks_completed'],
            ingested=measurement['tasks_ingested'],
        )

        self.pool._log_event('zorans_measurement', 'zorans_law',
                             f"S={s:.3f} PRO={pro:.1%} State={state}")

        self._measurements.append(measurement)
        return measurement

    def get_latest(self) -> dict | None:
        return self._measurements[-1] if self._measurements else None

    def format_report(self) -> str:
        """Human-readable Zoran's Law report."""
        m = self.measure()
        lines = [
            "╔══════════════════════════════════════╗",
            "║       ZORAN'S LAW — STATUS           ║",
            "╠══════════════════════════════════════╣",
            f"║  S (Stability):  {m['stability_quotient']:.4f}              ║",
            f"║  PRO (Roles):    {m['primary_role_occupancy']:.1%}              ║",
            f"║  State:          {m['system_state']:<20s} ║",
            f"║  Stations:       {m['active_stations']} active ({m['primary_stations']} primary) ║",
            f"║  Tasks:          {m['tasks_completed']}/{m['tasks_ingested']} completed     ║",
            "╚══════════════════════════════════════╝",
        ]
        return "\n".join(lines)
