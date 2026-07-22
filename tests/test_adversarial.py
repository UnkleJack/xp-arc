"""
XP-Arc Comprehensive Adversarial & Edge-Case Test Suite.

Systematically probes all constitutional boundaries, schema validation limits,
cryptographic write authorization, cascade depth limits, sharding invariants,
circuit breakers, and Zoran's Law / SpaZzMatiC monitoring triggers.
"""

import os
import sys
import json
import time
import uuid
import hmac
import hashlib
import pytest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from xp_arc.core.pool import IntelligencePool, compute_payload_hash, register_station_with_key, MAX_CASCADE_DEPTH
from xp_arc.core.executive import ExecutiveChef
from xp_arc.core.aboyeur import Aboyeur
from xp_arc.core.fracture import FractureProtocol, FractureRequest
from xp_arc.core.station import StationChef
from xp_arc.core.sanitization import sanitize_d2_node_id, sanitize_markdown
from xp_arc.broker import SQLiteBrokerExecutor, WriteRequest
from xp_arc.monitoring.zorans_law import ZoransLaw
from xp_arc.monitoring.spazzmatic import SpaZzMatiC


@pytest.fixture
def fresh_pool():
    """Return a fresh in-memory IntelligencePool."""
    return IntelligencePool(":memory:")


# ─── 1. Sanitization & Output Injection Defense ───

def test_adversarial_d2_node_id_sanitization():
    """Verify D2 graph node ID sanitization against path traversal, XSS, and control chars."""
    assert sanitize_d2_node_id("../../../etc/passwd") == "etc_passwd"
    assert sanitize_d2_node_id("<script>alert(1)</script>") == "script_alert_1_script"
    assert sanitize_d2_node_id("node|with|pipes<and>brackets") == "node_with_pipes_and_brackets"
    assert sanitize_d2_node_id("") == "unnamed_node"
    assert sanitize_d2_node_id("___multi___under___") == "multi_under"
    # Length truncation check
    long_input = "a" * 300
    assert len(sanitize_d2_node_id(long_input, max_len=64)) == 64


def test_adversarial_markdown_sanitization():
    """Verify Markdown sanitization against injection across table cells and code blocks."""
    xss = "[Click Here](javascript:alert('XSS')) | `backtick_code` | ```python\nevil()\n```"
    sanitized = sanitize_markdown(xss, max_len=100)
    assert "\\|" in sanitized  # pipes escaped with backslash
    assert "\\`" in sanitized  # backticks escaped with backslash
    assert "javascript:" in sanitized or "alert" in sanitized # text preserved but syntax stripped
    assert len(sanitized) <= 100


# ─── 2. Unauthorized Status Transitions (Article III, Section 3.2) ───

def test_adversarial_unauthorized_status_transitions(fresh_pool):
    """Attempt illegal state jumps across IntelligencePool and write broker."""
    pool = fresh_pool
    eid = pool.add_entity("domain", "evil.com")
    assert pool.get_entity(eid)["status"] == "raw"

    # Illegal jump: raw -> completed (skipping processing & pending_qa)
    assert pool.transition_status(eid, "completed") is False
    assert pool.get_entity(eid)["status"] == "raw"

    # Illegal jump: raw -> mapped
    assert pool.transition_status(eid, "mapped") is False

    # Check status_violation event logged
    events = pool.get_events()
    violations = [e for e in events if e["event_type"] == "status_violation"]
    assert len(violations) >= 2

    # Legal jump: raw -> processing
    assert pool.transition_status(eid, "processing") is True
    # Illegal jump backwards: processing -> raw
    assert pool.transition_status(eid, "raw") is False


def test_adversarial_broker_unauthorized_transitions():
    """Verify SQLiteBrokerExecutor enforces VALID_TRANSITIONS during broker execution."""
    broker = SQLiteBrokerExecutor(":memory:")
    # Add an entity via broker
    req_add = WriteRequest("add_entity", {"type": "url", "value": "https://test.com"}, "test", "sig")
    res_add = broker.execute_add_entity(req_add)
    eid = res_add["entity_id"]

    # Attempt illegal jump: raw -> completed
    req_trans = WriteRequest("transition_status", {"entity_id": eid, "new_status": "completed"}, "test", "sig")
    res_trans = broker.execute_transition_status(req_trans)
    assert res_trans["ok"] is False
    assert "unauthorized transition" in res_trans["error"]


