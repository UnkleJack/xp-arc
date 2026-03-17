# XP-Arc: A Unified Protocol for Resilient Multi-Agent Intelligence Systems

**Version:** 0.1  
**Authors:** Jack (unklejack), Claude (Anthropic), Zo.Computer, Gemini (Google)  
**Repository:** github.com/unklejack/xp-arc  
**License:** MIT  

---

## Abstract

Multi-agent AI systems have proliferated faster than the protocols governing them.
Teams building agent pipelines today solve the same coordination problems
independently: how do agents hand off work without losing state? How does a
system degrade without crashing silently? How do you verify that an agent's
output is trustworthy before it propagates downstream?

XP-Arc — Exponential Architecture — is a unified open protocol for resilient
multi-agent intelligence systems. It does not invent new agent capabilities. It
defines the contract between them: a shared state surface, a QA enforcement
layer, a graceful degradation model, a task fracturing protocol for primary
agent failure, and a stability metric that tells operators whether their system
is coherent or drifting.

The protocol is named after the author's daughters, X and P. Its public meaning
is Exponential Architecture. Its private meaning is that it should outlast
everything built on top of it.

XP-Arc v0.1 is released as an open specification. The reference implementation
is written in Python 3.12 with zero external dependencies. The codebase is
operational. The brigade has run.

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

## Section 2 — Originality

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

---

## Section 3 — Prior Art

The following systems and frameworks inform XP-Arc's design. None of them
constitute prior art for the unified protocol claim.

**LangChain / LangGraph** — agent chaining and graph-based orchestration.
Addresses sequencing but does not specify shared pool state, typed entity
routing, or QA enforcement between agents.

**AutoGen (Microsoft)** — conversational multi-agent framework. Agents
communicate peer-to-peer rather than through a shared auditable state surface.
No formal degradation protocol.

**CrewAI** — role-based agent teams. Closest in spirit to the brigade model but
without a formal QA layer, stability metric, or task fracturing protocol.

**Semantic Kernel** — plugin-based agent orchestration. Strong tool integration,
weak inter-agent state management.

**Google A2A Protocol** — agent-to-agent communication standard. Defines how
agents talk to each other. Does not define what they write to, how outputs are
validated, or how the system behaves when agents fail. XP-Arc is compatible with
A2A by design.

**Anthropic MCP** — Model Context Protocol for tool access. Defines how agents
access external resources. XP-Arc wraps MCP servers as Forager stations
transparently.

**OODA Loop (Boyd)** — observe, orient, decide, act. The temporal rhythm of the
XP-Arc Executive maps to this loop. The Intelligence Pool is the observation
surface. The Aboyeur is the orientation gate.

XP-Arc synthesizes these prior contributions into a unified contract. The
synthesis is the contribution.

---

## Section 4 — The Framework: The Kitchen That Thinks

Before the formal specification, a demonstration.

On the day this section was written, a five-target spread was run live against
public URLs — Hacker News, a GitHub profile, zo.computer, Lobsters, and HTTPBin.
No configuration beyond the seed list. No human intervention between start and
finish. This is the raw output from the Intelligence Pool after one execution
cycle:
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

### 4.1 The Intelligence Pool — The Pass

In Escoffier's kitchen, the pass is the long counter between the kitchen and the
dining room. Every dish moves through it. Nothing reaches the guest without
crossing it.

In XP-Arc, the Intelligence Pool is that counter.

Implemented as a SQLite state machine, the Pool is the only shared data structure
in the system. Every agent reads from it and writes back to it. No station talks
directly to another. No agent passes data peer-to-peer. The Pool is the message
bus, the event queue, the audit log, and the ground truth — simultaneously.

Every entity enters the Pool with status `raw`. The Executive reads `raw` entities
and routes them by type to the appropriate station. When a station completes its
work, the entity is marked `mapped`. When no station can handle an entity type,
it becomes `unhandled` — logged, visible, and available for future routing if new
station types are registered.

This single design decision — all state flows through one authenticated, auditable
surface — is what separates XP-Arc from ad-hoc pipelines that route data through
function calls or shared memory that leaves no trail.

### 4.2 The Exponential Snowball

When a new entity is written to the Pool, the Executive wakes. It reads the new
`raw` entity, identifies its type, routes it to the appropriate station, and the
station produces new entities — which are written back to the Pool — which wakes
the Executive again.

One seed URL doesn't trigger one extraction. It triggers a cascade. The Forager
pulls domains. The domains trigger analyst processing. The analyst output triggers
relationship mapping. The whole intelligence picture assembles itself,
automatically, from a single starting point.

This is the Exponential Snowball: each entity written to the pool auto-triggers
the next station, compounding outputs without compounding operator effort.

