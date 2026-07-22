# XP-Arc

**A Unified Protocol for Resilient Multi-Agent Intelligence Systems**

XP-Arc — Exponential Architecture — is an open protocol defining the contract between multi-agent systems: a shared state surface, a QA enforcement layer, a graceful degradation model, a task fracturing protocol for primary agent failure, and a stability metric that tells operators whether their system is coherent or drifting.

## The Kitchen That Thinks

Inspired by Escoffier's kitchen brigade system, XP-Arc orchestrates AI agents through a shared `Intelligence Pool` rather than ad-hoc chaining. Every agent reads from and writes back to the Pool. No station talks directly to another. The Pool is the message bus, the event queue, the audit log, and the ground truth — simultaneously.

## Architecture

```
xp-arc/
├── xp_arc/                    # Core Python package
│   ├── core/
│   │   ├── pool.py            # Intelligence Pool — SQLite WAL state machine
│   │   ├── executive.py       # Routing loop — reads raw, dispatches by type
│   │   ├── station.py         # Base station class — all agents inherit this
│   │   ├── aboyeur.py         # QA enforcement — validates every station output
│   │   ├── authorization.py   # HMAC write authentication & access control
│   │   ├── fracture.py        # Cognitive sharding & shard stitching engine
│   │   ├── network_guard.py   # SSRF defense & public URL verification
│   │   └── sanitization.py    # Graph node/label & Markdown output sanitization
│   ├── stations/              # The 13 Canonical Brigade Stations
│   │   ├── amphithere.py      # DNS & network infrastructure enrichment
│   │   ├── analyst.py         # Relationship inference — domain classification + edges
│   │   ├── auditor.py         # Constitutional compliance & schema verification
│   │   ├── cartographer.py    # Topology mapping & cluster detection
│   │   ├── dossier.py         # OSINT report synthesis & Markdown assembly
│   │   ├── forager.py         # DOM scraping — seed URLs → entity extraction
│   │   ├── herald.py          # Alert evaluation & operator notification
│   │   ├── hydra.py           # Multi-headed pattern scanning & prefix analysis
│   │   ├── librarian.py       # Historical archiving & intelligence gap tracking
│   │   ├── plongeur.py        # Cleanup — orphan recovery, GC sweeps
│   │   ├── salamander.py      # Data normalization & deduplication
│   │   ├── sentinel.py        # Anomaly detection — pool health monitoring
│   │   └── warden.py          # Risk assessment & threat level scoring
│   ├── broker.py              # Write Broker — Redis-buffered Pool write sequencer
│   ├── broker_client.py       # Broker Client for stations & DRAGON API
│   └── monitoring/
│       ├── zorans_law.py      # Stability metrics — S quotient + PRO
│       └── spazzmatic.py      # Adversarial review — cold-eyes QA authority
├── dragon/                    # DRAGON web dashboard
│   ├── index.html             # Live visualization of Intelligence Pool
│   └── pool_state.json        # Exported pipeline state
├── run_kitchen.py             # CLI entry point
├── run_persistent.py          # Continuous daemon runner
├── stress_test.py             # 5000-entity stress test gauntlet
├── stress_test_instrumented.py # Proof-of-work instrumented runner
├── WHITEPAPER.md              # Full protocol specification
├── CONSTITUTION.MD            # Operational law (v1.5)
└── docs/
    └── aboyeur-protocol-v1.json
```

## Recent Changes

- **Comprehensive Adversarial Audit & Edge-Case Hardening**: Aligned every station's output schema with the Aboyeur QA protocol (`entity_type` / `entity_value` preservation), fixed `claim_next_raw` and `get_next_raw` to retry transient failures while respecting circuit breakers (`rejection_count >= 3` suspends SLA), enabled HMAC write authorization for `FractureProtocol` cognitive sharding, eliminated slow DNS timeouts on `.test` domains in `network_guard`, and fixed `SpaZzMatiC` report formatting side effects.
- **Adversarial Gauntlet (`tests/test_adversarial.py`)**: Added an exhaustive 12-point adversarial test suite verifying D2/Markdown sanitization, unauthorized status transition rejection, HMAC write authentication, Snowball cascade depth limit enforcement (`MAX_CASCADE_DEPTH = 5`), Aboyeur circuit breaker escalation, fracture depth bounds (`depth <= 1`), and Zoran's Law sustained distress auto-compression.
- Added GitHub Actions CI workflow (tests + Bandit security scan).
- Fixed unit tests to use fresh in‑memory pool and correct row access.
- Mitigated Bandit B310 by validating URL schemes in `forager` and adding `# nosec B310` comment.


```bash
# Run the default 5-target spread
python run_kitchen.py

# Custom targets
python run_kitchen.py https://example.com https://news.ycombinator.com

# Custom database path
python run_kitchen.py --db myrun.db https://example.com

# Re-export existing DB for DRAGON
python run_kitchen.py --export-only --db myrun.db
```

## Dependencies

| Tier | Scope | Requirements |
|------|-------|-------------|
| Orchestration core | `pool.py`, `station.py`, `executive.py`, `fracture.py` | Python 3 stdlib only — SQLite built in, zero pip deps |
| Full deployment | Production runtime | Python 3.10+, standard library `sqlite3` |
| Visualization | DRAGON dashboard | Any modern browser (static `pool_state.json` or live via `run_persistent.py`) |

## The Six Coordination Primitives

| # | Primitive | Implementation | Status |
|---|---|---|---|
| 1 | Shared Pool State | `pool.py` — SQLite WAL state machine, constitutional schema | ✓ |
| 2 | Typed Routing | `executive.py` — dispatches by entity type to registered stations | ✓ |
| 3 | QA Enforcement | `aboyeur.py` — validates every output, signs approved entities | ✓ |
| 4 | Graceful Degradation | `executive.py` — Brigade Compression fallback roles matrix | ✓ |
| 5 | Cognitive Sharding | `fracture.py` — Fracture Protocol task decomposition & stitching | ✓ |
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
- [CONSTITUTION.MD](./CONSTITUTION.MD) — Operational law (v1.4)
- [LEGAL.md](./LEGAL.md) — Legal framework and operator responsibilities

## License

MIT License. Free to use for any purpose including commercial production.
No license fee, no attribution requirement beyond the copyright notice.

**Version:** 0.2.0
**Author:** David J. Riedl (UnkleJack)
**Repository:** github.com/unklejack/xp-arc
