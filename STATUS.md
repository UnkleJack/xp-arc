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
| **Zoran's Law (S & PRO)** | Monitoring | `xp_arc/monitoring/zorans_law.py`| **SHIPPED** | Windowed rate ratio (Article VIII 8.4), not a cumulative ratio. `S > 1.0` (HEALTHY) is now reachable — see §5.1. |
| **Adversarial Review** | Monitoring | `xp_arc/monitoring/spazzmatic.py`| **SHIPPED** | Rule-based monitoring. |
| **Brigade Compression** | Core | `xp_arc/core/executive.py` | **SHIPPED** | Degrades to critical stations. `chef_de_cuisine` is now one of the survivors — see §5.3. |
| **Article I 1.2 Retry Budget** | Core | `xp_arc/core/executive.py` | **SHIPPED** | `_qa_gate_with_retry()`. Previously never ran for any entity — see §5.2. |
| **Escalation Station (Chef de Cuisine)** | Core | `xp_arc/stations/chef_de_cuisine.py` | **SHIPPED** | New in `5c67e42`; did not exist before. CRITICAL, survives Brigade Compression. |
| **Persistent Daemon** | Deployment | `run_persistent.py` | **SHIPPED** | HTTP API server for DRAGON. `--host`/`XP_ARC_HOST`, `/ws` + `/metrics` auth, `/api/seed` validation + rate limiting added — see §5.4. |
| **DRAGON Dashboard** | UI | `dragon/index.html` | **SHIPPED** | JS dashboard polling `/api/dragon`. |
|| **Asset Engine** | Extension | `xp_arc/asset_engine/` | **SKELETON** | Not shipped. `xp_arc/asset_engine/` currently contains only `__init__.py` (6 lines) and `config.py` (93 lines) plus empty-looking subdirectories (`api_agent/`, `asset_store/`, `browser_agent/`, `evolution/`, etc.) — no working pipeline code was found. This row previously said SHIPPED with "evolutionary asset pipeline"; that claim was not verifiable by reading the code in this clone, so it is corrected here. Verify independently before relying on it. ||
|| **Competitive Intel** | Extension | `xp_arc/competitive_intel/`| **SHIPPED** | Watchlist + gap detection, and, new in `59b98c1`, a one-way bridge that republishes findings into the Intelligence Pool — see §5.5. ||
|| **GRC Supervisor** | Extension | `xp_arc/stations/grc_supervisor.py` | **SHIPPED** | CISO Assistant write integration (assets, applied-controls, incidents, reference-controls, evidences, compliance-assessments). Opt-in via `run_kitchen.py --grc`; requires `XP_ARC_CISO_TOKEN` (hardcoded fallback token removed) — see §5.6. ||
|| **GRC Commis** | Extension | `xp_arc/stations/grc_commis.py` | **SHIPPED** | CISO Assistant read-only validation + audit exports. Same opt-in / token requirement as GRC Supervisor. ||
|| **Write Broker** | Obsolete | `xp_arc/broker.py` | **OBSOLETE** | *Do not implement.* Still present in the tree despite the removal ruling — see §6. ||
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
- **Status**: **SKELETON, NOT SHIPPED.** (Corrected — see note below.)
- **Scope**: Package structure exists (`api_agent/`, `asset_store/`, `browser_agent/`, `concepts/`, `evolution/`, `prompt_engine/`, `style_genomes/`, `templates/`, `themes/`, `unity_pipeline/`), but the only Python files present are `__init__.py` (6 lines) and `config.py` (93 lines). There is no verified pipeline code behind the subdirectory names.
- **Correction note**: this section previously read "SHIPPED (v0.1.0) — Evolutionary asset generation with human-in-the-loop curation." That was not corroborated by reading the code in this clone and has been walked back. Do not treat this subpackage as functional until someone has read the actual module contents and confirmed otherwise.
- **Dependencies (as declared in `pyproject.toml` extras, not verified as exercised by working code)**: `pyyaml`, `jinja2`, `sqlite-utils`, `httpx`, `openai`, `playwright`, `watchdog`, `rich`, `typer`, `pydantic`, `pydantic-settings`.
- **Install**: `pip install -e .[asset-engine]`
- **Key Files**: `SPEC.md`, `PROMPT_LIBRARY.md`, `FILTER_SAFE_PROMPTS.md` at repo root.