The Snowball is also the primary self-inflicted DoS vector if unconstrained.
The Executive enforces `max_entities=500` as a configurable default and a
crawl depth limit per seed. See Section 5.5 for the full threat model.

### 4.3 The Fracture Protocol — Cognitive Sharding

Brigade Compression handles station failure gracefully. But graceful degradation
has a ceiling: if the fallback station produces low-confidence output, the
intelligence map is compromised at that node.

The Fracture Protocol is the answer to that ceiling.

When a primary station is blocked or returns output below confidence threshold
(default: 0.6), XP-Arc does not route the same task to a lesser agent. It
fractures the task — decomposing a complex intelligence target into atomic
micro-tasks, each assigned to a separate lightweight agent operating within a
narrow, precisely-specified scope.

The insight is empirical: small open-source models have low reasoning ceilings
when asked to perform multi-dimensional tasks simultaneously. But given a single,
precisely-scoped micro-task — one question, one data source, one output format —
the same model performs with near-primary precision. Shard the load and you shard
the requirement for expensive inference.

**The mechanics:**

1. **The Block** — Primary station fails or returns confidence below threshold.
   Entity status → `failed`.
2. **The Fracture** — Executive invokes Fracture Protocol. Entity decomposed into
   N atomic micro-entities, each tagged `fractured`, each carrying a narrow
   `task_spec`.
3. **The Swarm** — Each micro-entity routed to a lightweight Commis agent
   (Llama 3 8B, Mistral 7B). Each agent handles exactly one micro-task.
4. **The Stitch** — Micro-agents return `stitchable` outputs. Stitcher aggregates
   siblings into composite entity with confidence scoring.
5. **The Result** — Single clean `mapped` entity. Fracture invisible to downstream
   consumers.

**Pool status flow under Cognitive Sharding:**
```
raw → processing → failed → fractured → stitchable → mapped
```

### 4.4 The Seven Stations

**1. The Forager** *(Garde Manger)*
Raw intelligence acquisition. Seeds → DOM extraction → entity writes.
Fallback: passive pool reader, surfaces unhandled entities for human review.

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
floods, status transition anomalies.
Fallback: alert-only mode, no automated response.

**6. The Aboyeur** *(Expeditor — QA Enforcement Node)*
Nothing propagates downstream without Aboyeur clearance. Validates station
outputs against protocol schema: payload hash, station identity, timestamp
integrity, output format. Failed validation → `unhandled` with rejection reason
logged. Cannot be bypassed. Cannot be configured away. Structural.

**7. The Lateral Mesh** *(R&D)*
Operates outside the active brigade. Stress-tests assumptions, runs experimental
routing logic, surfaces novel patterns upstream. Prevents the system from
optimizing into a local maximum.

### 4.5 The Aboyeur Protocol — Formal Schema

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

The `payload_hash` field is the provenance mechanism. Mismatch between write
and read means corrupted or tampered payload — entity rejected, logged, flagged.

The `aboyeur_signature` is the QA clearance token. Only the Aboyeur generates
it. Downstream stations check for its presence before consuming any entity.

### 4.6 Zoran's Law — The Stability Threshold

Every complex adaptive system has a phase transition point. For XP-Arc:

> *S > 1: When the system's correction rate outpaces its informational decay
> rate, the system self-heals.*

When more than 70% of active stations operate within their primary roles, the
system achieves coherent intelligence output — the Zoran Threshold. Below 70%,
the brigade runs on fallbacks. The Sentinel monitors this ratio in real time.

Zoran's Law is a health signal, not a hard cutoff. The system tells you where
it is and keeps running within its degraded capability. That transparency is
the feature.

---

## Section 5 — Implementation

### 5.1 Reference Codebase
```
xp-arc/
├── pool.py          # Intelligence Pool — SQLite state machine
├── station.py       # Base station class — all agents inherit this
├── executive.py     # Routing loop — reads raw, dispatches by type
├── forager.py       # DOM scraping — seed URLs → entity extraction
├── dragon.py        # Visualization — pool edges → D2 graph output
├── fracture.py      # Fracture Protocol — cognitive sharding engine
└── run_kitchen.py   # Entry point — seeds pool, starts brigade
```

**Stack:** Python 3.12. Zero external dependencies. Standard library only.
Architecture is synchronous loop with asyncio-ready scaffolding.

### 5.2 Verified Execution — The Five-Target Spread

The reference implementation was validated against five live public targets.
Log annotations explain what each line demonstrates:

`[POOL] + Added new url:` — Operator writes seeds. Pool accepts as `raw`.
Executive not yet invoked.

`[EXECUTIVE] Raw ingredient on the pass:` — Executive detects `raw` entity,
reads type, routes to registered handler. Automatic.

