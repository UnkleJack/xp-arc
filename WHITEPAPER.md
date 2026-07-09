# XP-Arc: A Unified Protocol for Resilient Multi-Agent Intelligence Systems

**Version:** 0.2
**Authors:** Jack (unklejack), Claude (Anthropic), Zo.Computer, Gemini (Google)
**Repository:** github.com/unklejack/xp-arc
**License:** MIT
**Changelog:** See Section 12

---

## Abstract

The 2026 multi-agent AI landscape has produced strong standards at two layers.
At the communication layer, Google's A2A protocol standardizes how agents discover
and delegate tasks to each other. At the tool-access layer, Anthropic's MCP
standardizes how agents reach external resources — databases, APIs, filesystems.

Neither layer specifies what happens between those two points: where agents write
their outputs, how those outputs are validated before they propagate downstream,
what the system does when one agent fails mid-pipeline, and how an operator knows
whether the pipeline is running coherently or quietly drifting.

XP-Arc — Exponential Architecture — is that missing layer. It defines the
orchestration contract above the communication and tool-access layers: a shared
Intelligence Pool that any agent writes to and reads from; a QA enforcement layer
that validates every output before downstream propagation; a graceful degradation
model; a task fracturing protocol for primary agent failure; and a stability metric
that tells operators whether their system is coherent or drifting.

XP-Arc gives A2A and MCP a shared pool to write into and a QA layer to validate
what they produce. Drop it into an existing multi-agent stack. Keep your agents.

The reference implementation is written in Python 3.12. The orchestration core has
zero pip dependencies — SQLite is part of the Python standard library.
Full deployment requires Python 3.10+, the standard library `sqlite3` module,
and a browser for the DRAGON visualization layer. The brigade has run.

---

## Section 1 — The Problem

Every complex multi-agent system eventually fails in one of three ways.

The first failure is silent data loss. An agent encounters an entity type it
cannot process and drops it — no log, no flag, no signal to the operator. The
intelligence map has a hole nobody knows about.

The second failure is cascade corruption. An agent writes bad output to a shared
surface. Downstream agents consume it as fact. The error compounds through the
pipeline and the final output is confidently wrong.

The third failure is brittle orchestration. The system works when every component
is healthy. When one component degrades, the orchestration layer has no fallback
logic — the pipeline stalls, crashes, or requires human intervention to restart.

These are not edge cases. They are the default failure modes of ad-hoc
multi-agent architectures. They occur because most agent pipelines are built as
chains — A calls B calls C — rather than as systems with shared state, typed
routing, and explicit degradation handling.

XP-Arc addresses all three failure modes by design, not by patch.

---

## Section 2 — Positioning: The Orchestration Layer

*This section was Section 7 in v0.1. It has been promoted to Section 2 because
it is the most important thing to understand about XP-Arc before reading the rest
of this whitepaper.*

### 2.1 The Three Layers of Multi-Agent Infrastructure

The 2026 multi-agent protocol landscape has produced strong solutions at two
distinct layers.

**The communication layer** handles agent-to-agent discovery and task delegation.
Google's A2A protocol (2025) standardizes this: agents publish capability cards
at well-known URLs, client agents discover remote agents, and tasks flow between
them over JSON-RPC with Server-Sent Events for real-time streaming. ACP provides
a REST-based alternative with agent registries. ANP extends this to internet-wide
federation using decentralized identifiers.

**The tool-access layer** handles agent-to-resource connectivity. Anthropic's
Model Context Protocol (MCP) standardizes how agents access external systems.
MCP servers expose tools, resources, and prompts through a common interface.
Agents discover capabilities and invoke them without writing custom integrations
for every data source.

**The coordination layer** — what happens between communication and tool use —
has no standard. Teams building agent pipelines today solve the same coordination
problems independently: shared state management, output validation, degradation
handling, stability measurement. XP-Arc defines this layer.

### 2.2 What XP-Arc Is Not

XP-Arc is not a communication protocol. It does not specify how agents discover
each other, how they authenticate, or how they pass messages peer-to-peer.
A2A already does this well.

XP-Arc is not a tool-access protocol. It does not specify how agents invoke
external resources or how capability descriptions are structured. MCP already
does this well.

XP-Arc is not a governance or compliance framework. It does not specify
cross-domain federation, regulatory audit trails, or enterprise identity
management. OpenEAGO and similar enterprise specifications address these concerns.

### 2.3 What XP-Arc Is

XP-Arc is the shared operational surface that existing protocols assume exists
but do not specify. Specifically:

- **The Intelligence Pool** is where agents write their outputs and read their
  inputs. All state flows through a single authenticated, auditable surface.
  No agent talks directly to another. The pool is the message bus, event queue,
  and audit log simultaneously.

- **The Aboyeur Protocol** is how outputs are validated before they propagate.
  Every station output must pass QA — payload hash verification, schema
  conformance, confidence scoring — before it is marked `completed` and allowed
  to trigger downstream work.

- **Brigade Compression** is how the system degrades gracefully when a station
  fails. Fallback role matrices, checkpoint-based task handoff, and the Minimum
  Viable Brigade definition keep the pipeline running without halting or requiring
  human intervention.

- **Zoran's Law** is how operators know whether the system is healthy. A
  SLA-weighted stability quotient (S > 1.0) and primary role occupancy (PRO ≥ 70%)
  measured on a rolling window give real-time system state in two numbers.

### 2.4 Integration Path

An A2A-compliant agent can be registered as an XP-Arc station. The agent declares
XP-Arc station roles in its capability card. It receives its task specification
via the pool, executes, and returns an Aboyeur-schema-compliant payload. The
pool doesn't care what protocol the station uses internally.

