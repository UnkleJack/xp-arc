# Constitutional Core & DRAGON Remediation Plan

## Scope

This change set targets the canonical XP-Arc orchestration core and the DRAGON observability layer for a self-contained, single-machine deployment. The acceptance run will use real outbound retrieval alongside controlled malformed, duplicate, unreachable, and bounded-depth inputs. Optional Asset Engine and Competitive Intelligence pipelines are intentionally excluded.

## Authority Order

The implementation follows the Constitution first, the canonical Architecture specification second, and the current implementation and status map third.

## Baseline Findings

| ID | Finding | Constitutional impact | Planned remedy |
| --- | --- | --- | --- |
| C-01 | `pytest -q` collects root-level executable probes that require an Aboyeur key and fails at collection. | The documented verification path is not reproducible. | Limit default discovery to the maintained `tests/` suite and retain root probes as explicit scripts. |
| C-02 | The maintained load suite performs hundreds of sequential outbound requests to non-routable `.test` hosts. | Routine verification is unbounded and cannot establish reliable health. | Replace live-load behavior with deterministic test doubles; reserve a small, explicit live acceptance run for real network validation. |
| C-03 | The Pool writes `assigned_at` and `completed_at` from Python. | Article I §1.2 and Article III §3.3 reserve those timestamps for SQLite. | Use SQLite time expressions in the same status-update transaction. |
| C-04 | `pending_qa → completed` can occur without a valid Aboyeur signature. | Article III §3.2 and Article IV §4.3 permit downstream propagation before mandatory QA. | Enforce the signature gate at the Pool boundary and cover it with tests. |
| C-05 | The one-shot runner writes root lineage with direct SQL after ingestion. | Root lineage is not sealed in the Pool's atomic write path. | Have the Pool initialize a seed's root ID inside its insertion transaction. |
| C-06 | The Executive passes a duplicate `station_id` during spawned-entity creation. | A valid post-QA Snowball path can raise instead of creating a verified child. | Let the station writer own identity and remove the duplicate argument. |
| C-07 | A malformed or unreachable URL returns a QA-compliant low-confidence output and can be marked `completed`. | Station refusal and failure disposition are not represented truthfully. | Introduce an explicit station-refusal path that records a reason and ends the task in `failed`. |
| C-08 | The live DRAGON API export lacks fields the dashboard renders unconditionally (`dossiers`, `audit`, and `topology`). | The constitutionally required live observability layer can fail in the browser. | Normalize the export contract and harden the dashboard for an empty but valid state. |
| C-09 | Runtime dependency and dashboard startup behavior are not verified by automated tests. | A nominal local deployment cannot be demonstrated end-to-end. | Add API, export-contract, and live seeded-pipeline tests; perform a browser/API verification during final acceptance. |

## Atomic Work Sequence

| Task | Change boundary | Completion evidence |
| --- | --- | --- |
| A1 | Verification configuration and deterministic tests | `pytest -q` is bounded, repeatable, and green. |
| A2 | Pool state-machine integrity | SQLite-generated timestamps, signature-gated completion, and atomic root lineage are demonstrated. |
| A3 | Executive and station dispositions | Spawn lineage works; malformed and unreachable inputs become explained failures without propagating. |
| A4 | DRAGON export and local API contract | The `/api/dragon` payload validates against all dashboard access paths. |
| A5 | Self-critique and refactor | Data-flow review finds no direct post-ingestion lineage writes or unguarded completion path. |
| A6 | Live adversarial acceptance run | A bounded real-network run shows both verified completions and correctly contained failures in DRAGON-ready output. |

## Acceptance Criteria

The branch is ready for review only when all maintained tests, static checks, security scan, local API checks, and the live adversarial seeded run pass. The final evidence must show each valid completed task has an Aboyeur signature, each controlled invalid case has an explicit refusal/failure reason, lineage remains bounded, and the DRAGON export contains all required dashboard collections.

## Browser Verification Record

On the local persistent runtime at `http://127.0.0.1:8091/`, DRAGON successfully connected over WebSocket and rendered the empty-Pool dashboard after the audit-contract repair. The visible page showed the Brigade, live connection indicator, metrics, audit cards, entity registry, and event timeline with no render error. This corrected the prior live failure caused by absent audit-detail fields.

## Self-Critique and Refactor Record

The implementation was reviewed after the first green suite rather than accepted on first pass. The review found and corrected three additional data-flow defects: runtime station registration was mutating the tracked `station_keys.json`; the Fracture Protocol wrote entity state with direct SQL and could silently produce zero shards under authenticated writes; and the Dossier and Librarian helpers could complete their own derivative entities without an Aboyeur seal. Keys are now scoped to the selected Pool database, fracture metadata has authenticated Pool methods, and internal derivative artifacts use the shared `submit_for_qa()` path.

The final direct-entity-write scan shows remaining raw SQL writes only in the explicitly obsolete `broker.py` implementation and in the Gauntlet’s deliberate tampering scenarios. Neither is loaded by the canonical kitchen or local DRAGON runtime. The canonical station tree has no remaining direct completed-status call; all completions pass through the Pool’s signature gate.

## Final DRAGON Verification Record

DRAGON was verified in a browser against the final live seeded database. It maintained a live WebSocket connection and rendered seven entities, one edge, the graph nodes, the audit panel, the entity registry, SpaZzMatiC findings, and the chronological event timeline. The entity registry showed two signed completions (`https://example.com` and its derived `iana.org` domain) and five controlled terminal failures: HTTP 404, redirect/service failure, malformed FTP scheme, private-loopback rejection, and a depth-limit refusal. The audit panel showed 7/7 valid payload hashes, 2/2 signed completed entities, zero transition violations, 7/7 terminal entities, and zero unaccounted records.

The observed **ZORAN: DISTRESS** state and safe-halt recommendation are expected outcomes of this intentionally adversarial batch: five of seven tasks are purposefully rejected. DRAGON correctly made that operational condition visible rather than suppressing it.

## Compression Regression Verification

A second DRAGON browser check after the compression-role refactor showed the new event `Brigade compressed: 11 stations -> 4 critical`, retaining The Forager, The Analyst, The Plongeur, and The Sentinel while removing only noncritical stations. This replaces the earlier observed zero-station compression behavior. The older zero-station event remains in the retained historical timeline of the proof database, which is useful audit evidence of the defect that was corrected.