### 2.6 Competitive Intelligence (`xp_arc/competitive_intel/`)
- **Status**: **SHIPPED (v0.1.0)**, plus a new pool bridge as of `59b98c1`.
- **Scope**: Watchlist monitoring, gap detection, weekly reports. Subpackage under `xp_arc.competitive_intel`. `CompetitiveIntelStation` remains standalone — its own async pipeline, its own private SQLite database, its own CLI — by deliberate design (Dragon's dual-path ruling), not an oversight.
- **New — the bridge (`xp_arc/competitive_intel/bridge.py`, `analyst.py`)**: `CompetitiveIntelBridge` is a one-way adapter (competitive DB -> pool, never the reverse) that republishes open gaps as `competitive_gap` entities in the Intelligence Pool, where `CompetitiveGapAnalyst` (an ordinary `StationChef`) picks them up. Once bridged, a gap gets HMAC-signed writes, the mandatory Aboyeur QA gate, lineage tracking, and Zoran measurement — the same as any other pool entity. Capped at `MAX_GAPS_PER_SCAN = 50` per scan, dropping the least-severe gaps first if exceeded, not the tail. `snapshot_competitor()` (previously a stub that logged and stored nothing) is now implemented, assembled from watchlist + already-collected `raw_events` data with no additional network fetch.
- **Acceptance run**: `scripts/competitive_acceptance_run.py` runs this path against live external sources and gates on nine stages (fetch -> detect -> snapshot -> bridge -> route -> Aboyeur seal -> Zoran -> DRAGON export, plus an RT-11 check that no HMAC key leaks into the export). Per the `59b98c1` commit message, it was executed this session and all nine gates passed: 149 real events fetched, 11 gaps published, 11/11 entities Aboyeur-signed, 0 unhandled, S = 1.0 / PRO 100% / state `equilibrium`, 0 leaked HMAC keys. This is stated in the commit message as the run's own report, not independently re-run as part of this documentation pass — the tests in `tests/test_competitive_bridge.py` (10 network-free test functions counted directly in this pass, not the 11 the commit message states — a minor discrepancy, noted rather than silently corrected) are what this doc pass confirmed still pass (see §5.5/§7). Note the commit's own honest caveat: this run does not demonstrate `S > 1` (draining pre-existing backlog), because all 11 entities were ingested and completed inside the same 60-second window — that scenario is covered by unit tests instead.
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
| `xp_arc/core/sanitization.py` | **EXPERIMENTAL** | D2 export; also now home to `sanitize_station_id()` / `sanitize_display_name()` (station-id injection hardening, `5c67e42`) |
| `xp_arc/broker.py` | **OBSOLETE** | Legacy. Still present despite the removal ruling — see §6. |
| `xp_arc/broker_client.py` | **OBSOLETE** | Legacy. Still present despite the removal ruling — see §6. |
| `xp_arc/stations/*.py` (17 files) | **SHIPPED** | All core stations, including `chef_de_cuisine.py` (new, `5c67e42`) |
| `xp_arc/asset_engine/__init__.py` | **SHIPPED** | Subpackage marker only |
| `xp_arc/asset_engine/*` | **SKELETON** | Only `config.py` has content; see §2.5. Previously listed SHIPPED — corrected. |
| `xp_arc/competitive_intel/__init__.py` | **SHIPPED** | Subpackage marker |
| `xp_arc/competitive_intel/*.py` | **SHIPPED** | Intel modules, plus new `bridge.py` and `analyst.py` (`59b98c1`) — see §2.6 |
| `scripts/competitive_acceptance_run.py` | **SHIPPED** | New (`59b98c1`). Live-source acceptance gate for the competitive-intel bridge. |
| `run_kitchen.py` | **SHIPPED** | One-shot runner. `--grc` flag added (`5c67e42`) to opt into GRC stations. |
| `run_persistent.py` | **SHIPPED** | Daemon + API. `--host`/`XP_ARC_HOST`, `/ws`+`/metrics` auth, `/api/seed` validation + rate limit added (`5c67e42`). |
| `Dockerfile`, `docker-compose.yml`, `.github/workflows/release.yml`, `docs/RELEASING.md` | **SHIPPED (BUILD NOT EXECUTED FOR IMAGE)** | New (`5c67e42`). The wheel/sdist build (`python -m build`) was run and passes. The Docker image build was NOT executed — no `docker` binary was available in the sandbox that built these files, so the image itself is desk-checked, not verified to actually build or run. |
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

## 5. Recent Engineering Changes (commits `5c67e42`, `59b98c1`)

**Date**: 2026-08-24

These two commits closed a punch list of security gaps, fixed a load-bearing math error in Zoran's Law, made the constitutional retry budget actually run, built the missing escalation station, and stood up a second (bridged) path for competitive-intel data into the pool. Full commit messages are the source of truth for rationale; this section summarizes what changed and where to verify it.

### 5.1 Zoran's Law — `S > 1.0` was mathematically unreachable

`S` was computed as *cumulative* completed SLA-seconds over *cumulative* ingested SLA-seconds (`xp_arc/monitoring/zorans_law.py`). Every completed task is also an ingested task, so the numerator was a strict subset of the denominator — `S` was bounded at `<= 1.0` by construction, no matter how healthy the brigade was. Article VIII 8.1 defines HEALTHY as `S > 1.0`, a state that was literally impossible to reach: the best any brigade could ever report was "equilibrium" (`S == 1.0`) or worse.

The fix applies Article VIII 8.4's rolling window (`DEFAULT_WINDOW_SECONDS = 60`, `MIN_WINDOW_SECONDS = 10`): `S` is now a **rate ratio** — SLA-seconds drained in the window over SLA-seconds arriving in the window (`pool.windowed_sla_flow()`). `S > 1` now means the brigade is paying down backlog faster than it arrives, which is what the Constitution says it should mean. `sla_suspended` rows are excluded from both sides. A window with zero arrivals is reported as a finite `S_MAX = 10.0` ceiling rather than infinity, so it can't poison stored metrics or DRAGON charts.

The PRO denominator was also corrected: infrastructure that registers with the pool purely to obtain an HMAC write key (the Aboyeur, the Fracture Protocol, and now the competitive-intel bridge — `ZoransLaw.NON_LABOR_STATIONS`) is excluded from the "agents in a role" count, because it isn't an agent operating in a role. Before this, the Fracture Protocol and the bridge were silently dragging PRO down and could trigger a spurious `compression_review` on an otherwise healthy brigade.

**Verify**: `xp_arc/monitoring/zorans_law.py`; `tests/test_zorans_law.py`.

### 5.2 Article I 1.2 retry budget — now actually drives retries

Before this change, the three-strike retry budget never ran for **any** entity, not just shards (it had been mis-tracked as a shard-specific gap, Article V 5.5). The Aboyeur's circuit breaker only flips an entity to `failed` once `rejection_count` reaches `max_rejections`; nothing else ever re-processed a rejected entity, so the Executive's "if not already failed, fail it" branch fired on strike one every time.

`ExecutiveChef._qa_gate_with_retry()` (`xp_arc/core/executive.py`) now transitions a rejected entity `pending_qa -> failed -> processing` and re-runs the same handler, bounded by the entity's own `rejection_count`/`max_rejections` budget and a hard ceiling `RETRY_HARD_CAP = 25` as defense in depth. A `FractureRequest` raised during a retry attempt is returned to the caller (not re-raised) and handled by the same `_handle_fracture_request()` path used for first-attempt fractures.

**Verify**: `xp_arc/core/executive.py` (`_qa_gate_with_retry`, `_handle_fracture_request`); `tests/test_retry_and_escalation.py`.

### 5.3 Stranded fracture detection + the Chef de Cuisine

`FractureProtocol.create_shards()` moves a parent entity to `'fractured'` **before** any shards exist, and `'fractured'` could previously only advance to `'stitchable'`, which requires every shard to complete. A single shard that permanently exhausts its own rejection budget therefore stranded its parent forever — there was no exit.

- `FractureProtocol.check_failed_shards()` (`xp_arc/core/fracture.py`) detects this: a shard only counts as permanently failed once it has exhausted its own retry budget (`status == 'failed' and rejection_count >= max_rejections`); a failed shard with retries remaining is still live work, not a dead end.
- `ExecutiveChef._check_stranded_fracture()` calls it after a shard exhausts retries and, if the whole group is unrecoverable, raises an `escalation` entity handled by the new **Chef de Cuisine** station (`xp_arc/stations/chef_de_cuisine.py`).
- The Chef de Cuisine is a brand-new station — it did not exist before `5c67e42`. It is `CRITICAL = True`, meaning it survives Brigade Compression (a degraded brigade is exactly when escalations happen). It echoes `entity_type`/`entity_value` back unchanged (the Aboyeur rejects a station that rewrites the entity it was handed) and records its ruling in `notes`/`findings`.
- A new `'fractured' -> 'failed'` transition was added to `VALID_TRANSITIONS` to make this exit possible. **This is a state-machine change and is flagged for Dragon's review**, per the commit message.

**Verify**: `xp_arc/core/fracture.py` (`check_failed_shards`); `xp_arc/core/executive.py` (`_check_stranded_fracture`); `xp_arc/stations/chef_de_cuisine.py`; `tests/test_retry_and_escalation.py`.

### 5.4 Security hardening (`run_persistent.py`, `pool.py`, `sanitization.py`, GRC stations)

- **`/ws` and `/metrics` auth bypass closed.** `auth_middleware` previously exempted `/ws`, `/api/health`, and `/metrics` unconditionally. `/ws` streams the full pool telemetry payload, so setting `XP_ARC_API_KEY` protected the REST surface while leaving a live feed of the same data completely open. Only `/api/health` (credential-free liveness probe, no pool data) is exempt now. `/ws` additionally accepts the key as `?token=...` because browsers can't set an `Authorization` header on a WebSocket handshake — same secret, same constant-time comparison.
- **`POST /api/seed` validated and rate-limited.** Seed URLs go through `network_guard.public_url()` (the same SSRF check the Forager uses) plus a scheme allowlist (`http`/`https` only) and a length cap (`MAX_SEED_URL_LEN = 2048`). A per-client fixed-window rate limiter (`RateLimiter`, 30 requests/minute) guards the endpoint, returning `429` + `Retry-After` when exceeded.
- **RT-14 / `MAX_SPAWN_PER_ENTITY = 50`** (`xp_arc/core/pool.py`, enforced in `xp_arc/core/executive.py`). One `process()` call returning a huge `spawn_targets` list could previously flood the pool from a single entity.
- **RT-15 / `MAX_SHARD_COUNT = 20`** (`xp_arc/core/pool.py`, enforced in `xp_arc/core/fracture.py`). Shard count is **clamped**, not refused, because the parent is already moved to `'fractured'` before shards exist — refusing outright would strand it. A non-positive shard count is still refused before that transition happens.
- **Station-id injection closed.** `register_station()` used to accept any string as the HMAC write-auth lookup key and encrypted-keystore component. `sanitize_station_id()` (`xp_arc/core/sanitization.py`) now validates against `^[A-Za-z0-9_-]{1,64}$` and **raises** rather than rewrites (a rewritten id could bind two stations onto one key). `sanitize_display_name()` sanitizes the human-readable name in place (strips control characters, caps length, never raises).
- **GRC hardcoded token removed.** Both `GRCSupervisor` and `GRCCommis` previously shipped a hardcoded "dev, change in production"-style fallback credential — baked into the source tree, which made an unconfigured station look configured. Both now read `XP_ARC_CISO_TOKEN` at construction and raise `RuntimeError` if it's unset. As a consequence, GRC stations are opt-in: `run_kitchen.py --grc`. `GRCSupervisor.sync_from_ciso()` was also fixed — it previously called `pool.add_entity(type=..., source=...)`, which is the wrong keyword and a nonexistent parameter, and raised `TypeError` on every sync; it now writes through the station writer so the write is HMAC-signed.
- **`station_keys.json` untracked and gitignored.** The plaintext file (14 live station HMAC keys, per the commit message) defeated the v0.3.0 Fernet-at-rest mitigation, and no code actually read it. **Untracking does not remove it from git history** — a `git filter-repo` scrub and key rotation are still needed and are explicitly held for Dragon (see §6).
- **`--host` / `XP_ARC_HOST`** added to `run_persistent.py` (default `127.0.0.1`, unchanged). Prints an explicit startup warning when bound to `0.0.0.0` with no `XP_ARC_API_KEY` set.

**Verify**: `run_persistent.py`; `xp_arc/core/pool.py`; `xp_arc/core/sanitization.py`; `xp_arc/stations/grc_supervisor.py`, `grc_commis.py`; `tests/test_security_hardening.py`.

### 5.5 Competitive intel bridge (new)

Implements what the commit message calls "Dragon's dual-path ruling": `CompetitiveIntelStation` stays exactly as it was — standalone, its own async pipeline, its own private SQLite database, its own CLI. A second, new path reads that database and republishes findings into the Intelligence Pool as ordinary entities, where they get HMAC-signed writes, the mandatory Aboyeur gate, lineage, Zoran measurement, and DRAGON visibility.

- `CompetitiveIntelBridge` (`xp_arc/competitive_intel/bridge.py`): one-way (competitive DB -> pool, never back), explicitly **not** `concurrent_safe` (it reads a database another process writes on its own schedule — run it between scans, not during one). Caps a scan at `MAX_GAPS_PER_SCAN = 50`, dropping the least-severe gaps first, not by database order, so a truncation can't discard critical findings while keeping cosmetic ones. Gap severity maps to `sla_seconds` (critical=300s, high=180s, medium=120s, low=60s) so Zoran's Law weights it correctly. Entity values serialize deterministically (`sort_keys=True`, fixed field set) so the pool's `UNIQUE(type, value)` constraint makes republishing idempotent across scans.
- `CompetitiveGapAnalyst` (`xp_arc/competitive_intel/analyst.py`): an ordinary `StationChef` handling `'competitive_gap'`. Without it, every bridged gap would be marked unhandled by the Executive, so the bridge alone would prove nothing. Deliberately rule-based, not LLM-backed — this path exists to demonstrate the plumbing under real constitutional constraints, not to be clever.
- `snapshot_competitor()` (in `xp_arc/competitive_intel/station.py`) is now implemented. It was previously a stub that logged and stored nothing, which is why `competitor_snapshots` rendered empty in every weekly report. Built from watchlist profile fields plus metrics already derived from collected `raw_events` — deliberately no additional network fetch. Idempotent per day via `UNIQUE(competitor, snapshot_date)`.
- **Acceptance gate**: `scripts/competitive_acceptance_run.py` runs the full path against live external sources and asserts at every stage (fetch, detect, snapshot, bridge, route, Aboyeur seal, Zoran, DRAGON export, plus an RT-11 check that no station HMAC key appears in the export). Per the `59b98c1` commit message, it was executed this session and all nine gates passed: 149 live events fetched, 11 gaps published, 11/11 entities Aboyeur-signed, 0 unhandled, S = 1.0 / PRO 100% / state `equilibrium`, 0 leaked HMAC keys. That live run is reported in the commit message; it was not re-executed as part of writing this documentation. Per the commit's own honest framing, `S = 1.0` here reflects a run where all 11 entities were ingested and completed in the same 60-second window (drained == arrived), and this run does **not** demonstrate `S > 1` — that requires draining pre-existing backlog, which the unit tests cover directly.

**Verify**: `xp_arc/competitive_intel/bridge.py`, `analyst.py`, `station.py`; `scripts/competitive_acceptance_run.py`; `tests/test_competitive_bridge.py` (10 network-free test functions counted in this pass — the commit message says 11; confirmed passing in this clone under Python 3.12).

### 5.6 Release infrastructure (new, partially unverified)

`Dockerfile` (multi-stage, non-root, healthcheck), `.dockerignore`, `docker-compose.yml`, `.github/workflows/release.yml` (PyPI trusted publishing on `v*` tags, gated on the test suite and on tag/version agreement), and `docs/RELEASING.md` were added in `5c67e42`.

**Docker was not available in the build sandbox, so the image build was desk-checked, not executed.** No one has confirmed the image actually builds or runs. The wheel/sdist build (`python -m build --sdist --wheel`) **was** run and passes — that part is verified.

**Verify**: `Dockerfile`; `docker-compose.yml`; `.github/workflows/release.yml`; `docs/RELEASING.md`.

### 5.7 Test suite

Confirmed in this documentation pass by running `python3.12 -m pytest tests/ -q` against this clone: **104 passed** (up from 40 before `5c67e42`; that commit's own message reports 92 passing at the point it landed, and `59b98c1` added the 11 competitive-bridge tests referenced in §5.5, and 1 additional Zoran test, bringing the total to 104 — consistent with what this pass observed).

---

## 6. Still Open / Not Done

Items below are known gaps or loose ends as of this documentation pass. None of them are fixed by `5c67e42` or `59b98c1`; listing them here is explicitly about what did **not** change.

- **Git tags are stale.** `v0.2` and `v0.3` both point at the same commit (`d108fa3`, the initial commit from March 2026). Neither tag reflects the `0.3.0` version currently in `pyproject.toml`, let alone the work in `5c67e42`/`59b98c1`. `docs/RELEASING.md` describes the correct tagging process going forward (`git tag -a vX.Y.Z`), but no one has cut a tag matching current `main`.
- **`station_keys.json` is still in git history.** Untracking the file (`5c67e42`) stops new commits from including it, but it does not remove the 14 HMAC keys already committed under prior history. A `git filter-repo` scrub plus rotation of every key that was ever committed is still required. This is explicitly held for Dragon, per the commit message — do not do this unilaterally, since rewriting history and rotating live write-auth keys is disruptive to any other clone/fork.
- **Open/redundant PRs** (state as of this pass, not independently re-verified beyond what was reported): PR #4 is stale, PR #7 is redundant with the relicense work that has already landed on `main`, and PR #8 is still needed. Whoever picks this up should re-check PR status directly rather than trusting this line indefinitely — PR state changes independently of the code in this clone.
- **`xp_arc/__init__.py` version/licence drift — FIXED in this pass.** The module
  docstring declared `Version: 0.2.1` / `License: MIT` and `__version__ = "0.2.1"`,
  contradicting `pyproject.toml` (0.3.0, Apache-2.0) and README.md. It was the last
  surface still asserting MIT as the live licence. Now reads 0.3.0 / Apache-2.0.
- **`broker.py` / `broker_client.py` are still present** in `xp_arc/`, despite being ruled obsolete (see §1, §2.1, §3) and not loaded by `run_kitchen.py` or `run_persistent.py`. The removal itself has not happened.
- **`xp_arc/asset_engine/` is a skeleton**, not a shipped feature (corrected in §1, §2.5, §3 above). This was already the state of the code before `5c67e42`/`59b98c1` — those commits did not touch `asset_engine/` — but the prior version of this document claimed it was SHIPPED, which was not supported by what's actually in the directory. Flagging it here so it isn't mistaken for new information from this pass.

---

*Last updated: 2026-08-24 — reconciled against commits `5c67e42` and `59b98c1` (Zoran's Law fix, retry budget, Chef de Cuisine, security hardening, competitive-intel bridge, release infra). Prior entry below preserved for history.*

*Previously updated: 2026-07-21 — v0.2.1 consolidation complete*