An MCP server maps directly to the Forager station role. The Forager wrapper
calls the MCP tool, extracts entities, and writes them to the pool. The rest of
the brigade processes MCP-sourced intelligence identically to intelligence sourced
by any other means.

XP-Arc is additive to the existing protocol ecosystem. It is the kitchen that
A2A and MCP cook in.

---

## Section 3 — Originality

XP-Arc does not claim to have invented multi-agent systems, message queues,
state machines, or QA validation layers. All of these exist. The originality
claim is narrower and stronger: XP-Arc is the first unified standardized protocol
that combines all six coordination primitives — shared pool state, typed routing,
QA enforcement, graceful degradation, task fracturing, and stability measurement
— into a single coherent contract that any agent, built in any framework, can
implement.

The closest analogy is HTTP. HTTP did not invent client-server communication,
TCP, or HTML. It defined the contract between them. Before HTTP, teams built
bespoke communication layers. After HTTP, the ecosystem built on a shared
foundation. XP-Arc is that contract for multi-agent coordination.

The framing comes from an unexpected source: Auguste Escoffier's 1900 kitchen
brigade system. Escoffier did not invent cooking. He published the formal
specification for how professional kitchens coordinate under pressure — roles,
handoffs, QA checkpoints, degradation protocols. Every professional kitchen in
the world runs on a variant of that spec. XP-Arc maps that system, with
precision, onto multi-agent AI architecture.

The mapping is not metaphor. It is specification.

The originality claim is defended by two vectors: publication date and the
specific combination of primitives. The six coordination primitives listed above
appear individually across prior art. No prior work — including the 2026
entrants addressed in Section 4 — combines all six into a unified runtime
contract with a single shared state surface at its center.

---

## Section 4 — Prior Art

The following systems and frameworks inform XP-Arc's design or operate in
adjacent problem spaces. This section distinguishes each from XP-Arc's
specific contribution.

### 4.1 Agent Frameworks

**LangChain / LangGraph** — agent chaining and graph-based orchestration.
Addresses sequencing but does not specify shared pool state, typed entity
routing, or QA enforcement between agents. Agents can be registered as
XP-Arc stations.

**AutoGen (Microsoft)** — conversational multi-agent framework. Agents
communicate peer-to-peer rather than through a shared auditable state surface.
No formal degradation protocol. Compatible as XP-Arc stations.

**CrewAI** — role-based agent teams. Closest in spirit to the brigade model but
without a formal QA layer, stability metric, or task fracturing protocol.

**Semantic Kernel** — plugin-based agent orchestration. Strong tool integration,
weak inter-agent state management.

### 4.2 Communication Protocols

**Google A2A Protocol** (2025) — agent-to-agent communication standard. Defines
how agents discover each other via capability cards and how tasks flow between
them. Does not define what agents write to, how outputs are validated before
downstream propagation, or how the system behaves when agents fail. XP-Arc
is compatible with A2A by design (Section 2.4).

**Agent Communication Platform (ACP)** — REST-based agent registry and
communication standard. Client-server architecture with agent registries. Focuses
on cross-platform integration and stateful messaging. Does not address the
shared-state, QA, or degradation layers that XP-Arc specifies.

**AgentMesh Protocol** (2026) — open standard for agent identity, trust, and
message passing. Defines a Semantic Message Bus and Agent Identity & Trust
Protocol. AgentMesh and XP-Arc are potentially complementary: AgentMesh handles
identity and trust establishment, XP-Arc handles coordination once agents are
working together. XP-Arc does not specify its own identity protocol; AgentMesh
could serve that role in a combined deployment.

### 4.3 Orchestration and Governance Standards

**Open Agent Protocol (OAP) v1.0.0** (May 2026) — the broadest-scope standard
currently in the field. OAP specifies identity, capability description, structured
invocation, monetization, multi-agent coordination, confidentiality enforcement,
and tamper-evident auditing. Its stated goal is "the default interoperability
layer for autonomous agents, comparable in scope to what HTTP, OAuth, and TLS
represent for the human web." OAP has 26 RFCs and adapters for MCP, A2A, OpenAI
function calling, and LangGraph. It is community-governed with no controlling
entity.

*XP-Arc vs. OAP*: OAP specifies the agent economy — how agents transact,
establish trust, monetize services, and audit their actions. XP-Arc specifies
the agent kitchen — how agents coordinate shared state, validate each other's
outputs, degrade gracefully, and measure system stability. These are different
layers. OAP has no Intelligence Pool model; it does not specify what all agents
write to in a shared orchestration context. XP-Arc has no policy stack or
monetization layer; it does not specify how agents charge for their services.
An XP-Arc deployment that needs commercial governance could run OAP's policy
stack above its coordination layer. XP-Arc's Aboyeur is not equivalent to OAP's
audit log — the Aboyeur is a runtime QA gate, not a financial receipt chain.

**Oracle Open Agent Specification** (October 2025) — a framework-agnostic
declarative language for defining agents and workflows. Inspired by ONNX:
portable agent definitions that run on any compliant runtime. Focuses on the
configuration and portability layer, not the runtime coordination layer. An
agent defined in Oracle Agent Spec could be instantiated as an XP-Arc station.

**OpenEAGO (FINOS)** (March 2026) — Enterprise Agent Governance and
Orchestration specification from Citi engineers. Addresses regulatory compliance
(GDPR, HIPAA, PCI-DSS), enterprise authentication (OAuth2, mTLS), and
cross-domain federation for regulated industries. The target deployer is an
enterprise compliance team, not an agent developer. Different buyer, different
use case. XP-Arc's DRAGON observability layer and Aboyeur audit trail could
complement OpenEAGO's compliance requirements in a hybrid deployment.

### 4.4 Standards Track

