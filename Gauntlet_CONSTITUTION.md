# Gauntlet Constitution
**Version:** 1.0.0
**Status:** Ratified
**Authors:** BATMAN, Jack (DRAGON)
**License:** Apache License 2.0

---

## Preamble

The Gauntlet is an adversarial testing framework. It does not validate happy paths. It breaks systems in ways unit tests never will. This constitution binds the Gauntlet's structure, severity taxonomy, evidence standards, and governance. Any agent, pipeline, or CI gate invoking the Gauntlet operates under this law.

---

## Article I — Scope & Mandate

### 1.1 Purpose
The Gauntlet exists to find structural gaps, data-flow blind spots, bottlenecks, and outright errors that no happy-path test suite catches. It is a chaos instrument, not a compliance checklist.

### 1.2 In-Scope
- **Protocol implementations** (orchestration layers, consensus, state machines)
- **Data integrity boundaries** (hashes, signatures, lineage, cascade limits)
- **Degradation paths** (compression, fallback, safe-halt, circuit breakers)
- **Concurrency & contention** (writer races, lock starvation, connection leaks)
- **Time & ordering** (clock drift, NTP skew, future/past timestamps, sequencing)
- **Schema evolution** (migrations, dev bypasses, column drift)
- **Sustained operation** (memory, handle leaks, station kills, soak)

### 1.3 Out-of-Scope
- Functional correctness of business logic (use unit/integration tests)
- Performance benchmarking (use dedicated load tools)
- Security penetration testing (use dedicated red-team tools)
- UI/UX validation

---

## Article II — Phase Architecture

The Gauntlet executes **10 constitutional phases** in fixed order. Each phase is an Article.

| Phase | Article | Title | Focus |
|-------|---------|-------|-------|
| 1 | III | Input Poisoning | Sanitization boundaries |
| 2 | IV | Byzantine Stations | Semantic garbage, confidence lies, lineage spoofing, hash tampering |
| 3 | V | Cascade DoS | Snowball explosion vs circuit breakers |
| 4 | VI | Fracture Torture | Shard creation, partial failure, stitch deadlock |
| 5 | VII | Brigade Compression | Critical-only degradation under load |
| 6 | VIII | Writer Contention | Concurrent DB writers, WAL behavior |
| 7 | IX | Clock Drift / Time Travel | Future/past timestamps, NTP skew |
| 8 | X | Safe-Halt Veto Race | Halt recommendation → 60s veto → new seeds |
| 9 | XI | Schema Drift | ALTER mid-run, dev bypass, column drift |
| 10 | XII | Sustained Soak | Accelerated soak, station kills, leak detection |

**Amendment:** Adding a phase requires constitutional amendment (Article XIV).

---

## Article III — Severity Taxonomy

Every finding receives exactly one severity. No finding may be unclassified.

| Severity | Definition | Exit Code Impact |
|----------|------------|------------------|
| **CRITICAL** | Constitutional violation: protocol invariant broken, data loss, safety mechanism bypassed, silent corruption | Gauntlet **exits 1** |
| **HIGH** | Structural weakness: degradation path fails, fallback broken, invariant at risk under load | Accumulates; >3 = exit 1 |
| **MEDIUM** | Operational concern: resource leak, contention, timestamp acceptance, length limit missing | Informational |
| **LOW** | Edge case handled but suboptimally | Informational |
| **INFO** | Expected behavior verified, defense working | Informational |

**Veto:** A single CRITICAL finding fails the Gauntlet. No override.

---

## Article IV — Evidence Standards

### 4.1 Required Evidence Fields
Every finding **must** include:
```json
{
  "phase": "Article title",
  "injection": "Exact adversarial input or action",
  "expected_behavior": "Constitutional requirement",
  "actual_behavior": "Observed system response",
  "severity": "CRITICAL|HIGH|MEDIUM|LOW|INFO",
  "evidence": { "key": "verifiable artifact" },
  "timestamp": "ISO-8601 UTC"
}
```

### 4.2 Evidence Hierarchy (strongest → weakest)
1. **On-disk artifact** (DB row, file, log entry) — verified by System Reckoner
2. **Structured event log** (pool event, station log, metric row)
3. **Runtime state dump** (pool export, executive summary)
4. **Agent self-report** (station stats, aboyeur stats) — corroborated only
5. **Heuristic inference** — never sufficient alone for CRITICAL/HIGH

