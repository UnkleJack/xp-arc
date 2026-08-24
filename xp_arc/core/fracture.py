"""
Fracture Protocol — Cognitive Sharding Engine.

Handles task decomposition into cognitive shards and shard recombination.
Constitution Article V.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

MAX_SHARD_COUNT = 20  # RT-15: upper bound to prevent fracture shard-flood DoS


class FractureRequest(Exception):
    """
    Exception raised by a station to indicate that the entity needs to be fractured.
    """
    def __init__(self, complexity_notes: str, shard_count: int = 3, shard_type: str = 'shard'):
        super().__init__(complexity_notes)
        self.complexity_notes = complexity_notes
        self.shard_count = shard_count
        self.shard_type = shard_type


class FractureProtocol:
    """Manages cognitive sharding and recombination."""
    
    def __init__(self, pool):
        self.pool = pool
        self.station_id = 'fracture_protocol'
        self.pool.register_station(
            self.station_id, 'Fracture Protocol', ['shard'], is_primary=False
        )
        self.writer = self.pool.station_writer(self.station_id)
    
    def authorize_fracture(self, entity_id: int, station_id: str,
                          complexity_notes: str) -> bool:
        """Authorize fracture using the same QA rule as the executive path."""
        from .aboyeur import Aboyeur
        return Aboyeur(self.pool).validate_fracture(entity_id, station_id, complexity_notes)
    
    def create_shards(self, entity_id: int, entity_type: str, 
                       entity_value: str, shard_count: int = 3,
                       shard_type: str = 'shard') -> List[int]:
        """Create cognitive shards from a parent entity."""
        if shard_count > MAX_SHARD_COUNT:
            self.pool._log_event('fracture_shard_capped', 'fracture_protocol',
                                 f'shard_count {shard_count} capped to {MAX_SHARD_COUNT}',
                                 f'entity_id={entity_id}')
            shard_count = MAX_SHARD_COUNT

        # Get the parent entity
        parent = self.pool.get_entity(entity_id)
        if not parent:
            self.pool._log_event('fracture_failed', 'fracture_protocol',
                                 f'Parent entity {entity_id} not found')
            return []
        
        # Generate fracture ID
        fracture_id = str(uuid.uuid4())
        
        # The parent transitions and records fracture identity through the Pool.
        if not self.writer.transition_status(
            entity_id, 'fractured', notes=f"Fractured into {shard_count} shards"
        ):
            return []
        if not self.writer.set_fracture_metadata(entity_id, fracture_id, parent_task_id=entity_id):
            return []
        
        shard_ids = []
        
        # Create shard entities
        for i in range(shard_count):
            shard_value = json.dumps({
                'shard_index': i,
                'total_shards': shard_count,
                'parent_entity_id': entity_id,
                'fracture_id': fracture_id,
                'shard_data': f"Shard {i+1} of {shard_count} from {entity_type}: {entity_value}"
            })
            
            shard_id = self.writer.add_entity(
                ent_type=shard_type,
                value=shard_value,
                parent_task_id=entity_id,
            )
            if shard_id:
                if not self.writer.set_fracture_metadata(shard_id, fracture_id):
                    return []
                shard_ids.append(shard_id)
                
                self.pool._log_event('shard_created', 'fracture_protocol',
                                   f"Shard {shard_id} created for fracture {fracture_id}")
        
        return shard_ids
    
    def check_shard_completion(self, fracture_id: str) -> Dict[str, Any]:
        """Check if all shards for a fracture group are completed."""
        # Get all entities with this fracture_id
        rows = self.pool.conn.execute("""
            SELECT id, type, value, status, parent_task_id
            FROM entities 
            WHERE fracture_id = ?
            ORDER BY id""", (fracture_id,)).fetchall()
        
        if not rows:
            return {'all_complete': False, 'shards': [], 'parent_id': None}
        
        # The first entity is the parent (has parent_task_id pointing to itself or NULL)
        # Shards have parent_task_id pointing to parent
        parent_id = None
        shards = []
        
        for row in rows:
            if row['parent_task_id'] == row['id'] or row['parent_task_id'] is None:
                parent_id = row['id']
            else:
                shards.append(dict(row))
        
        if parent_id is None:
            # Fallback: assume lowest ID is parent
            parent_id = rows[0]['id']
            shards = [dict(row) for row in rows[1:]]
        
        # Check if all shards are completed
        incomplete_shards = [s for s in shards if s['status'] != 'completed']
        
        all_complete = len(incomplete_shards) == 0 and len(shards) > 0
        
        return {
            'all_complete': all_complete,
            'shards': shards,
            'incomplete_shards': incomplete_shards,
            'parent_id': parent_id,
            'fracture_id': fracture_id
        }
    
    def stitch_shards(self, fracture_id: str) -> Optional[int]:
        """Stitch completed shards back into a single mapped entity."""
        completion = self.check_shard_completion(fracture_id)
        
        if not completion['all_complete']:
            return None
        
        parent_id = completion['parent_id']
        shards = completion['shards']
        
        if not shards:
            return None
        
        # Collect shard results
        shard_results = []
        for shard in shards:
            try:
                shard_data = json.loads(shard['value'])
                shard_results.append(shard_data)
            except json.JSONDecodeError:
                shard_results.append({'raw_value': shard['value']})
        
        # Create stitched value
        stitched_value = json.dumps({
            'fracture_id': fracture_id,
            'shard_count': len(shards),
            'shard_results': shard_results,
            'notes': f"Stitched {len(shards)} shards from fracture {fracture_id}"
        })

        if not self.writer.transition_status(
            parent_id, 'stitchable', station=self.station_id,
            notes=f"All {len(shards)} shards completed, ready for stitching"
        ):
            return None
        
        # Create mapped entity (this represents the stitched result)
        # Get parent entity for type/value
        parent = self.pool.get_entity(parent_id)
        if not parent:
            return None
        
        mapped_id = self.writer.add_entity(
            ent_type=parent['type'], value=stitched_value, parent_task_id=parent_id
        )

        if mapped_id:
            if not self.writer.set_fracture_metadata(mapped_id, fracture_id):
                return None
            if not self.writer.transition_status(mapped_id, 'processing', station=self.station_id):
                return None
            if not self.writer.transition_status(mapped_id, 'pending_qa'):
                return None

            # A stitched output is still labor and must receive a real QA seal.
            from .aboyeur import Aboyeur
            aboyeur = Aboyeur(self.pool)
            output = {
                'entity_type': parent['type'],
                'entity_value': stitched_value,
                'relationships': [],
                'confidence': 1.0,
                'notes': f"Stitched result from fracture {fracture_id}",
            }
            qa_result = aboyeur.validate_and_sign(mapped_id, self.station_id, output)
            if not qa_result['approved']:
                self.writer.transition_status(mapped_id, 'failed', notes=qa_result['rejection_reason'])
                self.writer.transition_status(parent_id, 'failed', notes='Stitched output rejected by Aboyeur')
                return None
            if not self.writer.transition_status(
                mapped_id, 'completed', station=self.station_id, confidence=1.0,
                notes=f"Stitched result from fracture {fracture_id}"
            ):
                return None

            # The original task is completed only after its mapped child is sealed.
            if not self.writer.transition_status(parent_id, 'mapped', notes=f"Stitched into entity {mapped_id}"):
                return None
            if not self.writer.set_aboyeur_signature(parent_id, qa_result['signature']):
                return None
            if not self.writer.transition_status(parent_id, 'completed', notes=f"Stitched into entity {mapped_id}"):
                return None
            
            self.pool._log_event('shards_stitched', 'fracture_protocol',
                               f"Stitched {len(shards)} shards into entity {mapped_id}")
            
            return mapped_id
        
        return None
    
    def get_fracture_groups(self) -> List[Dict[str, Any]]:
        """Get all active fracture groups for monitoring."""
        rows = self.pool.conn.execute("""
            SELECT DISTINCT fracture_id
            FROM entities
            WHERE fracture_id IS NOT NULL
            AND status IN ('fractured', 'stitchable')
        """).fetchall()
        
        groups = []
        for row in rows:
            fracture_id = row['fracture_id']
            completion = self.check_shard_completion(fracture_id)
            groups.append({
                'fracture_id': fracture_id,
                'shard_count': len(completion['shards']),
                'completed_count': len(completion['shards']) - len(completion['incomplete_shards']),
                'all_complete': completion['all_complete'],
                'parent_id': completion['parent_id']
            })
        
        return groups