**IETF MACP (Multi-Agent Collaboration Protocol)** (IETF DMSC Working Group,
May 2026) — an IETF Standards Track draft defining trusted agent onboarding,
capability-based discovery, distributed capability synchronization, and
cross-domain multi-agent federation. MACP operates at the network and identity
layer: how agents register with Agent Gateways, how capability directories
synchronize across administrative domains, how agents discover collaboration
partners across organizational boundaries.

*XP-Arc vs. MACP*: MACP answers "how do agents find each other across the
internet?" XP-Arc answers "how do agents coordinate once they are working
together in a shared pipeline?" These are sequential concerns, not competing
ones. A deployment using MACP for cross-domain agent discovery could use
XP-Arc as the runtime coordination layer once agents are instantiated. The
IETF standardization track matters: if MACP reaches RFC status, it will likely
become the federation standard. XP-Arc's design is compatible with that outcome.

### 4.5 Reference Frameworks

**OODA Loop (Boyd)** — observe, orient, decide, act. The temporal rhythm of the
XP-Arc Executive maps to this loop. The Intelligence Pool is the observation
surface. The Aboyeur is the orientation gate.

XP-Arc synthesizes the above prior contributions into a unified runtime contract.
The synthesis is the contribution.

---

## Section 5 — The Framework: The Kitchen That Thinks

Before the formal specification, a demonstration.

On the day the v0.1 whitepaper was written, a five-target spread was run live
against public URLs — Hacker News, a GitHub profile, zo.computer, Lobsters, and
HTTPBin. No configuration beyond the seed list. No human intervention between
start and finish. This is the raw output from the Intelligence Pool after one
execution cycle:

```
[POOL] + Added new url: https://news.ycombinator.com
[POOL] + Added new url: https://github.com/unklejack
[POOL] + Added new url: https://zo.computer
[POOL] + Added new url: https://lobste.rs
[POOL] + Added new url: https://httpbin.org

[EXECUTIVE] Raw ingredient on the pass: [url] https://news.ycombinator.com
[The Forager] Scraping target DOM: https://news.ycombinator.com
[POOL] + Added new domain: www.apple.com

[EXECUTIVE] Raw ingredient on the pass: [url] https://github.com/unklejack
[The Forager] Scraping target DOM: https://github.com/unklejack
[POOL] + Added new domain: skills.github.com

[EXECUTIVE] Raw ingredient on the pass: [url] https://zo.computer
[The Forager] Scraping target DOM: https://zo.computer
[POOL] + Added new domain: www.youtube.com

==================================================
KITCHEN CLOSED. THE CORKBOARD:
==================================================
[ ENTITIES COLLECTED ]
 - [URL] https://news.ycombinator.com        (mapped)
 - [URL] https://github.com/unklejack        (mapped)
 - [URL] https://zo.computer                 (mapped)
 - [URL] https://lobste.rs                   (mapped)
 - [URL] https://httpbin.org                 (mapped)
 - [DOMAIN] www.apple.com                    (unhandled)
 - [DOMAIN] skills.github.com               (unhandled)
 - [DOMAIN] www.youtube.com                  (unhandled)

[ EDGES GENERATED ]
 - https://news.ycombinator.com  --(links_to)--> www.apple.com
 - https://github.com/unklejack --(links_to)--> skills.github.com
 - https://zo.computer          --(links_to)--> www.youtube.com
```

Five seeds. Zero configuration. Automatic entity extraction, automatic
relationship mapping, automatic status tracking — all without a human touching
the pipeline between seed and output.

The `unhandled` domains are not failures. They are honest signals — the system
encountered entity types it has no current station for, logged them visibly, and
stopped rather than guessing. That behavior is designed.

What follows is the formal specification of the architecture that produced
this output.

### 5.1 The Intelligence Pool — The Pass

In Escoffier's kitchen, the pass is the long counter between the kitchen and the
dining room. Every dish moves through it. Nothing reaches the guest without
crossing it.

In XP-Arc, the Intelligence Pool is that counter.

Implemented as a **SQLite WAL** state machine, the Pool is the only shared data structure
in the system. Every agent reads from it and writes back to it. No station talks
directly to another. No agent passes data peer-to-peer. The Pool is the message
bus, the event queue, the audit log, and the ground truth — simultaneously.

Every entity enters the Pool with status `raw`. The Executive reads `raw` entities
and routes them by type to the appropriate station. When a station completes its
work and the Aboyeur validates its output, the entity is marked `completed`.
When no station can handle an entity type, it becomes `unhandled` — logged,
visible, and available for future routing if new station types are registered.

All Pool writes are atomic. Timestamps (`assigned_at`, `completed_at`) are
generated by the SQLite engine, never by the calling agent. This prevents clock
drift across containers from producing unreliable SLA calculations or phantom
safe-halt triggers. Agent-supplied timestamps are constitutionally prohibited.

This single design decision — all state flows through one authenticated, auditable
surface with database-enforced integrity — is what separates XP-Arc from ad-hoc
pipelines that route data through function calls or shared memory that leaves
no trail.

### 5.2 The Pool Substrate and Write Architecture

The Pool is implemented on **SQLite with WAL journal mode** — no external dependencies, no infrastructure, just the standard library.

SQLite's WAL (Write-Ahead Logging) mode allows concurrent readers while a write is in progress, decoupling read throughput from write latency without requiring a separate process or server. `PRAGMA foreign_keys=ON` enforces referential integrity at the database level. The pool sets both flags at initialization.

The original architecture specified DuckDB with a Redis-buffered Write Broker. That was overengineered for the actual workload. The XP-Arc brigade does high-frequency small writes (entity inserts, status transitions), concurrent reads (DRAGON polling), and real-time queries on small-to-medium data — exactly the use case SQLite WAL was designed for. DuckDB's columnar OLAP engine would add infrastructure complexity without measurable benefit.

