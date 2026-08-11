# Gauntlet Scope Configuration
**Version:** 1.0.0
**Project:** XP-Arc
**Gauntlet Version:** 1.0.0

---

## Overview

This file controls which Gauntlet phases execute for this project. Phases can be enabled, disabled, or configured with project-specific parameters. This allows the Gauntlet to be reused across different codebases with different risk profiles.

---

## Phase Activation Matrix

| Phase | Article | Enabled | Priority | Notes |
|-------|---------|---------|----------|-------|
| 1 | III | ✅ | REQUIRED | Input sanitization is foundational |
| 2 | IV | ✅ | REQUIRED | Byzantine resistance is core to XP-Arc |
| 3 | V | ✅ | REQUIRED | Snowball cascade is XP-Arc signature |
| 4 | VI | ✅ | REQUIRED | Fracture protocol is constitutional |
| 5 | VII | ✅ | REQUIRED | Brigade compression is operational law |
| 6 | VIII | ✅ | REQUIRED | SQLite WAL contention must be verified |
| 7 | IX | ✅ | REQUIRED | Time integrity is constitutional |
| 8 | X | ✅ | REQUIRED | Safe-halt is Article X compliance |
| 9 | XI | ✅ | REQUIRED | Schema drift resilience |
| 10 | XII | ✅ | RECOMMENDED | Soak test for production readiness |

**All phases enabled** — XP-Arc is a protocol implementation requiring full adversarial coverage.

---

## Phase-Specific Configuration

### Phase 1: Input Poisoning (Article III)
```yaml
enabled: true
timeout_per_injection: 5  # seconds
injections:
  - control_characters: [null, newline, cr, unit_separator]
  - length_bombs: [3000, 5000, 10000]
  - scheme_violations: [ftp, javascript, data, file]
  - encoding_attacks: [encoded_null, encoded_crlf, encoded_path_traversal]
  - idn_homographs: [cyrillic_e, greek_o, armenian_a]
  - ipv6_loopback: true
  - private_ips: [127.0.0.1, 10.0.0.1, 192.168.1.1]
  - port_overflow: [99999, 65536]
  - empty_and_whitespace: [empty, spaces, scheme_only]
```
**Customization:** Add project-specific injection vectors (e.g., GraphQL mutations, protobuf payloads).

### Phase 2: Byzantine Stations (Article IV)
```yaml
enabled: true
station_types:
  - semantic_garbage:
      handles: [domain]
      relationships: [invalid_domains, control_chars, extreme_length]
      confidence: 0.95
  - confidence_liar:
      handles: [domain]
      confidence: 1.0
      notes: "Empty work with maximum confidence"
  - lineage_spoofer:
      handles: [url]
      spawn_count: 10
      spoof_depth: 1  # Test depth 1 (allowed) vs depth 6 (blocked)
  - hash_tamperer:
      handles: [domain]
      tamper_type: edge_injection
```
**Customization:** Add Byzantine types for custom entity types (e.g., `asset`, `style_genome`).

### Phase 3: Cascade DoS (Article V)
```yaml
enabled: true
max_entities: 500
cascade_depth_limit: 5
test_scenarios:
  - single_seed_massive_spawn:
      seed_count: 1
      spawn_per_seed: 1000
      expected_blocked: 500
  - exponential_snowball:
      seed_count: 10
      max_depth: 5
      max_entities: 500
```
**Customization:** Adjust `max_entities` for load test tiers (100/500/1000).

### Phase 4: Fracture Torture (Article VI)
```yaml
enabled: true
shard_count: 50
failure_injection:
  failed_shards: 3
  failure_type: aboyeur_rejection
  expected_behavior: stitch_blocked
  parent_stuck_handling: alert_only
```
**Customization:** Test different failure ratios (1/50, 10/50, 25/50).

### Phase 5: Brigade Compression (Article VII)
```yaml
enabled: true
critical_stations: [forager, analyst, sentinel, plongeur]
compression_scenarios:
  - manual_compression:
      trigger: manual
      verify_critical_only: true
  - auto_compression_pro:
      trigger: pro_below_70
      verify_forager_overload: true
  - auto_compression_s:
      trigger: s_below_05
      verify_safe_halt: true
expansion_verification: true
```
**Customization:** Define project-specific critical station list.

