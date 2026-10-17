# XP-Arc Deployment Guide

## Overview

This guide covers installing XP-Arc on a single Linux or macOS machine, running
the one-shot pipeline, and running the persistent daemon that serves the DRAGON
dashboard and the HTTP API.

```
┌──────────────────────────────────────────────────────┐
│  run_persistent.py  (one Python process)             │
│                                                      │
│   brigade loop ──writes──▶ xp_arc.db (SQLite WAL)    │
│        │                        ▲                    │
│        ▼                        │ reads              │
│   aiohttp server ───────────────┘                    │
│     /            DRAGON dashboard (dragon/index.html)│
│     /ws          live telemetry (WebSocket)          │
│     /api/dragon  full pool state (JSON)              │
│     /api/seed    seed ingestion (POST)               │
│     /api/health  liveness probe                      │
│     /metrics     Prometheus counters                 │
└──────────────────────────────────────────────────────┘
```

The daemon is the only writer. Anything else that wants pool data should use the
HTTP API, or open the SQLite file read-only.

---

## Installation

```bash
git clone https://github.com/unklejack/xp-arc.git
cd xp-arc
./install.sh            # core; or: ./install.sh all | competitive-intel | gauntlet
```

Python 3.10+ is required. The core depends on `cryptography` (station key
encryption at rest) and `aiohttp` (daemon); see `pyproject.toml`.

### Required and recommended environment

| Variable | Required | Purpose |
|---|---|---|
| `XP_ARC_ABOYEUR_KEY` | **Yes** | Aboyeur signing secret. There is no default; the pipeline refuses to start without it. |
| `XP_ARC_MASTER_KEY` | Strongly recommended | Encrypts the station key file at rest. Without it, station keys are written in **plaintext** next to the database. |
| `XP_ARC_API_KEY` | Required off-loopback | Bearer token for the daemon API. |
| `XP_ARC_HOST` | No | Bind address for the daemon (default `127.0.0.1`). |
| `XP_ARC_CISO_TOKEN` | Only with `--grc` | Credential for the opt-in GRC stations. |
| `XP_ARC_LOG_LEVEL` | No | `DEBUG`, `INFO` (default), `WARNING`, `ERROR`. |
| `XP_ARC_LOG` | No | Log file path. Logs go to stdout when unset. |

```bash
export XP_ARC_ABOYEUR_KEY="$(python3 -c 'import secrets;print(secrets.token_hex(32))')"
export XP_ARC_MASTER_KEY="$(python3 -c 'import secrets;print(secrets.token_hex(32))')"
```

Keep both values somewhere durable. A new `XP_ARC_MASTER_KEY` cannot decrypt a
key file written under the old one.

---

## Running

### One-shot pipeline

```bash
python3 run_kitchen.py --db xp_arc.db https://example.com
```

With no targets, a default five-target spread is used. Add `--grc` to register
the GRC stations (requires `XP_ARC_CISO_TOKEN`). The run prints the corkboard and
writes a DRAGON export to `xp_arc_dragon.json`.

### Persistent daemon

```bash
python3 run_persistent.py --db xp_arc.db --port 8089
# open http://127.0.0.1:8089/
```

Run it in the background with `./start.sh`, `nohup`, or a process manager. The
daemon handles `SIGTERM`; under systemd set `KillSignal=SIGTERM` and a
`TimeoutStopSec=`.

For a containerized deployment (Dockerfile, docker-compose, PyPI release
workflow), see `docs/RELEASING.md`. The Docker image build has been desk-checked
but not yet executed in CI.

### Seeding URLs into the daemon

```bash
curl -X POST http://127.0.0.1:8089/api/seed \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'

# or
./seed.sh https://example.com
```

---

## Optional Subpackages

| Subpackage | Install | Purpose |
|---|---|---|
| Core | `pip install -e .` | Pool, stations, monitoring, daemon |
| Competitive Intel | `pip install -e .[competitive-intel]` | Watchlist monitoring, gap detection, weekly report |
| Asset Engine | `pip install -e .[asset-engine]` | **Skeleton only**; see STATUS.md |
| Gauntlet | `pip install -e .[gauntlet]` | Adversarial test harness (`xp-arc-gauntlet`) |
| Everything | `pip install -e .[all]` | All of the above |