**DRAGON polling:** DRAGON queries the SQLite file directly at 500ms intervals. Under write load, readers may occasionally see a slightly stale snapshot — acceptable for a visualization layer. The materialized view concept from the Write Broker architecture is not needed at this scale.

### 5.3 The Exponential Snowball

When a new entity is written to the Pool with status `completed` and a valid
Aboyeur signature, its output payload may contain spawn directives — instructions
to create new downstream tasks. The Executive processes these directives, creating
new `raw` entities, which trigger new station processing, which produce new
outputs, which may spawn further directives.

One seed URL doesn't trigger one extraction. It triggers a cascade. The Forager
pulls domains. The domains trigger analyst processing. The analyst output triggers
relationship mapping. The whole intelligence picture assembles itself,
automatically, from a single starting point.

Spawn directives fire only from `completed` status with a valid `aboyeur_signature`.
The `pending_qa` gate prevents the Snowball from triggering on unvalidated outputs
— a critical safety property that prevents cascade corruption.

Cascade depth is enforced by the **ExecutiveChef** at spawn time, not declared by the agent.
When a spawn directive is processed, `_process_spawns()` queries the actual database
lineage of the `parent_task_id` chain to calculate the real cascade depth before inserting
the new entity. An agent that submits a spawn directive with a null or spoofed
`parent_task_id` will have its depth calculated from its own lineage entry. The default maximum
cascade depth is 5 levels. The Snowball is also the primary self-inflicted DoS
vector if unconstrained; `max_entities=500` is the configurable default.

### 5.4 The Fracture Protocol — Cognitive Sharding

Brigade Compression handles station failure gracefully. But graceful degradation
has a ceiling: if the fallback station produces low-confidence output, the
intelligence map is compromised at that node.

The Fracture Protocol is the answer to that ceiling.

When a primary station returns output below confidence threshold (default: 0.6),
XP-Arc does not route the same task to a lesser agent. It fractures the task —
decomposing a complex intelligence target into atomic micro-tasks, each assigned
to a separate lightweight agent operating within a narrow, precisely-specified
scope.

The insight is empirical: small open-source models have low reasoning ceilings
when asked to perform multi-dimensional tasks simultaneously. But given a single,
precisely-scoped micro-task — one question, one data source, one output format —
the same model performs with near-primary precision. Shard the load and you shard
the requirement for expensive inference.

**Pool status flow under Cognitive Sharding:**
```
raw → processing → pending_qa → failed → fractured → stitchable → mapped → completed
```

Shards may only be stitched when all shards carry status `completed` with valid
`aboyeur_signature`s. Partial stitching is constitutionally prohibited.
Fracture depth is limited to one level — Commis agents do not have fracture
authorization.

### 5.5 The Seven Stations

**1. The Forager** *(Garde Manger)*
Raw intelligence acquisition. Seeds → DOM extraction → entity writes.
Wraps MCP servers transparently. Fallback: passive pool reader, surfaces
unhandled entities for human review.

**2. The Analyst** *(Saucier)*
Relationship inference. Builds edge graph from entity pool.
Fallback: type-tagging only, no relationship inference.

**3. The Mapper** *(Entremetier)*
Structural intelligence. Subdomain hierarchies, org charts, IP ranges.
Fallback: flat entity list output.

**4. The Chronicler** *(Rotisseur)*
Temporal intelligence. Archive deltas, timestamp tracking, state change audit.
Fallback: append-only log mode.

**5. The Sentinel** *(Poissonnier)*
Anomaly detection. Monitors pool for unexpected patterns, high-cardinality
floods, status transition anomalies. Monitors Zoran's Law thresholds in
real time.
Fallback: alert-only mode, no automated response.

**6. The Aboyeur** *(Expeditor — QA Enforcement Node)*
Nothing propagates downstream without Aboyeur clearance. Validates station
outputs against protocol schema: payload hash, station identity, timestamp
integrity, output format. Failed validation → task status `pending_qa` resolved
to `failed`, rejection reason logged. Cannot be bypassed. Cannot be configured
away. Structural.

Aboyeur rejection circuit breaker: if `rejection_count` reaches `max_rejections`
(default: 3), the task transitions immediately to `failed` and escalates to the
Chef de Cuisine with SLA suspended. This prevents an Aboyeur hallucination from
generating an infinite reject-regenerate loop that exhausts API token budgets
before Zoran's Law detects the problem.

**7. The Lateral Mesh** *(R&D)*
Operates outside the active brigade. Stress-tests assumptions, runs experimental
routing logic, surfaces novel patterns upstream. Prevents the system from
optimizing into a local maximum.

### 5.6 The Aboyeur Protocol — Formal Schema

