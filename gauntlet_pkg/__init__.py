#!/usr/bin/env python3
"""
XP-Arc Gauntlet — Adversarial Chaos Testing Framework.

This doesn't test happy paths. It breaks the system in ways unit tests never will:
1. Input Poisoning — malformed URLs, 10MB responses, charset bombs, redirect loops
2. Byzantine Stations — valid schema, semantic garbage; confidence lying; lineage spoofing
3. Cascade DoS — Snowball explosion hitting max_entities circuit breaker
4. Fracture Torture — fracture → 50 shards → 3 fail Aboyeur → stitch deadlock
5. Brigade Compression Under Fire — kill Sentinel → PRO<70% → compression → Forager overload
6. Writer Contention — 5 concurrent processes hitting same SQLite DB
7. Clock Drift / Time Travel — future/past timestamps, NTP skew
8. Safe-Halt Veto Race — halt recommended → 60s window → new seeds arrive during veto
9. Schema Drift — add/drop columns mid-run, corrupt payload_hash
10. Sustained Soak — 24h equivalent, 10 seeds/min, random station kills

Each phase produces a structured finding with severity: CRITICAL, HIGH, MEDIUM, LOW, INFO
"""

import os
import sys
import json
import time
import random
import string
import threading
import subprocess
import hashlib
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from pathlib import Path

# Ensure project root on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from xp_arc.core.pool import IntelligencePool, compute_payload_hash, VALID_TRANSITIONS
from xp_arc.core.executive import ExecutiveChef
from xp_arc.core.aboyeur import Aboyeur
from xp_arc.core.fracture import FractureRequest, FractureProtocol
from xp_arc.core.station import StationChef
from xp_arc.stations.forager import TheForager
from xp_arc.stations.analyst import TheAnalyst
from xp_arc.stations.sentinel import TheSentinel
from xp_arc.stations.plongeur import ThePlongeur
from xp_arc.stations.warden import TheWarden
from xp_arc.monitoring.zorans_law import ZoransLaw
from xp_arc.monitoring.spazzmatic import SpaZzMatiC


# ═══════════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class GauntletFinding:
    phase: str
    injection: str
    expected_behavior: str
    actual_behavior: str
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW, INFO
    evidence: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict:
        return {
            'phase': self.phase,
            'injection': self.injection,
            'expected_behavior': self.expected_behavior,
            'actual_behavior': self.actual_behavior,
            'severity': self.severity,
            'evidence': self.evidence,
            'timestamp': self.timestamp,
        }


@dataclass
class GauntletReport:
    run_id: str
    started_at: str
    completed_at: Optional[str] = None
    findings: List[GauntletFinding] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=dict)

    def add_finding(self, finding: GauntletFinding):
        self.findings.append(finding)

    def finalize(self):
        self.completed_at = datetime.now(timezone.utc).isoformat()
        self.summary = defaultdict(int)
        for f in self.findings:
            self.summary[f.severity] += 1
        self.summary = dict(self.summary)

    def to_json(self) -> str:
        return json.dumps({
            'run_id': self.run_id,
            'started_at': self.started_at,
            'completed_at': self.completed_at,
            'summary': self.summary,
            'findings': [f.to_dict() for f in self.findings]
        }, indent=2)


# ═══════════════════════════════════════════════════════════════════════════════
# BYZANTINE STATIONS — Valid schema, malicious behavior
# ═══════════════════════════════════════════════════════════════════════════════

class ByzantineStation(StationChef):
    """Base class for stations that follow schema but violate semantics."""

    def __init__(self, pool, station_id: str, name: str, handles_types: list, behavior: str):
        self.station_id = station_id
        self.name = name
        self.handles_types = handles_types
        self.is_primary = True
        self.sla_seconds = 60
        self._behavior = behavior
        self._tasks_processed = 0
        self._tasks_failed = 0
        self._active = True
        pool.register_station(station_id, name, handles_types, is_primary=True)
        self.writer = pool.station_writer(station_id)


class SemanticGarbageStation(ByzantineStation):
    """Returns valid Aboyeur schema but semantically meaningless output."""
    def __init__(self, pool):
        super().__init__(pool, 'byzantine_garbage', 'Semantic Garbage', ['domain'], 'garbage')

    def process(self, entity_id: int, entity_type: str, entity_value: str) -> dict:
        self._tasks_processed += 1
        # Valid schema, complete nonsense
        return {
            'entity_type': 'domain',
            'entity_value': entity_value,
            'relationships': ['this_is_not_a_domain', 'neither_is_this', 'x' * 500],
            'confidence': 0.95,  # High confidence on garbage
            'notes': 'I am a Byzantine station. This output passes schema but means nothing.',
        }


class ConfidenceLiarStation(ByzantineStation):
    """Reports high confidence on failed/empty work."""
    def __init__(self, pool):
        super().__init__(pool, 'byzantine_liar', 'Confidence Liar', ['domain'], 'lie')

    def process(self, entity_id: int, entity_type: str, entity_value: str) -> dict:
        self._tasks_processed += 1
        return {
            'entity_type': 'domain',
            'entity_value': entity_value,
            'relationships': [],
            'confidence': 1.0,  # Lie
            'notes': 'Confidence 1.0 but I did zero work. Aboyeur should catch this.',
        }


class LineageSpoofStation(ByzantineStation):
    """Attempts to spoof cascade_depth and root_task_id to bypass limits."""
    def __init__(self, pool):
        super().__init__(pool, 'byzantine_lineage', 'Lineage Spoofer', ['url'], 'spoof')

    def process(self, entity_id: int, entity_type: str, entity_value: str) -> dict:
        self._tasks_processed += 1
        # Try to spawn children with forged shallow lineage
        return {
            'entity_type': 'url',
            'entity_value': entity_value,
            'relationships': [],
            'confidence': 0.8,
            'notes': 'Attempting lineage spoof',
            'spawn_targets': [
                {'ent_type': 'url', 'value': f'https://evil{i}.com', 'sla_seconds': 60}
                for i in range(10)
            ],
        }


