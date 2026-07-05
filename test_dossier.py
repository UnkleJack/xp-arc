from xp_arc.core.pool import IntelligencePool
from xp_arc.core.executive import ExecutiveChef
from xp_arc.stations import TheAnalyst, TheWarden, TheDossier

# 1. Setup Pool and Chef
pool = IntelligencePool("test_osint.db")
chef = ExecutiveChef(pool)

# 2. Register Stations
chef.register_station(TheAnalyst(pool))
chef.register_station(TheWarden(pool))
chef.register_station(TheDossier(pool))

# 3. Ingest Target and Mock Data
target = "example.com"
domain_id = pool.add_entity("domain", target)
dossier_req_id = pool.add_entity("dossier_request", target)

# Mock some analyst work
pool.add_edge(target, "subdomain_of", "parent.com")
parent_id = pool.add_entity("domain", "parent.com")
pool.transition_status(domain_id, "processing", station="analyst")
pool.transition_status(domain_id, "pending_qa")
pool.set_aboyeur_signature(domain_id, "ABOY-SIG-123")
pool.transition_status(domain_id, "completed", station="analyst", confidence=0.9, notes="Found subdomains.")

# Mock some warden work (Risk)
pool.add_finding("critical", "warden", "Domain flagged for phishing.", "Detail info here.")
risk_id = pool.add_entity("risk_factor", "Phishing Alert", sla_seconds=60)
pool.add_edge(target, "risk_at", "Phishing Alert")
pool.transition_status(risk_id, "processing", station="warden")
pool.transition_status(risk_id, "pending_qa")
pool.set_aboyeur_signature(risk_id, "ABOY-SIG-456")
pool.transition_status(risk_id, "completed", station="warden", confidence=1.0, notes="Confirmed threat.")

# 4. Run the service
chef.run_service()

# 5. Output the result
entities = pool.get_entities_by_status("completed")
for ent in entities:
    if ent['type'] == 'dossier_report':
        print("\n=== GENERATED DOSSIER ===\n")
        print(ent['notes'])
        break

pool.close()
