# XP-Arc Deployment Guide — Zo.Computer Integration

## Overview

This guide covers installing XP-Arc v0.2 on Zo.Computer and integrating with the existing `unklejack.zo.space` infrastructure (Hono + Bun backend, React frontend).

## Architecture on Zo

```
┌─────────────────────────────────────────────────────────┐
│                    Zo.Computer                          │
│                                                         │
│  ┌──────────────────┐     ┌──────────────────────────┐  │
│  │  XP-Arc Engine   │     │  Hono + Bun Backend      │  │
│  │  (Python 3.10+)  │     │  unklejack.zo.space      │  │
│  │                  │     │                          │  │
│  │  run_persistent  │────▶│  /api/dragon (reads DB)  │  │
│  │  writes to DB    │     │  /api/seed   (writes DB) │  │
│  └──────────────────┘     └───────────┬──────────────┘  │
│           │                           │                 │
│           ▼                           ▼                 │
│  ┌──────────────────┐     ┌──────────────────────────┐  │
│  │  xp_arc.db       │     │  React DRAGON Dashboard  │  │
│  │  (shared SQLite)  │◀───│  /dragon (polls /api)    │  │
│  └──────────────────┘     └──────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

The Python engine and the Hono backend share the same SQLite file on the Zo filesystem. No network hop between pool and API.

---

## Installation

### 1. Upload and extract

```bash
# Upload the zip to Zo
# Then on Zo:
cd ~
unzip xp-arc-v0.2-deploy.zip
cd xp-arc
chmod +x install.sh
./install.sh
```

### 2. Test the one-shot run

```bash
cd ~/xp-arc
python3 run_kitchen.py --db xp_arc.db
```

You should see the full pipeline execute — entities seeded, forager extracting, analyst processing, Aboyeur signing, Zoran's Law measurement.

### 3. Start the persistent daemon

```bash
# Foreground (for testing):
python3 run_persistent.py --db xp_arc.db --port 8089

# Background (for production):
nohup python3 run_persistent.py --db xp_arc.db --port 8089 &

# Or use the convenience script:
./start.sh
```

### 4. Seed URLs into the running daemon

```bash
# Via the API:
curl -X POST http://localhost:8089/api/seed \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'

# Via convenience script:
./seed.sh https://example.com
```

---

## Zo.Computer Integration

### Option A: Use XP-Arc's Built-in API (Simplest)

The persistent daemon already serves the same endpoints your existing Hono routes provide. You can proxy directly:

```typescript
// In your Hono backend on Zo:
import { Hono } from 'hono'

const app = new Hono()

// Proxy /api/dragon to the XP-Arc daemon
app.get('/api/dragon', async (c) => {
  const resp = await fetch('http://localhost:8089/api/dragon')
  return c.json(await resp.json())
})

