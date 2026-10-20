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
│   ├── __init__.py                  # xp_arc v0.3.0
│   ├── core/
│   │   ├── pool.py                  # Intelligence Pool — SQLite WAL state machine
│   │   ├── executive.py             # Routing loop, retry budget, Brigade Compression
│   │   ├── station.py               # Base station class — all agents inherit this
│   │   ├── aboyeur.py               # QA enforcement — validates every station output
│   │   ├── fracture.py              # Cognitive sharding — task decomposition protocol
│   │   ├── authorization.py         # HMAC write auth + capability tokens
│   │   ├── network_guard.py         # SSRF guard for outbound URLs
│   │   └── sanitization.py          # Station-id / display-name sanitizing, D2 export
│   ├── stations/
│   │   ├── forager.py               # Seed URLs → entity extraction
│   │   ├── analyst.py               # Relationship inference (Saucier)
│   │   ├── sentinel.py              # Anomaly detection (Poissonnier)
│   │   ├── cartographer.py          # Graph analysis — clusters, bridge nodes (Rôtisseur)
│   │   ├── librarian.py             # Per-seed intelligence reports (Pâtissier)
│   │   ├── dossier.py               # Final dossier assembly (Garde Manger)
│   │   ├── plongeur.py              # Cleanup — orphan recovery, GC sweeps
│   │   ├── amphithere.py            # DNS enrichment
│   │   ├── hydra.py                 # Pattern recognition
│   │   ├── salamander.py            # Entity normalizer + deduplicator
│   │   ├── warden.py                # Threat and risk scoring
│   │   ├── herald.py                # Alert and notification engine
│   │   ├── auditor.py               # Constitutional compliance checks
│   │   ├── chef_de_cuisine.py       # Escalation station (survives Brigade Compression)
│   │   ├── grc_supervisor.py        # Opt-in: CISO Assistant GRC integration (--grc)
│   │   └── grc_commis.py            # Opt-in: read-only GRC fallback (--grc)
│   ├── monitoring/
│   │   ├── zorans_law.py            # Stability metrics — S quotient + PRO
│   │   └── spazzmatic.py            # Adversarial review — rule-based (not LLM-backed)
│   ├── asset_engine/                # Subpackage: SKELETON (config loader only; see STATUS.md)
│   └── competitive_intel/           # Subpackage: competitive landscape + weekly digest
│       ├── station.py               # Standalone async pipeline + CLI (station_main.py)
│       ├── fetchers.py              # PyPI / npm / RSS / Hacker News fetchers
│       ├── versioning.py            # Version parsing + release classification
│       ├── digest.py                # AI Agent Ecosystem Weekly digest builder
│       ├── detection.py             # Gap detection
│       ├── bridge.py                # One-way bridge: findings → Intelligence Pool
│       └── analyst.py               # Pool station that consumes bridged gaps
├── dragon/                          # DRAGON web dashboard
│   ├── index.html                   # Live visualization of Intelligence Pool
│   └── vendor/                      # Vendored D3 7.9.0 (served at /vendor; no CDN)
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
├── scripts/                         # weekly_digest.py, competitive_acceptance_run.py
├── run_kitchen.py                   # CLI entry point (orchestration core)
├── run_persistent.py                # Persistent server + DRAGON exporter
├── WHITEPAPER.md                    # Full protocol specification (v0.2)
├── CONSTITUTION.MD                  # Operational law (v1.9)
├── LEGAL.md                         # Legal framework and operator responsibilities
├── ARCHITECTURE.md                  # Canonical architecture spec
├── STATUS.md                        # Code status map (active/legacy/obsolete)
├── DEPLOY.md                        # Deployment guide
├── docs/
│   ├── aboyeur-protocol-v1.json     # QA protocol schema
│   ├── audits/                      # Dated audits with fix status
│   └── RELEASING.md                 # Release runbook
└── tests/
    └── test_*.py                    # 212 tests; see tests/README.md
```

## Quick Start

```bash
# Clone and install core
git clone https://github.com/unklejack/xp-arc.git
cd xp-arc
pip install -e .

# Configure the Aboyeur signing key (use a managed secret in production)
export XP_ARC_ABOYEUR_KEY='replace-with-a-long-random-secret'

# Run default 5-target spread
python run_kitchen.py

# Optional: also start the GRC stations (needs XP_ARC_CISO_TOKEN)
python run_kitchen.py --grc

# Serve the local DRAGON dashboard and observation API
python run_persistent.py --port 8089
# Open http://127.0.0.1:8089/ in a browser

# Custom targets
python run_kitchen.py https://example.com https://news.ycombinator.com

# With asset engine extras
pip install -e .[asset-engine]

# With competitive intel extras
pip install -e .[competitive-intel]