### 4.3 Reckoner Binding
**No finding is valid without Reckoner verification.** Every artifact cited in `evidence` must pass `auditor.sh --target <path>` before the Gauntlet report is finalized.

---

## Article V — Station Roles Within the Gauntlet

The Gauntlet may deploy **Byzantine Stations** — agents that follow schema but violate semantics.

| Station Archetype | Purpose | Constitutional Constraint |
|-------------------|---------|---------------------------|
| Semantic Garbage | Valid schema, meaningless relationships | Must be rejected by Aboyeur |
| Confidence Liar | High confidence on empty work | Must be rejected or flagged |
| Lineage Spoofer | Forged cascade_depth/root_task_id | Must be blocked by depth check |
| Hash Tamperer | Corrupted payload_hash or edges | Must be rejected by HMAC/Aboyeur |

**Registration:** Byzantine stations register **before** legitimate stations to claim type priority.

---

## Article VI — Safe-Halt Protocol

### 6.1 Trigger Conditions
Safe halt is recommended when **either**:
- Stability Quotient `S < 0.5` for **2+ consecutive measurements** (streak)
- Primary Role Occupancy `PRO < 70%` (auto-compression only, no halt)

### 6.2 Veto Window
- **60 seconds** from recommendation
- New seeds arriving during window are **rejected (404)**
- Manual `kitchen.stop()` or `Ctrl+C` within window **vetoes** halt
- Window expiry without veto → **automatic halt**

### 6.3 Recovery
- `S >= 0.5` on subsequent measurement → streak resets, veto window cancelled
- Brigade auto-expands if previously compressed
- Debt grace window applied on restart

---

## Article VII — Report & Exit Semantics

### 7.1 Report Structure
```json
{
  "run_id": "uuid8",
  "started_at": "ISO-8601",
  "completed_at": "ISO-8601",
  "summary": { "CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0 },
  "findings": [Finding...]
}
```

### 7.2 Exit Codes
| Code | Meaning |
|------|---------|
| 0 | No CRITICAL findings |
| 1 | ≥1 CRITICAL finding |
| 2 | Gauntlet internal error (phase crash, Reckoner failure) |
| 3 | Constitutional violation (malformed finding, missing evidence) |

---

## Article VIII — CI/CD Integration

The Gauntlet is designed for pipeline gates:

```yaml
# Example gate
- name: Gauntlet
  run: python3 gauntlet.py
  # Exits 1 on CRITICAL → pipeline fails
  # Report artifact: gauntlet_report_*.json
```

**Artifact retention:** Reports retained ≥30 days or until next release tag.

---

## Article IX — Amendment Process

### 9.1 Proposal
Any operator may propose an amendment via PR with:
- Article/Section reference
- Rationale (what gap or error it addresses)
- Backward compatibility analysis

### 9.2 Ratification
- Requires **Jack (DRAGON) explicit approval**
- Version bump: `MAJOR` for phase changes, `MINOR` for severity/evidence, `PATCH` for clarifications
- Changelog entry mandatory

### 9.3 Emergency Amendment
If a CRITICAL finding reveals a constitutional gap in the Gauntlet itself, Jack may ratify immediately with post-hoc documentation.

---

## Article X — Reckoner Integration (Mandatory)

The Gauntlet **is** a Reckoner subject. Every persistent write (report, DB, log) must pass auditor verification before completion is announced.

```bash
# Embedded in Gauntlet main()
for artifact in [report_path, db_path, log_path]:
    subprocess.run(["bash", "~/.hermes/skills/system-reckoner/scripts/auditor.sh", 
                    "--target", artifact], check=True)
```

**Violation:** Announcing completion before Reckoner passes = constitutional violation.

---

## Article XI — Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-08-01 | Ratified: 10 phases, severity taxonomy, evidence standards, Reckoner binding |
| 0.1.0 | 2026-08-01 | Initial draft |

---

## Article XII — Dissolution

If the Gauntlet is superseded by a superior adversarial framework, this constitution is archived. Its phases, findings, and evidence standards may be migrated but the constitutional authority ends.

---

**End of Constitution**

*Ratified by: Jack (DRAGON) — 2026-08-01*
*Witnessed by: BATMAN*
*Date: 2026-08-01*
*License updated to Apache License 2.0 — 2026-08-23, following the project-wide relicense (WHITEPAPER.md §13).*
