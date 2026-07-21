# XP-Arc Project Status
*Implemented, Pending, and Obsolete Protocol Features*

This document tracks the engineering status of all features described in the XP-Arc Whitepaper, Constitution, and developer notes. Rebuilders should consult this file before implementing components to ensure they do not write obsolete patterns.

---

## 1. Implementation Matrix

| Protocol Component | Spec Status | Code Location | Production Status | Notes |
|---|---|---|---|---|
| **Intelligence Pool (WAL)** | Core | `xp_arc/core/pool.py` | **SHIPPED** | Standard SQLite WAL backing. |
| **Typed Routing** | Core | `xp_arc/core/executive.py` | **SHIPPED** | Handled by `ExecutiveChef`. |
| **Aboyeur QA Validation** | Core | `xp_arc/core/aboyeur.py` | **SHIPPED** | Schema validation, confidence gates. |
| **HMAC Pool Authentication**| Security | `xp_arc/core/pool.py` | **SHIPPED** | Verifies station signatures on write. |
| **Cognitive Sharding** | Core | `xp_arc/core/fracture.py` | **SHIPPED** | Micro-shard spawning and stitching. |
| **Lineage Tracking** | Core | `xp_arc/core/pool.py` | **SHIPPED** | Automatic ancestor tracking. |
| **Zoran's Law (S & PRO)** | Monitoring | `xp_arc/monitoring/zorans_law.py`| **SHIPPED** | SLA-weighted stability quotients. |
| **Adversarial Review** | Monitoring | `xp_arc/monitoring/spazzmatic.py`| **SHIPPED** | Rule-based monitoring. |
| **Brigade Compression** | Core | `xp_arc/core/executive.py` | **SHIPPED** | Degrades to critical stations. |
| **Persistent Daemon** | Deployment | `run_persistent.py` | **SHIPPED** | HTTP API server for DRAGON. |
| **DRAGON Dashboard** | UI | `dragon/index.html` | **SHIPPED** | JS dashboard polling `/api/dragon`. |
| **Asset Engine** | Extension | `xp_arc/asset_engine/` | **SHIPPED** | Evolutionary asset pipeline. |
| **Competitive Intel** | Extension | `xp_arc/competitive_intel/`| **SHIPPED** | Watchlist + gap detection. |
| **Write Broker** | Obsolete | `xp_arc/broker.py` | **OBSOLETE** | *Do not implement.* |
| **DuckDB Backend** | Obsolete | — | **OBSOLETE** | *Do not implement. Use SQLite WAL.* |
| **Gemini-backed SpaZzMatiC** | Aspirational| — | **PENDING** | Current implementation is rule-based. |

---

## 2. Status of Key Architecture Modules

### 2.1 Write Broker & Redis Sequencer (`xp_arc/broker.py`)
- **Status**: **OBSOLETE / EXPERIMENTAL**.
- **Context**: The original spec required a standalone Redis-buffered queue writing to DuckDB. This was replaced by a SQLite-direct WAL state machine.
- **Guidance**: `broker.py` and its counterpart `broker_client.py` remain in the codebase as legacy or experimental endpoints. They are **not** loaded or executed by `run_kitchen.py` or `run_persistent.py`. A rebuild from scratch should target the direct SQLite-WAL operations in `pool.py` and ignore the Broker.

### 2.2 SpaZzMatiC Adversarial Review (`xp_arc/monitoring/spazzmatic.py`)
- **Status**: **ACTIVE (RULE-BASED)**.
- **Context**: The README and Whitepaper refer to SpaZzMatiC as an "LLM-backed (Gemini) adversarial authority."
- **Guidance**: The actual implementation is entirely rule-based (analyzing S metrics, orphan count, status violations). Rebuilders should write a deterministic, rule-based checker matching `spazzmatic.py`. LLM evaluations are proposed future expansions.

### 2.3 DuckDB Pool Backend
- **Status**: **OBSOLETE**.
- **Guidance**: DuckDB is not used in the reference implementation. The project uses standard library `sqlite3` exclusively to eliminate pip dependency footprints.

### 2.4 D2 Graph Exporters (`xp_arc/core/sanitization.py`)
- **Status**: **EXPERIMENTAL**.
- **Guidance**: These functions exist to export structural graphs into D2 markup files. They are not currently active in the DRAGON runtime dashboard loop, which consumes standard JSON representations.