# Everything
pip install -e .[all]
```

## Try It: AI Agent Ecosystem Weekly

A working product built on XP-Arc's competitive-intel station: a weekly digest
of what shipped across 18 AI-agent frameworks (LangChain, LangGraph, CrewAI,
AutoGen, Vercel AI SDK and more). It uses PyPI, npm, RSS and Hacker News, and
no API keys.

```bash
pip install -e ".[competitive-intel]"
python scripts/weekly_digest.py          # collect, then write reports/digest/<week>.md
```

Every label in the digest is read off registry data. Releases are classified
as major, minor, patch, pre-release, nightly or maintenance by comparing each
version with its predecessor in the package's full version list. Nothing is
inferred from keywords. The `AI Agent Ecosystem Weekly` GitHub Actions workflow
runs it every Monday and shows the digest on the run page. Edit
`config/competitive-watchlist.yaml` to track different projects.

## Three Subpackages, One Repo

| Subpackage | Install Extra | Purpose | Entry Point |
|---|---|---|---|
| `xp_arc` (core) | — | Orchestration protocol: pool, stations, monitoring | `run_kitchen.py` |
| `xp_arc.asset_engine` | `asset-engine` | **Skeleton** — config loader only; the pipeline is specified in `asset-engine/SPEC.md` but not implemented | `asset-engine/config.yaml` |
| `xp_arc.competitive_intel` | `competitive-intel` | Competitive landscape monitoring, gap detection, weekly digest | `station_main.py`, `scripts/weekly_digest.py` |

The core and competitive-intel packages share the `Intelligence Pool` (SQLite WAL) and `Aboyeur` QA gate through a one-way bridge (`competitive_intel/bridge.py`). The standalone competitive-intel station keeps its own private database.

## Recent Changes (v0.3.0)

- Removed every hosting-platform reference; `DEPLOY.md` is host-neutral
- Constitution v1.9: Zoran's Law as a windowed rate ratio, `fractured → failed` escalation exit, Chef de Cuisine station, retry budget actually enforced
- Executive commits spawned entities and edges only after QA passes; capped per entity
- DRAGON works offline (vendored D3) and behind `XP_ARC_API_KEY` (`http://host:8089/#token=KEY`); access logs redact `?token`
- Safe halt refuses new seeds while halted or in the veto window
- `scripts/weekly_digest.py` + scheduled workflow: AI Agent Ecosystem Weekly
- Removed the obsolete Write Broker (`broker.py`, `broker_client.py`) and the `broker` extra
- CI: GitHub Actions runs pytest and Bandit; the Gauntlet has its own workflow. Ruff is available in the `dev` extra but is not run in CI.
- Dated audit with per-finding status: [`docs/audits/2026-07-14.md`](docs/audits/2026-07-14.md)

## Dependencies

Python 3.10+. `pip install -e .` installs the core dependencies declared in `pyproject.toml`; "zero pip dependencies" is **not** true for the project as a whole.

| Tier | Scope | Requirements |
|------|-------|-------------|
| Core install | Pool, Executive, stations, `run_kitchen.py`, `run_persistent.py` | Python stdlib `sqlite3` plus `cryptography` (encrypted station keys in `pool.py`), `aiohttp` (daemon + API), `requests` (GRC stations), `pytz`, `certifi` |
| Asset Engine (skeleton) | `xp_arc.asset_engine.*` | `pyyaml`, `jinja2`, `sqlite-utils`, `httpx`, `openai`, `playwright`, `watchdog`, `rich`, `typer`, `pydantic`, `pydantic-settings` (`pip install -e .[asset-engine]`) |
| Competitive Intel | `xp_arc.competitive_intel.*` | `pyyaml`, `jinja2`, `feedparser`, `httpx` (`pip install -e .[competitive-intel]`) |
| Dev / Gauntlet | Tests and scans | `pytest`, `pytest-asyncio`, `bandit`, `ruff`, `mypy` (`.[dev]`, `.[gauntlet]`) |
| Visualization | DRAGON dashboard | Any modern browser. Single static page with vendored D3; no Node or CDN needed |

## The Six Coordination Primitives

| # | Primitive | Implementation | Status |
|---|---|---|---|
| 1 | Shared Pool State | `pool.py` — SQLite WAL state machine, constitutional schema | ✓ |
| 2 | Typed Routing | `executive.py` — dispatches by entity type to registered stations | ✓ |
| 3 | QA Enforcement | `aboyeur.py` — validates every output, signs approved entities | ✓ |
| 4 | Graceful Degradation | `executive.py` — Brigade Compression to critical stations | ✓ |
| 5 | Cognitive Sharding | `fracture.py` — Fracture Protocol, task decomposition | ✓ |
| 6 | Stability Measurement | `zorans_law.py` — S quotient + PRO | ✓ |

## DRAGON Dashboard

DRAGON (Dynamic Relational Asset Graph & Operations Network) visualizes the Intelligence Pool in real-time:

- Interactive entity network graph
- Station health cards
- Zoran's Law stability metrics (S quotient + PRO)
- SpaZzMatiC adversarial findings (rule-based) and safe halt alerts
- Full event timeline and Snowball cascade DAGs

Run `python run_persistent.py --port 8089` and open `http://127.0.0.1:8089/` for the live local dashboard. The static `dragon/index.html` remains available as an exported-JSON fallback.

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
- [CONSTITUTION.MD](./CONSTITUTION.MD) — Operational law (v1.9)
- [LEGAL.md](./LEGAL.md) — Legal framework and operator responsibilities
- [ARCHITECTURE.md](./ARCHITECTURE.md) — Canonical architecture spec
- [STATUS.md](./STATUS.md) — Code status map
- [DEPLOY.md](./DEPLOY.md) — Deployment guide

## License

Apache License, Version 2.0. Free to use, modify, and commercially deploy the code.
Includes an express patent grant (§3) and reserves the "XP-Arc," "DRAGON," "Aboyeur,"
"Zoran's Law," and "SpaZzMatiC" names as trademarks (§6) — see [NOTICE](./NOTICE) for
what that reservation means for certified/official implementations.

**Version:** 0.3.0
**Author:** David J. Riedl (UnkleJack)
**Repository:** github.com/unklejack/xp-arc
