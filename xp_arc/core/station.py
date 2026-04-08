"""
Base Station Chef — All agents inherit this.

Every station owns a sovereign domain of cognitive labor.
No station may perform labor outside its domain without
explicit Compression authorization (Constitution Article VI).
"""

from datetime import datetime, timezone


class StationChef:
    """
    Base class for all brigade stations.

    Subclasses must implement process() and return a dict:
    {
        'entity_type': str,
        'entity_value': str,
        'relationships': list,
        'confidence': float (0.0 - 1.0),
        'notes': str
    }
    """

    station_id: str = "base"
    name: str = "Base Station"
    handles_types: list = []
    sla_seconds: int = 60
    is_primary: bool = True

    def __init__(self, pool):
        self.pool = pool
        self._tasks_processed = 0
        self._tasks_failed = 0
        self._active = True
        # Register with the pool
        pool.register_station(
            station_id=self.station_id,
            name=self.name,
            handles_types=self.handles_types,
            is_primary=self.is_primary,
        )

    def can_handle(self, ent_type: str) -> bool:
        return ent_type in self.handles_types

    def process(self, entity_id: int, entity_type: str, entity_value: str) -> dict:
        """
        Process an entity. Must return Aboyeur-schema-compliant dict.
        Raises on failure.
        """
        raise NotImplementedError

    def log(self, msg: str):
        print(f"[{self.name}] {msg}")
        self.pool._log_event('station_log', self.station_id, msg)

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def stats(self) -> dict:
        return {
            'station_id': self.station_id,
            'name': self.name,
            'processed': self._tasks_processed,
            'failed': self._tasks_failed,
            'active': self._active,
            'is_primary': self.is_primary,
        }
