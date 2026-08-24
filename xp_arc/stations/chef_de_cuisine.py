"""
The Chef de Cuisine — escalation station.

Every other station does labor. This one handles the cases where labor has
already failed and something has to decide what happens next. It is the
terminal authority in the brigade: when an entity can no longer make progress
on its own, the Executive publishes an 'escalation' entity and the Chef de
Cuisine records the ruling.

CONSTITUTION Article V (Cognitive Sharding) 5.5 — a fracture whose shards
cannot all complete must escalate rather than strand its parent.

The Chef is CRITICAL: it survives Brigade Compression. A degraded brigade is
exactly the condition under which escalations are most likely, so removing the
escalation handler during compression would be self-defeating.
"""

import json

from ..core.station import StationChef


class ChefDeCuisine(StationChef):
    """Handles escalations raised by the Executive when labor cannot proceed."""

    station_id = "chef_de_cuisine"
    name = "The Chef de Cuisine"
    handles_types = ["escalation"]
    sla_seconds = 300
    is_primary = True
    critical = True  # survives Brigade Compression

    # Escalation kinds this station knows how to rule on. An unknown kind is
    # still recorded — it is never silently dropped — but is marked for a human.
    KNOWN_KINDS = ("stranded_fracture",)

    def process(self, entity_id: int, entity_type: str, entity_value: str) -> dict:
        try:
            payload = json.loads(entity_value)
        except (json.JSONDecodeError, TypeError):
            payload = {"kind": "unparseable", "raw": str(entity_value)[:512]}

        kind = payload.get("kind", "unknown")

        if kind == "stranded_fracture":
            ruling, confidence = self._rule_stranded_fracture(payload)
        else:
            ruling = (f"Unrecognized escalation kind {kind!r}. Recorded for human "
                      f"review; the Chef de Cuisine does not invent a ruling for "
                      f"a case it does not understand.")
            confidence = 0.5
            self.pool.add_finding(
                "high", self.station_id,
                f"Unhandled escalation kind: {kind}", json.dumps(payload)[:1000],
            )

        self.log(ruling)

        # entity_type and entity_value are echoed back UNCHANGED. The Aboyeur
        # compares both against the sealed payload_hash and rejects any output
        # that rewrites them (Article IV), so a station records its conclusion in
        # notes, relationships and findings — never by mutating the entity it was
        # handed. Returning a synthesized "escalation_ruling" type here was
        # rejected three times by the retry driver and then failed, which is how
        # this was caught.
        return {
            "entity_type": entity_type,
            "entity_value": entity_value,
            "relationships": self._relationships(payload),
            "confidence": confidence,
            "notes": ruling,
        }

    def _rule_stranded_fracture(self, payload: dict):
        """Record the disposition of a fracture group that cannot complete."""
        parent_id = payload.get("parent_entity_id")
        fracture_id = payload.get("fracture_id")
        failed = payload.get("failed_shards", [])

        self.pool.add_finding(
            "critical", self.station_id,
            f"Fracture {fracture_id} abandoned: parent entity {parent_id} could "
            f"not be stitched",
            f"Shards {failed} exhausted their rejection budget. The parent has "
            f"been released from 'fractured' to 'failed' so it is no longer "
            f"stranded. The work itself is NOT complete — the original task must "
            f"be re-seeded, decomposed differently, or handled manually.",
        )

        return (
            f"Fracture {fracture_id} abandoned. {len(failed)} shard(s) exhausted "
            f"their rejection budget; parent entity {parent_id} released from "
            f"'fractured' and marked failed. Re-seed or re-decompose to retry.",
            1.0,
        )

    def _relationships(self, payload: dict) -> list:
        """Relationships are a list of plain STRINGS, not dicts.

        The Aboyeur validates each element with isinstance(rel, str) and rejects
        anything else outright — a dict of {target, relationship} is refused.
        """
        parent_id = payload.get("parent_entity_id")
        if parent_id is None:
            return []
        return [f"escalated_from:entity:{parent_id}"]
