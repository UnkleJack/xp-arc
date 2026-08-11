"""
Base Station Chef — All agents inherit this.

Every station owns a sovereign domain of cognitive labor.
No station may perform labor outside its domain without
explicit Compression authorization (Constitution Article VI).
"""

from datetime import datetime, timezone
import os


# SLA Validation Constants (RT-13 mitigation)
MIN_SLA_SECONDS = 1
MAX_SLA_SECONDS = 3600  # 1 hour max - prevents SLA inflation gaming
SLA_AUDIT_ENABLED = os.environ.get('XP_ARC_SLA_AUDIT', '1') != '0'


def validate_sla(sla_seconds: int, station_id: str) -> int:
    """Validate and clamp SLA seconds to prevent gaming.
    
    Args:
        sla_seconds: The SLA value to validate
        station_id: Station identifier for audit logging
        
    Returns:
        Clamped SLA value within [MIN_SLA_SECONDS, MAX_SLA_SECONDS]
    """
    if sla_seconds < MIN_SLA_SECONDS:
        if SLA_AUDIT_ENABLED:
            print(f"[SLA-AUDIT] Station {station_id}: SLA {sla_seconds} below minimum {MIN_SLA_SECONDS}, clamping")
        return MIN_SLA_SECONDS
    if sla_seconds > MAX_SLA_SECONDS:
        if SLA_AUDIT_ENABLED:
            print(f"[SLA-AUDIT] Station {station_id}: SLA {sla_seconds} above maximum {MAX_SLA_SECONDS}, clamping")
        return MAX_SLA_SECONDS
    return sla_seconds


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
        # Validate SLA on registration
        self.sla_seconds = validate_sla(self.sla_seconds, self.station_id)
        self.writer = pool.station_writer(self.station_id)

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
