# XP-Arc Verification Suite
*Tests proving protocol and runtime behavior*

These tests validate the XP-Arc pipeline. Rebuilders can use them to check that a from-scratch implementation honors the core protocol guarantees.

---

## Running the Tests

From the repository root:

```bash
pip install -e ".[dev,competitive-intel,gauntlet]"
export XP_ARC_ABOYEUR_KEY='any-test-secret'   # required by the Aboyeur
pytest -q
```

A full run is 212 tests (about 45 seconds). Security scan: `bandit -r xp_arc -ll`.

---

## Test Catalog (`tests/`)

| File | Focus |
|---|---|
| `test_basic.py` | Basic unit tests for core modules |
| `test_constitutional_core.py` | Canonical core behavior and the DRAGON export contract |
| `test_zorans_law.py` | Zoran's Law (Article VIII): windowed S ratio, PRO, equilibrium states |
| `test_retry_and_escalation.py` | Aboyeur retry budget and Chef de Cuisine escalation (Articles I 1.2, V 5.5) |
| `test_fracture_protocol.py` | Fracture Protocol HMAC allowlist regression |
| `test_post_qa_commit.py` | Station side effects (spawned entities, edges) commit only after QA |
| `test_competitive_bridge.py` | Competitive-intel bridge and gap analyst, pool integration (network-free) |
| `test_digest.py` | AI Agent Ecosystem Weekly: version labels, week window, rendering |
| `test_security_hardening.py` | Security punch-list: auth, spawn/shard caps, station-id sanitizing, GRC tokens |
| `test_hmac_key_exposure.py` | RT-11: station HMAC keys never leave the Pool |
| `test_red_team.py` | Red-team scenarios (RT-1..RT-n), including that the Write Broker stays removed |
| `test_pr4_reconciled.py` | Fixes ported from the PR #4 red-team audit |
| `test_audit_2026_07_14.py` | Regressions for the 2026-07-14 audit findings (see `docs/audits/2026-07-14.md`) |
| `test_conformance.py` | License and version conformance across the documents |
| `test_repository_hygiene.py` | Repository hygiene guards |
| `test_ci_green_guards.py` | Guards for defects that previously turned CI red |
| `test_load.py` | Load behavior: SQLite WAL under high-frequency writes, cascade depth limits, entity caps |

---

## Other checks outside `tests/`

- `test_dossier.py`, `test_fracture.py` (repo root): dossier generation and fracture/stitch flows.
- `stress_test.py`, `stress_test_instrumented.py`, `benchmark.py`: performance and snowball-cascade stress runs. These are scripts, not part of the pytest suite.
- `xp-arc-gauntlet` (from `gauntlet_pkg/`): adversarial red-team harness with its own workflow (`.github/workflows/gauntlet.yml`) and constitution (`Gauntlet_CONSTITUTION.md`).