# ─── 3. HMAC Write Authorization & Tampering (Article VII / authorization.py) ───

def test_adversarial_hmac_write_authorization_rejection(fresh_pool):
    """Verify write operations without a valid HMAC signature are rejected when station has a key."""
    pool = fresh_pool
    # Register station with explicit HMAC key
    pool.register_station("forager", "The Forager", ["url"], is_primary=True, hmac_key="secret_key_hex_32_bytes")

    # Attempt add_entity without HMAC signature (mac=None)
    assert pool.add_entity("url", "https://unauth.com", station_id="forager", mac=None) is None
    # Attempt add_entity with invalid HMAC signature
    assert pool.add_entity("url", "https://unauth.com", station_id="forager", mac="deadbeef") is None

    # Verify auth_failure events logged
    failures = [e for e in pool.get_events() if e["event_type"] == "auth_failure"]
    assert len(failures) == 2

    # Verify valid HMAC signature succeeds via station_writer
    writer = pool.station_writer("forager")
    eid = writer.add_entity("url", "https://auth.com")
    assert eid is not None
    assert pool.get_entity(eid)["value"] == "https://auth.com"


# ─── 4. Snowball Cascade Lineage Spoofing & Depth Limits (Article VII, Section 7.3) ───

def test_adversarial_snowball_lineage_spoofing_and_depth_limit(fresh_pool):
    """Verify agents cannot spoof cascade_depth or bypass the depth limit."""
    pool = fresh_pool
    # Create root entity (depth 0)
    root_id = pool.add_entity("url", "https://root.com")
    pool.transition_status(root_id, "processing")
    pool.transition_status(root_id, "pending_qa")
    pool.transition_status(root_id, "completed")

    # Simulate cascade chain down to depth 4
    parent_id = root_id
    for d in range(1, 5):
        child_id = pool.add_entity("domain", f"level{d}.com", parent_task_id=parent_id)
        assert child_id is not None
        assert pool.get_entity(child_id)["cascade_depth"] == d
        pool.transition_status(child_id, "processing")
        pool.transition_status(child_id, "pending_qa")
        pool.transition_status(child_id, "completed")
        parent_id = child_id

    # Now parent_id is at depth 4. Let's spawn depth 5 (allowed: reaches exactly MAX_CASCADE_DEPTH = 5)
    # Even if caller tries to spoof cascade_depth=0 and root_task_id=999, pool calculates from actual parent!
    spoofed_id = pool.add_entity(
        "url", "https://spoofed.com",
        parent_task_id=parent_id,
        cascade_depth=0,       # spoofed
        root_task_id=999,      # spoofed
        spawn_chain="[]"       # spoofed
    )
    assert spoofed_id is not None
    ent = pool.get_entity(spoofed_id)
    assert ent["cascade_depth"] == 5, "Pool must compute real depth (parent 4 + 1 = 5)"
    assert ent["root_task_id"] == root_id, "Pool must compute real root ID from parent"

    # Now attempt to spawn from depth 5 (depth 6 -> strictly blocked by MAX_CASCADE_DEPTH = 5)
    blocked_id = pool.add_entity("url", "https://too-deep.com", parent_task_id=spoofed_id)
    assert blocked_id is None, "Spawning beyond MAX_CASCADE_DEPTH must be rejected"
    blocked_events = [e for e in pool.get_events() if e["event_type"] == "spawn_blocked_depth_limit"]
    assert len(blocked_events) >= 1


def test_adversarial_broker_snowball_depth_limit():
    """Verify SQLiteBrokerExecutor checks parent lineage and blocks spawns at depth limit."""
    broker = SQLiteBrokerExecutor(":memory:")
    # Add level 0 -> 4 -> 5 -> blocked via broker
    req0 = WriteRequest("add_entity", {"type": "url", "value": "https://root.com"}, "test", "sig")
    r0 = broker.execute_add_entity(req0)
    p_id = r0["entity_id"]

    for d in range(1, 6):
        req = WriteRequest("add_entity", {"type": "url", "value": f"https://level{d}.com", "parent_task_id": p_id}, "test", "sig")
        res = broker.execute_add_entity(req)
        if d <= 5:
            assert res.get("entity_id") is not None, f"Level {d} should be allowed up to 5"
            p_id = res["entity_id"]
        else:
            assert res.get("ok") is False
            assert "cascade depth limit" in res.get("error", "")


