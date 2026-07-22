import os
if os.path.exists("test_fracture.db"):
    os.unlink("test_fracture.db")
from xp_arc.core.pool import IntelligencePool
from xp_arc.core.executive import ExecutiveChef
from xp_arc.core.station import StationChef
from xp_arc.core.fracture import FractureRequest

class TheComplexStation(StationChef):
    station_id = "complex_station"
    name = "The Complex Station"
    handles_types = ['complex_task']
    
    def process(self, entity_id: int, entity_type: str, entity_value: str) -> dict:
        self.log(f"Processing complex task: {entity_value}")
        # Request fracture
        raise FractureRequest(
            complexity_notes=f"Task value {entity_value} is too large, sharding required.",
            shard_count=2,
            shard_type='shard'
        )

class TheShardProcessor(StationChef):
    station_id = "shard_processor"
    name = "The Shard Processor"
    handles_types = ['shard']
    
    def process(self, entity_id: int, entity_type: str, entity_value: str) -> dict:
        self.log(f"Processing shard entity: {entity_value}")
        return {
            'entity_type': 'shard',
            'entity_value': entity_value,
            'confidence': 1.0,
            'notes': f"Processed shard output for {entity_value}"
        }

# 1. Setup
pool = IntelligencePool("test_fracture.db")
chef = ExecutiveChef(pool)

# 2. Register
chef.register_station(TheComplexStation(pool))
chef.register_station(TheShardProcessor(pool))

# 3. Ingest
complex_id = pool.add_entity("complex_task", "VeryLargeTaskData")

# 4. Run loop
chef.run_service()

# 5. Check database state
print("\n=== DATABASE STATE AFTER RUN ===")
entities = pool.get_all_entities()
for e in entities:
    sig = f" sig:{e['aboyeur_signature'][:12]}..." if e['aboyeur_signature'] else ""
    print(f"ID={e['id']} Type={e['type']} Status={e['status']} FractureID={e['fracture_id']} Parent={e['parent_task_id']}{sig}")
    if e['notes']:
        print(f"  Notes: {e['notes'][:120]}")

pool.close()
import os
if os.path.exists("test_fracture.db"):
    os.unlink("test_fracture.db")