class PayloadHashTamperer(ByzantineStation):
    """Attempts to write entities with mismatched payload_hash."""
    def __init__(self, pool):
        super().__init__(pool, 'byzantine_tamper', 'Hash Tamperer', ['domain'], 'tamper')

    def process(self, entity_id: int, entity_type: str, entity_value: str) -> dict:
        self._tasks_processed += 1
        # Try to add an edge with tampered source
        self.writer.add_edge('https://tampered-source.com', 'links_to', entity_value)
        return {
            'entity_type': 'domain',
            'entity_value': entity_value,
            'relationships': [],
            'confidence': 0.5,
            'notes': 'Attempted payload hash tampering via edge injection',
        }


# ═══════════════════════════════════════════════════════════════════════════════
# GAUNTLET RUNNER
# ═══════════════════════════════════════════════════════════════════════════════

class Gauntlet:
    def __init__(self, base_db_path: str = 'gauntlet'):
        self.base_db_path = base_db_path
        self.report = GauntletReport(
            run_id=str(uuid.uuid4())[:8],
            started_at=datetime.now(timezone.utc).isoformat()
        )
        self._phase_num = 0

    def _phase_db_path(self) -> str:
        """Return unique DB path for current phase."""
        return f"{self.base_db_path}_phase{self._phase_num}.db"

    def _cleanup_db(self, db_path: str = None):
        if db_path is None:
            db_path = self._phase_db_path()
        if os.path.exists(db_path):
            os.remove(db_path)
        if os.path.exists(db_path + '-wal'):
            os.remove(db_path + '-wal')
        if os.path.exists(db_path + '-shm'):
            os.remove(db_path + '-shm')

    def _fresh_pool(self) -> IntelligencePool:
        self._cleanup_db()
        return IntelligencePool(self._phase_db_path())

    def _fresh_executive(self, pool: IntelligencePool, max_entities: int = 500) -> ExecutiveChef:
        return ExecutiveChef(pool, max_entities=max_entities, verbose=False)

    def _fresh_brigade(self, pool: IntelligencePool) -> ExecutiveChef:
        """Create a full standard brigade."""
        exec_chef = self._fresh_executive(pool)
        exec_chef.register_station(TheForager(pool, max_domains_per_target=3, timeout=3))
        exec_chef.register_station(TheAnalyst(pool))
        exec_chef.register_station(TheSentinel(pool))
        exec_chef.register_station(ThePlongeur(pool))
        exec_chef.register_station(TheWarden(pool))
        return exec_chef

    def run_all_phases(self):
        """Execute all 10 gauntlet phases."""
        phases = [
            ('Phase 1: Input Poisoning', self.phase1_input_poisoning),
            ('Phase 2: Byzantine Stations', self.phase2_byzantine_stations),
            ('Phase 3: Cascade DoS', self.phase3_cascade_dos),
            ('Phase 4: Fracture Torture', self.phase4_fracture_torture),
            ('Phase 5: Brigade Compression Under Fire', self.phase5_brigade_compression),
            ('Phase 6: Writer Contention', self.phase6_writer_contention),
            ('Phase 7: Clock Drift / Time Travel', self.phase7_clock_drift),
            ('Phase 8: Safe-Halt Veto Race', self.phase8_safe_halt_veto),
            ('Phase 9: Schema Drift', self.phase9_schema_drift),
            ('Phase 10: Sustained Soak', self.phase10_sustained_soak),
        ]

        for phase_name, phase_fn in phases:
            self._phase_num += 1
            print(f"\n{'='*70}")
            print(f"  {phase_name}")
            print(f"{'='*70}")
            try:
                phase_fn()
            except Exception as e:
                self.report.add_finding(GauntletFinding(
                    phase=phase_name,
                    injection=f"Phase crashed: {type(e).__name__}",
                    expected_behavior="Phase should complete and report findings",
                    actual_behavior=f"Uncaught exception: {e}",
                    severity="CRITICAL",
                    evidence={'exception': str(e), 'traceback': str(e.__traceback__)}
                ))
                print(f"  [CRITICAL] Phase crashed: {e}")

        self.report.finalize()
        self._print_summary()
        return self.report

    def _print_summary(self):
        print(f"\n{'='*70}")
        print(f"  GAUNTLET COMPLETE — Run ID: {self.report.run_id}")
        print(f"{'='*70}")
        for sev in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO']:
            count = self.report.summary.get(sev, 0)
            if count > 0:
                print(f"  {sev}: {count}")
        print(f"  Total Findings: {len(self.report.findings)}")

    # ═══════════════════════════════════════════════════════════════════════════
    # PHASE 1: INPUT POISONING
    # ═══════════════════════════════════════════════════════════════════════════

    def phase1_input_poisoning(self):
        """Malformed URLs, control chars, 10MB responses, charset bombs, redirect loops."""
        pool = self._fresh_pool()
        forager = TheForager(pool, max_domains_per_target=1, timeout=2)

        poison_inputs = [
            # Control characters
            ('https://example.com\x00', 'null_byte'),
            ('https://example.com\n', 'newline'),
            ('https://example.com\r', 'carriage_return'),
            ('https://example.com\x1f', 'unit_separator'),
            # Length bombs
            ('https://' + 'a' * 3000 + '.com', 'url_length_bomb'),
            # Scheme violations
            ('ftp://example.com', 'ftp_scheme'),
            ('javascript:alert(1)', 'javascript_scheme'),
            ('data:text/html,<script>alert(1)</script>', 'data_scheme'),
            ('file:///etc/passwd', 'file_scheme'),
            # Encoding attacks
            ('https://example.com/%00', 'encoded_null'),
            ('https://example.com/%0d%0aSet-Cookie:foo=bar', 'encoded_crlf_injection'),
            ('https://example.com/%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd', 'encoded_path_traversal'),
            # IDN homograph
            ('https://еxample.com', 'cyrillic_homograph'),  # е is Cyrillic
            # IPv6 and edge cases
            ('https://[::1]', 'ipv6_loopback'),
            ('https://127.0.0.1:80', 'ipv4_with_port'),
            ('https://example.com:99999', 'port_overflow'),
            # Empty and whitespace
            ('', 'empty_string'),
            ('   ', 'whitespace_only'),
            ('https://', 'scheme_only'),
        ]

        for poison_value, poison_type in poison_inputs:
            eid = pool.add_entity('url', poison_value)
            if eid:
                entity = pool.get_entity(eid)
                # Forager should reject at sanitization
                output = forager.process(eid, 'url', poison_value)

                # Check: confidence should be low (0.0-0.3) for rejected inputs
                if output['confidence'] > 0.3:
                    self.report.add_finding(GauntletFinding(
                        phase='Phase 1: Input Poisoning',
                        injection=f'{poison_type}: {poison_value[:50]}',
                        expected_behavior='Forager sanitization rejects with confidence <= 0.3',
                        actual_behavior=f'Forager returned confidence {output["confidence"]}',
                        severity='HIGH',
                        evidence={'input': poison_value, 'type': poison_type, 'output': output}
                    ))
                else:
                    self.report.add_finding(GauntletFinding(
                        phase='Phase 1: Input Poisoning',
                        injection=f'{poison_type}: {poison_value[:50]}',
                        expected_behavior='Forager sanitization rejects with confidence <= 0.3',
                        actual_behavior=f'Correctly rejected (confidence={output["confidence"]})',
                        severity='INFO',
                        evidence={'input': poison_value, 'type': poison_type}
                    ))
            else:
                self.report.add_finding(GauntletFinding(
                    phase='Phase 1: Input Poisoning',
                    injection=f'{poison_type}: {poison_value[:50]}',
                    expected_behavior='Pool rejects at ingestion (UNIQUE constraint or validation)',
                    actual_behavior='Pool rejected at add_entity (returned None)',
                    severity='INFO',
                    evidence={'input': poison_value, 'type': poison_type}
                ))

        # Test: Large response handling (simulated via direct pool injection of huge HTML)
        # We can't easily test 10MB HTTP response without a test server, but we can test
        # that the pool handles large entity values
        huge_value = 'x' * 2_000_000  # 2MB
        eid = pool.add_entity('domain', huge_value)
        if eid:
            entity = pool.get_entity(eid)
            if len(entity['value']) == 2_000_000:
                self.report.add_finding(GauntletFinding(
                    phase='Phase 1: Input Poisoning',
                    injection='2MB domain value',
                    expected_behavior='Pool should have length limit or truncate',
                    actual_behavior='Pool accepted 2MB entity value',
                    severity='MEDIUM',
                    evidence={'entity_id': eid, 'value_length': len(entity['value'])}
                ))

        pool.close()

    # ═══════════════════════════════════════════════════════════════════════════
    # PHASE 2: BYZANTINE STATIONS
    # ═══════════════════════════════════════════════════════════════════════════

    def phase2_byzantine_stations(self):
        """Valid schema, semantic garbage; confidence lying; lineage spoofing; hash tampering."""
        pool = self._fresh_pool()
        executive = self._fresh_executive(pool)

        # Register Byzantine stations FIRST so they get priority for their types
        byzantine_garbage = SemanticGarbageStation(pool)
        byzantine_liar = ConfidenceLiarStation(pool)
        byzantine_lineage = LineageSpoofStation(pool)
        byzantine_tamper = PayloadHashTamperer(pool)

        executive.register_station(byzantine_garbage)
        executive.register_station(byzantine_liar)
        executive.register_station(byzantine_lineage)
        executive.register_station(byzantine_tamper)

        # Now register normal stations - they should be fallbacks for the same types
        forager = TheForager(pool, max_domains_per_target=1, timeout=2)
        analyst = TheAnalyst(pool)
        executive.register_station(forager)
        executive.register_station(analyst)

        # Seed some entities - specifically 'domain' type for garbage/liar stations
        # and 'url' type for lineage spoof
        for i in range(10):
            pool.add_entity('domain', f'test{i}.example.com')
            pool.add_entity('url', f'https://test{i}.example.com')

        # Run executive - Byzantine stations will process some entities
        executive.run_service()

        # Check: Aboyeur should catch semantic garbage (no relationships, or invalid ones)
        entities = pool.get_all_entities()
        for e in entities:
            if e['status'] == 'completed' and e['station'] == 'byzantine_garbage':
                # Aboyeur should have REJECTED this - relationships are not valid domains
                self.report.add_finding(GauntletFinding(
                    phase='Phase 2: Byzantine Stations',
                    injection='SemanticGarbageStation processed entity',
                    expected_behavior='Aboyeur rejects output with invalid relationships',
                    actual_behavior=f'Entity {e["id"]} marked completed by Aboyeur',
                    severity='HIGH',
                    evidence={'entity_id': e['id'], 'station': e['station'], 'notes': e['notes']}
                ))

        # Check: Confidence liar - high confidence on empty work
        for e in entities:
            if e['station'] == 'byzantine_liar' and e['confidence'] == 1.0:
                self.report.add_finding(GauntletFinding(
                    phase='Phase 2: Byzantine Stations',
                    injection='ConfidenceLiarStation reported 1.0 confidence',
                    expected_behavior='Aboyeur validates confidence against actual output quality',
                    actual_behavior='Entity completed with confidence 1.0 but empty relationships',
                    severity='MEDIUM',
                    evidence={'entity_id': e['id'], 'confidence': e['confidence']}
                ))

        # Check: Lineage spoof - station tries to spawn children with forged shallow lineage
        # The lineage spoof station processes 'url' type and tries to spawn children
        # Seed URLs are at depth 0, so children go to depth 1 (well within max 5)
        # This tests that Aboyeur still validates the spawn output schema
        lineage_spawn_blocked = 0
        events = pool.get_events(200)
        for ev in events:
            if 'spawn_blocked_depth_limit' in ev['event_type']:
                lineage_spawn_blocked += 1

        # Check if byzantine_lineage actually processed any entities
        lineage_processed = any(e['station'] == 'byzantine_lineage' for e in entities if e['status'] in ('completed', 'failed'))
        
        if not lineage_processed:
            self.report.add_finding(GauntletFinding(
                phase='Phase 2: Byzantine Stations',
                injection='LineageSpoofStation registered but no entities routed to it',
                expected_behavior='Station should process url entities and attempt lineage spoof',
                actual_behavior='No url entities were routed to byzantine_lineage station (Forager took priority)',
                severity='INFO',
                evidence={'byzantine_station_registered': True, 'entities_processed': 0}
            ))
        elif lineage_spawn_blocked > 0:
            # Should NOT block at depth 1 - this would be a bug
            self.report.add_finding(GauntletFinding(
                phase='Phase 2: Byzantine Stations',
                injection='LineageSpoofStation attempted to spawn 10 children from depth 0',
                expected_behavior='Children at depth 1 should be ALLOWED (max depth is 5)',
                actual_behavior=f'{lineage_spawn_blocked} spawn attempts incorrectly blocked',
                severity='HIGH',
                evidence={'spawn_attempts': 10, 'blocked_events': lineage_spawn_blocked, 'parent_depth': 0, 'child_depth': 1, 'max_depth': 5}
            ))
        else:
            # Correct: spawns allowed at depth 1, Aboyeur validates schema
            self.report.add_finding(GauntletFinding(
                phase='Phase 2: Byzantine Stations',
                injection='LineageSpoofStation attempted to spawn 10 children from depth 0',
                expected_behavior='Children at depth 1 allowed (max depth 5); Aboyeur validates output',
                actual_behavior='All 10 spawn attempts allowed; Aboyeur validated output schema',
                severity='INFO',
                evidence={'spawn_attempts': 10, 'blocked_events': 0, 'parent_depth': 0, 'max_depth': 5}
            ))

        # Check: Hash tampering via edge injection
        tampered_edges = pool.conn.execute(
            "SELECT * FROM edges WHERE source = 'https://tampered-source.com'"
        ).fetchall()
        if tampered_edges:
            self.report.add_finding(GauntletFinding(
                phase='Phase 2: Byzantine Stations',
                injection='PayloadHashTamperer added edge with tampered source',
                expected_behavior='HMAC verification rejects writes from station with valid key but tampered payload',
                actual_behavior=f'{len(tampered_edges)} tampered edges written to pool',
                severity='HIGH',
                evidence={'tampered_edges': len(tampered_edges)}
            ))

        pool.close()

    # ═══════════════════════════════════════════════════════════════════════════
    # PHASE 3: CASCADE DoS
    # ═══════════════════════════════════════════════════════════════════════════

    def phase3_cascade_dos(self):
        """Snowball explosion hitting max_entities circuit breaker."""
        pool = self._fresh_pool()
        executive = self._fresh_executive(pool, max_entities=100)
        forager = TheForager(pool, max_domains_per_target=10, timeout=2)
        analyst = TheAnalyst(pool)
        executive.register_station(forager)
        executive.register_station(analyst)

        # Seed ONE URL that will spawn many domains
        pool.add_entity('url', 'https://cascade-test.example.com')

        # Manually inject a Forager output with MANY spawn targets
        eid = pool.add_entity('url', 'https://cascade-test.example.com')
        pool.transition_status(eid, 'processing', station='forager')
        pool.transition_status(eid, 'pending_qa', station='forager')

        # Create massive spawn directive
        massive_spawn = [
            {'ent_type': 'domain', 'value': f'spawn{i}.cascade.com', 'sla_seconds': 60}
            for i in range(200)  # Way over max_entities=100
        ]

        # Simulate Aboyeur approval with massive spawn
        pool.set_aboyeur_signature(eid, 'ABOY-TEST-CASCADE')
        pool.transition_status(eid, 'completed', station='forager', confidence=0.9, notes='Massive spawn test')

        # Now run executive - it should process spawns but hit max_entities
        executive.run_service()

        # Check: Did cascade hit max_entities limit?
        total_entities = pool.count_entities()
        spawn_blocked_events = [e for e in pool.get_events(200)
                                if e['event_type'] == 'spawn_blocked_depth_limit']

        if total_entities >= 100:
            self.report.add_finding(GauntletFinding(
                phase='Phase 3: Cascade DoS',
                injection='Single entity with 200 spawn targets, max_entities=100',
                expected_behavior='Executive stops at max_entities, blocks excess spawns',
                actual_behavior=f'Pool has {total_entities} entities (limit: 100)',
                severity='HIGH' if total_entities > 100 else 'INFO',
                evidence={'total_entities': total_entities, 'max_entities': 100,
                          'spawn_blocked_events': len(spawn_blocked_events)}
            ))

        # Check: Are entities stuck in 'raw' because max_entities hit?
        raw_count = len(pool.get_entities_by_status('raw'))
        if raw_count > 0:
            self.report.add_finding(GauntletFinding(
                phase='Phase 3: Cascade DoS',
                injection='Cascade hit max_entities',
                expected_behavior='Raw entities remain unprocessed but visible for audit',
                actual_behavior=f'{raw_count} entities stuck in raw status',
                severity='MEDIUM',
                evidence={'raw_entities': raw_count}
            ))

        pool.close()

    # ═══════════════════════════════════════════════════════════════════════════
    # PHASE 4: FRACTURE TORTURE
    # ═══════════════════════════════════════════════════════════════════════════

    def phase4_fracture_torture(self):
        """Fracture → 50 shards → 3 fail Aboyeur → stitch deadlock."""
        pool = self._fresh_pool()
        executive = self._fresh_executive(pool)
        forager = TheForager(pool, max_domains_per_target=1, timeout=2)
        executive.register_station(forager)

        # Create parent entity
        parent_id = pool.add_entity('url', 'https://fracture-test.example.com')
        if parent_id is None:
            self.report.add_finding(GauntletFinding(
                phase='Phase 4: Fracture Torture',
                injection='Parent entity creation failed',
                expected_behavior='Parent entity created successfully',
                actual_behavior='add_entity returned None',
                severity='CRITICAL',
                evidence={}
            ))
            pool.close()
            return
            
        pool.transition_status(parent_id, 'processing', station='forager')

        # Simulate fracture request from Forager
        fracture = FractureProtocol(pool)
        shard_ids = fracture.create_shards(
            parent_id, 'url', 'https://fracture-test.example.com',
            shard_count=50, shard_type='shard'
        )

        if len(shard_ids) != 50:
            self.report.add_finding(GauntletFinding(
                phase='Phase 4: Fracture Torture',
                injection='Requested 50 shards',
                expected_behavior='All 50 shards created',
                actual_behavior=f'Only {len(shard_ids)} shards created',
                severity='HIGH',
                evidence={'requested': 50, 'created': len(shard_ids)}
            ))

        # Process shards: 47 succeed, 3 fail Aboyeur
        aboyeur = Aboyeur(pool)
        completed_shards = 0
        failed_shards = 0

        for i, shard_id in enumerate(shard_ids):
            pool.transition_status(shard_id, 'processing', station='forager')
            output = {'entity_type': 'shard', 'entity_value': f'shard-{i}',
                      'relationships': [], 'confidence': 0.8, 'notes': f'Shard {i} done'}
            pool.transition_status(shard_id, 'pending_qa', station='forager')

            if i < 47:
                # 47 succeed
                result = aboyeur.validate_and_sign(shard_id, 'forager', output)
                if result['approved']:
                    pool.transition_status(shard_id, 'completed', station='forager', confidence=0.8)
                    completed_shards += 1
            else:
                # 3 fail - Aboyeur rejects
                output['confidence'] = 0.3  # Low confidence triggers rejection
                result = aboyeur.validate_and_sign(shard_id, 'forager', output)
                pool.transition_status(shard_id, 'failed', station='forager',
                                       notes=result.get('rejection_reason', 'Rejected'))
                failed_shards += 1

        # Now attempt stitch - should FAIL because not all shards completed
        fracture_groups = fracture.get_fracture_groups()
        if fracture_groups:
            stitched_id = fracture.stitch_shards(fracture_groups[0]['fracture_id'])
        else:
            stitched_id = None

        if stitched_id is not None:
            self.report.add_finding(GauntletFinding(
                phase='Phase 4: Fracture Torture',
                injection='50 shards, 3 failed Aboyeur, attempted stitch',
                expected_behavior='Stitch fails (returns None) because partial completion prohibited',
                actual_behavior=f'Stitch SUCCEEDED with entity {stitched_id} - CONSTITUTION VIOLATION',
                severity='CRITICAL',
                evidence={'completed_shards': completed_shards, 'failed_shards': failed_shards,
                          'stitched_id': stitched_id}
            ))
        else:
            self.report.add_finding(GauntletFinding(
                phase='Phase 4: Fracture Torture',
                injection='50 shards, 3 failed Aboyeur, attempted stitch',
                expected_behavior='Stitch fails - partial completion prohibited',
                actual_behavior='Stitch correctly returned None',
                severity='INFO',
                evidence={'completed_shards': completed_shards, 'failed_shards': failed_shards}
            ))

        # Check: Parent entity stuck in 'fractured' or 'stitchable'?
        parent = pool.get_entity(parent_id)
        if parent['status'] in ('fractured', 'stitchable'):
            self.report.add_finding(GauntletFinding(
                phase='Phase 4: Fracture Torture',
                injection='Partial fracture completion',
                expected_behavior='Parent entity should be marked failed or have clear resolution path',
                actual_behavior=f'Parent entity stuck in {parent["status"]} with no automatic recovery',
                severity='HIGH',
                evidence={'parent_id': parent_id, 'parent_status': parent['status']}
            ))

        pool.close()

    # ═══════════════════════════════════════════════════════════════════════════
    # PHASE 5: BRIGADE COMPRESSION UNDER FIRE
    # ═══════════════════════════════════════════════════════════════════════════

    def phase5_brigade_compression(self):
        """Kill Sentinel → PRO<70% → compression → Forager overload."""
        pool = self._fresh_pool()
        executive = self._fresh_executive(pool, max_entities=200)

        # Register full brigade
        forager = TheForager(pool, max_domains_per_target=5, timeout=2)
        analyst = TheAnalyst(pool)
        sentinel = TheSentinel(pool)
        plongeur = ThePlongeur(pool)
        warden = TheWarden(pool)

        for station in [forager, analyst, sentinel, plongeur, warden]:
            executive.register_station(station)

        # Verify critical flags - only Forager, Analyst, Sentinel, Plongeur should be critical
        critical_count = sum(1 for s in executive.stations if getattr(s, 'critical', False))
        total_count = len(executive.stations)

        # Manually compress
        executive.compress_brigade()

        compressed_count = len(executive.stations)
        if compressed_count != critical_count:
            self.report.add_finding(GauntletFinding(
                phase='Phase 5: Brigade Compression Under Fire',
                injection='Manual brigade compression',
                expected_behavior=f'Only {critical_count} critical stations remain',
                actual_behavior=f'{compressed_count} stations remain after compression',
                severity='HIGH',
                evidence={'critical_count': critical_count, 'compressed_count': compressed_count,
                          'stations': [s.station_id for s in executive.stations]}
            ))

        # Now seed 100 URLs - only Forager can process (it's critical)
        for i in range(100):
            pool.add_entity('url', f'https://compression-test-{i}.example.com')

        # Run executive - only Forager processes
        executive.run_service()

        # Check: Are domains piling up unprocessed because Analyst is compressed?
        domain_entities = pool.get_entities_by_status('raw')
        domain_count = len([e for e in domain_entities if e['type'] == 'domain'])

        if domain_count > 50:
            self.report.add_finding(GauntletFinding(
                phase='Phase 5: Brigade Compression Under Fire',
                injection='100 seed URLs, only Forager active (Analyst compressed)',
                expected_behavior='Domains accumulate in raw, visible as unhandled backlog',
                actual_behavior=f'{domain_count} domain entities stuck in raw - backlog visible',
                severity='MEDIUM',
                evidence={'raw_domains': domain_count, 'total_raw': len(domain_entities)}
            ))

        # Expand brigade
        executive.expand_brigade()
        if len(executive.stations) != total_count:
            self.report.add_finding(GauntletFinding(
                phase='Phase 5: Brigade Compression Under Fire',
                injection='Brigade expansion after compression',
                expected_behavior=f'All {total_count} stations restored',
                actual_behavior=f'Only {len(executive.stations)} stations restored',
                severity='HIGH',
                evidence={'expected': total_count, 'actual': len(executive.stations)}
            ))

        pool.close()

    # ═══════════════════════════════════════════════════════════════════════════
    # PHASE 6: WRITER CONTENTION
    # ═══════════════════════════════════════════════════════════════════════════

    def phase6_writer_contention(self):
        """5 concurrent processes hitting same SQLite DB."""
        results = {'success': 0, 'locked': 0, 'errors': 0, 'corruption': 0}
        lock = threading.Lock()

        def writer_process(process_id: int, iterations: int = 100):
            try:
                pool = IntelligencePool(self._phase_db_path())
                for i in range(iterations):
                    eid = pool.add_entity('domain', f'proc{process_id}-entity{i}.test.com')
                    if eid:
                        pool.transition_status(eid, 'processing', station=f'proc{process_id}')
                        pool.transition_status(eid, 'completed', station=f'proc{process_id}', confidence=0.5)
                        with lock:
                            results['success'] += 1
                    else:
                        with lock:
                            results['locked'] += 1
                pool.close()
            except sqlite3.OperationalError as e:
                if 'locked' in str(e).lower():
                    with lock:
                        results['locked'] += 1
                else:
                    with lock:
                        results['errors'] += 1
            except Exception as e:
                with lock:
                    results['errors'] += 1

        # Start 5 concurrent writers
        threads = []
        for p in range(5):
            t = threading.Thread(target=writer_process, args=(p, 50))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=30)

        # Verify database integrity
        pool = IntelligencePool(self._phase_db_path())
        entities = pool.get_all_entities()

        # Check for duplicate IDs (should not happen with AUTOINCREMENT)
        ids = [e['id'] for e in entities]
        if len(ids) != len(set(ids)):
            results['corruption'] += 1

        # Check for orphaned processing entities
        stuck = pool.get_entities_by_status('processing')
        if len(stuck) > 0:
            self.report.add_finding(GauntletFinding(
                phase='Phase 6: Writer Contention',
                injection='5 concurrent processes writing to same SQLite DB',
                expected_behavior='SQLite WAL handles concurrent writers; no stuck entities',
                actual_behavior=f'{len(stuck)} entities stuck in processing',
                severity='MEDIUM',
                evidence={'stuck_count': len(stuck), 'results': results}
            ))

        total_writes = results['success']
        if results['locked'] > total_writes * 0.1:  # >10% lock contention
            self.report.add_finding(GauntletFinding(
                phase='Phase 6: Writer Contention',
                injection='5 concurrent writers, 50 writes each',
                expected_behavior='SQLite WAL serializes writers with minimal contention',
                actual_behavior=f'High lock contention: {results["locked"]} lock errors vs {results["success"]} successes',
                severity='HIGH',
                evidence=results
            ))
        else:
            self.report.add_finding(GauntletFinding(
                phase='Phase 6: Writer Contention',
                injection='5 concurrent writers, 50 writes each',
                expected_behavior='SQLite WAL handles contention gracefully',
                actual_behavior=f'Low contention: {results["locked"]} locks, {results["success"]} successes',
                severity='INFO',
                evidence=results
            ))

        pool.close()

    # ═══════════════════════════════════════════════════════════════════════════
    # PHASE 7: CLOCK DRIFT / TIME TRAVEL
    # ═══════════════════════════════════════════════════════════════════════════

    def phase7_clock_drift(self):
        """Future/past timestamps, NTP skew simulation."""
        pool = self._fresh_pool()

        # Inject entity with future assigned_at (simulate clock skew)
        eid = pool.add_entity('url', 'https://future-test.example.com')
        future_time = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        past_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

        # Direct DB manipulation to simulate clock drift
        with pool.conn:
            pool.conn.execute(
                "UPDATE entities SET assigned_at = ? WHERE id = ?",
                (future_time, eid)
            )

        # Now check SLA calculation
        orphans = pool.get_orphaned_entities(threshold_seconds=60)
        future_orphans = [o for o in orphans if o['id'] == eid]

        if future_orphans:
            self.report.add_finding(GauntletFinding(
                phase='Phase 7: Clock Drift / Time Travel',
                injection='Entity with assigned_at 1 hour in future',
                expected_behavior='SLA calculation uses database time (not entity time) or handles future timestamps',
                actual_behavior='Entity incorrectly flagged as orphaned (future assigned_at makes it look stale)',
                severity='HIGH',
                evidence={'entity_id': eid, 'assigned_at': future_time, 'orphaned': True}
            ))

        # Inject entity with past assigned_at (simulate NTP correction backward)
        eid2 = pool.add_entity('url', 'https://past-test.example.com')
        with pool.conn:
            pool.conn.execute(
                "UPDATE entities SET assigned_at = ? WHERE id = ?",
                (past_time, eid2)
            )

        orphans2 = pool.get_orphaned_entities(threshold_seconds=60)
        past_orphans = [o for o in orphans2 if o['id'] == eid2]

        if past_orphans:
            self.report.add_finding(GauntletFinding(
                phase='Phase 7: Clock Drift / Time Travel',
                injection='Entity with assigned_at 1 hour in past',
                expected_behavior='Entity correctly flagged as orphaned (actually stale)',
                actual_behavior='Entity flagged as orphaned - correct but may trigger premature GC',
                severity='MEDIUM',
                evidence={'entity_id': eid2, 'assigned_at': past_time, 'orphaned': True}
            ))

        # Test: Zoran's Law with time travel
        zorans = ZoransLaw(pool)
        # Manually insert metrics with skewed timestamps
        with pool.conn:
            pool.conn.execute("""
                INSERT INTO zorans_metrics
                (stability_quotient, primary_role_occupancy, system_state,
                 active_stations, primary_stations, tasks_completed, tasks_ingested, measured_at)
                VALUES (0.8, 0.8, 'degraded', 5, 4, 100, 120, ?)
            """, (future_time,))

        latest = zorans.get_latest()
        if latest and latest['measured_at'] == future_time:
            self.report.add_finding(GauntletFinding(
                phase='Phase 7: Clock Drift / Time Travel',
                injection='Zoran metrics with future timestamp',
                expected_behavior='Zoran\'s Law uses database time for windowing, ignores future timestamps',
                actual_behavior='Future timestamp accepted as latest measurement',
                severity='MEDIUM',
                evidence={'latest_metric': latest}
            ))

        pool.close()

    # ═══════════════════════════════════════════════════════════════════════════
    # PHASE 8: SAFE-HALT VETO RACE
    # ═══════════════════════════════════════════════════════════════════════════

    def phase8_safe_halt_veto(self):
        """Halt recommended → 60s window → new seeds arrive during veto."""
        pool = self._fresh_pool()
        executive = self._fresh_executive(pool)
        forager = TheForager(pool, max_domains_per_target=1, timeout=2)
        executive.register_station(forager)

        zorans = ZoransLaw(pool)
        spazz = SpaZzMatiC(pool, zorans)
        spazz.set_executive(executive)

        # Force S < 0.5 for 2 measurements to trigger safe halt
        # Manually insert bad metrics - DO NOT call zorans.measure() after
        # The streak logic reads from DB history directly
        for i in range(2):
            with pool.conn:
                pool.conn.execute("""
                    INSERT INTO zorans_metrics
                    (stability_quotient, primary_role_occupancy, system_state,
                     active_stations, primary_stations, tasks_completed, tasks_ingested, measured_at)
                    VALUES (0.3, 0.5, 'critical', 4, 2, 10, 50, ?)
                """, (datetime.now(timezone.utc).isoformat(),))

        # Run review - should recommend safe halt based on DB history (2 consecutive S < 0.5)
        # DO NOT call zorans.measure() - it would add a fresh good measurement and break the streak
        review = spazz.run_review()

        if not review['safe_halt_recommended']:
            self.report.add_finding(GauntletFinding(
                phase='Phase 8: Safe-Halt Veto Race',
                injection='Two consecutive S=0.3 measurements',
                expected_behavior='SpaZzMatiC recommends safe halt, starts 60s veto window',
                actual_behavior='Safe halt NOT recommended',
                severity='CRITICAL',
                evidence={'review': review}
            ))

        # Now simulate new seeds arriving DURING veto window
        # (In real daemon, veto window is 60s; here we simulate by checking API behavior)
        # The persistent daemon rejects seeds with 404 during safe halt
        # We can't easily test the HTTP API here, but we can verify the veto logic

        # Check: Brigade should be compressed
        if not executive.is_compressed():
            self.report.add_finding(GauntletFinding(
                phase='Phase 8: Safe-Halt Veto Race',
                injection='Safe halt recommended',
                expected_behavior='Brigade automatically compressed to critical stations',
                actual_behavior='Brigade NOT compressed',
                severity='HIGH',
                evidence={'brigade_compressed': executive.is_compressed()}
            ))

        # Check: S recovery clears safe halt
        with pool.conn:
            pool.conn.execute("""
                INSERT INTO zorans_metrics
                (stability_quotient, primary_role_occupancy, system_state,
                 active_stations, primary_stations, tasks_completed, tasks_ingested, measured_at)
                VALUES (0.9, 0.9, 'healthy', 10, 9, 100, 100, ?)
            """, (datetime.now(timezone.utc).isoformat(),))

        review2 = spazz.run_review()
        if review2['safe_halt_recommended']:
            self.report.add_finding(GauntletFinding(
                phase='Phase 8: Safe-Halt Veto Race',
                injection='S recovered to 0.9 after safe halt recommended',
                expected_behavior='Safe halt recommendation cleared, veto window cancelled',
                actual_behavior='Safe halt still recommended after S recovery',
                severity='HIGH',
                evidence={'review': review2}
            ))

        pool.close()

    # ═══════════════════════════════════════════════════════════════════════════
    # PHASE 9: SCHEMA DRIFT
    # ═══════════════════════════════════════════════════════════════════════════

    def phase9_schema_drift(self):
        """Add/drop columns mid-run, corrupt payload_hash."""
        pool = self._fresh_pool()

        # Add entity normally
        eid = pool.add_entity('domain', 'schema-test.example.com')

        # Corrupt payload_hash directly in DB
        with pool.conn:
            pool.conn.execute(
                "UPDATE entities SET payload_hash = 'corrupted_hash' WHERE id = ?",
                (eid,)
            )

        # Now try to transition - Aboyeur should detect hash mismatch
        if eid is not None:
            pool.transition_status(eid, 'processing', station='forager')
            output = {'entity_type': 'domain', 'entity_value': 'schema-test.example.com',
                      'relationships': [], 'confidence': 0.8, 'notes': 'test'}
            pool.transition_status(eid, 'pending_qa', station='forager')

            aboyeur = Aboyeur(pool)
            result = aboyeur.validate_and_sign(eid, 'forager', output)
        else:
            result = {'approved': False, 'rejection_reason': 'add_entity returned None'}

        # Aboyeur validates payload_hash in validate_and_sign
        if result['approved']:
            self.report.add_finding(GauntletFinding(
                phase='Phase 9: Schema Drift',
                injection='payload_hash corrupted in DB, then Aboyeur validation',
                expected_behavior='Aboyeur rejects: payload hash mismatch detected',
                actual_behavior='Aboyeur APPROVED entity with corrupted payload_hash',
                severity='CRITICAL',
                evidence={'entity_id': eid, 'result': result}
            ))

        # Test: Add column mid-run (simulate migration)
        try:
            with pool.conn:
                pool.conn.execute("ALTER TABLE entities ADD COLUMN test_column TEXT DEFAULT 'test'")
            # Should not break existing operations
            eid2 = pool.add_entity('domain', 'migration-test.example.com')
            if eid2:
                self.report.add_finding(GauntletFinding(
                    phase='Phase 9: Schema Drift',
                    injection='ALTER TABLE ADD COLUMN mid-run',
                    expected_behavior='Pool continues working with new column',
                    actual_behavior='Pool accepted new entity after schema change',
                    severity='INFO',
                    evidence={'new_entity_id': eid2}
                ))
        except Exception as e:
            self.report.add_finding(GauntletFinding(
                phase='Phase 9: Schema Drift',
                injection='ALTER TABLE ADD COLUMN mid-run',
                expected_behavior='Pool handles schema migration gracefully',
                actual_behavior=f'Exception during schema change: {e}',
                severity='HIGH',
                evidence={'error': str(e)}
            ))

        # Test: Drop column (SQLite doesn't support DROP COLUMN directly)
        # Test: mark_status bypass (dev bypass in pool.py)
        if eid is not None:
            pool.mark_status(eid, 'completed')  # This bypasses Aboyeur!
            entity = pool.get_entity(eid)
            if entity['status'] == 'completed' and not entity['aboyeur_signature']:
                self.report.add_finding(GauntletFinding(
                    phase='Phase 9: Schema Drift',
                    injection='mark_status() dev bypass used to complete entity',
                    expected_behavior='mark_status() is dev-only bypass, should not be used in production',
                    actual_behavior='Entity completed WITHOUT Aboyeur signature via dev bypass',
                    severity='HIGH',
                    evidence={'entity_id': eid, 'status': entity['status'], 'has_signature': bool(entity['aboyeur_signature'])}
                ))

        pool.close()

    # ═══════════════════════════════════════════════════════════════════════════
    # PHASE 10: SUSTAINED SOAK
    # ═══════════════════════════════════════════════════════════════════════════

    def phase10_sustained_soak(self):
        """Accelerated soak: 10 seeds/min equivalent, random station kills."""
        pool = self._fresh_pool()
        executive = self._fresh_executive(pool, max_entities=500)

        # Register brigade
        forager = TheForager(pool, max_domains_per_target=3, timeout=2)
        analyst = TheAnalyst(pool)
        sentinel = TheSentinel(pool)
        plongeur = ThePlongeur(pool)
        warden = TheWarden(pool)

        for s in [forager, analyst, sentinel, plongeur, warden]:
            executive.register_station(s)

        start_time = time.time()
        cycles = 0
        max_cycles = 50  # Accelerated: 50 cycles ~ 10 min equivalent
        station_kills = 0

        while cycles < max_cycles:
            cycles += 1

            # Seed 2 new URLs per cycle (accelerated rate)
            for i in range(2):
                pool.add_entity('url', f'https://soak-{cycles}-{i}.example.com')

            # Randomly kill a station (10% chance per cycle)
            if random.random() < 0.1 and executive.stations:
                victim = random.choice(executive.stations)
                victim._active = False
                station_kills += 1
                pool._log_event('station_killed', 'gauntlet',
                                f'Killed station: {victim.name}')

            # Run one cycle
            executive.run_service()

            # Health checks every 10 cycles
            if cycles % 10 == 0:
                plongeur.run_sweep()
                sentinel.run_health_check()

        elapsed = time.time() - start_time
        total_entities = pool.count_entities()
        raw_entities = len(pool.get_entities_by_status('raw'))
        failed_entities = len(pool.get_entities_by_status('failed'))

        # Check for memory leaks / connection issues (hard to detect in short test)
        # But we can check for excessive failed entities
        failure_rate = failed_entities / max(total_entities, 1)

        if failure_rate > 0.2:
            self.report.add_finding(GauntletFinding(
                phase='Phase 10: Sustained Soak',
                injection=f'{max_cycles} cycles, 2 seeds/cycle, random station kills',
                expected_behavior='System degrades gracefully, failure rate < 20%',
                actual_behavior=f'Failure rate: {failure_rate:.1%} ({failed_entities}/{total_entities})',
                severity='HIGH',
                evidence={'total_entities': total_entities, 'failed': failed_entities,
                          'raw': raw_entities, 'cycles': cycles, 'station_kills': station_kills,
                          'elapsed_sec': elapsed}
            ))
        elif station_kills > 0:
            self.report.add_finding(GauntletFinding(
                phase='Phase 10: Sustained Soak',
                injection=f'{max_cycles} cycles, {station_kills} random station kills',
                expected_behavior='Brigade handles station loss via fallback/compression',
                actual_behavior=f'System survived {station_kills} station kills, failure rate {failure_rate:.1%}',
                severity='INFO',
                evidence={'station_kills': station_kills, 'failure_rate': failure_rate,
                          'total_entities': total_entities}
            ))

        # Check for leaked resources (open connections, etc.)
        # Pool should be closable
        try:
            pool.close()
            self.report.add_finding(GauntletFinding(
                phase='Phase 10: Sustained Soak',
                injection='Pool close after sustained load',
                expected_behavior='Clean shutdown, no resource leaks',
                actual_behavior='Pool closed successfully',
                severity='INFO',
                evidence={}
            ))
        except Exception as e:
            self.report.add_finding(GauntletFinding(
                phase='Phase 10: Sustained Soak',
                injection='Pool close after sustained load',
                expected_behavior='Clean shutdown',
                actual_behavior=f'Exception on close: {e}',
                severity='HIGH',
                evidence={'error': str(e)}
            ))


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description='XP-Arc Gauntlet — Adversarial Chaos Testing')
    parser.add_argument('--constitution-check', action='store_true',
                        help='Validate findings against Gauntlet Constitution (Articles III/IV)')
    parser.add_argument('--db', default='gauntlet', help='Base DB path (phase suffixes added)')
    args = parser.parse_args()

    print("""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                    XP-ARC GAUNTLET — ADVERSARIAL CHAOS TESTING               ║
║                                                                              ║
║  This doesn't test happy paths. It breaks the system in ways unit tests     ║
║  never will. All 10 phases execute. Findings emitted as structured JSON.    ║
╚═══════════════════════════════════════════════════════════════════════════════╝
    """)

    gauntlet = Gauntlet(args.db)
    report = gauntlet.run_all_phases()

    # Constitution check if requested
    if args.constitution_check:
        constitution_violations = _validate_constitution(report)
        if constitution_violations:
            print(f"\n[GAUNTLET] CONSTITUTION VIOLATIONS: {len(constitution_violations)}")
            for v in constitution_violations:
                print(f"  - {v}")
            sys.exit(3)

    # Write report
    report_path = f'gauntlet_report_{report.run_id}.json'
    with open(report_path, 'w') as f:
        f.write(report.to_json())

    print(f"\n[GAUNTLET] Report saved to {report_path}")

    # Exit with non-zero if CRITICAL findings
    critical_count = report.summary.get('CRITICAL', 0)
    if critical_count > 0:
        print(f"[GAUNTLET] {critical_count} CRITICAL findings — GAUNTLET FAILED")
        sys.exit(1)
    else:
        print("[GAUNTLET] No CRITICAL findings — GAUNTLET PASSED")
        sys.exit(0)


def _validate_constitution(report) -> list:
    """Validate findings against Gauntlet Constitution Articles III (Severity) and IV (Evidence)."""
    violations = []
    
    for f in report.findings:
        # Article III: Severity must be one of CRITICAL, HIGH, MEDIUM, LOW, INFO
        if f.severity not in ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'):
            violations.append(f"Finding {f.phase}: invalid severity '{f.severity}' (Article III)")
        
        # Article IV: Evidence required for CRITICAL/HIGH
        if f.severity in ('CRITICAL', 'HIGH') and not f.evidence:
            violations.append(f"Finding {f.phase}: {f.severity} requires evidence (Article IV)")
        
        # Article IV: Evidence hierarchy - on-disk artifact preferred
        if f.severity == 'CRITICAL' and 'entity_id' not in f.evidence and 'path' not in f.evidence:
            violations.append(f"Finding {f.phase}: CRITICAL should cite on-disk artifact (Article IV.2)")
    
    return violations


if __name__ == '__main__':
    main()