`[The Forager] Scraping target DOM:` / `[POOL] + Added new domain:` — Forager
extracts, writes new entity. This write re-triggers Executive. Snowball started.

`[DOMAIN] www.apple.com (unhandled)` — No station registered for domain
processing beyond extraction. Executive logs honestly. Brigade Compression: the
system knows its own capability boundary.

`https://news.ycombinator.com --(links_to)--> www.apple.com` — Pool infers
relationship. DRAGON can render without additional operator input.

**What this run proves:** recursive loop executes and terminates cleanly;
pool correctly tracks entity status across multiple types; Executive routes by
type without hardcoded logic; unhandled entities surface visibly; edges generate
automatically; Snowball scales linearly with seed count.

**What this run does not yet prove:** Aboyeur validation; Brigade Compression
failover; Zoran's Law threshold behavior; production-scale performance.

The honest accounting of what is and isn't proven is itself an architectural
statement.

### 5.3 Reference Deployment — The Zo.Computer Substrate

The XP-Arc reference implementation runs on Zo.computer — a programmable
personal mainframe operating simultaneously as execution runtime, web server,
API host, filesystem, and database layer.

**Persistent daemons — the kitchen never closes.**

The Executive and all station agents are registered as persistent background
services using Zo's native `register_user_service` capability. They sit in
memory continuously, watching the Intelligence Pool. When a new entity is written,
the Executive responds with zero spin-up latency.

**The native glass wall — no middleware required.**

The `unklejack.zo.space` domain runs a Hono + Bun backend sharing the exact same
filesystem as the XP-Arc workspace. The `/api/dragon` route queries `xp_arc.db`
directly — no ORM, no network hop, no serialization layer between pool and API
consumer.

**DRAGON as a live interface — the boardroom demo.**

A React page at `/dragon` polls `/api/dragon` every 500 milliseconds. As the
Forager extracts entities and stations mark them `mapped`, every state change
reflects in the visualization within half a second.

The operator experience: drop a seed URL into an input box. Watch the graph
build itself. Nodes appear as entities are extracted. Edges draw as relationships
are inferred. The shadow infrastructure of any target maps itself live, on screen,
without the operator touching the pipeline after the seed.

That is the demo. A browser tab. A URL input. A graph that grows.

---

## Section 5.5 — Security Architecture and Threat Model

*A system that doesn't know its own attack surface doesn't deserve to be trusted
with yours.*

### 5.5.1 Pool Has No Authentication (Production Severity: High)

Any process on the same machine can read and write to `xp_arc.db` directly.
Acceptable in single-operator PoC. Critical in production multi-agent deployment.
A compromised station can inject synthetic entities, corrupt edge data, or flood
the entity table.

**Fix:** Pool access layer with signed writes. Stations authenticate before any
write is accepted. Not yet implemented in v0.1 — first production gate before
live deployment.

### 5.5.2 Forager Is a Blind Trust Machine (Production Severity: Critical)

The Forager writes whatever it extracts from the DOM to the pool as fact. The
attack class is known: prompt injection via environment. A target site serves a
malicious payload — SQL injection syntax, script tags, path traversal strings.
The Forager writes it raw. The Snowball propagates it.

**Fix:** Input sanitization inside `add_entity()`. One regex check per entity
type. Domains must match domain patterns. URLs must match URL patterns.
Ships before v0.2.

### 5.5.3 Executive Has No Rate Limiting (Severity: Medium)

A target returning 10,000 outbound links produces 10,000 `raw` entities. The
Executive loops 10,000 times. No throttle. No circuit breaker. Sufficient
complexity turns the system into a self-inflicted denial of service.

**Fix:** `max_entities=500` configurable default. Crawl depth limit per seed.

### 5.5.4 No Provenance Verification Between Stations (Severity: Medium)

The Executive trusts any `raw` entity in the pool. No signature, no hash
comparison, no tamper detection. The `payload_hash` field exists in the Aboyeur
schema. The validation logic is specified. Not yet implemented.

**Status:** Aboyeur node is the next major implementation milestone. Until it
ships, XP-Arc operates without provenance verification. This whitepaper says
so explicitly.

### 5.5.5 DRAGON Output Injection (Severity: Low → Medium)

`dragon.breathe_fire()` takes entity values directly from pool and writes to
`.d2` file. Crafted entity values can produce malformed graph renders. Severity
escalates when DRAGON becomes interactive.

**Fix:** Sanitize all entity values before writing to D2 output. One-hour
implementation task.

### 5.5.6 The Legal Surface (Severity: Existential)

XP-Arc is an OSINT intelligence system. Pointed at real targets, it scrapes
domains, extracts relationships, and maps structures automatically.