app.post('/api/seed', async (c) => {
  const body = await c.req.json()
  const resp = await fetch('http://localhost:8089/api/seed', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return c.json(await resp.json())
})
```

### Option B: Read DB Directly from Hono (Zero Latency)

Since Hono/Bun and the Python engine share the same filesystem, you can query the SQLite DB directly. The schema changed from v0.1 — here's the new structure:

```typescript
// Bun has built-in SQLite support
import { Database } from 'bun:sqlite'

const db = new Database('/path/to/xp_arc.db', { readonly: true })

app.get('/api/dragon', (c) => {
  const entities = db.query('SELECT * FROM entities ORDER BY id').all()
  const edges = db.query('SELECT * FROM edges ORDER BY id').all()
  const stations = db.query("SELECT * FROM station_registry WHERE status = 'active'").all()
  const findings = db.query('SELECT * FROM findings ORDER BY id DESC').all()
  const zorans = db.query('SELECT * FROM zorans_metrics ORDER BY id DESC LIMIT 1').get()
  const events = db.query('SELECT * FROM events ORDER BY id DESC LIMIT 200').all()

  return c.json({
    entities,
    edges,
    stations,
    findings,
    zorans_latest: zorans || {},
    events: events.reverse(),
    meta: {
      version: '0.2.0',
      protocol: 'XP-Arc',
    }
  })
})
```

### Option C: Use as Zo User Service

If Zo supports `register_user_service`:

```bash
register_user_service xp-arc-kitchen \
  "python3 /home/workspace/xp-arc/run_persistent.py --db /home/workspace/xp-arc/xp_arc.db --port 8089"
```

---

## DB Schema Reference (v0.2)

### entities
| Column | Type | Description |
|---|---|---|
| id | INTEGER | Primary key |
| type | TEXT | Entity type (url, domain, etc.) |
| value | TEXT | Entity value |
| status | TEXT | raw → processing → pending_qa → completed/failed |
| payload_hash | TEXT | SHA-256 sealed at ingestion |
| station | TEXT | Processing station ID |
| confidence | REAL | 0.0 - 1.0 |
| notes | TEXT | Station output notes |
| sla_seconds | INTEGER | Max processing time |
| assigned_at | TEXT | ISO-8601 processing start |
| completed_at | TEXT | ISO-8601 completion time |
| created_at | TEXT | ISO-8601 creation time |
| aboyeur_signature | TEXT | QA seal (ABOY-{hash}) |
| fallback_role | INTEGER | 1 if processed by fallback station |
| rejection_count | INTEGER | Aboyeur rejection counter |
| max_rejections | INTEGER | Circuit breaker threshold (default: 3) |

### edges
| Column | Type | Description |
|---|---|---|
| source | TEXT | Source entity value |
| relationship | TEXT | links_to, subdomain_of, etc. |
| target | TEXT | Target entity value |

### station_registry
| Column | Type | Description |
|---|---|---|
| station_id | TEXT | Unique station identifier |
| name | TEXT | Display name |
| handles_types | TEXT | JSON array of handled entity types |
| status | TEXT | active/inactive |
| is_primary | INTEGER | 1 = primary role, 0 = fallback |

### findings (SpaZzMatiC)
| Column | Type | Description |
|---|---|---|
| severity | TEXT | critical/warning/info |
| source | TEXT | Finding source |
| message | TEXT | Description |

### zorans_metrics
| Column | Type | Description |
|---|---|---|
| stability_quotient | REAL | S value |
| primary_role_occupancy | REAL | PRO value |
| system_state | TEXT | healthy/equilibrium/debt/distress |

---

## DRAGON Dashboard

### Static mode (for quick demos)
Open `dragon/index.html` in a browser. It loads `dragon/pool_state.json`.

To update the static file after a run:
```bash
python3 run_kitchen.py --export-only --db xp_arc.db
cp xp_arc_dragon.json dragon/pool_state.json
```

### Live mode (connected to API)
Modify the `fetch` call in `dragon/index.html` to point to your API:

```javascript
// Change this line in index.html:
fetch('pool_state.json')
// To:
fetch('http://localhost:8089/api/dragon')
// Or for Zo:
fetch('/api/dragon')
```

The DRAGON page on `unklejack.zo.space/dragon` can poll this endpoint at 500ms intervals for real-time visualization.

---

## Troubleshooting

**"Database is locked"**: Only one writer at a time. The persistent daemon is the writer. The Hono backend should open the DB as `readonly: true`.

**Entities stuck in "processing"**: The Plongeur sweeps orphans automatically every 5 cycles. Force a sweep:
```bash
python3 -c "
from xp_arc.core.pool import IntelligencePool
from xp_arc.stations.plongeur import ThePlongeur
pool = IntelligencePool('xp_arc.db')
p = ThePlongeur(pool)
p.run_sweep()
pool.close()
"
```

**Safe halt triggered**: SpaZzMatiC detected S < 0.5 for 2+ measurements. Check the findings table for details. The daemon pauses ingestion automatically.
