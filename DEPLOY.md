# XP-Arc Deployment Guide — Zo.Computer Integration

## Overview

This guide covers installing XP-Arc v0.2.1 on a generic Linux/macOS environment and integrating with any backend of your choice.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│            XP-Arc Engine (Python)                        │
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
unzip xp-arc-v0.2.1-deploy.zip
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

For a containerized deployment (Dockerfile, docker-compose, and the PyPI release
workflow), see `docs/RELEASING.md`. Note that the Docker image build has been
desk-checked but not executed in CI or locally as of this writing — Docker was
not available in the sandbox that built it — while the wheel/sdist build (`python
-m build`) has been run and passes.

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

## Optional Subpackages

XP-Arc v0.2.1 ships three subpackages under a single `pip install -e .` — install only what you need:

| Subpackage | Install Command | Purpose |
|---|---|---|
| Core (orchestration) | `pip install -e .` | Pool, stations, broker, monitoring |
| Asset Engine | `pip install -e .[asset-engine]` | Evolutionary asset generation |
| Competitive Intel | `pip install -e .[competitive-intel]` | Watchlist + gap detection |
| Everything | `pip install -e .[all]` | All of the above |

**All subpackages share the same Intelligence Pool (SQLite WAL) and Aboyeur QA gate.**

---

## API Interaction (Generic)

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
      version: '0.2.1',
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
| parent_task_id | INTEGER | Parent entity ID (for spawned tasks) |
| fracture_id | TEXT | Fracture group ID (for sharded tasks) |
| cascade_depth | INTEGER | Spawn cascade level (0=seed, max=5) |
| root_task_id | INTEGER | Root entity ID of this Snowball chain |
| spawn_chain | TEXT | JSON array of ancestor IDs tracing to root |
| sla_suspended | INTEGER | 1 if SLA timer is paused |
| crawl_depth | INTEGER | Web crawl depth (Forager) |
| max_crawl_depth | INTEGER | Max crawl depth for this entity's subtree |

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
| hmac_key | TEXT | Derived HMAC write authentication key |
| status | TEXT | active/inactive |
| is_primary | INTEGER | 1 = primary role, 0 = fallback |
| registered_at | TEXT | ISO-8601 registration time |

### findings (SpaZzMatiC)

| Column | Type | Description |
|---|---|---|
| severity | TEXT | critical/warning/info |
| source | TEXT | Finding source |
| message | TEXT | Description |
| detail | TEXT | Expanded trace or telemetry logs |

### zorans_metrics

| Column | Type | Description |
|---|---|---|
| stability_quotient | REAL | S value |
| primary_role_occupancy | REAL | PRO value |
| system_state | TEXT | healthy/equilibrium/debt/distress |
| active_stations | INTEGER | Total active registered stations |
| primary_stations | INTEGER | Count of active primary stations |
| tasks_completed | INTEGER | Completed task count |
| tasks_ingested | INTEGER | Total ingested task count |
| measured_at | TEXT | Timestamp of measurement |

### events

| Column | Type | Description |
|---|---|---|
| event_type | TEXT | event type (e.g. zorans_measurement, status_transition) |
| source | TEXT | Component origin |
| message | TEXT | Log description |
| detail | TEXT | Extended detail |
| created_at | TEXT | Timestamp of event |

---

## Persistent Daemon HTTP API (`run_persistent.py`)

The persistent runner initializes the pipeline and starts an HTTP API interface.

### Endpoints

#### 1. `POST /api/seed`
Injects a new seed entity into the pool.
- **Request Body**: `{"url": "https://example.com"}`
- **Response**: `{"status": "success", "id": <entity_id>}` or `{"status": "duplicate"}`

#### 2. `GET /api/dragon`
Retrieves a JSON payload containing the complete state of the pool, edges, registered stations, metrics, and event timeline for DRAGON visualization.
- **Response**: Full JSON-serializable pool state dump matching `pool.export_state()`.

