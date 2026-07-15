"""
Executive Chef — The routing loop.

Reads raw entities from the pool, dispatches by type to
registered stations, enforces Aboyeur QA on every output,
and manages the Exponential Snowball with rate limiting.

CONSTITUTION Article II + Article VII.
"""

import time
from .aboyeur import Aboyeur
from .fracture import FractureRequest
from .pool import MAX_CASCADE_DEPTH


class ExecutiveChef:
    """
    The Executive reads raw entities, routes by type, enforces QA.

    The Executive does not process. It orchestrates.
    """

    MAX_CASCADE_DEPTH = MAX_CASCADE_DEPTH  # class-level alias to module constant

    def __init__(self, pool, max_entities: int = 500, verbose: bool = True):
        self.pool = pool
        self.writer = pool.station_writer('executive')
        self.stations = []
        self._critical_stations = []  # stations that survive compression
        self._station_backup = []     # preserved copy for expansion
        self._brigade_compressed = False
        self.aboyeur = Aboyeur(pool)
        self.max_entities = max_entities
        self.verbose = verbose
        self._cycles = 0
        self._routed = 0
        self._unhandled = 0
        self._spawn_blocked = 0
        self._spawn_created = 0

    def register_station(self, station):
        """Register a station with the brigade."""
        self.pool.register_station(station.station_id, station.name, station.handles_types,
                                   is_primary=getattr(station, 'critical', getattr(station, 'is_primary', True)))
        self.stations.append(station)
        if self.verbose:
            types_str = ", ".join(station.handles_types)
            print(f"[EXECUTIVE] Registered: {station.name} -> [{types_str}]")

    def compress_brigade(self):
        """Compress the brigade into critical-only stations for degraded mode.

        Saves a full backup of all stations, then removes non-critical stations.
        Subsequent routing only dispatches to critical stations.
        Safe to call multiple times (idempotent).
        """
        if not self._brigade_compressed:
            self._station_backup = list(self.stations)
            critical = [s for s in self.stations if getattr(s, 'critical', False)]
            self._critical_stations = critical
            self.stations = critical
            self._brigade_compressed = True
            self.pool._log_event(
                'brigade_compressed', 'executive',
                f"Brigade compressed: {len(self._station_backup)} stations -> {len(critical)} critical. "
                f"Removed: {[s.name for s in self._station_backup if not getattr(s, 'critical', False)]}"
            )
            if self.verbose:
                print(f"[EXECUTIVE] Brigade COMPRESSED: {len(critical)} critical stations active. "
                      f"Backup: {len(self._station_backup)} stations preserved.")
        return self

    def expand_brigade(self):
        """Restore the brigade from backup, restoring all non-critical stations.

        Idempotent — calling when already expanded is a no-op.
        """
        if self._brigade_compressed and self._station_backup:
            self.stations = list(self._station_backup)
            self._brigade_compressed = False
            removed = [s for s in self._station_backup if s not in self.stations]
            self.pool._log_event(
                'brigade_expanded', 'executive',
                f"Brigade expanded: {len(self._station_backup)} stations restored. "
                f"Critical: {len(self._critical_stations)}."
            )
            if self.verbose:
                print(f"[EXECUTIVE] Brigade EXPANDED: all {len(self._station_backup)} stations restored.")
        return self

    def is_compressed(self) -> bool:
        """Returns True if brigade is currently in degraded/compressed mode."""
        return self._brigade_compressed

    def run_service(self):
        """
        Main routing loop. Processes all raw entities until
        the pool is drained or max_entities is reached.

        Returns summary dict.
        """
        print("\n" + "=" * 60)
        print("  KITCHEN OPEN - Executive Chef on the pass")
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
                    print(f"  [!] No station available for [{ent_type}] - marking unhandled")
                self._unhandled += 1
                self.writer.transition_status(entity_id, 'processing', station='none')
                self.writer.transition_status(entity_id, 'failed',
                                            notes=f"No station registered for type: {ent_type}")
                continue

            # Route to Station
            claimed = self.pool.claim_entity(entity_id, handler.station_id)
            if not claimed or claimed['id'] != entity_id:
                continue

            try:
                output = handler.process(entity_id, ent_type, ent_value)
                handler._tasks_processed += 1
                self._routed += 1

                # Aboyeur QA Gate
                self.pool.station_writer(handler.station_id).transition_status(entity_id, 'pending_qa')
                result = self.aboyeur.validate_and_sign(
                    entity_id, handler.station_id, output,
                    is_fallback=(not handler.is_primary)
                )

                if result['approved']:
                    self.pool.station_writer(handler.station_id).transition_status(
                        entity_id, 'completed',
                        station=handler.station_id,
                        confidence=output.get('confidence'),
                        notes=output.get('notes', '')
                    )
                    if self.verbose:
                        print(f"  [✓] Aboyeur approved. Signature: {result['signature'][:20]}...")

                    # Shard Stitching Check
                    entity = self.pool.get_entity(entity_id)
                    if entity and entity['parent_task_id'] is not None and entity['fracture_id'] is not None:
                        from xp_arc.core.fracture import FractureProtocol
                        fracture = FractureProtocol(self.pool)
                        comp = fracture.check_shard_completion(entity['fracture_id'])
                        if comp['all_complete']:
                            if self.verbose:
                                print(f"  [i] All shards for fracture {entity['fracture_id']} completed. Stitching...")
                            mapped_id = fracture.stitch_shards(entity['fracture_id'])
                            if mapped_id and self.verbose:
                                print(f"  [✓] Shards stitched successfully. Stitched entity ID: {mapped_id}")

                    # Spawn directives — Snowball expansion
                    spawn_targets = output.get('spawn_targets', [])
                    if spawn_targets:
                        new_ids = self._process_spawns(entity_id, spawn_targets)
                        if self.verbose and new_ids:
                            print(f"  [i] Snowball: spawned {len(new_ids)} child entities")
                else:
                    # Rejected — check if circuit breaker tripped
                    entity_check = self.pool.get_entity(entity_id)
                    if entity_check and entity_check['status'] != 'failed':
                        self.pool.station_writer(handler.station_id).transition_status(entity_id, 'failed',
                                                    notes=result['rejection_reason'])
                    if self.verbose:
                        print(f"  [✗] Aboyeur rejected: {result['rejection_reason']}")

            except FractureRequest as fr:
                if self.verbose:
                    print(f"  [i] {handler.name} requested fracture: {fr.complexity_notes}")
                if self.aboyeur.validate_fracture(entity_id, handler.station_id, fr.complexity_notes):
                    from xp_arc.core.fracture import FractureProtocol
                    fracture = FractureProtocol(self.pool)
                    shard_ids = fracture.create_shards(entity_id, ent_type, ent_value, fr.shard_count, fr.shard_type)
                    if self.verbose:
                        print(f"  [✓] Fracture authorized. Spawned {len(shard_ids)} shards.")
                else:
                    if self.verbose:
                        print(f"  [✗] Fracture unauthorized by Aboyeur. Marking failed.")
                    self.pool.station_writer(handler.station_id).transition_status(entity_id, 'failed', notes="Fracture unauthorized by Aboyeur")

            except Exception as e:
                handler._tasks_failed += 1
                if self.verbose:
                    print(f"  [!] {handler.name} dropped the pan: {e}")
                self.pool.station_writer(handler.station_id).transition_status(entity_id, 'failed',
                                            notes=f"Station error: {str(e)}")

        # Kitchen Closed
        print("\n" + "=" * 60)
        print("  KITCHEN CLOSED - The Corkboard")
        print("=" * 60)

        self.pool._log_event('kitchen_closed', 'executive',
                             f"Processed {processed} entities. "
                             f"Routed: {self._routed}. Unhandled: {self._unhandled}. "
                             f"Spawn created: {self._spawn_created}. Spawn blocked: {self._spawn_blocked}.")

        return self.summary()

    def _process_spawns(self, parent_id: int, spawn_targets: list[dict]) -> list[int]:
        """
        Process spawn directives from a completed entity.

        Each dict in spawn_targets:
            ent_type: str   — entity type for the new entity
            value: str      — entity value
            sla_seconds: int (optional, default 60)

        Cascade depth is calculated by tracing parent_task_id chain,
        NOT declared by the agent. (CONSTITUTION Article VII, Section 7.3)

        Returns list of new entity IDs created.
        """
        import json
        created = []
        parent = self.pool.get_entity(parent_id)

        # Inherit lineage from parent
        parent_depth = parent['cascade_depth'] if parent else 0
        parent_root = parent['root_task_id'] if parent else parent_id
        parent_chain_raw = parent['spawn_chain'] if parent else None
        if parent_chain_raw:
            try:
                parent_chain = json.loads(parent_chain_raw)
            except (json.JSONDecodeError, TypeError):
                parent_chain = []
        else:
            parent_chain = []

        for target in spawn_targets:
            ent_type = target.get('ent_type') or target.get('type') or 'url'
            value = target.get('value') or target.get('ent_value')
            if not value:
                continue

            # Broker-enforced cascade depth
            if parent_depth >= self.MAX_CASCADE_DEPTH:
                self._spawn_blocked += 1
                self.pool._log_event(
                    'spawn_blocked_depth_limit',
                    'executive',
                    f"spawn_blocked_depth_limit: {ent_type}:{value} at depth {parent_depth} >= {self.MAX_CASCADE_DEPTH}",
                    f"parent_id={parent_id}, root_task_id={parent_root}"
                )
                continue

            # Build new spawn chain: parent chain + parent_id
            new_chain = parent_chain + [parent_id]

            eid = self.writer.add_entity(
                ent_type=ent_type,
                value=value,
                sla_seconds=target.get('sla_seconds', 60),
                parent_task_id=parent_id,
                root_task_id=parent_root,
                station_id='executive',
                cascade_depth=parent_depth + 1,
                spawn_chain=json.dumps(new_chain)
            )
            if eid:
                created.append(eid)
                self._spawn_created += 1
                if self.verbose:
                    print(f"    [SPAWN] + {ent_type}: {value[:60]} (depth={parent_depth+1}, chain={len(new_chain)})")
            else:
                # Duplicate — entity already exists in pool
                pass

        return created

    def summary(self) -> dict:
        s = {
            'cycles': self._cycles,
            'routed': self._routed,
            'unhandled': self._unhandled,
            'spawn_created': self._spawn_created,
            'spawn_blocked': self._spawn_blocked,
            'stations': [s.stats for s in self.stations],
            'aboyeur': self.aboyeur.stats,
        }
        return s