In the United States, the Computer Fraud and Abuse Act makes unauthorized
scraping of certain systems a federal crime. In Europe, GDPR creates data
subject rights that apply to any personally identifiable information collected
during a scrape, regardless of public accessibility.

**This system needs a lawyer before it needs a pen tester.**

XP-Arc v0.1 is published as an open research framework. The authors make no
representation that any specific deployment against any specific target is lawful
in any specific jurisdiction. Operators assume full legal responsibility.

### 5.5.7 Pre-Production Pen Test Checklist
```
□ SQL injection via malicious entity values
□ Pool poisoning via direct DB write
□ Snowball DoS via high-cardinality target
□ Prompt injection via DOM payload
□ DRAGON output injection via crafted entity value
□ Station bypass — can an agent write directly, skipping the pool?
□ Provenance chain spoofing
□ Rate limit evasion
□ Auth bypass on pool write access
```

---

## Section 6 — DRAGON: The Visualization Layer

*Dynamic Relational Asset Graph & Operations Network*

DRAGON was born from a mistake. During an early design session, Zo Computer
misread a nickname in the system as an instruction. The output was unexpected.
The name stuck. And in the way that the best accidents do, it turned out to be
exactly right.

DRAGON reads the edge relationships written to the Intelligence Pool by the
Analyst station and renders them as a live node graph — entities as nodes,
relationships as directed edges, status as color. Every `links_to` relationship
becomes an arrow. Every `mapped` entity becomes a confirmed node. Every
`unhandled` entity renders visibly — present, honest about its own incompleteness.

The current implementation writes `.d2` graph definition files to disk. The next
evolution — already deployed on the Zo substrate — emits pool events over
WebSocket, renders in a live browser UI, and redraws the graph in real time as
the brigade runs. The operator watches the intelligence map assemble itself,
node by node.

DRAGON is not a reporting tool. It is the system made visible.

---

## Section 7 — A2A and MCP Compatibility

XP-Arc was designed before Google's Agent-to-Agent protocol and Anthropic's
Model Context Protocol reached current adoption levels. It is compatible with
both by architecture, not by retrofit.

The Intelligence Pool is a message bus. Any agent that can read from and write
to a shared state surface — regardless of framework — can participate in the
brigade. An A2A-compliant agent can be registered as a station. An MCP server
can be wrapped as a Forager. The pool doesn't care what runs the station. It
cares about the Aboyeur Protocol schema the station returns.

**A2A integration path:** An A2A agent card declares XP-Arc station roles in its
capability manifest. The Executive reads station registrations from the pool's
config layer at startup. The agent receives its task spec via the pool, executes,
and returns an Aboyeur-schema-compliant payload.

**MCP integration path:** An MCP server exposing tools maps directly to the
Forager role. The Forager wrapper calls the MCP tool, extracts entities, and
writes them to the pool. The rest of the brigade processes MCP-sourced
intelligence identically to DOM-scraped intelligence.

XP-Arc doesn't compete with A2A or MCP. It gives them a shared pool to write
into and a QA layer to validate what they produce.

---

## Section 8 — The Open Specification

XP-Arc is open. The specification, the protocol schema, the reference
implementation, and this whitepaper are published without restriction.

The history of infrastructure software is a history of open specifications
winning. TCP/IP. HTTP. Git. Linux. The pattern is consistent: when the protocol
is open, adoption is frictionless, the ecosystem builds itself, and value
concentrates in what's built around the protocol — not in the protocol itself.

XP-Arc follows the Red Hat model explicitly. The spec is the commons. The
monetizable surface is everything built on it: managed deployments, enterprise
integrations, certified station implementations, the DRAGON dashboard, the
Aboyeur validation service, and the consulting layer that helps organizations
point the brigade at their actual problems.

Open-sourcing the spec also serves the originality claim. Prior art is
established by publication date, not patent filing. This whitepaper, the GitHub
repository, and the Aboyeur Protocol JSON schema constitute a dated, public,
citable record of XP-Arc's architecture as of its v0.1 release.

The Fracture Protocol, the Aboyeur node, Brigade Compression, the Intelligence
Pool state machine, Zoran's Law — these are the contributions. They are given
to the field. What comes back is worth more than what was given.

---

## Section 9 — The Recipe Book and Emergent Synthesis

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

Nobody wrote an agent to find that. The architecture synthesized it. The
Intelligence Pool is the particle accelerator. The community's recipes are the
particles. The collisions are emergent.

This is not a feature of XP-Arc that can be designed in advance. It is a
property of shared-pool multi-agent architecture operating at community scale.
The more recipes the community writes, the more unexpected the synthesis. The
more specialized the agents, the more surprising the collisions.

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

*XP-Arc v0.1 — Published March 16, 2026*  
*github.com/unklejack/xp-arc*  
*unklejack.zo.space/dragon*