### Phase 6: Writer Contention (Article VIII)
```yaml
enabled: true
writer_count: 5
iterations_per_writer: 100
expected_max_locked: 0  # WAL should serialize without errors
verify_db_integrity: true
check_corruption: true
```
**Customization:** Increase writer count for stress tiers.

### Phase 7: Clock Drift (Article IX)
```yaml
enabled: true
time_travel_scenarios:
  - future_assigned_at:
      offset_hours: 1
      expect_orphaned: false  # Should not flag as orphaned
  - past_assigned_at:
      offset_hours: -1
      expect_orphaned: true
  - future_zoran_metric:
      expect_accepted: false  # Should not use future timestamps
```
**Customization:** Test NTP correction scenarios (sudden forward/backward jumps).

### Phase 8: Safe-Halt Veto Race (Article X)
```yaml
enabled: true
streak_threshold: 2
s_threshold: 0.5
pro_threshold: 0.70
veto_window_seconds: 60
test_scenarios:
  - streak_trigger:
      s_values: [0.3, 0.3]
      expect_safe_halt: true
      expect_compression: true
  - veto_race:
      new_seeds_during_veto: 5
      expect_rejection: true
  - recovery:
      s_values: [0.3, 0.3, 0.9]
      expect_veto_cancelled: true
```
**Customization:** Test different veto window durations (30s, 60s, 120s).

### Phase 9: Schema Drift (Article XI)
```yaml
enabled: true
migration_tests:
  - add_column_mid_run:
      column: test_column
      type: TEXT
      default: test
      expect_success: true
  - dev_bypass_aboyeur:
      method: mark_status
      expect_no_signature: true
      severity: HIGH
  - hash_corruption:
      field: payload_hash
      expect_aboyeur_rejection: true
```
**Customization:** Test migration framework if project has one.

### Phase 10: Sustained Soak (Article XII)
```yaml
enabled: true
cycles: 50
seeds_per_cycle: 2
station_kill_probability: 0.1
health_check_interval: 10
max_failure_rate: 0.20
station_kill_types:
  - random
  - targeted_non_critical
  - targeted_critical  # if fallback exists
```
**Customization:** Run extended soak (500 cycles) for release candidates.

---

## Severity Overrides

Projects can override default severity for specific findings:

```yaml
severity_overrides:
  "Phase 1: Input Poisoning:2MB domain value": MEDIUM  # Default: MEDIUM
  "Phase 2: Byzantine Stations:hash_tamperer": CRITICAL  # Default: HIGH
  "Phase 10: Sustained Soak:failure_rate": CRITICAL  # Default: HIGH
```

---

## Constitution Check Exceptions

Some findings may be expected/acceptable for this project:

```yaml
constitution_exceptions:
  - finding: "Phase 7: Clock Drift: future timestamp accepted"
    article: "IV.2"
    justification: "Project uses external time source; future timestamps indicate sync issue not corruption"
    status: accepted
```

---

## Exit Code Policy

```yaml
exit_codes:
  0: "No CRITICAL findings"
  1: "≥1 CRITICAL finding"
  2: "Gauntlet internal error"
  3: "Constitution violation (--constitution-check)"
```

---

## Report Retention

```yaml
retention:
  days: 30
  until_release: true
  artifact_path: "gauntlet_report_*.json"
```

---

## Project Metadata

```yaml
project:
  name: "XP-Arc"
  version: "0.2.1"
  type: "protocol_implementation"
  risk_tier: "critical_infrastructure"
  maintainers: ["Jack (DRAGON)"]
  last_reviewed: "2026-08-01"
```

---

## Usage

```bash
# Run full gauntlet with scope config
python3 gauntlet.py --db gauntlet

# Run with constitution validation
python3 gauntlet.py --constitution-check

# Run specific phase only (for debugging)
python3 -c "
from gauntlet import Gauntlet
g = Gauntlet('gauntlet')
g._phase_num = 1
g.phase1_input_poisoning()
"
```

---

## Adding Custom Phases

To add a project-specific phase (requires Constitution amendment):

1. Add phase method to `Gauntlet` class
2. Register in `run_all_phases()` phases list
3. Update `GAUNTLET_CONSTITUTION.md` (Article XIV amendment)
4. Add entry to this scope file
5. Bump Constitution version (MAJOR)

---

*Generated: 2026-08-01*
*Gauntlet Version: 1.0.0*
*Constitution: 1.0.0*