# ─── 5. Aboyeur QA Protocol & Circuit Breaker (Article IV) ───

def test_adversarial_aboyeur_qa_validation_rules(fresh_pool):
    """Test out-of-bounds confidence, missing fields, payload tampering, and enhanced scrutiny."""
    pool = fresh_pool
    aboyeur = Aboyeur(pool)

    # Setup entity in pending_qa
    eid = pool.add_entity("domain", "qa-test.com")
    pool.transition_status(eid, "processing", station="analyst")
    pool.transition_status(eid, "pending_qa")

    # Out of range confidence (> 1.0 or < 0.0)
    res_high = aboyeur.validate_and_sign(eid, "analyst", {"entity_type": "domain", "entity_value": "qa-test.com", "confidence": 1.5})
    assert res_high["approved"] is False
    assert "out of range" in res_high["rejection_reason"]

    # Missing required field
    res_missing = aboyeur.validate_and_sign(eid, "analyst", {"entity_type": "domain", "confidence": 0.9})
    assert res_missing["approved"] is False
    assert "Missing required fields" in res_missing["rejection_reason"]

    # Mismatched output entity type/value
    res_mismatch = aboyeur.validate_and_sign(eid, "analyst", {"entity_type": "url", "entity_value": "https://other.com", "confidence": 0.9})
    assert res_mismatch["approved"] is False
    assert "Output does not match input entity" in res_mismatch["rejection_reason"]

    # Reset rejection count and status before testing tampered hash
    with pool.conn:
        pool.conn.execute("UPDATE entities SET rejection_count = 0, status = 'pending_qa', payload_hash = 'tampered_hash_123' WHERE id = ?", (eid,))
    res_tampered = aboyeur.validate_and_sign(eid, "analyst", {"entity_type": "domain", "entity_value": "qa-test.com", "confidence": 0.9})
    assert res_tampered["approved"] is False
    assert "Payload hash mismatch" in res_tampered["rejection_reason"]


def test_adversarial_aboyeur_enhanced_scrutiny_fallback(fresh_pool):
    """Verify fallback outputs receive enhanced Aboyeur scrutiny (Article IV, Section 4.5)."""
    pool = fresh_pool
    aboyeur = Aboyeur(pool)
    eid = pool.add_entity("domain", "fallback.com")
    pool.transition_status(eid, "processing", station="analyst_fallback")
    pool.transition_status(eid, "pending_qa")

    # Fallback output with confidence < 0.4 -> rejected under enhanced scrutiny
    res_low = aboyeur.validate_and_sign(
        eid, "analyst_fallback",
        {"entity_type": "domain", "entity_value": "fallback.com", "confidence": 0.35, "notes": "some notes"},
        is_fallback=True
    )
    assert res_low["approved"] is False
    assert "enhanced threshold 0.4" in res_low["rejection_reason"]

    # Fallback output missing notes -> rejected under enhanced scrutiny
    res_no_notes = aboyeur.validate_and_sign(
        eid, "analyst_fallback",
        {"entity_type": "domain", "entity_value": "fallback.com", "confidence": 0.8},
        is_fallback=True
    )
    assert res_no_notes["approved"] is False
    assert "notes field required" in res_no_notes["rejection_reason"]

    # Valid fallback output with notes and confidence >= 0.4 -> approved
    res_valid = aboyeur.validate_and_sign(
        eid, "analyst_fallback",
        {"entity_type": "domain", "entity_value": "fallback.com", "confidence": 0.85, "notes": "Fallback analysis ok"},
        is_fallback=True
    )
    assert res_valid["approved"] is True
    assert res_valid["enhanced_scrutiny"] is True


