"""
Executive Chef — The routing loop.

Reads raw entities from the pool, dispatches by type to
registered stations, enforces Aboyeur QA on every output,
and manages the Exponential Snowball with rate limiting.

Constitution Article II + Article VII.
"""

import time
from .aboyeur import Aboyeur


class ExecutiveChef:
    """
    The Executive reads raw entities, routes by type, enforces QA.

    The Executive does not process. It orchestrates.
    """

    def __init__(self, pool, max_entities: int = 500, verbose: bool = True):
        self.pool = pool
        self.stations = []
        self.aboyeur = Aboyeur(pool)
        self.max_entities = max_entities
        self.verbose = verbose
        self._cycles = 0
        self._routed = 0
        self._unhandled = 0

    def register_station(self, station):
        """Register a station with the brigade."""
        self.stations.append(station)
        if self.verbose:
            types_str = ", ".join(station.handles_types)
            print(f"[EXECUTIVE] Registered: {station.name} → [{types_str}]")

    def run_service(self):
        """
        Main routing loop. Processes all raw entities until
        the pool is drained or max_entities is reached.

        Returns summary dict.
        """
        print("\n" + "=" * 60)
        print("  KITCHEN OPEN — Executive Chef on the pass")
        print("=" * 60 + "\n")

        self.pool._log_event('kitchen_open', 'executive',
                             f"Brigade started. {len(self.stations)} stations registered. "
                             f"Max entities: {self.max_entities}")

        processed = 0

        while processed < self.max_entities:
            raw = self.pool.get_next_raw()
            if not raw:
                break

            entity_id = raw['id']
            ent_type = raw['type']
            ent_value = raw['value']
            self._cycles += 1
            processed += 1

            if self.verbose:
                print(f"\n[EXECUTIVE] Raw ingredient on the pass: [{ent_type}] {ent_value}")

            # Find a handler
            handler = None
            for station in self.stations:
                if station.can_handle(ent_type) and station.is_active:
                    handler = station
                    break

            if not handler:
                if self.verbose:
                    print(f"  [!] No station available for [{ent_type}] — marking unhandled")
                self._unhandled += 1
                # Can't go raw → unhandled directly, so raw → processing → failed
                self.pool.transition_status(entity_id, 'processing', station='none')
                self.pool.transition_status(entity_id, 'failed',
                                            notes=f"No station registered for type: {ent_type}")
                continue

            # ─── Route to Station ───
            self.pool.transition_status(entity_id, 'processing', station=handler.station_id)

            try:
                output = handler.process(entity_id, ent_type, ent_value)
                handler._tasks_processed += 1
                self._routed += 1

                # ─── Aboyeur QA Gate ───
                self.pool.transition_status(entity_id, 'pending_qa')
                result = self.aboyeur.validate_and_sign(
                    entity_id, handler.station_id, output,
                    is_fallback=(not handler.is_primary)
                )

                if result['approved']:
                    self.pool.transition_status(
                        entity_id, 'completed',
                        station=handler.station_id,
                        confidence=output.get('confidence'),
                        notes=output.get('notes', '')
                    )
                    if self.verbose:
                        print(f"  [✓] Aboyeur approved. Signature: {result['signature'][:20]}...")
                else:
                    # Rejected — check if circuit breaker tripped
                    entity_check = self.pool.get_entity(entity_id)
                    if entity_check and entity_check['status'] != 'failed':
                        self.pool.transition_status(entity_id, 'failed',
                                                    notes=result['rejection_reason'])
                    if self.verbose:
                        print(f"  [✗] Aboyeur rejected: {result['rejection_reason']}")

            except Exception as e:
                handler._tasks_failed += 1
                if self.verbose:
                    print(f"  [!] {handler.name} dropped the pan: {e}")
                # processing → failed
                self.pool.transition_status(entity_id, 'failed',
                                            notes=f"Station error: {str(e)}")

        # ─── Kitchen Closed ───
        print("\n" + "=" * 60)
        print("  KITCHEN CLOSED — The Corkboard")
        print("=" * 60)

        self.pool._log_event('kitchen_closed', 'executive',
                             f"Processed {processed} entities. "
                             f"Routed: {self._routed}. Unhandled: {self._unhandled}.")

        return self.summary()

    def summary(self) -> dict:
        return {
            'cycles': self._cycles,
            'routed': self._routed,
            'unhandled': self._unhandled,
            'stations': [s.stats for s in self.stations],
            'aboyeur': self.aboyeur.stats,
        }
