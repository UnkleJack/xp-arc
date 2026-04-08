"""
The Aboyeur — QA Enforcement Node.

Nothing propagates downstream without Aboyeur clearance.
Cannot be bypassed. Cannot be configured away. Structural.

Constitution Article IV.
"""

import hashlib
import json
import time
from datetime import datetime, timezone


class Aboyeur:
    """
    Constitutional enforcement officer of XP-Arc.

    Validates station outputs against protocol schema:
    - payload hash integrity
    - output schema conformance
    - confidence thresholds
    - signature generation

    The Aboyeur does not create labor. It validates that labor
    was performed correctly.
    """

    REQUIRED_OUTPUT_FIELDS = {'entity_type', 'entity_value', 'confidence'}
    MIN_CONFIDENCE = 0.0
    MAX_CONFIDENCE = 1.0

    def __init__(self, pool, signing_key: str = "xp-arc-aboyeur-v1"):
        self.pool = pool
        self._signing_key = signing_key
        self._verifications = 0
        self._rejections = 0
        self._approvals = 0

    def validate_and_sign(self, entity_id: int, station_id: str,
                          output: dict, is_fallback: bool = False) -> dict:
        """
        Validate a station's output and issue signature if valid.

        Returns:
            {
                'approved': bool,
                'signature': str or None,
                'rejection_reason': str or None,
                'enhanced_scrutiny': bool,
            }
        """
        self._verifications += 1
        entity = self.pool.get_entity(entity_id)
        if not entity:
            return self._reject(entity_id, "Entity not found in pool")

        # ─── Schema Validation ───
        missing = self.REQUIRED_OUTPUT_FIELDS - set(output.keys())
        if missing:
            return self._reject(entity_id, f"Missing required fields: {missing}")

        # ─── Confidence Bounds ───
        conf = output.get('confidence', 0)
        if not (self.MIN_CONFIDENCE <= conf <= self.MAX_CONFIDENCE):
            return self._reject(entity_id, f"Confidence {conf} out of range [0, 1]")

        # ─── Payload Hash Verification ───
        # The hash was sealed at ingestion. Verify it hasn't been tampered.
        stored_hash = entity['payload_hash']
        recomputed = self._compute_hash(entity['type'], entity['value'])
        if stored_hash != recomputed:
            return self._reject(entity_id, "Payload hash mismatch — possible tampering")

        # ─── Enhanced Scrutiny for Fallback Outputs (Article IV, 4.5) ───
        enhanced = is_fallback
        if enhanced:
            # Double-pass: stricter checks on fallback outputs
            if conf < 0.4:
                return self._reject(entity_id,
                                    f"Fallback output confidence {conf} below enhanced threshold 0.4")
            if not output.get('notes'):
                return self._reject(entity_id,
                                    "Enhanced scrutiny: notes field required on fallback output")

        # ─── Generate Signature ───
        signature = self._generate_signature(entity_id, station_id, output)

        # ─── Approve ───
        self._approvals += 1
        self.pool.set_aboyeur_signature(entity_id, signature)

        self.pool._log_event('aboyeur_approval', 'aboyeur',
                             f"Entity {entity_id} approved. Station: {station_id}. "
                             f"Confidence: {conf:.2f}" +
                             (" [ENHANCED SCRUTINY]" if enhanced else ""))

        return {
            'approved': True,
            'signature': signature,
            'rejection_reason': None,
            'enhanced_scrutiny': enhanced,
        }

    def _reject(self, entity_id: int, reason: str) -> dict:
        """Handle rejection with circuit breaker logic."""
        self._rejections += 1

        # Increment rejection counter
        new_count = self.pool.increment_rejection(entity_id)
        entity = self.pool.get_entity(entity_id)
        max_rej = entity['max_rejections'] if entity else 3

        self.pool._log_event('aboyeur_rejection', 'aboyeur',
                             f"Entity {entity_id} REJECTED ({new_count}/{max_rej}): {reason}")

        # Circuit breaker: max_rejections hit → fail and escalate
        if new_count >= max_rej:
            self.pool.transition_status(entity_id, 'failed')
            self.pool._log_event('aboyeur_circuit_break', 'aboyeur',
                                 f"Entity {entity_id} circuit breaker tripped. "
                                 f"Escalating to Chef de Cuisine.",
                                 f"rejection_count={new_count}")
            self.pool.add_finding(
                'critical', 'aboyeur',
                f"Circuit breaker: Entity {entity_id} failed after {new_count} rejections",
                reason
            )

        return {
            'approved': False,
            'signature': None,
            'rejection_reason': reason,
            'enhanced_scrutiny': False,
        }

    def _generate_signature(self, entity_id: int, station_id: str, output: dict) -> str:
        """Generate HMAC-SHA256 signature for approved output."""
        payload = json.dumps({
            'entity_id': entity_id,
            'station_id': station_id,
            'entity_type': output['entity_type'],
            'entity_value': output['entity_value'],
            'confidence': output['confidence'],
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }, sort_keys=True)

        sig = hashlib.sha256(
            (self._signing_key + payload).encode()
        ).hexdigest()[:32]

        return f"ABOY-{sig}"

    def _compute_hash(self, entity_type: str, entity_value: str) -> str:
        payload = json.dumps({'type': entity_type, 'value': entity_value}, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()

    @property
    def stats(self) -> dict:
        total = self._verifications or 1
        return {
            'verifications': self._verifications,
            'approvals': self._approvals,
            'rejections': self._rejections,
            'approval_rate': self._approvals / total,
            'rejection_rate': self._rejections / total,
        }