---

## Persistent Daemon HTTP API (`run_persistent.py`)

#### `POST /api/seed`
Injects a new seed entity into the pool.
- **Request Body**: `{"url": "https://example.com"}`
- **Response**: `{"status": "success", "id": <entity_id>}`, `{"status": "duplicate"}`, or `400` with a rejection reason.

#### `GET /api/dragon`
Full pool state for DRAGON: entities, edges, stations, findings, Zoran metrics,
events, dossiers, audit and topology.

#### `GET /ws`
WebSocket stream of the same telemetry, pushed each cycle.

#### `GET /api/health`
Credential-free liveness probe. Returns no pool data.

#### `GET /metrics`
Prometheus text format: `xp_arc_entities_total` and `xp_arc_entities_completed`.

### Authentication and network exposure

- **Bind address:** loopback (`127.0.0.1`) by default. `--host 0.0.0.0` or
  `XP_ARC_HOST=0.0.0.0` accepts outside connections; the daemon warns at startup
  if that is done without `XP_ARC_API_KEY`.
- **API key:** when `XP_ARC_API_KEY` is set, every endpoint except `/api/health`
  requires `Authorization: Bearer <key>`. `/ws` also accepts `?token=<key>`,
  because browsers cannot set headers on a WebSocket handshake.
- **Seed validation:** `POST /api/seed` accepts only `http`/`https`, caps URL
  length at 2048, and rejects URLs that do not resolve to public addresses (the
  same SSRF guard the Forager uses).
- **Rate limit:** `POST /api/seed` allows 30 requests per minute per client and
  returns `429` with `Retry-After` beyond that.

Run behind a TLS-terminating reverse proxy for anything beyond loopback; see
`SECURITY.md`.

### Key files

Each Pool stores station HMAC keys beside its database at
`{db_path}.station_keys.json.enc` (override with `XP_ARC_STATION_KEY_FILE`). The
file is encrypted when `XP_ARC_MASTER_KEY` is set, and plaintext at the same path
minus `.enc` otherwise. These files are gitignored; never commit them.

---

## DRAGON Dashboard

### Live mode
Open `http://127.0.0.1:8089/` while the daemon runs. The page connects to `/ws`
and falls back to polling `/api/dragon`. D3 is vendored in `dragon/vendor/`, so
the dashboard works without internet access.

### Static mode
```bash
python3 run_kitchen.py --export-only --db xp_arc.db
cp xp_arc_dragon.json dragon/pool_state.json
```
Then open `dragon/index.html` directly in a browser.

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

## Troubleshooting

**"Aboyeur signing key not configured"**: export `XP_ARC_ABOYEUR_KEY` (see above).

**"XP_ARC_CISO_TOKEN is not set"**: you passed `--grc` without the token. Drop
`--grc` or export the token.

**"Database is locked"**: only one writer at a time. The daemon is the writer;
other readers should open the DB read-only.

**Entities stuck in "processing"**: the Plongeur sweeps orphans automatically
every 5 cycles. Force a sweep:
```bash
python3 -c "
from xp_arc.core.pool import IntelligencePool
from xp_arc.stations.plongeur import ThePlongeur
pool = IntelligencePool('xp_arc.db')
ThePlongeur(pool).run_sweep()
pool.close()
"
```

**Safe halt triggered**: SpaZzMatiC detected S < 0.5 for 2+ consecutive
measurements and opened a 60-second veto window. Stop the daemon (Ctrl+C) within
the window to veto; otherwise the system halts. New seeds are rejected during
safe halt. On restart, a debt grace window is applied.

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 0.3.0 | 2026-10 | `--grc` opt-in, vendored D3, deployment guide made host-neutral |
| 0.2.1 | 2026-07-21 | Consolidated 3 codebases; single pyproject.toml with extras |
| 0.2.0 | 2026-07-11 | 5 production gaps shipped; CI; SQLite WAL locked |
| 0.1.x | 2026-06 | Initial development |
