"""
The Plongeur — Cleanup station.

State reconciliation, pool maintenance, GC sweeps.
The Plongeur cleans up after the brigade.

Whitepaper Section 4.4 (implied). Constitution Article IV, Section 4.2.
"""

from ..core.station import StationChef


class ThePlongeur(StationChef):
    """
    Pool janitor. Sweeps orphans, marks stale entries,
    and maintains pool hygiene.
    """

    station_id = "plongeur"
    name = "The Plongeur"
    handles_types = ['_plongeur_sweep']  # Internal type
    sla_seconds = 45

    def __init__(self, pool, orphan_threshold: int = 300):
        super().__init__(pool)
        self.orphan_threshold = orphan_threshold
        self._sweeps = 0
        self._orphans_recovered = 0

    def run_sweep(self) -> dict:
        """
        Run a cleanup sweep of the pool.

        - Recovers orphaned entities (stuck in processing)
        - Logs pool state for auditing

        Returns sweep summary.
        """
        self._sweeps += 1
        self.log(f"Running sweep #{self._sweeps}")

        orphans_recovered = 0

        # Find orphaned entities
        orphans = self.pool.get_orphaned_entities(self.orphan_threshold)
        for orphan in orphans:
            self.log(f"  Recovering orphan: entity {orphan['id']} "
                     f"({orphan['type']}:{orphan['value']})")

            # processing → failed (so it can be retried)
            self.pool.transition_status(
                orphan['id'], 'failed',
                notes=f"Plongeur recovery: exceeded SLA ({orphan['sla_seconds']}s)"
            )
            orphans_recovered += 1

        self._orphans_recovered += orphans_recovered

        # Log pool stats
        stats = self.pool.get_stats()
        status_summary = ", ".join(f"{k}: {v['count']}" for k, v in stats.items())
        self.log(f"  Pool state: {status_summary}")

        return {
            'sweep_number': self._sweeps,
            'orphans_recovered': orphans_recovered,
            'pool_stats': stats,
        }

    def process(self, entity_id: int, entity_type: str, entity_value: str) -> dict:
        """Internal process — triggers sweep."""
        result = self.run_sweep()
        return {
            'entity_type': '_plongeur_sweep',
            'entity_value': 'sweep',
            'relationships': [],
            'confidence': 1.0,
            'notes': f"Sweep #{result['sweep_number']}: "
                     f"recovered {result['orphans_recovered']} orphans",
        }