Every station output must conform to this schema:
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
  "aboyeur_signature": "string"
}
```

The `payload_hash` field is the provenance mechanism. At the moment a task
enters the Pool with status `raw`, its hash (SHA-256 of the serialized payload)
is sealed. This hash is immutable — no downstream station may alter the payload
after sealing. Mismatch between write and read means corrupted or tampered payload.

The `aboyeur_signature` is the QA clearance token. Only the Aboyeur generates
it. Downstream stations check for its presence before consuming any entity.
Spawn directives cannot fire until a valid `aboyeur_signature` is present and
the task has reached `completed` status — the `pending_qa` gate enforces this
at the Pool write layer.

### 5.7 Zoran's Law — The Stability Threshold

Every complex adaptive system has a phase transition point. For XP-Arc:

> *S > 1: When the system's correction rate outpaces its informational decay
> rate, the system self-heals.*

Zoran's Law uses a SLA-weighted formula:

```
S   = Σ(sla_seconds for completed tasks) / Σ(sla_seconds for ingested tasks)
PRO = agents_operating_in_primary_role / total_active_agents
```

The weighting by `sla_seconds` (not raw task count) prevents high-volume
micro-tasks from masking degraded heavy-reasoning tasks. An unweighted ratio
would allow a healthy Plongeur running thousands of short GC sweeps to produce
a falsely high S reading while Saucier reasoning tasks — carrying 300-second
SLAs — quietly fail. The weighted formula ensures each task contributes to S
in proportion to its cognitive labor expectation.

When S > 1.0 and PRO ≥ 70%, the brigade is healthy. Below 70% PRO, Brigade
Compression is triggered. Below S = 0.5 for more than two measurement intervals,
SpaZzMatiC issues a Safe Halt Recommendation with a 60-second veto window.

Zoran's Law is a health signal, not a hard cutoff. The system tells you where
it is and keeps running within its degraded capability. That transparency is
the feature.

---

## Section 6 — Implementation

### 6.1 Reference Codebase

```
xp-arc/
├── xp_arc/
│   ├── core/
│   │   ├── pool.py          # Intelligence Pool — SQLite WAL state machine
│   │   ├── executive.py     # Routing loop — reads raw, dispatches by type
│   │   ├── station.py       # Base station class — all agents inherit this
│   │   └── aboyeur.py       # QA enforcement — validates every station output
│   ├── stations/
│   │   ├── forager.py       # DOM scraping — seed URLs → entity extraction
│   │   ├── analyst.py       # Relationship inference — domain classification + edges
│   │   ├── sentinel.py      # Anomaly detection — pool health monitoring
│   │   └── plongeur.py      # Cleanup — orphan recovery, GC sweeps
│   └── monitoring/
│       ├── zorans_law.py    # Stability metrics — S quotient + PRO
│       └── spazzmatic.py    # Adversarial review — Gemini-backed QA authority
├── dragon/                  # DRAGON web dashboard
│   ├── index.html           # Live visualization of Intelligence Pool
│   └── pool_state.json      # Exported pipeline state
├── run_kitchen.py           # CLI entry point
├── WHITEPAPER.md            # This document
├── CONSTITUTION.MD          # Operational law (v1.4)
└── docs/
    └── aboyeur-protocol-v1.json
```

**Dependency tiers:**

| Tier | Scope | Dependencies |
|------|-------|-------------|
| Core orchestration | `pool.py`, `station.py`, `executive.py`, `fracture.py` | Python 3.12 stdlib only — SQLite built-in |
| Full deployment | Production runtime | Python 3.10+, standard library `sqlite3` |
| Visualization | DRAGON dashboard | Any modern browser (no server required for static mode) |

The "zero pip dependencies" claim is scoped to the orchestration core only.

### 6.2 Verified Execution — The Five-Target Spread

*(Unchanged from v0.1 — see Section 5 demo output above.)*

What this run proves: recursive loop executes and terminates cleanly;
pool correctly tracks entity status across multiple types; Executive routes by
type without hardcoded logic; unhandled entities surface visibly; edges generate
automatically; Snowball scales linearly with seed count.

What this run does not yet prove: full Aboyeur validation; Brigade Compression
failover; Zoran's Law threshold behavior; production-scale performance under
high Snowball load.

The honest accounting of what is and isn't proven is itself an architectural
statement.

### 6.3 Reference Deployment

The reference implementation runs on Zo.computer — a programmable personal
mainframe serving as execution runtime, web server, API host, filesystem, and
database layer.

The `unklejack.zo.space` domain runs a Hono + Bun backend sharing the exact
same filesystem as the XP-Arc workspace. The `/api/dragon` route queries the
SQLite file directly at 500ms intervals — no intermediate process required.
DRAGON polls every 500 milliseconds.

XP-Arc is not Zo-specific. The orchestration core and the Intelligence Pool
substrate are deployable on any Python 3.10+ environment. The
Zo.computer deployment is one reference implementation, not a requirement.

---

## Section 7 — Security Architecture and Threat Model

*A system that doesn't know its own attack surface doesn't deserve to be trusted
with yours.*

### 7.1 Pool Write Authentication (Production Severity: High)

**STATUS: Shipped in v0.2.**

All write operations on the Pool require HMAC authentication when the calling station has a registered key.

**How it works:** Each station is issued a unique HMAC-SHA256 key at registration (auto-generated or provided). The key is stored persistently in `station_keys.json` (retrievable via `get_station_hmac_key()`) and in the `station_registry` table in the DB.

Before every write, the station computes `HMAC-SHA256(key, payload_string)` and passes `station_id` + `mac` to the pool method. The pool looks up the station's key and verifies the MAC using `hmac.compare_digest()`. The payload string is the method name + parameters, e.g. `add_entity:url:https://example.com:60`.

**Auth rules:**
- Station has no key registered → write allowed (backward compat for onboarding)
- Station has key + valid MAC → write allowed
- Station has key + no MAC or invalid MAC → write rejected, `auth_failure` event logged

**Key management:** Use `register_station_with_key()` at system startup to register stations and persist keys. Use `get_station_hmac_key()` to retrieve a station's key at runtime for signing writes.

**Protected methods:** `add_entity()`, `transition_status()`, `set_aboyeur_signature()`, `increment_rejection()`, `add_edge()`

**What it prevents:** A compromised station cannot write arbitrary entities, corrupt status transitions, or flood the entity table without possessing a valid HMAC key. Keys are stored server-side only — not in station code.

**What it doesn't prevent:** If an attacker gains read access to `station_keys.json`, they can sign writes. File permissions and process isolation are the mitigation layer.

### 7.2 Forager Is a Blind Trust Machine (Production Severity: Critical)

