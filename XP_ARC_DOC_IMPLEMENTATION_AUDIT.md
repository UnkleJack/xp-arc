# XP-Arc Documentation vs Implementation Audit

Date: 2026-07-10
Repository inspected: `source/xp-arc`
Remote: `https://github.com/UnkleJack/xp-arc.git`

## Executive Summary

XP-Arc is implementable as a working reference prototype, but the repository is not yet a clean rebuild specification. The documentation describes a broader and cleaner system than the current code consistently provides. The largest gaps are failing tests, CI that scans the wrong path, schema/protocol drift around the Aboyeur contract, stale broker/auth code, and deployment docs that assume generated helper scripts already exist.

For a new implementation, treat the runtime code as the source of truth for current behavior and the docs as partially aspirational until the mismatches below are resolved.

## Verification Performed

Commands run from `source/xp-arc`:

```bash
python3 -m pytest -q tests
python3 -m compileall -q xp_arc run_kitchen.py run_persistent.py
python3 -m bandit -r src -ll -f txt
python3 -m bandit -r xp_arc -ll -f txt
```

Results:

- `compileall` passed.
- `pytest` failed: 2 failed, 13 passed, 1 warning.
- Bandit against `src` scanned zero code because `src` does not exist.
- Bandit against `xp_arc` found 7 medium findings.

## Priority Findings

### P0: Tests Are Documented as Fixed, but They Fail

Documentation claim:

- `README.md` says unit tests were fixed to use fresh in-memory pools.

Current behavior:

- `python3 -m pytest -q tests` fails with two failures in `tests/test_basic.py`.

Root causes:

- `tests/test_basic.py::_fresh_pool()` claims it returns an in-memory pool, but it calls `IntelligencePool()` with no argument.
- `IntelligencePool()` defaults to `xp_arc.db`, not `:memory:`.
- `test_intelligence_pool_mark_completed` expects direct `raw -> completed`, but `pool.py` only permits `raw -> processing -> pending_qa -> completed`.

Relevant files:

- `source/xp-arc/README.md:41`
- `source/xp-arc/tests/test_basic.py:10`
- `source/xp-arc/tests/test_basic.py:24`
- `source/xp-arc/xp_arc/core/pool.py:61`
- `source/xp-arc/xp_arc/core/pool.py:106`

Recommended fix:

- Change `_fresh_pool()` to `IntelligencePool(":memory:")`.
- Update completion tests to use the current status path:

```python
pool.transition_status(entity_id, "processing")
pool.transition_status(entity_id, "pending_qa")
pool.transition_status(entity_id, "completed")
```

### P0: CI Security Scan Does Not Scan the Actual Package

Documentation claim:

- README says GitHub Actions CI includes tests and Bandit security scan.

Current behavior:

- `.github/workflows/ci.yml` runs `bandit -r src -ll -f txt`.
- There is no `src` directory.
- Bandit reports no issues because it scans zero lines.

Relevant files:

- `source/xp-arc/.github/workflows/ci.yml:35`
- `source/xp-arc/README.md:41`

Recommended fix:

- Change CI to scan the actual package:

```yaml
- name: Run Bandit security scan
  run: bandit -r xp_arc -ll -f txt
```

- Then triage or explicitly suppress the current findings.

### P1: Aboyeur Protocol Documentation Does Not Match Runtime Validation

Documentation claim:

- `docs/aboyeur-protocol-v1.json` and README describe an envelope with:
  - `station_id`
  - `entity_id`
  - `timestamp`
  - `status`
  - `payload_hash`
  - nested `output`
  - `fallback_activated`
  - `aboyeur_signature`

Current behavior:

- `Aboyeur.REQUIRED_OUTPUT_FIELDS` only requires:
  - `entity_type`
  - `entity_value`
  - `confidence`

Impact:

- A new system built from the JSON protocol doc will implement a different interface than the current runtime.
- A station built against the current runtime may not satisfy the documented protocol.

Relevant files:

- `source/xp-arc/docs/aboyeur-protocol-v1.json:1`
- `source/xp-arc/README.md:92`
- `source/xp-arc/xp_arc/core/aboyeur.py:30`

Recommended fix:

- Decide whether the Aboyeur contract is:
  - a lightweight station output payload, or
  - a full signed protocol envelope.
- Update either the validator or the JSON schema so they match exactly.
- Add tests that validate one canonical accepted payload and one rejected payload.

### P1: Persistent Deployment Has a Smaller Brigade Than the One-Shot Runner

Documentation implication:

- Deployment docs describe the system as the full XP-Arc brigade.
- Dashboard docs imply station health and broader pipeline visibility.

Current behavior:

- `run_kitchen.py` registers the fuller station set:
  - Forager
  - Analyst
  - Librarian
  - Cartographer
  - Hydra
  - Warden
  - Auditor
  - Amphithere
  - Salamander
  - Herald
  - Dossier
- `run_persistent.py` creates Sentinel and Plongeur, but only registers Forager and Analyst with the Executive.

Impact:

- A deployed daemon does not behave like the one-shot run.
- Entity types handled by the full runner may be unhandled in persistent mode.

Relevant files:

- `source/xp-arc/run_kitchen.py:75`
- `source/xp-arc/run_persistent.py:70`

Recommended fix:

- Either register the same station set in persistent mode, or explicitly document persistent mode as a smaller URL/domain ingestion daemon.

### P1: Stale Broker/Auth Code Conflicts With Current SQLite WAL Story

Documentation claim:

- Current top-level docs and Constitution v1.5 say the system uses SQLite WAL and removed DuckDB/Redis/materialized-view references.

Current behavior:

- `xp_arc/broker.py` still describes a Redis-buffered broker committing to DuckDB and a Redis materialized view.
- `xp_arc/broker_client.py` imports Redis and describes broker-backed operation.
- The broker path includes hard-coded local path assumptions.

Impact:

- A new implementer may build the wrong architecture.
- The repo contains two competing operational stories:
  - simple SQLite WAL pool
  - Redis broker/materialized view system

Relevant files:

- `source/xp-arc/xp_arc/broker.py:1`
- `source/xp-arc/xp_arc/broker_client.py:1`
- `source/xp-arc/CONSTITUTION.MD:697`

Recommended fix:

- If broker mode is abandoned, move these files to an archive folder outside the package or remove them.
- If broker mode is still intended, update the top-level docs to describe it as optional/experimental and add dependencies/tests.

### P1: HMAC Write Authentication Is Available but Not Strictly Enforced

Documentation claim:

- Whitepaper and code comments describe HMAC-signed pool writes as shipped hardening.

Current behavior:

- `pool.py` verifies HMAC only when `station_id` is provided.
- If a station has no registered key, writes are allowed for backward compatibility.
- Main in-process station calls generally use direct pool methods, not signed station-client requests.

Impact:

- This is not a hard security boundary in the reference runtime.
- A new implementation could overestimate the current protection model.

Relevant files:

- `source/xp-arc/xp_arc/core/pool.py:230`
- `source/xp-arc/xp_arc/core/pool.py:261`
- `source/xp-arc/xp_arc/core/station.py:31`

Recommended fix:

- Document HMAC as optional/backward-compatible in the current runtime, or enforce signed writes consistently.
- Add an explicit production mode that rejects unsigned writes.

### P2: Fracture Protocol Is Partly Implemented but Still Has Placeholder Authorization

Documentation claim:

- README marks Cognitive Sharding as “Spec’d”.

Current behavior:

- `xp_arc/core/fracture.py` exists and is wired into `ExecutiveChef`.
- `FractureProtocol.authorize_fracture()` still returns `True` as placeholder development logic.
- Executive currently calls `Aboyeur.validate_fracture()` directly in one path, so there are two authorization concepts.

Impact:

- The capability is neither purely spec-only nor fully production-ready.
- A new implementation needs clarity on which authorization path is canonical.

Relevant files:

