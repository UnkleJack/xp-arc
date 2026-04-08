#!/usr/bin/env python3
"""Pre-load the Dragon Hoard with 36,000 seeds."""
import sqlite3, hashlib, json, time, random, os

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dragon_hoard.db')

random.seed(42)
BASES = ['apple.com','microsoft.com','google.com','amazon.com','nvidia.com','oracle.com',
'salesforce.com','adobe.com','cisco.com','stripe.com','shopify.com','cloudflare.com',
'openai.com','anthropic.com','deepmind.com','mistral.ai','huggingface.co','perplexity.ai',
'groq.com','cerebras.ai','usa.gov','nasa.gov','nih.gov','cdc.gov','nist.gov',
'mit.edu','stanford.edu','harvard.edu','berkeley.edu','caltech.edu','cmu.edu',
'jpmorgan.com','coinbase.com','visa.com','paypal.com','twitter.com','reddit.com',
'discord.com','youtube.com','spotify.com','owasp.org','hackerone.com','nmap.org',
'steampowered.com','unity.com','roblox.com','nature.com','arxiv.org','cern.ch',
'spacex.com','bbc.com','reuters.com','bloomberg.com','wired.com','techcrunch.com',
'alibaba.com','tencent.com','toyota.com','samsung.co.kr','ikea.com','meta.com',
'intel.com','amd.com','ibm.com','dell.com','slack.com','zoom.us','dropbox.com',
'stability.ai','cohere.com','fbi.gov','sec.gov','treasury.gov','defense.gov',
'congress.gov','yale.edu','columbia.edu','princeton.edu','cornell.edu','gatech.edu',
'blackrock.com','robinhood.com','facebook.com','snapchat.com','telegram.org',
'linkedin.com','medium.com','twitch.tv','pinterest.com','vimeo.com']

PREFIXES = ['www','api','docs','dev','staging','beta','app','mail','blog','cdn',
'static','assets','status','support','admin','dashboard','portal','auth','login',
'sso','data','analytics','search','store','shop','forum','community','wiki','learn',
'academy','careers','jobs','press','investor','monitor','metrics','billing','help',
'ir','id','pay','training','media','account','my']

print("Generating 36,000 unique domains...")
seeds = set(BASES)
while len(seeds) < 36000:
    seeds.add(f'{random.choice(PREFIXES)}.{random.choice(BASES)}')
seeds = list(seeds)[:36000]
print(f"Generated {len(seeds)}")

print("Computing hashes...")
batch = []
for d in seeds:
    h = hashlib.sha256(json.dumps({'type':'domain','value':d},sort_keys=True).encode()).hexdigest()
    batch.append(('domain',d,'raw',h))
print("Hashes done")

print(f"Opening DB: {DB}")
conn = sqlite3.connect(DB)
conn.execute('PRAGMA journal_mode=WAL')
conn.execute('PRAGMA synchronous=OFF')
conn.execute('PRAGMA cache_size=-64000')

SCHEMA = [
    'CREATE TABLE IF NOT EXISTS entities (id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT NOT NULL, value TEXT NOT NULL, status TEXT NOT NULL DEFAULT "raw", payload_hash TEXT NOT NULL, station TEXT, confidence REAL, notes TEXT, sla_seconds INTEGER DEFAULT 60, assigned_at TEXT, completed_at TEXT, created_at TEXT NOT NULL DEFAULT (datetime("now")), aboyeur_signature TEXT, fallback_role INTEGER DEFAULT 0, fracture_id TEXT, parent_task_id INTEGER, rejection_count INTEGER DEFAULT 0, max_rejections INTEGER DEFAULT 3, sla_suspended INTEGER DEFAULT 0, UNIQUE(type, value))',
    'CREATE TABLE IF NOT EXISTS edges (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, relationship TEXT NOT NULL, target TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime("now")))',
    'CREATE TABLE IF NOT EXISTS station_registry (id INTEGER PRIMARY KEY AUTOINCREMENT, station_id TEXT UNIQUE NOT NULL, name TEXT NOT NULL, handles_types TEXT NOT NULL, status TEXT DEFAULT "active", is_primary INTEGER DEFAULT 1, registered_at TEXT NOT NULL DEFAULT (datetime("now")))',
    'CREATE TABLE IF NOT EXISTS findings (id INTEGER PRIMARY KEY AUTOINCREMENT, severity TEXT NOT NULL, source TEXT NOT NULL, message TEXT NOT NULL, detail TEXT, created_at TEXT NOT NULL DEFAULT (datetime("now")))',
    'CREATE TABLE IF NOT EXISTS zorans_metrics (id INTEGER PRIMARY KEY AUTOINCREMENT, stability_quotient REAL NOT NULL, primary_role_occupancy REAL NOT NULL, system_state TEXT NOT NULL, active_stations INTEGER, primary_stations INTEGER, tasks_completed INTEGER, tasks_ingested INTEGER, measured_at TEXT NOT NULL DEFAULT (datetime("now")))',
    'CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL, source TEXT NOT NULL, message TEXT NOT NULL, detail TEXT, created_at TEXT NOT NULL DEFAULT (datetime("now")))',
]
for sql in SCHEMA:
    conn.execute(sql)

print("Inserting...")
t = time.time()
# Insert in chunks of 5000
for i in range(0, len(batch), 5000):
    chunk = batch[i:i+5000]
    conn.executemany('INSERT OR IGNORE INTO entities (type,value,status,payload_hash) VALUES (?,?,?,?)', chunk)
    conn.commit()
    print(f"  {min(i+5000, len(batch))}/{len(batch)}")

count = conn.execute('SELECT COUNT(*) FROM entities').fetchone()[0]
raw = conn.execute("SELECT COUNT(*) FROM entities WHERE status='raw'").fetchone()[0]
elapsed = time.time() - t
print(f"\nDone: {count} entities ({raw} raw) in {elapsed:.1f}s")
conn.close()
