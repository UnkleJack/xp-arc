import sys
sys.path.append('/home/workspace/TheKitchen')
from orchestrator.pool import IntelligencePool
from orchestrator.executive import ExecutiveChef
from agents.forager import TheForager

pool = IntelligencePool(":memory:")
exec_chef = ExecutiveChef(pool)
exec_chef.register_station(TheForager(pool))

# 5 TARGETS. LIVE.
targets = [
    "https://news.ycombinator.com",
    "https://github.com/unklejack",
    "https://zo.computer",
    "https://lobste.rs",
    "https://httpbin.org"
]

print(">>> STARTING XP-ARC 5-TARGET SPREAD LIVE <<<")
for t in targets:
    pool.add_entity('url', t)

exec_chef.run_service()

print("\n" + "="*50)
print("KITCHEN CLOSED. THE CORKBOARD:")
print("="*50)

cur = pool.conn.cursor()
print("\n[ ENTITIES COLLECTED (Showing 15 max) ]")
for row in cur.execute("SELECT type, value, status FROM entities LIMIT 15"):
    print(f" - [{row[0].upper()}] {row[1]} ({row[2]})")

print("\n[ EDGES GENERATED (Showing 15 max) ]")
for row in cur.execute("SELECT source, relationship, target FROM edges LIMIT 15"):
    print(f" - {row[0]} --({row[1]})--> {row[2]}")
