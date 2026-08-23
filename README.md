[![CI](https://github.com/unklejack/xp-arc/actions/workflows/ci.yml/badge.svg)](https://github.com/unklejack/xp-arc/actions/workflows/ci.yml)

# XP-Arc

**A Unified Protocol for Resilient Multi-Agent Intelligence Systems**

> [!IMPORTANT]
> **Building from Scratch?**
> If you are setting up or rebuilding XP-Arc from scratch:
> - Read the [ARCHITECTURE.md](ARCHITECTURE.md) to understand the canonical spec, schemas, state flow, and station registries.
> - Read the [STATUS.md](STATUS.md) to distinguish active code from legacy, experimental, or obsolete ideas.

XP-Arc — Exponential Architecture — is an open protocol defining the contract between multi-agent systems: a shared state surface, a QA enforcement layer, a graceful degradation model, a task fracturing protocol for primary agent failure, and a stability metric that tells operators whether their system is coherent or drifting.

## The Kitchen That Thinks

Inspired by Escoffier's kitchen brigade system, XP-Arc orchestrates AI agents through a shared `Intelligence Pool` rather than ad-hoc chaining. Every agent reads from and writes back to the Pool. No station talks directly to another. The Pool is the message bus, the event queue, the audit log, and the ground truth — simultaneously.

## Architecture

```
xp-arc/
├── xp_arc/                          # Core Python package (install: pip install -e .)
│   ├── __init__.py                  # xp_arc v0.2.0
│   ├── core/
│   │   ├── pool.py                  # Intelligence Pool — SQLite WAL state machine
│   │   ├── executive.py             # Routing loop — reads raw, dispatches by type
│   │   ├── station.py               # Base station class — all agents inherit this
│   │   ├── aboyeur.py               # QA enforcement — validates every station output
│   │   ├── fracture.py              # Cognitive sharding — task decomposition protocol
│   │   ├── authorization.py         # HMAC write auth + capability tokens
│   │   └── sanitization.py          # Input/output sanitization pipeline
│   ├── stations/
│   │   ├── forager.py               # DOM scraping — seed URLs → entity extraction
│   │   ├── analyst.py               # Relationship inference — domain classification + edges
│   │   ├── sentinel.py              # Anomaly detection — pool health monitoring
│   │   ├── plongeur.py              # Cleanup — orphan recovery, GC sweeps
│   │   ├── dossier.py               # Entity profiling + enrichment
│   │   ├── warden.py                # Access control + rate limiting
│   │   ├── herald.py                # Notification + webhook dispatch
│   │   ├── hydra.py                 # Multi-headed concurrent execution
│   │   ├── salamander.py            # Regenerative station — self-healing patterns
│   │   ├── amphithere.py            # Cross-pool synchronization
│   │   ├── auditor.py               # Compliance + audit trail
│   │   ├── cartographer.py          # Topology mapping + drift detection
│   │   └── __init__.py
│   ├── monitoring/
│   │   ├── zorans_law.py            # Stability metrics — S quotient + PRO
│   │   ├── spazzmatic.py            # Adversarial review — Gemini-backed QA authority
│   │   └── __init__.py
│   ├── broker.py                    # Redis-buffered write sequencer + hot standby
│   ├── broker_client.py             # Client interface for remote broker
│   ├── asset_engine/                # Subpackage: Evolutionary asset generation
│   │   ├── __init__.py              # asset_engine v0.1.0
│   │   ├── api_agent/               # LLM API integration layer
│   │   ├── asset_store/             # SQLite-backed asset versioning
│   │   ├── browser_agent/           # Playwright automation
│   │   ├── concepts/                # Concept graph + evolution
│   │   ├── config.py                # Config loader (config.yaml)
│   │   ├── evolution/               # Genetic operators + selection
│   │   ├── prompt_engine/           # Prompt templating + optimization
│   │   ├── style_genomes/           # Style encoding + inheritance
│   │   ├── templates/               # Jinja2 asset templates
│   │   ├── themes/                  # Theme definitions + mutation
│   │   └── unity_pipeline/          # Unity Editor + Addressables export
│   ├── competitive_intel/           # Subpackage: Competitive landscape monitoring
│   │   ├── __init__.py
│   │   ├── station.py               # Core station implementation
│   │   ├── config.py                # YAML config loader
│   │   └── station_main.py          # CLI entry point
│   └── __init__.py
├── dragon/                          # DRAGON web dashboard
│   ├── index.html                   # Live visualization of Intelligence Pool
│   └── pool_state.json              # Exported pipeline state
├── config/                          # Station YAML configs
│   ├── competitive-intelligence-station.yaml
│   └── competitive-watchlist.yaml
├── specs/                           # Spec documents (machine-readable)
│   └── competitive-intelligence-station.yaml
├── sql/                             # Schema definitions
│   └── competitive-gaps-schema.sql
├── templates/                       # Report templates
│   └── competitive-weekly-report.md
├── asset-engine/                    # Asset engine support files (gitignored runtime dirs)
│   ├── SPEC.md                      # Asset Engine specification
│   ├── PROMPT_LIBRARY.md            # Curated prompt library
│   ├── FILTER_SAFE_PROMPTS.md       # Safety-filtered prompt set
│   └── config.yaml                  # Runtime config template
├── run_kitchen.py                   # CLI entry point (orchestration core)
├── run_persistent.py                # Persistent server + DRAGON exporter
├── WHITEPAPER.md                    # Full protocol specification (v0.2)
├── CONSTITUTION.MD                  # Operational law (v1.4)
├── LEGAL.md                         # Legal framework and operator responsibilities
├── ARCHITECTURE.md                  # Canonical architecture spec
├── STATUS.md                        # Code status map (active/legacy/obsolete)
├── DEPLOY.md                        # Deployment guide
├── docs/
│   ├── aboyeur-protocol-v1.json     # QA protocol schema
│   └── advanced.md                  # Advanced topics
└── tests/
    └── test_basic.py, test_load.py  # Unit + load tests
```

## Quick Start

```bash
# Clone and install core
git clone https://github.com/unklejack/xp-arc.git
cd xp-arc
pip install -e .

# Run default 5-target spread
python run_kitchen.py

# Custom targets
python run_kitchen.py https://example.com https://news.ycombinator.com

# With asset engine extras
pip install -e .[asset-engine]

# With competitive intel extras
pip install -e .[competitive-intel]

# Everything (broker + asset-engine + competitive-intel)
pip install -e .[all]
```

## Three Subpackages, One Repo

| Subpackage | Install Extra | Purpose | Entry Point |
|---|---|---|---|
| `xp_arc` (core) | — | Orchestration protocol: pool, stations, broker, monitoring | `run_kitchen.py` |
| `xp_arc.asset_engine` | `asset-engine` | Evolutionary asset generation with human-in-the-loop curation | `asset-engine/config.yaml` |
| `xp_arc.competitive_intel` | `competitive-intel` | Competitive landscape monitoring, gap detection, weekly reports | `station_main.py` |

All three share the same `Intelligence Pool` (SQLite WAL) and `Aboyeur` QA gate. They don't talk to each other — they write to the Pool, independently or in concert, it's the same contract.

## Recent Changes (v0.2.1)

- Consolidated three independent codebases into single repo with three subpackages under `xp_arc/`
- Single `pyproject.toml` with optional dependency groups: `broker`, `asset-engine`, `competitive-intel`, `all`
- Asset Engine: SPEC.md, PROMPT_LIBRARY.md, FILTER_SAFE_PROMPTS.md at repo root
- Competitive Intel: watchlist config, gap schema, weekly report template
- CI: GitHub Actions (tests + Bandit + Ruff)
- Docs: ARCHITECTURE.md, STATUS.md, WHITEPAPER.md, CONSTITUTION.MD all aligned with v0.2 reality

## Dependencies

| Tier | Scope | Requirements |
|------|-------|-------------|
| Orchestration core | `pool.py`, `station.py`, `executive.py`, `fracture.py` | Python 3 stdlib only — SQLite built in, zero pip deps |
| Broker (optional) | `broker.py`, `broker_client.py` | `redis` (via `pip install -e .[broker]`) |
| Asset Engine | `xp_arc.asset_engine.*` | `pyyaml`, `jinja2`, `sqlite-utils`, `httpx`, `openai`, `playwright`, `watchdog`, `rich`, `typer`, `pydantic` (via `pip install -e .[asset-engine]`) |
| Competitive Intel | `xp_arc.competitive_intel.*` | `pyyaml`, `jinja2` (via `pip install -e .[competitive-intel]`) |
| Full deployment | Production runtime | Python 3.10+, standard library `sqlite3` |
| Visualization | DRAGON dashboard | Any modern browser (static `pool_state.json` or live via `run_persistent.py`) |

## The Six Coordination Primitives

| # | Primitive | Implementation | Status |
|---|---|---|---|
| 1 | Shared Pool State | `pool.py` — SQLite WAL state machine, constitutional schema | ✓ |
| 2 | Typed Routing | `executive.py` — dispatches by entity type to registered stations | ✓ |
| 3 | QA Enforcement | `aboyeur.py` — validates every output, signs approved entities | ✓ |
| 4 | Graceful Degradation | Brigade Compression fallback roles | Spec'd |
| 5 | Cognitive Sharding | Fracture Protocol — task decomposition | Spec'd |
| 6 | Stability Measurement | `zorans_law.py` — S quotient + PRO | ✓ |

## DRAGON Dashboard

DRAGON (Dynamic Relational Asset Graph & Operations Network) visualizes the Intelligence Pool in real-time:

- Interactive entity network graph
- Station health cards
- Zoran's Law stability metrics (S quotient + PRO)
- SpaZzMatiC adversarial findings and safe halt alerts
- Full event timeline and Snowball cascade DAGs

Open `dragon/index.html` in a browser after running the pipeline.

## The Aboyeur Protocol

Every station output must pass QA before propagating downstream:

```json
{
  "station_id": "string",
  "entity_id": "integer",
  "timestamp": "ISO 8601",
  "status": "mapped | unhandled | rejected",
  "payload_hash": "SHA-256 of output payload",
  "output": {
    "entity_type": "string",
    "entity_value": "string",
    "relationships": ["array of related entity IDs"],
    "confidence": "float 0.0–1.0",
    "notes": "string"
  },
  "fallback_activated": "boolean",
  "aboyeur_signature": "ABOY-{hash}"
}
```

Full schema: [`docs/aboyeur-protocol-v1.json`](./docs/aboyeur-protocol-v1.json)

## Positioning

XP-Arc is not a communication protocol (that's A2A). It is not a tool-access protocol (that's MCP). It is the orchestration layer above them both — the shared Intelligence Pool that any agent writes to, the QA gate that validates what they produce, and the stability signal that tells operators when the system is drifting.

An A2A-compliant agent can be registered as an XP-Arc station. An MCP server can be wrapped as a Forager. The pool doesn't care what protocol the station uses internally.

See [WHITEPAPER.md §2](./WHITEPAPER.md) for the full positioning argument.

## Documentation

- [WHITEPAPER.md](./WHITEPAPER.md) — Full protocol specification (v0.2)
- [CONSTITUTION.MD](./CONSTITUTION.MD) — Operational law (v1.6)
- [LEGAL.md](./LEGAL.md) — Legal framework and operator responsibilities
- [ARCHITECTURE.md](./ARCHITECTURE.md) — Canonical architecture spec
- [STATUS.md](./STATUS.md) — Code status map
- [DEPLOY.md](./DEPLOY.md) — Deployment guide

## License

Apache License 2.0. Free to use for any purpose including commercial production,
with an express patent grant. See `NOTICE` — "XP-Arc," "DRAGON," "Aboyeur,"
"Zoran's Law," and "SpaZzMatiC" are reserved trademarks; the code is unrestricted,
using these names to claim official/certified status is not.

**Version:** 0.2.1
**Author:** David J. Riedl (UnkleJack)
**Repository:** github.com/unklejack/xp-arc