### Configuration Rules & Path Constraints
- **Station key file path**: There is no fixed `station_keys.json` anymore. Each Pool derives its key file path from its own DB path: `{db_path}.station_keys.json.enc` (e.g. `xp_arc.db.station_keys.json.enc`), next to the database rather than in the repo. Override with `XP_ARC_STATION_KEY_FILE` if you need a different location. Set `XP_ARC_MASTER_KEY` to encrypt that file at rest (Fernet); without it, the loader falls back to a plaintext file at the same path with `.enc` stripped. Either way, run `run_persistent.py` / `run_kitchen.py` from a working directory you control — the key file is written relative to `--db`.
- **Aboyeur QA Key Configuration**: Default signing key is set to `"xp-arc-aboyeur-v1"` in `aboyeur.py`. This key must be changed in a secure production context (`XP_ARC_ABOYEUR_KEY`).

### API Authentication & Network Exposure

- **`--host` / `XP_ARC_HOST`**: `run_persistent.py` binds to `127.0.0.1` (loopback only) by default — unchanged from before. Pass `--host 0.0.0.0` or set `XP_ARC_HOST=0.0.0.0` to accept connections from outside the process's own machine (containers need this for a published port to reach the daemon). If you bind to `0.0.0.0` without `XP_ARC_API_KEY` set, the daemon prints an explicit warning at startup: every endpoint, including the `/ws` telemetry stream, is unauthenticated in that configuration. Bind to `0.0.0.0` only behind a trusted network boundary, with `XP_ARC_API_KEY` set.
- **`/ws` and `/metrics` now require auth** when `XP_ARC_API_KEY` is set. They used to be unconditionally exempt from `auth_middleware`, which meant `/ws` — a live feed of the full pool telemetry payload — was reachable by anyone who could reach the port even with the REST API locked down. Only `/api/health` (a credential-free liveness probe that returns no pool data) is still exempt.
- **WebSocket auth via query parameter**: browsers cannot set an `Authorization` header on a WebSocket handshake, so `/ws` additionally accepts the API key as `?token=...`. Same secret, same constant-time comparison as the `Bearer` header path — e.g. `ws://host:8089/ws?token=<XP_ARC_API_KEY>`.
- **`POST /api/seed` is rate-limited**: 30 requests per minute per client (fixed window, in-process — see `RateLimiter` in `run_persistent.py`), returning `429` with a `Retry-After` header once exceeded. This guards a single-machine daemon against a runaway script, not a distributed attacker; a real deployment behind a reverse proxy should also rate-limit there.
- **`POST /api/seed` validates the URL** before ingestion: only `http`/`https` schemes, a length cap, and the same SSRF check the Forager uses (`network_guard.public_url()`) — the endpoint cannot be used to point the brigade at an internal address. Invalid or unresolvable-to-public URLs are rejected with `400` and never reach the pool.
- **GRC stations are opt-in**: `run_kitchen.py --grc` registers `GRCSupervisor` and `GRCCommis`. Both now read their CISO Assistant token from `XP_ARC_CISO_TOKEN` at construction and raise `RuntimeError` if it is unset — there is no more hardcoded fallback token, so an unconfigured GRC station fails loudly instead of silently looking configured.

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

**Safe halt triggered**: SpaZzMatiC detected S < 0.5 for 2+ measurements. The daemon starts a 60-second veto window. If Jack does not call `kitchen.stop()` or send Ctrl+C within 60 seconds, the system halts automatically. Incoming entities are rejected (404) during safe halt state. On restart, a debt grace window is applied.

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 0.2.1 | 2026-07-21 | Consolidated 3 codebases; single pyproject.toml with extras; docs aligned |
| 0.2.0 | 2026-07-11 | 5 production gaps shipped; CI; MIT + SQLite WAL locked |
| 0.1.x | 2026-06 | Initial development |

*Last updated: 2026-07-21 — v0.2.1 deployment guide updated for consolidated repo*