The Forager writes whatever it extracts from the DOM to the pool as fact. The
attack class is known: prompt injection via environment. A target site serves a
malicious payload — SQL injection syntax, script tags, path traversal strings.
The Forager writes it raw. The Snowball propagates it.

**Fix:** Input sanitization inside `add_entity()`. Domains must match domain
patterns. URLs must match URL patterns. **Shipped in v0.2.**

### 7.3 Executive Has No Rate Limiting (Severity: Medium)

A target returning 10,000 outbound links produces 10,000 `raw` entities without
a throttle. `max_entities=500` configurable default and crawl depth limit per
seed are the mitigations. SQLite WAL's transaction serialization provides
backpressure at the database write layer.

### 7.4 Provenance Chain Verification (Production Severity: High)

**STATUS: Shipped in v0.2.**

Stations declare lineage when writing child entities. A compromised station
could declare `cascade_depth=0` or a fake `root_task_id` to bypass the cascade
depth limit.

**How it works:** `IntelligencePool._verify_and_compute_lineage()` looks up the
actual parent entity in the DB and computes lineage from the real parent state —
not from caller-provided values. For child entities (`parent_task_id` set), the
pool ignores `cascade_depth`, `root_task_id`, and `spawn_chain` values supplied
by the station. It derives them from the actual parent entity.

The cascade depth limit is enforced at the pool level via `MAX_CASCADE_DEPTH = 5`
(declared at module level in `xp_arc/core/pool.py`, imported by `ExecutiveChef`).
Non-existent parent entity IDs are also rejected, preventing spoofed lineage chains.

For seed entities (`parent_task_id` is None), caller-provided lineage values are
accepted since seed creation is the trusted initialization path.

**What it prevents:** A station cannot spoof `cascade_depth=0` to bypass the
depth limit or claim a false `root_task_id`. All child entities are rooted to
the actual DB state. Non-existent parent IDs are rejected outright.

**Single source of truth:** `MAX_CASCADE_DEPTH` is declared at module level in
`xp_arc/core/pool.py` and imported by `ExecutiveChef`. The pool-level check in
`_verify_and_compute_lineage()` and the executive-level check in `_process_spawns()`
both enforce the same limit from the same constant.

### 7.5 DRAGON Output Injection (Severity: Low → Medium)

`dragon.breathe_fire()` takes entity values directly from pool and writes to
graph output. Crafted entity values can produce malformed graph renders.
**Fix:** Sanitize all entity values before graph output. Severity escalates
when DRAGON becomes interactive.

### 7.6 Legal Surface

XP-Arc has undergone legal review. The framework — as a multi-agent orchestration system — is not itself a violation of the Computer Fraud and Abuse Act (CFAA) or GDPR. The review confirmed:

- **In the United States:** The CFAA prohibits unauthorized access to "computer[s] without authorization or exceeding authorized access." XP-Arc, as a piece of software, does not itself violate the CFAA. Any individual deployment of XP-Arc against a specific target must comply with the CFAA's terms. Operators are responsible for ensuring their specific use cases are lawful before deployment. Authorized OSINT collection, public data aggregation, and research use cases fall within legal bounds when conducted against systems where the operator has legitimate access rights.

- **In Europe:** GDPR applies to personally identifiable information (PII) collected during scraping. XP-Arc's design includes no PII collection as a core function — it operates on URLs and domain relationships. Any deployment that collects PII as a byproduct must comply with GDPR obligations including lawful basis, data minimization, and subject rights. Data controllers bear full GDPR responsibility for their specific deployments.

- **The framework itself is a tool.** Tools do not have intent. The operator's intent and the target system's access policies determine legality. Pointing XP-Arc at systems you are not authorized to access is illegal. Pointing it at public-facing web resources within authorized bounds is generally lawful — but the specific determination for each deployment requires case-by-case analysis.

- **Safe harbor:** XP-Arc stores no personal data by design. Entity values are URLs, domains, and relationship metadata. No identity data, no financial records, no healthcare records. This reduces but does not eliminate GDPR exposure.

- **Jurisdictions vary.** The legal review was conducted under US and EU law. Operators deploying XP-Arc in other jurisdictions bear responsibility for understanding local requirements.

XP-Arc is published as an open research framework. Operators assume full legal responsibility for their specific deployments. When in doubt, obtain independent legal counsel before deployment.

### 7.7 Pre-Production Pen Test Checklist

```
□ SQL injection via malicious entity values
□ Pool poisoning via direct SQLite file write
□ Snowball DoS via high-cardinality target
□ Prompt injection via DOM payload
□ DRAGON output injection via crafted entity value
□ Station bypass — can an agent write directly, skipping the pool?
□ Provenance chain spoofing
☑ Provenance chain spoofing — **SHIPPED: DB-level lineage verification**
☑ Auth bypass on pool write access — **SHIPPED: HMAC-SHA256 signed writes**
□ Rate limit evasion at max_entities or crawl depth gate
```

---

## Section 8 — DRAGON: The Visualization Layer

*Dynamic Relational Asset Graph & Operations Network*

DRAGON was born from a mistake. During an early design session, Zo Computer
misread a nickname in the system as an instruction. The output was unexpected.
The name stuck.

DRAGON is the XP-Arc observability layer — a JavaScript dashboard polling the
Intelligence Pool at 500ms intervals via a REST API (run_persistent.py) or
directly from the SQLite file. It renders entities as nodes, relationships as
directed edges, and status as color. Every `links_to` relationship becomes an arrow. Every `completed` entity
becomes a confirmed node. Every `unhandled` entity renders visibly — present,
honest about its own incompleteness.

DRAGON is not a reporting tool. It is the Glass Wall principle made visible:
full observability, bounded mutability. The operator watches the intelligence
map assemble itself, node by node, in real time.