- `source/xp-arc/README.md:77`
- `source/xp-arc/xp_arc/core/fracture.py:30`
- `source/xp-arc/xp_arc/core/executive.py`
- `source/xp-arc/xp_arc/core/aboyeur.py`

Recommended fix:

- Mark fracture as “partial/reference implementation.”
- Remove placeholder authorization or route all fracture approvals through Aboyeur.

### P2: Deployment Docs Reference Scripts Before Explaining They Are Generated

Documentation claim:

- `DEPLOY.md` tells users to run `./start.sh` and `./seed.sh`.

Current behavior:

- `start.sh`, `run_once.sh`, and `seed.sh` are not committed.
- They are generated by `install.sh`.

Impact:

- Fresh-clone users may think files are missing.

Relevant files:

- `source/xp-arc/DEPLOY.md:56`
- `source/xp-arc/DEPLOY.md:69`
- `source/xp-arc/install.sh:93`
- `source/xp-arc/install.sh:115`

Recommended fix:

- In `DEPLOY.md`, say these scripts exist after running `./install.sh`.
- Optionally commit the scripts directly if they are meant to be repo-level developer tools.

### P2: No Packaging or Dependency Manifest

Current behavior:

- No `pyproject.toml`, `setup.py`, `requirements.txt`, `poetry.lock`, or `uv.lock` was found.
- CI installs `pytest`, `bandit`, and `duckdb` manually.
- Runtime has optional imports such as `certifi`; broker mode requires `redis`.

Impact:

- A new system has no authoritative install contract.
- It is unclear which dependencies are required, optional, or legacy.

Recommended fix:

- Add `pyproject.toml`.
- Define optional dependency groups, for example:
  - `dev`: pytest, bandit
  - `tls`: certifi
  - `broker`: redis, if broker mode survives

## Bandit Findings When Scanning `xp_arc`

The CI currently misses these because it scans `src`.

Medium findings observed:

- Possible SQL injection warnings from dynamic SQL construction:
  - `xp_arc/broker.py:349`
  - `xp_arc/core/pool.py:428`
  - `xp_arc/core/pool.py:600`
- Binding to all interfaces:
  - `xp_arc/broker.py:916`
- `urllib.request.urlopen` audit warnings:
  - `xp_arc/stations/analyst.py:135`
  - `xp_arc/stations/analyst.py:148`
  - `xp_arc/stations/forager.py:206`

Notes:

- Some SQL warnings may be false positives if update columns/placeholders are controlled internally.
- They should still be reviewed and either rewritten or suppressed with justification.
- The `urlopen` warnings need explicit scheme validation or justified `# nosec` comments.

## What Is Actually Implemented

The repo is not just documentation. It has meaningful implementation coverage:

- SQLite-backed Intelligence Pool.
- Constitutional status transitions.
- Entity lineage and cascade depth tracking.
- Executive routing loop.
- Aboyeur QA gate.
- Forager and Analyst stations.
- Additional station modules for broader pipeline behavior.
- DRAGON static/live state export path.
- Zoran's Law and SpaZzMatiC monitoring.
- Plongeur orphan sweep logic.
- Partial fracture/sharding support.
- Install script for a Zo.Computer-style deployment.

## Recommended Fix Order

1. Fix tests and update CI so it tests/scans the actual package.
2. Align Aboyeur schema with runtime behavior.
3. Decide whether broker mode is alive, optional, or dead; then remove or document it accordingly.
4. Normalize one-shot and persistent station registration expectations.
5. Add packaging metadata and dependency groups.
6. Clarify HMAC security boundaries.
7. Update README/DEPLOY/WHITEPAPER status language after the above decisions.

## Suggested Instruction to the Implementing AI

Use this report as a mismatch checklist. Do not start by rewriting the architecture. First make the repo self-consistent:

1. Make tests pass with the current constitutional state machine.
2. Make CI actually validate the current package.
3. Pick one canonical runtime architecture.
4. Make the docs describe that architecture exactly.
5. Add tests for every documented protocol boundary.

After those are done, the repo can be treated as a much safer source for rebuilding XP-Arc in a new system.
