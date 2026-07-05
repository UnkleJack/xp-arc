import random
import os
import sys
from xp_arc.core.pool import IntelligencePool

# Define common high-quality target domains and patterns
DOMAINS = [
    "github.com", "linkedin.com", "twitter.com", "x.com", "reddit.com",
    "medium.com", "wikipedia.org", "arxiv.org", "stackoverflow.com",
    "news.ycombinator.com", "youtube.com", "facebook.com", "instagram.com",
    "gitlab.com", "bitbucket.org", "npmjs.com", "pypi.org", "docker.com"
]

SUBDOMAINS = ["blog", "api", "dev", "docs", "portal", "community", "status", "shop"]

USERNAMES = [
    "cyber_ninja", "data_dragon", "osint_hunter", "prompt_pimp", "code_wizard",
    "pixel_knight", "logic_lord", "shadow_walker", "net_runner", "debug_demon",
    "alpha_omega", "zen_master", "vector_viking", "neural_nomad", "git_guru"
]

def generate_entities(count=500):
    entities = []
    
    # Generate mix of URLs and Domains
    for _ in range(count // 2):
        domain = random.choice(DOMAINS)
        if random.random() > 0.7:
            sub = random.choice(SUBDOMAINS)
            domain = f"{sub}.{domain}"
        
        if random.random() > 0.5:
            entities.append(('url', f"https://{domain}/{random.choice(USERNAMES)}"))
        else:
            entities.append(('domain', domain))
            
    # Generate some emails/profiles (Hydra/Cartographer food)
    for _ in range(count // 4):
        user = random.choice(USERNAMES) + str(random.randint(10, 99))
        if random.random() > 0.5:
            entities.append(('username', user))
        else:
            entities.append(('email', f"{user}@{random.choice(DOMAINS)}"))
            
    # Fill remaining with Dossier requests for testing the new protocol
    remaining = count - len(entities)
    for _ in range(remaining):
        # Pick an existing domain or user to request a dossier for
        target = random.choice(DOMAINS) if random.random() > 0.5 else random.choice(USERNAMES)
        entities.append(('dossier_request', target))
        
    return entities

def seed_hoard(db_path="xp_arc_stress.db"):
    pool = IntelligencePool(db_path)
    entities = generate_entities(500)
    
    print(f"Seeding {len(entities)} high-quality entities into {db_path}...")
    
    added = 0
    for etype, evalue in entities:
        eid = pool.add_entity(etype, evalue)
        if eid:
            added += 1
            # Add some random edges to simulate a "hot" pool
            if random.random() > 0.8:
                source = evalue
                rel = random.choice(["related_to", "mapped_to", "found_on"])
                target = random.choice(DOMAINS)
                pool.add_edge(source, rel, target)
                
    print(f"Successfully added {added} new entities.")
    pool.close()

if __name__ == "__main__":
    seed_hoard()