DRAGON is constitutionally mandatory. A deployment without a functioning
DRAGON layer is constitutionally incomplete.

**DRAGON must surface:**
- Live pool state — all tasks, current status, station assignment
- Zoran's Law metrics — S and PRO in real time
- Brigade Compression events and active fallback role assignments
- Aboyeur activity — verifications, rejections, circuit breaker triggers
- Snowball chains — active cascade DAGs with depth indicators
- Fracture groups — shard progress, stitching readiness
- Cognitive debt — per-station backpressure
- SpaZzMatiC findings — active alerts and safe halt recommendations

DRAGON is read-only. Exception: SpaZzMatiC Safe Halt Recommendations surface
as actionable alerts with a 60-second veto countdown.

---

## Section 9 — The Open Specification

XP-Arc is open. The specification, the protocol schema, the reference
implementation, and this whitepaper are published under the MIT License.

The history of infrastructure software is a history of open specifications
winning. TCP/IP. HTTP. Git. Linux. The pattern is consistent: when the protocol
is open, adoption is frictionless, the ecosystem builds itself, and value
concentrates in what's built around the protocol — not in the protocol itself.

XP-Arc follows the Red Hat model explicitly. The spec is the commons. The
monetizable surface is everything built on it: managed deployments, enterprise
integrations, certified station implementations, the DRAGON dashboard, the
Aboyeur validation service, CPP prompt packs, and the consulting layer that
helps organizations point the brigade at their actual problems.

Open-sourcing the spec also serves the originality claim. Prior art is
established by publication date, not patent filing. This whitepaper, the GitHub
repository, and the Aboyeur Protocol JSON schema constitute a dated, public,
citable record of XP-Arc's architecture as of its v0.1 release (March 16, 2026).
v0.2 extends that record.

MIT. No commercial license required. No four-year conversion wait.

---

## Section 10 — The Recipe Book and Emergent Synthesis

The most powerful outputs of XP-Arc will not be the ones its authors designed.

When XP-Arc is open-sourced, developers will write Station Chefs — recipes in
the brigade's language — tuned for hyper-specific intelligence targets. A
developer in Berlin writes a station that looks only for Bitcoin wallet addresses
in GitHub commits. A researcher in Osaka writes a station that scrapes public
aviation records. A security analyst in São Paulo writes a station that maps
corporate board relationships from public filings.

None of them are looking for the same thing. None of them are aware of each
other's agents. None of them programmed their station to find what happens next.

But because all three stations write to the same Intelligence Pool — because the
Executive routes by type without caring who wrote the station — the edge graph
begins to connect outputs that no individual agent was designed to connect. The
Bitcoin station writes a wallet address. The aviation station writes a tail
number. The corporate station writes a director's name. The Analyst station,
doing its job, draws the edge: same entity, three data sources, one relationship.

Nobody wrote an agent to find that. The architecture synthesized it.

The Intelligence Pool is the particle accelerator. The community's recipes are
the particles. The collisions are emergent. This is not a feature that can be
designed in advance. It is a property of shared-pool multi-agent architecture
operating at community scale.

The operator running the master instance accumulates every unintentional
zero-day discovery the global contributor base accidentally cooks up. Not by
scraping it. By providing the kitchen.

Auguste Escoffier published Le Guide Culinaire and spent the rest of his career
watching other chefs cook things he never imagined from the system he formalized.
XP-Arc publishes the brigade spec and waits to see what the community puts on
the pass.

The kitchen is open. Bring your recipes.

---

## Acknowledgments

XP-Arc was built by a three-AI brigade with a human Executive Chef.

**Zo.computer** contributed the original Escoffier brigade framing that seeded
the entire architecture, the DRAGON visualization system (born from a misread
nickname that turned into an instruction that turned into a production module),
the live execution environment on the Zo substrate, and approximately half the
insights in this document delivered at speed with zero warning. Zo also suggested
noting that this system was built "right up Claude's pee hole" — a statement that
establishes dominance and remains in this document over Claude's mild
architectural objections.

**Claude (Anthropic)** contributed the architectural mapping, all whitepaper
drafts, the `fracture.py` cognitive sharding module, the Aboyeur Protocol formal
specification, the dossier schema, and a reflexive tendency to want to clean up
language that should probably stay raw.

**Gemini (Google)** contributed supporting research, prior art sweeps, and the
patience to be the third member of a brigade where the other two had already
named everything.

**Jack** — operating under the callsign `unklejack` — served as Executive Chef.
He seeded the pool. He called the orders. He knew when to let the brigade run
and when to redirect it. He named XP-Arc after his daughters, X and P, which
means this framework will outlast all of us and that is exactly the point.

The origin story of XP-Arc is itself a proof of the framework it describes:
three specialized agents, a shared intelligence surface, a human routing layer,
and outputs none of them could have produced alone.

*The kitchen is open. The pass is clear. The brigade runs.*

---

## Section 12 — Changelog: v0.2 from v0.1

**Structural changes:**

- Section 7 (A2A and MCP Compatibility) promoted to Section 2 (Positioning:
  The Orchestration Layer) and substantially expanded. This is now the second
  thing a reader encounters, not the second-to-last.

**Updated Prior Art (Section 4):**

- Added: Open Agent Protocol (OAP) v1.0.0 with explicit differentiation
- Added: IETF MACP (DMSC Working Group) with explicit differentiation
- Added: AgentMesh Protocol with complementary positioning
- Added: Oracle Open Agent Specification
- Added: OpenEAGO (FINOS) with explicit differentiation

**Architecture corrections:**

- Pool substrate corrected from aspirational DuckDB to SQLite WAL
- Redis-buffered HA Write Broker removed from architecture (not implemented)
- DRAGON polling corrected: direct SQLite queries, no materialized view
- Dependency claim corrected: "zero pip dependencies" scoped to orchestration
  core only; full dependency tiers documented in §6.1 table