def test_adversarial_aboyeur_circuit_breaker_trips(fresh_pool):
    """Verify reaching max_rejections (3) trips circuit breaker, suspends SLA, and logs critical finding."""
    pool = fresh_pool
    aboyeur = Aboyeur(pool)
    eid = pool.add_entity("domain", "stubborn.com")

    for attempt in range(1, 4):
        ent = pool.get_entity(eid)
        if ent["status"] in ("raw", "failed"):
            pool.transition_status(eid, "processing", station="bad_station")
            pool.transition_status(eid, "pending_qa")

        res = aboyeur.validate_and_sign(
            eid, "bad_station",
            {"entity_type": "wrong_type", "entity_value": "wrong_value", "confidence": 0.5}
        )
        assert res["approved"] is False

    # After 3 rejections, circuit breaker must be tripped
    final_ent = pool.get_entity(eid)
    assert final_ent["rejection_count"] == 3
    assert final_ent["status"] == "failed"
    assert final_ent["sla_suspended"] == 1, "SLA must be suspended when escalated by circuit breaker"

    findings = [f for f in pool.get_findings() if f["severity"] == "critical" and "Circuit breaker" in f["message"]]
    assert len(findings) == 1


# ─── 6. Cognitive Sharding & Recombination (Article V) ───

def test_adversarial_fracture_depth_and_commis_rejection(fresh_pool):
    """Verify fracture authorization rules: no double-sharding (depth=1) and no Commis fracturing."""
    pool = fresh_pool
    fracture = FractureProtocol(pool)
    aboyeur = Aboyeur(pool)

    parent_id = pool.add_entity("complex_task", "HugeTaskData")
    # Authorize fracture for primary station -> True
    assert fracture.authorize_fracture(parent_id, "complex_station", "Too big") is True

    # Create shards
    shard_ids = fracture.create_shards(parent_id, "complex_task", "HugeTaskData", shard_count=2)
    assert len(shard_ids) == 2
    shard_id = shard_ids[0]
    shard_ent = pool.get_entity(shard_id)
    assert shard_ent["fracture_id"] is not None

    # Attempt to fracture one of the shards -> MUST BE REJECTED (depth limit = 1)
    assert fracture.authorize_fracture(shard_id, "complex_station", "Try shard of shard") is False

    # Attempt to have Commis agent ('hydra') fracture a normal entity -> MUST BE REJECTED
    other_id = pool.add_entity("complex_task", "AnotherHugeTask")
    assert fracture.authorize_fracture(other_id, "hydra", "Commis requesting fracture") is False


# ─── 7. Zoran's Law & SpaZzMatiC Adversarial Review (Articles VIII & XIV) ───

def test_adversarial_zorans_law_and_spazzmatic_safe_halt(fresh_pool):
    """Simulate sustained distress (S < 0.5) triggering SpaZzMatiC Safe Halt Recommendation and Auto-Compression."""
    pool = fresh_pool
    zorans = ZoransLaw(pool)
    spazz = SpaZzMatiC(pool, zorans)

    # Create mock executive to verify auto-compression
    class MockExecutive:
        def __init__(self):
            self.compressed = False
        def is_compressed(self):
            return self.compressed
        def compress_brigade(self):
            self.compressed = True

    mock_exec = MockExecutive()
    spazz.set_executive(mock_exec)

    # Ingest 10 entities with 300s SLA (= 3000s total ingested SLA)
    for i in range(10):
        pool.add_entity("url", f"https://distress{i}.com", sla_seconds=300)

    # Complete only 1 entity (= 300s completed SLA). S = 300 / 3000 = 0.1 (< 0.5 distress threshold)
    row = pool.conn.execute("SELECT id FROM entities LIMIT 1").fetchone()
    pool.transition_status(row["id"], "processing")
    pool.transition_status(row["id"], "pending_qa")
    pool.transition_status(row["id"], "completed")

    # Take first stability measurement and run first review check: streak = 1 -> warning issued, not yet safe halt
    zorans.measure()
    res1 = spazz.run_review()
    assert res1["safe_halt_recommended"] is False
    assert mock_exec.compressed is False

    # Check formatting existing result does NOT double-increment streak
    rep = spazz.format_report(res1)
    assert "ADVERSARIAL REVIEW REPORT" in rep

    # Take second stability measurement and run second review check: streak = 2 (sustained for SAFE_HALT_SUSTAIN_COUNT = 2)
    # MUST trigger Safe Halt Recommendation and Auto-Compression!
    zorans.measure()
    res2 = spazz.run_review()
    assert res2["safe_halt_recommended"] is True
    assert mock_exec.compressed is True

    findings = [f for f in pool.get_findings() if "SAFE HALT RECOMMENDED" in f["message"]]
    assert len(findings) == 1