### 2.5 Asset Engine (`xp_arc/asset_engine/`)
- **Status**: **SHIPPED (v0.1.0)**.
- **Scope**: Evolutionary asset generation with human-in-the-loop curation. Subpackage under `xp_arc.asset_engine`.
- **Dependencies**: `pyyaml`, `jinja2`, `sqlite-utils`, `httpx`, `openai`, `playwright`, `watchdog`, `rich`, `typer`, `pydantic`, `pydantic-settings`.
- **Install**: `pip install -e .[asset-engine]`
- **Key Files**: `SPEC.md`, `PROMPT_LIBRARY.md`, `FILTER_SAFE_PROMPTS.md` at repo root.

### 2.6 Competitive Intelligence (`xp_arc/competitive_intel/`)
- **Status**: **SHIPPED (v0.1.0)**.
- **Scope**: Watchlist monitoring, gap detection, weekly reports. Subpackage under `xp_arc.competitive_intel`.
- **Dependencies**: `pyyaml`, `jinja2`.
- **Install**: `pip install -e .[competitive-intel]`
- **Config**: `config/competitive-intelligence-station.yaml`, `config/competitive-watchlist.yaml`
- **Schema**: `sql/competitive-gaps-schema.sql`
- **Output**: `reports/competitive/weekly-report.md` (via template)

---

## 3. Code Status Map

| File | Status | Notes |
|---|---|---|
| `xp_arc/core/pool.py` | **SHIPPED** | Canonical WAL state machine |
| `xp_arc/core/executive.py` | **SHIPPED** | Typed routing |
| `xp_arc/core/aboyeur.py` | **SHIPPED** | QA + signatures |
| `xp_arc/core/fracture.py` | **SHIPPED** | Cognitive sharding |
| `xp_arc/core/authorization.py` | **SHIPPED** | HMAC auth |
| `xp_arc/core/sanitization.py` | **EXPERIMENTAL** | D2 export |
| `xp_arc/broker.py` | **OBSOLETE** | Legacy |
| `xp_arc/broker_client.py` | **OBSOLETE** | Legacy |
| `xp_arc/stations/*.py` (13 files) | **SHIPPED** | All core stations |
| `xp_arc/asset_engine/__init__.py` | **SHIPPED** | Subpackage marker |
| `xp_arc/asset_engine/*` | **SHIPPED** | Asset pipeline modules |
| `xp_arc/competitive_intel/__init__.py` | **SHIPPED** | Subpackage marker |
| `xp_arc/competitive_intel/*.py` | **SHIPPED** | Intel modules |
| `run_kitchen.py` | **SHIPPED** | One-shot runner |
| `run_persistent.py` | **SHIPPED** | Daemon + API |
| `dragon/index.html` | **SHIPPED** | Dashboard |

---

## 4. Consolidation Notes (v0.2.1)

**Date**: 2026-07-21  
**Commit**: post-`99e527d` (MIT + SQLite WAL alignment)

### What changed
- **Three codebases → one**: `asset-engine/`, `competitive_intel/`, and `xp_arc/` merged under single `xp_arc/` package
- **Single `pyproject.toml`**: All optional dependencies declared as extras (`[asset-engine]`, `[competitive-intel]`, `[broker]`, `[all]`)
- **Runtime artifacts ignored**: `.gitignore` excludes `asset-engine/browser-profiles/`, `asset-engine/generation-runs/`, `asset-engine/logs/`, `asset-engine/review-vault/`, `data/competitive/`, `reports/competitive/`
- **Docs consolidated**: `SPEC.md`, `PROMPT_LIBRARY.md`, `FILTER_SAFE_PROMPTS.md` moved to repo root; `asset-engine/` dir now docs-only
- **Version bump**: 0.2.0 → 0.2.1 (patch = structural consolidation, no API changes)

### Migration for consumers
```bash
# Old: separate installs (never worked cleanly)
pip install -e ./asset-engine
pip install -e .

# New: single install with extras
pip install -e .[asset-engine,competitive-intel]
# or
pip install -e .[all]
```

```python
# Old imports (broken)
from asset_engine.config import ...
from competitive_intel.station import ...

# New imports (work)
from xp_arc.asset_engine.config import ...
from xp_arc.competitive_intel.station import ...
```

---

*Last updated: 2026-07-21 — v0.2.1 consolidation complete*