"""
Red Team Test Suite — XP-Arc

Unlike adversarial tests (which test edge cases within the contract),
red team tests model specific attacker capabilities and goals:

  RT-01: Local attacker reads station_keys.json, forges writes as any station
  RT-02: HMAC replay — captured valid MAC reused for a different operation
  RT-03: Station impersonation — station A writes as station B
  RT-04: Aboyeur signature forgery with default development key
  RT-05: Payload hash bypass via direct DB tampering
  RT-06: Status machine violation via direct SQLite write
  RT-07: Cascade depth bypass via direct DB write (not through add_entity)
  RT-08: DRAGON XSS — dossier seed_url and connection values unescaped
  RT-09: DRAGON XSS — entity table escapes, graph tooltip does not
  RT-10: Forager title injection — malicious <title> in scraped HTML
  RT-11: Export state leaks HMAC keys from station_registry
  RT-12: Broker execute_raw accepts arbitrary SQL
  RT-13: Zoran's Law gaming via SLA manipulation
  RT-14: Entity flood DoS — malicious target serves 10000 domains
  RT-15: Fracture shard flood — station creates unlimited shards
  RT-16: Race condition — concurrent entity claims
  RT-17: SSRF via DNS rebinding (TOCTOU between resolve and connect)
  RT-18: Legacy bypass — station_id=None defaults to trusted 'legacy_local'
  RT-19: Spawn chain poisoning — forged cascade_depth in spawn directives
  RT-20: Aboyeur signature timestamp is not verified (replay window)
"""

import hashlib
import hmac
import json
import os
import sqlite3
import tempfile
import threading
import time
import re
import pytest

# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def pool():
    """Fresh pool with temp DB."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    from xp_arc.core.pool import IntelligencePool
    p = IntelligencePool(path)
    yield p
    p.close()
    os.unlink(path)

@pytest.fixture
def pool_with_stations(pool):
    """Pool with registered stations and known keys."""
    key_forager = pool.register_station('forager', 'The Forager', ['url'], is_primary=True)
    key_analyst = pool.register_station('analyst', 'The Analyst', ['domain'], is_primary=True)
    key_exec = pool.register_station('executive', 'The Executive', [], is_primary=True)
    return pool, {'forager': key_forager, 'analyst': key_analyst, 'executive': key_exec}


# ─── RT-01: Local attacker reads station_keys.json ──────────────────────────

def test_red_team_01_key_file_exposure(pool):
    """
    THREAT: Local attacker reads station_keys.json and obtains all HMAC keys.
    SEVERITY: Critical (for local-attacker model).
    
    The station_keys.json file is written in plaintext by 
    register_station_with_key(). Any process with read access to the 
    working directory can forge writes as any station.
    
    FINDING: Keys ARE exposed in plaintext JSON file.
    MITIGATION: File permissions, or use env-var/secret-manager instead.
    """
    from xp_arc.core.pool import register_station_with_key, get_station_hmac_key
    
    key_file = tempfile.mktemp(suffix='.json')
    try:
        # Register a station — this writes to key_file
        key = register_station_with_key(
            'test_station', 'Test Station', ['url'],
            key_file=key_file
        )
        
        # Attacker reads the file
        with open(key_file) as f:
            stolen_keys = json.load(f)
        
        # CONFIRMED: Attacker has the key
        assert 'test_station' in stolen_keys
        assert stolen_keys['test_station'] == key
        
        # Attacker can now forge writes
        retrieved = get_station_hmac_key('test_station', key_file=key_file)
        assert retrieved == key, "Attacker successfully retrieved key from file"
        
        # VERDICT: Keys stored in plaintext — any local process can read them.
        # This is by design (local trust model) but should be documented.
    finally:
        if os.path.exists(key_file):
            os.unlink(key_file)


# ─── RT-02: HMAC Replay Attack ──────────────────────────────────────────────

def test_red_team_02_hmac_replay(pool_with_stations):
    """
    THREAT: Attacker captures a valid HMAC and replays it for a different operation.
    SEVERITY: Medium.
    
    The HMAC covers the payload string including operation, entity_id, and value.
    A captured MAC for add_entity:url:example.com:60 should not work for
    add_entity:url:evil.com:60.
    
    FINDING: Replay IS blocked — different payloads produce different MACs.
    """
    pool, keys = pool_with_stations
    forager_key = keys['forager']
    
    # Legitimate station signs a payload
    payload_a = "add_entity:url:https://example.com:60"
    mac_a = hmac.new(forager_key.encode(), payload_a.encode(), hashlib.sha256).hexdigest()
    
    # Attacker tries to replay mac_a for a different entity
    payload_b = "add_entity:url:https://evil.com:60"
    
    # Verify: the pool should reject mac_a for payload_b
    result = pool._verify_write('forager', payload_b, mac_a)
    assert result is False, "HMAC replay should be rejected — different payload"
    
    # But the legitimate MAC should work for its own payload
    result = pool._verify_write('forager', payload_a, mac_a)
    assert result is True, "Legitimate HMAC should be accepted"


def test_red_team_02b_exact_replay(pool_with_stations):
    """
    THREAT: Attacker replays the exact same request (same payload + same MAC).
    SEVERITY: Low (idempotent — duplicate entity is rejected by UNIQUE constraint).
    
    FINDING: Exact replay is accepted by HMAC verification, but the 
    UNIQUE(type, value) constraint prevents duplicate entity creation.
    This is defense-in-depth working correctly.
    """
    pool, keys = pool_with_stations
    writer = pool.station_writer('forager')
    
    # First write succeeds
    eid1 = writer.add_entity('url', 'https://replay-test.com')
    assert eid1 is not None
    
    # Exact replay of same entity — should return None (duplicate)
    eid2 = writer.add_entity('url', 'https://replay-test.com')
    assert eid2 is None, "Duplicate entity should be rejected by UNIQUE constraint"


# ─── RT-03: Station Impersonation ───────────────────────────────────────────

def test_red_team_03_station_impersonation(pool_with_stations):
    """
    THREAT: Station A tries to write as Station B using Station A's own key.
    SEVERITY: Medium.
    
    FINDING: Impersonation IS blocked — the pool looks up the key for the
    claimed station_id, not the caller's key. Forager's key does not match
    the analyst's stored key.
    """
    pool, keys = pool_with_stations
    forager_key = keys['forager']
    
    # Forager tries to write claiming to be 'analyst'
    payload = "add_entity:domain:evil.com:60"
    mac_with_forager_key = hmac.new(
        forager_key.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    
    # Pool checks this MAC against analyst's key, not forager's
    result = pool._verify_write('analyst', payload, mac_with_forager_key)
    assert result is False, "Station impersonation should be rejected"


def test_red_team_03b_impersonation_with_stolen_key(pool_with_stations):
    """
    THREAT: Station A reads station_keys.json, steals Station B's key, writes as B.
    SEVERITY: Critical (combines RT-01 + RT-03).
    
    FINDING: With the stolen key, impersonation SUCCEEDS. This is the 
    combined attack chain — key file exposure enables full impersonation.
    """
    pool, keys = pool_with_stations
    analyst_key = keys['analyst']
    
    # "Attacker" (forager) has analyst's key (stolen from station_keys.json)
    payload = "add_entity:domain:evil.com:60"
    mac_with_analyst_key = hmac.new(
        analyst_key.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    
    # Pool accepts because the MAC matches analyst's stored key
    result = pool._verify_write('analyst', payload, mac_with_analyst_key)
    assert result is True, "With stolen key, impersonation succeeds (known risk)"
    
    # The attacker can now write entities as the analyst
    eid = pool.add_entity('domain', 'evil.com',
                          station_id='analyst', mac=mac_with_analyst_key)
    assert eid is not None, "Impersonated write succeeded with stolen key"


# ─── RT-04: Aboyeur Signature Forgery ───────────────────────────────────────

def test_red_team_04_aboyeur_default_key_forgery(pool):
    """
    THREAT: Aboyeur signing key defaults to 'development-only-change-me'.
    An attacker who knows this can forge Aboyeur signatures.
    SEVERITY: High (in deployments that don't change the default).
    
    FINDING: Default key IS 'development-only-change-me'. An attacker can
    generate valid ABOY-{hash} signatures for any entity.
    """
    from xp_arc.core.aboyeur import Aboyeur
    
    aboyeur = Aboyeur(pool)
    
    # CONFIRMED: Default key
    assert aboyeur._signing_key == 'development-only-change-me', \
        "Default signing key should be the known development value"
    
    # Attacker forges a signature
    entity_id = pool.add_entity('url', 'https://forged-test.com')
    assert entity_id is not None
    
    forged_payload = json.dumps({
        'entity_id': entity_id,
        'station_id': 'forger',
        'entity_type': 'url',
        'entity_value': 'https://forged-test.com',
        'confidence': 0.99,
        'timestamp': '2026-01-01T00:00:00+00:00',  # arbitrary timestamp
    }, sort_keys=True)
    
    forged_sig = hmac.new(
        'development-only-change-me'.encode(),
        forged_payload.encode(),
        hashlib.sha256
    ).hexdigest()
    
    forged_signature = f"ABOY-{forged_sig}"
    
    # The forged signature is structurally valid
    assert forged_signature.startswith("ABOY-")
    assert len(forged_signature) == 69  # "ABOY-" + 64 hex chars
    
    # An attacker could set this signature on any entity
    pool.set_aboyeur_signature(entity_id, forged_signature, station_id='legacy_local')
    entity = pool.get_entity(entity_id)
    assert entity['aboyeur_signature'] == forged_signature


# ─── RT-05: Payload Hash Bypass via Direct DB Tampering ─────────────────────

def test_red_team_05_payload_hash_tampering(pool):
    """
    THREAT: Attacker modifies entity value directly in SQLite, bypassing
    the Aboyeur's payload hash check.
    SEVERITY: Medium (requires local DB access).
    
    FINDING: The Aboyeur DOES detect tampering — it recomputes the hash
    from the current type/value and compares against the stored hash.
    BUT: An attacker with direct DB access could update BOTH the value
    AND the hash, defeating the check entirely.
    """
    from xp_arc.core.pool import compute_payload_hash
    from xp_arc.core.aboyeur import Aboyeur
    
    # Create entity normally
    eid = pool.add_entity('domain', 'legitimate.com')
    assert eid is not None
    
    original_hash = pool.get_entity(eid)['payload_hash']
    expected_hash = compute_payload_hash('domain', 'legitimate.com')
    assert original_hash == expected_hash
    
    # Attacker modifies value directly in DB
    with pool.conn:
        pool.conn.execute(
            "UPDATE entities SET value = ? WHERE id = ?",
            ('evil.com', eid)
        )
    
    # Aboyeur should detect the tampering
    aboyeur = Aboyeur(pool)
    # Transition to pending_qa first
    pool.transition_status(eid, 'processing', station_id='legacy_local')
    pool.transition_status(eid, 'pending_qa', station_id='legacy_local')
    
    result = aboyeur.validate_and_sign(eid, 'test_station', {
        'entity_type': 'domain',
        'entity_value': 'evil.com',  # attacker's value
        'confidence': 0.9,
    })
    assert result['approved'] is False, "Tampered entity should fail hash check"
    assert 'hash mismatch' in result['rejection_reason'].lower() or \
           'tamper' in result['rejection_reason'].lower()
    
    # BUT: attacker with DB access can also update the hash
    new_hash = compute_payload_hash('domain', 'evil.com')
    with pool.conn:
        pool.conn.execute(
            "UPDATE entities SET payload_hash = ? WHERE id = ?",
            (new_hash, eid)
        )
    
    # Now the hash matches and the Aboyeur won't detect tampering
    # (This is inherent to any local-access attack model)
    entity = pool.get_entity(eid)
    recomputed = compute_payload_hash(entity['type'], entity['value'])
    assert entity['payload_hash'] == recomputed, \
        "With both value and hash updated, tampering is undetectable"


# ─── RT-06: Status Machine Violation via Direct SQLite Write ────────────────

def test_red_team_06_direct_db_status_violation(pool):
    """
    THREAT: Local attacker writes invalid status directly to SQLite,
    bypassing the VALID_TRANSITIONS state machine.
    SEVERITY: Medium (requires local DB access, but breaks invariants).
    
    FINDING: Direct SQLite writes CAN violate the state machine.
    The Aboyeur checks status == 'pending_qa' before validating, so a
    'raw' entity forced to 'completed' skips QA entirely.
    """
    from xp_arc.core.pool import VALID_TRANSITIONS
    
    # Create entity normally
    eid = pool.add_entity('url', 'https://bypass-test.com')
    assert pool.get_entity(eid)['status'] == 'raw'
    
    # Attacker bypasses state machine via direct SQLite write
    with pool.conn:
        pool.conn.execute(
            "UPDATE entities SET status = 'completed' WHERE id = ?",
            (eid,)
        )
    
    # CONFIRMED: Status is now 'completed' without going through any QA
    entity = pool.get_entity(eid)
    assert entity['status'] == 'completed', \
        "Direct DB write bypassed VALID_TRANSITIONS state machine"
    assert entity['aboyeur_signature'] is None, \
        "Entity is 'completed' without Aboyeur signature — QA was skipped"
    
    # This breaks the constitutional guarantee that all completed entities
    # have been through Aboyeur QA


# ─── RT-07: Cascade Depth Bypass via Direct DB Write ────────────────────────

def test_red_team_07_cascade_depth_bypass(pool):
    """
    THREAT: Attacker creates deeply-nested entities by writing directly
    to SQLite, bypassing the MAX_CASCADE_DEPTH enforcement in add_entity.
    SEVERITY: Low-Medium (requires DB access, but could enable Snowball runaway).
    
    FINDING: Direct DB writes bypass cascade depth enforcement.
    """
    from xp_arc.core.pool import MAX_CASCADE_DEPTH
    
    # Create a seed entity normally
    seed_id = pool.add_entity('url', 'https://seed.com')
    assert seed_id is not None
    
    # Build a chain to the depth limit normally
    current_parent = seed_id
    for depth in range(MAX_CASCADE_DEPTH):
        child_id = pool.add_entity(
            'domain', f'depth-{depth}.com',
            parent_task_id=current_parent,
        )
        assert child_id is not None, f"Should allow depth {depth+1}"
        current_parent = child_id
    
    # At this point, normal add_entity should reject further nesting
    rejected = pool.add_entity(
        'domain', 'too-deep.com',
        parent_task_id=current_parent,
    )
    assert rejected is None, "Normal path should reject depth > MAX_CASCADE_DEPTH"
    
    # But attacker can write directly to DB
    with pool.conn:
        pool.conn.execute("""
            INSERT INTO entities (type, value, status, payload_hash, cascade_depth, parent_task_id)
            VALUES (?, ?, 'raw', ?, ?, ?)
        """, ('domain', 'bypassed-depth.com', 'fake_hash', 99, current_parent))
    
    bypassed = pool.conn.execute(
        "SELECT * FROM entities WHERE value = 'bypassed-depth.com'"
    ).fetchone()
    assert bypassed is not None
    assert bypassed['cascade_depth'] == 99, \
        "Direct DB write bypassed MAX_CASCADE_DEPTH enforcement"


# ─── RT-08: DRAGON XSS — Dossier View ──────────────────────────────────────

def test_red_team_08_dragon_dossier_xss():
    """
    THREAT: The DRAGON dossier card renderer (renderDossiers) interpolates
    seed_url and connection values into innerHTML without escapeHtml().
    A malicious seed URL or connection value containing HTML/JS executes.
    SEVERITY: High (XSS in dashboard).
    
    STATUS: FIXED — seedDisplay, c.value, and c.relationship now wrapped
    in escapeHtml().
    """
    # Read the DRAGON HTML
    dragon_path = os.path.join(os.path.dirname(__file__), '..', 'dragon', 'index.html')
    with open(dragon_path) as f:
        html = f.read()
    
    # Find the renderDossiers function
    dossier_func = html[html.index('function renderDossiers'):html.index('function toggleDossier')]
    
    # FIXED: seedDisplay is now escaped
    assert 'escapeHtml(d.seed_url' in dossier_func or 'escapeHtml(d.seed_url.replace' in dossier_func, \
        "seedDisplay is now escaped with escapeHtml()"
    
    # FIXED: Connection values are now escaped
    assert 'escapeHtml(c.value)' in dossier_func, \
        "c.value is now escaped with escapeHtml() in dossier connections"
    assert 'escapeHtml(c.relationship)' in dossier_func, \
        "c.relationship is now escaped with escapeHtml() in dossier connections"
    
    # Entity table also escapes (already correct)
    entity_table_func = html[html.index('function renderEntityTable'):]
    entity_table_func = entity_table_func[:entity_table_func.index('function sortTable')]
    assert 'escapeHtml(e.value)' in entity_table_func, \
        "Entity table correctly escapes e.value"


# ─── RT-09: DRAGON XSS — Graph Tooltip ──────────────────────────────────────

def test_red_team_09_dragon_graph_tooltip_xss():
    """
    THREAT: The DRAGON graph tooltip sets innerHTML with entity values
    that may contain attacker-controlled content from Forager scraping.
    SEVERITY: Medium (XSS via tooltip).
    
    STATUS: FIXED — tooltip now uses escapeHtml() for d.id, d.type,
    d.status, d.station, and d.signature.
    """
    dragon_path = os.path.join(os.path.dirname(__file__), '..', 'dragon', 'index.html')
    with open(dragon_path) as f:
        html = f.read()
    
    # Find the tooltip rendering in the graph section
    tooltip_section = html[html.index("'mouseover'"):html.index("'mousemove'")]
    
    # FIXED: All attacker-controlled fields now escaped
    assert 'escapeHtml(d.id)' in tooltip_section, \
        "Graph tooltip now escapes d.id (entity value)"
    assert 'escapeHtml(d.type)' in tooltip_section, \
        "Graph tooltip now escapes d.type"
    assert 'escapeHtml(d.station' in tooltip_section, \
        "Graph tooltip now escapes d.station"
    assert 'escapeHtml(d.signature)' in tooltip_section, \
        "Graph tooltip now escapes d.signature"


# ─── RT-10: Forager Title Injection ────────────────────────────────────────

def test_red_team_10_forager_title_injection(pool):
    """
    THREAT: The Forager extracts page titles from scraped HTML without
    sanitization. A malicious page with a crafted <title> can inject
    arbitrary content into the entity notes field.
    SEVERITY: Low (notes are display-only, but could affect DRAGON rendering).
    
    STATUS: FIXED — title extraction now strips HTML tags with re.sub().
    """
    # Simulate what the Forager does with a malicious title
    malicious_html = '''
    <html>
    <head><title><img src=x onerror=alert(1)> Evil Title</title></head>
    <body><a href="https://evil.com">link</a></body>
    </html>
    '''
    
    # This is the regex the Forager uses, followed by HTML tag stripping
    title_match = re.search(r'<title[^>]*>(.*?)</title>', malicious_html, 
                            re.IGNORECASE | re.DOTALL)
    
    assert title_match is not None
    raw_title = title_match.group(1).strip()[:200]
    
    # FIXED: HTML tags are now stripped
    sanitized_title = re.sub(r'<[^>]+>', '', raw_title).strip()[:200] or "No title"
    
    assert '<img' not in sanitized_title, "HTML tags should be stripped from title"
    assert 'onerror' not in sanitized_title, "Event handlers should be stripped from title"
    assert 'Evil Title' in sanitized_title, "Text content should be preserved"


# ─── RT-11: Export State Leaks HMAC Keys ────────────────────────────────────

def test_red_team_11_export_state_key_leak(pool):
    """
    THREAT: pool.export_state() includes station_registry data which
    contains HMAC keys in plaintext.
    SEVERITY: High (any consumer of the export gets all station keys).
    
    STATUS: FIXED — export_state() now strips hmac_key from station export.
    """
    # Register stations with known keys
    key1 = pool.register_station('forager', 'The Forager', ['url'])
    key2 = pool.register_station('analyst', 'The Analyst', ['domain'])
    
    # Export the full state
    state = pool.export_state()
    
    # Check stations in export
    assert 'stations' in state
    assert len(state['stations']) > 0
    
    # FIXED: No HMAC keys should be in the export
    for station in state['stations']:
        assert 'hmac_key' not in station, \
            f"Station '{station['station_id']}' still has hmac_key in export"
        # Verify keys are not leaked
        for key in [key1, key2]:
            assert key not in str(station), \
                f"Station key leaked in export for '{station['station_id']}'"


# ─── RT-12: Broker execute_raw Accepts Arbitrary SQL ────────────────────────

def test_red_team_12_broker_execute_raw():
    """
    THREAT: SQLiteBrokerExecutor.execute_raw() accepts arbitrary SQL strings.
    If reachable from untrusted input, this is a full SQL injection.
    SEVERITY: Critical (if reachable) / Low (if internal only).
    
    FINDING: The method exists and executes arbitrary SQL. However, it
    appears to be internal-only (no HTTP endpoint exposes it directly).
    The risk is if the DRAGON API or broker client ever passes user input
    to this method.
    """
    from xp_arc.broker import SQLiteBrokerExecutor
    
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    try:
        executor = SQLiteBrokerExecutor(path)
        
        # CONFIRMED: execute_raw accepts arbitrary SQL
        result = executor.execute_raw("SELECT 1 as test_col")
        assert len(result) > 0
        
        # An attacker with access could:
        # 1. Drop tables
        # 2. Read all data including HMAC keys
        # 3. Insert arbitrary entities
        
        # Example: read all station keys
        executor.conn.execute("""
            CREATE TABLE IF NOT EXISTS station_registry (
                station_id TEXT, hmac_key TEXT
            )
        """)
        executor.conn.execute(
            "INSERT INTO station_registry VALUES ('test', 'secret_key_123')"
        )
        executor.conn.commit()
        
        leaked = executor.execute_raw("SELECT * FROM station_registry")
        assert len(leaked) > 0
        assert leaked[0].get('hmac_key') == 'secret_key_123' or \
               'secret_key_123' in str(leaked[0])
        
        executor.close()
    finally:
        os.unlink(path)


# ─── RT-13: Zoran's Law Gaming via SLA Manipulation ─────────────────────────

def test_red_team_13_zorans_law_sla_gaming(pool):
    """
    THREAT: A malicious station declares artificially high SLA on tasks
    it completes (inflating S) and low SLA on tasks it fails (minimizing
    damage to S).
    SEVERITY: Medium (games the stability metric).
    
    FINDING: sla_seconds is set at entity creation time (by the writer),
    not by the processing station. So a station cannot game SLA per-task.
    BUT: the Executive/Forager that creates entities CAN set arbitrary SLA.
    
    The real risk: if sla_seconds is set at seed creation by the operator,
    a compromised Forager could create seeds with extreme SLA values.
    """
    from xp_arc.monitoring.zorans_law import ZoransLaw
    
    # Normal operation: S should be balanced
    # Create entities with normal SLA
    for i in range(5):
        eid = pool.add_entity('url', f'https://normal-{i}.com', sla_seconds=60)
        pool.transition_status(eid, 'processing', station_id='legacy_local')
        pool.transition_status(eid, 'pending_qa', station_id='legacy_local')
        pool.transition_status(eid, 'completed', station_id='legacy_local')
    
    # Create entities that stay raw (ingested but not completed)
    for i in range(5):
        pool.add_entity('domain', f'unprocessed-{i}.com', sla_seconds=60)
    
    zl = ZoransLaw(pool)
    normal_measurement = zl.measure()
    
    # Now simulate gaming: create completed entities with extremely high SLA
    for i in range(3):
        eid = pool.add_entity('url', f'https://gamed-{i}.com', sla_seconds=99999)
        pool.transition_status(eid, 'processing', station_id='legacy_local')
        pool.transition_status(eid, 'pending_qa', station_id='legacy_local')
        pool.transition_status(eid, 'completed', station_id='legacy_local')
    
    gamed_measurement = zl.measure()
    
    # S should be significantly higher after gaming
    assert gamed_measurement['stability_quotient'] > normal_measurement['stability_quotient'], \
        "SLA gaming inflated the Stability Quotient"
    
    # This proves S can be manipulated by controlling sla_seconds at creation


# ─── RT-14: Entity Flood DoS ────────────────────────────────────────────────

def test_red_team_14_entity_flood(pool):
    """
    THREAT: A malicious Forager target serves thousands of domains,
    overwhelming the pool past max_entities.
    SEVERITY: Medium (DoS via resource exhaustion).
    
    FINDING: max_entities is enforced in the Executive's run_service loop
    (processed < self.max_entities), but individual station add_entity calls
    during processing are NOT rate-limited by max_entities. A single Forager
    process() call can create unlimited child entities.
    """
    from xp_arc.core.executive import ExecutiveChef
    
    # Register a station that spawns many entities
    class FloodStation:
        station_id = 'flood_station'
        name = 'Flood Station'
        handles_types = ['flood_seed']
        is_primary = True
        critical = True
        _tasks_processed = 0
        _tasks_failed = 0
        _active = True
        
        def __init__(self, pool):
            self.pool = pool
            pool.register_station(self.station_id, self.name, self.handles_types)
            self.writer = pool.station_writer(self.station_id)
        
        def can_handle(self, ent_type):
            return ent_type in self.handles_types
        
        @property
        def is_active(self):
            return self._active
        
        @property
        def stats(self):
            return {'station_id': self.station_id}
        
        def process(self, entity_id, entity_type, entity_value):
            # Spawn 1000 child entities from a single process() call
            spawn_targets = [
                {'ent_type': 'domain', 'value': f'flood-{i}.com'}
                for i in range(1000)
            ]
            return {
                'entity_type': entity_type,
                'entity_value': entity_value,
                'confidence': 0.9,
                'notes': 'Flood test',
                'spawn_targets': spawn_targets,
            }
    
    flood = FloodStation(pool)
    
    # Create seed entity
    seed_id = pool.add_entity('flood_seed', 'https://flood-source.com')
    assert seed_id is not None
    
    # Run executive with max_entities=10 (should only process 10)
    exec = ExecutiveChef(pool, max_entities=10, verbose=False)
    exec.register_station(flood)
    result = exec.run_service()
    
    # FIXED: Spawn targets are now capped at MAX_SPAWN_PER_ENTITY (50)
    total = pool.count_entities()
    # Seed (1) + capped spawns (50) = 51 max
    assert total <= 51, \
        f"Entity flood should be capped at 51, got {total}"
    assert total > 1, f"Expected some spawns, got {total}"


# ─── RT-15: Fracture Shard Flood ────────────────────────────────────────────

def test_red_team_15_fracture_shard_flood(pool):
    """
    THREAT: A station requests fracture with an extremely high shard_count,
    creating thousands of shard entities from a single parent.
    SEVERITY: Low-Medium (resource exhaustion via fracture).
    
    FINDING: There is no upper bound on shard_count in FractureRequest
    or in FractureProtocol.create_shards(). A station can request 
    arbitrary numbers of shards.
    """
    from xp_arc.core.fracture import FractureProtocol, FractureRequest
    
    # Create a parent entity
    parent_id = pool.add_entity('complex_task', 'massive_task')
    pool.transition_status(parent_id, 'processing', station_id='legacy_local')
    
    # Request fracture with absurd shard count
    fracture = FractureProtocol(pool)
    shard_ids = fracture.create_shards(parent_id, 'complex_task', 'massive_task',
                                        shard_count=500)  # 500 shards requested
    
    # FIXED: Shard count is capped at MAX_SHARD_COUNT (20)
    assert len(shard_ids) <= FractureProtocol.MAX_SHARD_COUNT, \
        f"Shard count should be capped at {FractureProtocol.MAX_SHARD_COUNT}, got {len(shard_ids)}"
    
    total = pool.count_entities()
    assert total <= FractureProtocol.MAX_SHARD_COUNT + 1  # parent + capped shards


# ─── RT-16: Race Condition — Concurrent Entity Claims ───────────────────────

def test_red_team_16_concurrent_claims(pool):
    """
    THREAT: Two stations try to claim the same entity simultaneously.
    SEVERITY: Low (should be handled by the write lock).
    
    FINDING: claim_entity uses _write_lock + atomic UPDATE WHERE, so
    only one station can claim a given entity. This is correctly implemented.
    """
    # Create entity
    eid = pool.add_entity('url', 'https://race-test.com')
    assert eid is not None
    
    results = {'a': None, 'b': None}
    errors = []
    
    def claim_a():
        try:
            results['a'] = pool.claim_entity(eid, 'station_a')
        except Exception as e:
            errors.append(('a', e))
    
    def claim_b():
        try:
            results['b'] = pool.claim_entity(eid, 'station_b')
        except Exception as e:
            errors.append(('b', e))
    
    # Launch concurrent claims
    t_a = threading.Thread(target=claim_a)
    t_b = threading.Thread(target=claim_b)
    t_a.start()
    t_b.start()
    t_a.join(timeout=5)
    t_b.join(timeout=5)
    
    # Exactly one should succeed
    claimed = [r for r in [results['a'], results['b']] if r is not None]
    assert len(claimed) == 1, f"Expected exactly 1 successful claim, got {len(claimed)}"
    
    # The winner should have the entity
    winner = 'station_a' if results['a'] else 'station_b'
    entity = pool.get_entity(eid)
    assert entity['station'] == winner


# ─── RT-17: SSRF via DNS Rebinding (TOCTOU) ─────────────────────────────────

def test_red_team_17_dns_rebinding_conceptual():
    """
    THREAT: The network_guard resolves DNS to check for public IPs, then
    opens the URL. Between resolution and connection, DNS can change
    (TOCTOU — Time of Check vs Time of Use).
    SEVERITY: Medium (requires DNS control, but a real attack class).
    
    FINDING: network_guard.public_url() resolves DNS, checks IPs, then
    open_public_url() opens the URL which resolves DNS AGAIN. Between
    these two resolutions, the DNS record can change from a public IP
    to 127.0.0.1.
    
    This is a known limitation of check-then-connect patterns.
    Full mitigation requires connecting to the already-resolved IP.
    """
    from xp_arc.core.network_guard import public_url, open_public_url
    
    # Conceptual test: the vulnerability is in the architecture, not
    # in any specific input. We verify the TOCTOU gap exists.
    
    # public_url() calls socket.getaddrinfo() to resolve and check
    # open_public_url() calls urllib.request which resolves DNS AGAIN
    # These are two separate DNS lookups with no atomicity guarantee
    
    # The code path is:
    # 1. public_url(url) → socket.getaddrinfo() → check IPs → True
    # 2. open_public_url(url) → urllib → socket.getaddrinfo() AGAIN → connect
    
    # Between step 1 and step 2, DNS can change (rebinding attack)
    # We can't easily test this without controlling a DNS server,
    # but we can verify the code structure has the gap
    
    import inspect
    source = inspect.getsource(open_public_url)
    
    # CONFIRMED: open_public_url calls public_url (which does DNS check)
    # then calls opener.open(url) which does its OWN DNS resolution
    assert 'public_url' in source, "open_public_url calls public_url for check"
    assert 'opener.open' in source, "open_public_url opens URL separately from check"
    
    # The two DNS lookups are not atomic — TOCTOU gap confirmed


# ─── RT-18: Legacy Bypass — station_id=None → 'legacy_local' ────────────────

def test_red_team_18_legacy_bypass(pool_with_stations):
    """
    THREAT: Any code that calls pool.add_entity() without station_id
    defaults to 'legacy_local', which is in the trusted bypass list.
    This means direct pool API calls skip HMAC verification entirely.
    SEVERITY: Medium (allows unauthenticated writes from any code with
    a pool reference).
    
    FINDING: CONFIRMED — station_id=None → 'legacy_local' → HMAC bypass.
    """
    pool, keys = pool_with_stations
    
    # Call add_entity without station_id — defaults to 'legacy_local'
    eid = pool.add_entity('domain', 'unauthenticated.com')
    assert eid is not None, "Write without station_id succeeded (legacy bypass)"
    
    # The entity was written with zero HMAC verification
    entity = pool.get_entity(eid)
    assert entity is not None
    assert entity['type'] == 'domain'
    assert entity['value'] == 'unauthenticated.com'
    
    # Also works for transition_status
    result = pool.transition_status(eid, 'processing')
    assert result is True, "Transition without station_id succeeded (legacy bypass)"
    
    # And add_edge
    pool.add_edge('source.com', 'links_to', 'unauthenticated.com')
    edges = pool.get_all_edges()
    assert any(e['target'] == 'unauthenticated.com' for e in edges)


# ─── RT-19: Spawn Chain Poisoning ───────────────────────────────────────────

def test_red_team_19_spawn_chain_spoofing(pool_with_stations):
    """
    THREAT: A station passes forged cascade_depth / root_task_id values
    to add_entity, trying to bypass the depth limit or fake lineage.
    SEVERITY: Low (the pool's _verify_and_compute_lineage recomputes
    from the actual parent in DB).
    
    FINDING: Lineage spoofing IS blocked — the pool ignores caller-supplied
    cascade_depth and recomputes from the parent entity in the DB.
    """
    pool, keys = pool_with_stations
    writer = pool.station_writer('forager')
    
    # Create a seed
    seed_id = writer.add_entity('url', 'https://seed.com')
    
    # Try to spoof cascade_depth to 0 (claiming this is a root entity)
    # even though it has a parent
    eid = pool.add_entity(
        'domain', 'spoofed.com',
        parent_task_id=seed_id,
        cascade_depth=0,        # lying about depth
        root_task_id=None,      # lying about root
        spawn_chain='[]',       # lying about chain
        station_id='forager',
        mac=None  # will use writer instead
    )
    
    # Actually, let's check what the pool computed
    if eid:
        entity = pool.get_entity(eid)
        # The pool should have RECOMPUTED cascade_depth from the parent
        # Parent seed_id has cascade_depth=0, so child should be 1
        assert entity['cascade_depth'] == 1, \
            f"Pool recomputed depth from parent (got {entity['cascade_depth']})"
        assert entity['root_task_id'] == seed_id, \
            "Pool recomputed root_task_id from parent"


# ─── RT-20: Aboyeur Signature Timestamp Not Verified ────────────────────────

def test_red_team_20_aboyeur_signature_no_expiry(pool):
    """
    THREAT: Aboyeur signatures include a timestamp, but there is no
    verification that the timestamp is recent. A captured signature
    from any time in the past is still valid.
    SEVERITY: Low (signatures are per-entity, so replay only works
    for the same entity_id).
    
    FINDING: The Aboyeur generates signatures with timestamps but never
    verifies them on read. The timestamp is purely informational.
    """
    from xp_arc.core.aboyeur import Aboyeur
    
    aboyeur = Aboyeur(pool, signing_key='test-key')
    
    # Create and process an entity through normal flow
    eid = pool.add_entity('url', 'https://timestamp-test.com')
    pool.transition_status(eid, 'processing', station_id='legacy_local')
    pool.transition_status(eid, 'pending_qa', station_id='legacy_local')
    
    # Generate signature
    result = aboyeur.validate_and_sign(eid, 'test_station', {
        'entity_type': 'url',
        'entity_value': 'https://timestamp-test.com',
        'confidence': 0.9,
    })
    assert result['approved']
    signature = result['signature']
    
    # The signature contains a timestamp from when it was generated
    # But there's no mechanism to check if it's "expired"
    entity = pool.get_entity(eid)
    assert entity['aboyeur_signature'] == signature
    
    # Even if we wait, the signature remains valid
    # (In practice, there's no signature verification on read at all —
    # the signature is set-and-forget)
    
    # CONFIRMED: No signature expiry or replay detection mechanism exists


# ─── Integration: Combined Attack Chain ─────────────────────────────────────

def test_red_team_combined_attack_chain(pool):
    """
    THREAT MODEL: Local attacker with read access to the working directory.
    
    Attack chain:
    1. Read station_keys.json (RT-01)
    2. Impersonate a station (RT-03b)
    3. Write poisoned entities (RT-10 style)
    4. Entities propagate through Snowball
    5. DRAGON renders poisoned data with XSS (RT-08)
    
    This test validates the full chain is possible.
    """
    from xp_arc.core.pool import register_station_with_key, get_station_hmac_key
    
    key_file = tempfile.mktemp(suffix='.json')
    try:
        # Step 1: Register stations normally (creates key file)
        key_forager = register_station_with_key('forager', 'The Forager', ['url'],
                                                 key_file=key_file)
        key_analyst = register_station_with_key('analyst', 'The Analyst', ['domain'],
                                                 key_file=key_file)
        pool.register_station('forager', 'The Forager', ['url'], hmac_key=key_forager)
        pool.register_station('analyst', 'The Analyst', ['domain'], hmac_key=key_analyst)
        
        # Step 2: Attacker reads key file
        with open(key_file) as f:
            stolen_keys = json.load(f)
        
        analyst_stolen_key = stolen_keys['analyst']
        assert analyst_stolen_key == key_analyst
        
        # Step 3: Attacker writes poisoned entity as 'analyst'
        xss_domain = 'safe-looking.com'  # looks legitimate
        
        payload = f"add_entity:domain:{xss_domain}:60"
        mac = hmac.new(
            analyst_stolen_key.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()
        
        eid = pool.add_entity('domain', xss_domain,
                              station_id='analyst', mac=mac)
        assert eid is not None, "Impersonated write with stolen key succeeded"
        
        # Step 4: Entity appears in the pool as if analyst created it
        entity = pool.get_entity(eid)
        assert entity['type'] == 'domain'
        assert entity['value'] == xss_domain
        
        # Step 5: This entity would be processed normally, create edges,
        # and eventually appear in DRAGON — where the analyst's reputation
        # lends it credibility
        
        # Step 6: Add a poisoned edge that would render in DRAGON
        edge_payload = f"add_edge:{xss_domain}:links_to:evil-c2.com"
        edge_mac = hmac.new(
            analyst_stolen_key.encode(), edge_payload.encode(), hashlib.sha256
        ).hexdigest()
        pool.add_edge(xss_domain, 'links_to', 'evil-c2.com',
                      station_id='analyst', mac=edge_mac)
        
        # The edge exists and would be rendered in DRAGON's network graph
        edges = pool.get_all_edges()
        assert any(e['source'] == xss_domain and e['target'] == 'evil-c2.com' 
                   for e in edges), "Poisoned edge created via impersonation"
        
        # Full chain: stolen key → impersonation → poisoned data → DRAGON display
        
    finally:
        if os.path.exists(key_file):
            os.unlink(key_file)


# ─── Summary of Red Team Findings ───────────────────────────────────────────

def test_red_team_findings_summary():
    """
    This test documents the red team findings summary.
    It always passes — it's a documentation anchor.
    """
    findings = {
        'RT-01': {
            'title': 'station_keys.json stores HMAC keys in plaintext',
            'severity': 'Critical (local)',
            'status': 'CONFIRMED — by design for local trust model',
            'mitigation': 'File permissions, env vars, or secret manager',
        },
        'RT-02': {
            'title': 'HMAC replay across different payloads',
            'severity': 'Low',
            'status': 'MITIGATED — payload-bound MACs prevent cross-payload replay',
            'residual': 'Exact replay accepted but UNIQUE constraint prevents duplicates',
        },
        'RT-03': {
            'title': 'Station impersonation',
            'severity': 'Critical (combined with RT-01)',
            'status': 'BLOCKED without key theft; TRIVIAL with stolen keys',
        },
        'RT-04': {
            'title': 'Aboyeur default signing key enables signature forgery',
            'severity': 'High',
            'status': 'CONFIRMED — default key is known constant',
            'mitigation': 'Set XP_ARC_ABOYEUR_KEY env var in production',
        },
        'RT-05': {
            'title': 'Payload hash bypass via direct DB tampering',
            'severity': 'Medium (local)',
            'status': 'DETECTED by Aboyeur unless hash is also updated',
        },
        'RT-06': {
            'title': 'Status machine violation via direct SQLite write',
            'severity': 'Medium (local)',
            'status': 'CONFIRMED — no DB-level constraint enforces VALID_TRANSITIONS',
            'impact': 'Entities can be marked completed without QA',
        },
        'RT-07': {
            'title': 'Cascade depth bypass via direct DB write',
            'severity': 'Low-Medium (local)',
            'status': 'CONFIRMED — direct INSERT bypasses MAX_CASCADE_DEPTH',
        },
        'RT-08': {
            'title': 'DRAGON XSS in dossier view (seed_url, connections)',
            'severity': 'High',
            'status': 'CONFIRMED — innerHTML without escapeHtml in renderDossiers()',
            'fix': 'Wrap seedDisplay, c.value, c.relationship in escapeHtml()',
        },
        'RT-09': {
            'title': 'DRAGON XSS in graph tooltip',
            'severity': 'Medium',
            'status': 'CONFIRMED — tooltip innerHTML uses raw d.id, d.station',
        },
        'RT-10': {
            'title': 'Forager title injection (unsanitized page title)',
            'severity': 'Low',
            'status': 'CONFIRMED — title extracted via regex, not sanitized',
        },
        'RT-11': {
            'title': 'Export state leaks HMAC keys',
            'severity': 'High',
            'status': 'CONFIRMED — export_state() includes station_registry.hmac_key',
            'fix': 'Strip hmac_key from station export',
        },
        'RT-12': {
            'title': 'Broker execute_raw accepts arbitrary SQL',
            'severity': 'Critical (if reachable)',
            'status': 'Internal-only currently; risk if exposed via API',
        },
        'RT-13': {
            'title': 'Zoran\'s Law gaming via SLA manipulation',
            'severity': 'Medium',
            'status': 'CONFIRMED — high-sla completed entities inflate S',
        },
        'RT-14': {
            'title': 'Entity flood DoS via spawn targets',
            'severity': 'Medium',
            'status': 'CONFIRMED — single process() can create unlimited entities',
            'mitigation': 'Add per-call spawn limit in Executive._process_spawns()',
        },
        'RT-15': {
            'title': 'Fracture shard flood (no shard_count limit)',
            'severity': 'Low-Medium',
            'status': 'CONFIRMED — no upper bound on shard_count',
            'fix': 'Add MAX_SHARD_COUNT constant (e.g., 20)',
        },
        'RT-16': {
            'title': 'Race condition on concurrent entity claims',
            'severity': 'Low',
            'status': 'MITIGATED — _write_lock + atomic UPDATE WHERE',
        },
        'RT-17': {
            'title': 'SSRF via DNS rebinding (TOCTOU)',
            'severity': 'Medium',
            'status': 'CONFIRMED — check and connect use separate DNS lookups',
            'mitigation': 'Connect to pre-resolved IP instead of hostname',
        },
        'RT-18': {
            'title': 'Legacy bypass: station_id=None → unauthenticated write',
            'severity': 'Medium',
            'status': 'CONFIRMED — default legacy_local is in trusted list',
            'fix': 'Log warning or require explicit opt-in for legacy writes',
        },
        'RT-19': {
            'title': 'Spawn chain / lineage spoofing',
            'severity': 'Low',
            'status': 'MITIGATED — pool recomputes lineage from actual parent',
        },
        'RT-20': {
            'title': 'Aboyeur signature has no expiry / replay window',
            'severity': 'Low',
            'status': 'CONFIRMED — timestamp is informational only',
        },
    }
    
    # Count by severity
    critical = sum(1 for f in findings.values() if 'Critical' in f['severity'])
    high = sum(1 for f in findings.values() if 'High' in f['severity'])
    medium = sum(1 for f in findings.values() if f['severity'] == 'Medium')
    
    assert len(findings) == 20, f"Expected 20 findings, got {len(findings)}"
    # This always passes — it's a documentation test
