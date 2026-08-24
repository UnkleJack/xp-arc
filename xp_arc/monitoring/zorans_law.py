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

    S   = SLA-seconds COMPLETED in the window / SLA-seconds INGESTED in the window
    PRO = agents_in_primary_role / total_active_agents

    Weighted by cognitive labor expectation (sla_seconds), not raw task count.

    S IS A RATE RATIO, NOT A CUMULATIVE RATIO (Article VIII 8.4).

    This distinction was the defect. The previous implementation divided the
    cumulative SLA-seconds of all completed tasks by the cumulative SLA-seconds
    of all tasks ever ingested. Every completed task is also an ingested task,
    so the numerator was a strict subset of the denominator and S was bounded at
    <= 1.0 by construction. Ten tasks in, ten tasks done, and the system reported
    S = 1.0 "equilibrium" — while Article VIII 8.1 defines HEALTHY as S > 1.0, a
    state that was literally unreachable. Every perfectly healthy brigade in
    XP-Arc's history reported, at best, "watch closely".

    Measuring flows over a rolling window instead makes S > 1 mean what the
    Constitution says it means: the brigade is draining work faster than work is
    arriving, so it is paying down backlog rather than accumulating it.
    """

    # Article VIII, Section 8.2
    THRESHOLDS = {
        'healthy': 1.0,      # S > 1.0
        'equilibrium': 1.0,  # S == 1.0
        'debt': 1.0,         # S < 1.0
        'distress': 0.5,     # S < 0.5
    }

    PRO_MINIMUM = 0.70  # 70% primary role occupancy

    # PRO measures "agents operating in their primary role" (Article VIII 8.1).
    # Infrastructure that registers with the pool purely to obtain an HMAC write
    # key is not an agent in a role and must not dilute the denominator. The
    # Aboyeur was already excluded; the Fracture Protocol and the competitive
    # intel bridge register the same way and were silently dragging PRO down —
    # the acceptance run reported 66.7% and a spurious compression_review with a
    # perfectly healthy two-station brigade, purely because the bridge was
    # counted as a non-primary agent.
    NON_LABOR_STATIONS = frozenset({
        'aboyeur',
        'fracture_protocol',
        'competitive_intel_bridge',
    })

    # Article VIII, Section 8.4 — rolling 60s window, 10s floor.
    DEFAULT_WINDOW_SECONDS = 60
    MIN_WINDOW_SECONDS = 10

    # A window in which work drained but nothing arrived is division by zero.
    # That is the healthiest possible state, not an error, so it is reported as
    # a finite ceiling rather than infinity — an unbounded S would poison the
    # DRAGON charts and the stored metrics history.
    S_MAX = 10.0

    def __init__(self, pool, window_seconds: int = None):
        self.pool = pool
        self.window_seconds = max(
            int(window_seconds or self.DEFAULT_WINDOW_SECONDS),
            self.MIN_WINDOW_SECONDS,
        )
        self._measurements = []

    def measure(self) -> dict:
        """
        Take a measurement of current system stability.
        Records to pool and returns the measurement.
        """
        stats = self.pool.get_stats()
        stations = [s for s in self.pool.get_active_stations()
                    if s['station_id'] not in self.NON_LABOR_STATIONS]

        # ─── Stability Quotient (S) — windowed rate ratio ───
        flow = self.pool.windowed_sla_flow(self.window_seconds)
        completed_sla = flow['completed_sla']
        ingested_sla = flow['ingested_sla']

        if ingested_sla > 0:
            s = min(completed_sla / ingested_sla, self.S_MAX)
        elif completed_sla > 0:
            # Draining backlog with zero arrivals: maximally healthy.
            s = self.S_MAX
        else:
            # Idle window — nothing in, nothing out. Not healthy, not failing.
            s = 1.0

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

        # Recorded counts are the WINDOWED flows that produced S, so a stored
        # metrics row can be re-derived. Cumulative lifetime totals are kept
        # alongside for the dashboard, clearly named as such.
        tasks_completed = flow['completed_count']
        tasks_ingested = flow['ingested_count']

        measurement = {
            'stability_quotient': round(s, 4),
            'primary_role_occupancy': round(pro, 4),
            'system_state': state,
            'active_stations': total_active,
            'primary_stations': primary_count,
            'tasks_completed': tasks_completed,
            'tasks_ingested': tasks_ingested,
            'window_seconds': flow['window_seconds'],
            'completed_sla_in_window': completed_sla,
            'ingested_sla_in_window': ingested_sla,
            'lifetime_completed': stats.get('completed', {}).get('count', 0),
            'lifetime_ingested': sum(v.get('count', 0) for v in stats.values()),
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

        self.pool._log_event(
            'zorans_measurement', 'zorans_law',
            f"S={s:.3f} PRO={pro:.1%} State={state}",
            f"window={flow['window_seconds']}s "
            f"completed_sla={completed_sla} ingested_sla={ingested_sla}"
        )

        self._measurements.append(measurement)
        return measurement

    def get_latest(self) -> dict | None:
        # Read latest from database to ensure we see all measurements
        rows = self.pool.conn.execute("""
            SELECT * FROM zorans_metrics ORDER BY id DESC LIMIT 1
        """).fetchone()
        if rows:
            return dict(rows)
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
            f"║  Window:         {m['window_seconds']}s rolling            ║",
            f"║  Flow:           {m['completed_sla_in_window']}s out / {m['ingested_sla_in_window']}s in       ║",
            f"║  Tasks:          {m['tasks_completed']}/{m['tasks_ingested']} in window     ║",
            "╚══════════════════════════════════════╝",
        ]
        return "\n".join(lines)
