"""
Fracture Protocol — Cognitive Sharding Engine.

Handles task decomposition into cognitive shards and shard recombination.
Constitution Article V.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

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
    
    def authorize_fracture(self, entity_id: int, station_id: str,
                          complexity_notes: str) -> bool:
        """Authorize fracture using the same QA rule as the executive path."""
        from .aboyeur import Aboyeur
        return Aboyeur(self.pool).validate_fracture(entity_id, station_id, complexity_notes)
    
    def create_shards(self, entity_id: int, entity_type: str, 
                       entity_value: str, shard_count: int = 3,
                       shard_type: str = 'shard') -> List[int]:
        """Create cognitive shards from a parent entity."""
        # Get the parent entity
        parent = self.pool.get_entity(entity_id)
        if not parent:
            self.pool._log_event('fracture_failed', 'fracture_protocol',
                                 f'Parent entity {entity_id} not found')
            return []
        
        # Generate fracture ID
        fracture_id = str(uuid.uuid4())
        
        # Update parent entity to fractured status
        self.pool.transition_status(entity_id, 'fractured',
                                  notes=f"Fractured into {shard_count} shards")
        
        # Set fracture_id and parent_task_id on parent
        with self.pool.conn:
            self.pool.conn.execute("""
                UPDATE entities 
                SET fracture_id = ?, parent_task_id = ?
                WHERE id = ?""", (fracture_id, entity_id, entity_id))
        
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
            
            shard_id = self.pool.add_entity(
                ent_type=shard_type,
                value=shard_value,
                parent_task_id=entity_id,
                station_id='fracture_protocol'
            )
            
            if shard_id:
                # Set fracture_id on shard
                with self.pool.conn:
                    self.pool.conn.execute(
                        "UPDATE entities SET fracture_id = ? WHERE id = ?",
                        (fracture_id, shard_id)
                    )
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
            'stitched_at': datetime.now(timezone.utc).isoformat(),
            'notes': f"Stitched {len(shards)} shards from fracture {fracture_id}"
        })
        
        if not self.pool.transition_status(parent_id, 'stitchable',
                                           station='fracture_protocol',
                                           station_id='fracture_protocol',
                                           notes=f"All {len(shards)} shards completed, ready for stitching"):
            return None
        
        # Create mapped entity (this represents the stitched result)
        # Get parent entity for type/value
        parent = self.pool.get_entity(parent_id)
        if not parent:
            return None
        
        mapped_id = self.pool.add_entity(
            ent_type=parent['type'],
            value=stitched_value,
            parent_task_id=parent_id,
            station_id='fracture_protocol'
        )
        
        if mapped_id:
            # Set fracture_id on mapped entity
            with self.pool.conn:
                self.pool.conn.execute(
                    "UPDATE entities SET fracture_id = ? WHERE id = ?",
                    (fracture_id, mapped_id)
                )
            
            # Transition mapped entity: raw -> processing -> pending_qa -> completed
            self.pool.transition_status(mapped_id, 'processing', station='fracture_protocol', station_id='fracture_protocol')
            self.pool.transition_status(mapped_id, 'pending_qa', station_id='fracture_protocol')
            
            # Generate and set Aboyeur signature for stitched entity
            sig_uuid = uuid.uuid4().hex[:16]
            signature = f"ABOY-STITCH-{sig_uuid}"
            self.pool.set_aboyeur_signature(mapped_id, signature, station_id='aboyeur')
            
            self.pool.transition_status(mapped_id, 'completed',
                                      station='fracture_protocol',
                                      station_id='fracture_protocol',
                                      confidence=1.0,
                                      notes=f"Stitched result from fracture {fracture_id}")
            
            # Transition parent entity: stitchable -> mapped -> completed
            self.pool.transition_status(parent_id, 'mapped',
                                      station_id='fracture_protocol',
                                      notes=f"Stitched into entity {mapped_id}")
            self.pool.transition_status(parent_id, 'completed',
                                      station_id='fracture_protocol',
                                      notes=f"Stitched into entity {mapped_id}")
            
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