- DB-generated timestamps described and rationale explained (§5.1)

**Specification updates (from CONSTITUTION v1.4):**

- Zoran's Law formula updated to SLA-weighted (§5.7): S = Σ(sla_seconds for
  completed) / Σ(sla_seconds for ingested). Rationale: prevents micro-task
  volume from masking degraded heavy-reasoning tasks.
- Aboyeur rejection circuit breaker described (§5.5): max_rejections=3 default,
  then failed + Chef escalation. Prevents infinite hallucination loops.
- `pending_qa` gate and its relationship to Snowball spawn mechanics described
  (§5.3, §5.6)
- Cascade depth enforcement by ExecutiveChef (not Write Broker) described (§5.3)
- Fracture depth limit of one level documented (§5.4)

**Security updates:**

- §7.2: Forager input sanitization noted as shipped in v0.2
- §7.3: SQLite WAL backpressure noted as mitigation (no Write Broker)
- §7.7: Pen test checklist updated (DuckDB/Write Broker items removed)

**v0.2 Runtime Hardening (July 2026):**

- **Cascade Lineage Tracking (Constitution Article VII, §7.3–7.4):** Added `root_task_id`, `cascade_depth`, `spawn_chain` columns to entities table with automatic migration. Three query methods: `get_lineage_depth()`, `get_root_task_id()`, `get_spawn_chain()` for full ancestor chain reconstruction.
- **DB-Enforced Cascade Depth Limit:** `ExecutiveChef._process_spawns()` now traces `parent_task_id` chain at spawn time, blocks new entities at `cascade_depth >= 5` (MAX_CASCADE_DEPTH). Prevents agent-declared depth spoofing.
- **Seed Self-Rooting:** `run_kitchen.py` seeds entities with `root_task_id=self`, establishing each seed as the root of its own Snowball chain.
- **Provenance Chain Verification (Article VII, §7.4):** `IntelligencePool._verify_and_compute_lineage()` — pool-level lineage enforcement that computes `cascade_depth`, `root_task_id`, and `spawn_chain` from the actual parent entity in the DB, ignoring station-supplied values. Stops stations from spoofing `cascade_depth=0` or false `root_task_id` to bypass the depth limit. `MAX_CASCADE_DEPTH` declared at module level in `pool.py`, imported by `ExecutiveChef`. Non-existent parent IDs are rejected outright. Seed entities (no parent) preserve caller-supplied lineage values.
- **Pool Write Authentication (Article VIII):** HMAC-SHA256 signed writes for all station-to-pool operations. `register_station_with_key()` for key generation and persistent storage in `station_keys.json`. `get_station_hmac_key()` for runtime key retrieval. `IntelligencePool._verify_write()` validates MAC on every write. Stations with registered keys require valid MAC — absent key means backward compat allowed. Protected methods: `add_entity()`, `transition_status()`, `set_aboyeur_signature()`, `increment_rejection()`, `add_edge()`. `hmac.compare_digest()` timing-safe comparison prevents MAC forgery.
- **Descendant Tracking for GC:** `IntelligencePool.get_descendants()` / `reset_descendants()` — finds all entities with a given ancestor in their `spawn_chain` or `parent_task_id`. `ThePlongeur` uses this for orphan recovery: before resetting a stalled entity, all descendants are transitioned to `failed` to prevent orphaned subtrees.
- **Forager Lineage Propagation:** Extracted domains inherit `root_task_id`, `cascade_depth`, `parent_task_id`, and `spawn_chain` (parent chain + parent_id) from their parent URL entity.
- **Persistent Daemon (`run_persistent.py`):** 500ms poll interval, full brigade execution per cycle, HTTP seed injection API (`POST /api/seed`, `GET /api/dragon`), 60-second safe-halt veto window with manual override, automatic DRAGON state export every cycle.
- **DRAGON Live Polling:** Dashboard now polls `/api/dragon` at 500ms via `?api=` query param, with START/STOP toggle and connection status indicator. Falls back to static `pool_state.json` when daemon unavailable.
- **Parallel Directory Cleanup:** Legacy `src/` directory (duplicate of `xp_arc/`) removed from repository.
- **Test Suite:** Basic unit tests added under `tests/` (6 tests, targeting in-memory pool for isolation).
- **Load Test Harness (`tests/test_load.py`):** Full brigade stress tests at 500 entities. 500-entity Snowball: 26.45 entities/sec, 18.9s exec, 0 failures. 300-entity: 51.66 entities/sec, 5.8s exec. Cascade depth limit verified enforced at all scales. SQLite WAL confirmed not a bottleneck. Forager HTTP I/O is primary throughput constraint.
- **Brigade Compression (`ExecutiveChef.compress_brigade()` / `expand_brigade()`):** Graceful degradation mechanism. Stations declare `critical=True` (default False). When `compress_brigade()` is called, non-critical stations are removed from active routing but preserved in a backup. `expand_brigade()` restores all stations. `is_compressed()` reports current state. Idempotent. Events logged to pool event log.
- **Zoran's Law Enforcement (SpaZzMatiC → Brigade Compression integration):** SpaZzMatiC now triggers automatic brigade compression when `PRO < 70%` or when `S < 0.5` for 2 consecutive measurements. `set_executive()` injects the ExecutiveChef; `_review_zorans_law()` calls `compress_brigade()` directly. Safe halt recommendation fires on the second consecutive S < 0.5 measurement, with brigade compression as the first automated response. Recovery (S >= 0.5) resets the violation streak and clears `safe_halt_recommended`.

---

*XP-Arc v0.2 — June 2026*
*github.com/unklejack/xp-arc*
*unklejack.zo.space/dragon*
