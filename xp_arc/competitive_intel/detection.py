"""
Detection engine for Competitive Intelligence Station.
Runs detection rules against fetched events to identify conflicts, gaps, and intelligence.
"""

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


class DetectionEngine:
    """Run detection rules against competitive intelligence events."""

    def __init__(self, station):
        self.station = station
        self.config = station.config
        self.watchlist = station.config.get("watchlist", {})
        self.rules = self._load_rules()

    def _load_rules(self) -> Dict[str, Any]:
        """Load detection rules from config."""
        # Use the detection_rules from the main station config
        return self.config.get("detection_rules", self._default_rules())

    def _default_rules(self) -> Dict[str, Any]:
        """Default detection rules if not in config."""
        return {
            "conflict_signals": {
                "api_breaking_change": {
                    "description": "Competitor releases breaking API change",
                    "sources": ["github", "pypi", "npm"],
                    "event_types": ["release"],
                    "patterns": [
                        r"breaking\s+change",
                        r"major\s+version",
                        r"v\d+\.0\.0",
                        r"migration\s+guide",
                        r"deprecated",
                        r"removed",
                    ],
                    "severity": "high",
                },
                "feature_parity": {
                    "description": "Competitor launches feature XP-Arc lacks",
                    "sources": ["github", "website", "hackernews", "reddit"],
                    "event_types": ["release", "blog_post", "story", "post"],
                    "patterns": [
                        r"new\s+feature",
                        r"introducing",
                        r"launch",
                        r"now\s+support",
                        r"added\s+support",
                    ],
                    "severity": "medium",
                },
                "pricing_model_shift": {
                    "description": "Competitor changes pricing model",
                    "sources": ["website", "blog_post", "linkedin"],
                    "event_types": ["blog_post", "announcement"],
                    "patterns": [
                        r"pricing",
                        r"plan",
                        r"tier",
                        r"subscription",
                        r"free\s+tier",
                        r"enterprise",
                        r"usage-based",
                    ],
                    "severity": "high",
                },
                "shutdown_sunset": {
                    "description": "Competitor announces shutdown or sunset",
                    "sources": ["website", "blog_post", "github"],
                    "event_types": ["blog_post", "announcement", "issue"],
                    "patterns": [
                        r"shutdown",
                        r"sunset",
                        r"deprecated",
                        r"end\s+of\s+life",
                        r"discontinu",
                        r"acquired",
                    ],
                    "severity": "critical",
                },
            },
            "gap_signals": {
                "missing_integration": {
                    "description": "Users request integration competitor lacks",
                    "sources": ["github", "reddit", "hackernews"],
                    "event_types": ["issue", "discussion", "post", "comment"],
                    "patterns": [
                        r"integrat",
                        r"support\s+for",
                        r"add\s+support",
                        r"plugin",
                        r"connector",
                        r"not\s+supported",
                        r"missing",
                        r"request",
                    ],
                    "severity": "medium",
                },
                "performance_complaint": {
                    "description": "Users complain about competitor performance",
                    "sources": ["github", "reddit", "hackernews"],
                    "event_types": ["issue", "discussion", "post", "comment"],
                    "patterns": [
                        r"slow",
                        r"latency",
                        r"performance",
                        r"memory",
                        r"cpu",
                        r"expensive",
                        r"cost",
                        r"scale",
                        r"timeout",
                    ],
                    "severity": "medium",
                },
                "dx_friction": {
                    "description": "Developer experience complaints",
                    "sources": ["github", "reddit", "hackernews"],
                    "event_types": ["issue", "discussion", "post", "comment"],
                    "patterns": [
                        r"documentation",
                        r"docs",
                        r"tutorial",
                        r"example",
                        r"getting\s+started",
                        r"typescript",
                        r"type\s+hint",
                        r"debug",
                        r"error\s+message",
                    ],
                    "severity": "low",
                },
                "vendor_lockin": {
                    "description": "Users concerned about vendor lock-in",
                    "sources": ["github", "reddit", "hackernews"],
                    "event_types": ["issue", "discussion", "post", "comment"],
                    "patterns": [
                        r"lock.?in",
                        r"vendor",
                        r"portab",
                        r"self.host",
                        r"on.premise",
                        r"data\s+ownership",
                        r"export",
                        r"migrat",
                    ],
                    "severity": "high",
                },
            },
        }

    async def process_events(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Process events through detection rules and emit signals."""
        signals = []

        for event in events:
            event_signals = self._analyze_event(event)
            signals.extend(event_signals)

        # Deduplicate signals
        signals = self._deduplicate_signals(signals)

        # Store signals in database
        for signal in signals:
            self.station.emit_event(signal)

        return signals

    def _analyze_event(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Analyze a single event against all detection rules."""
        signals = []
        competitor = event.get("competitor", "")
        source = event.get("source", "")
        event_type = event.get("source_type", "")
        title = event.get("title", "")
        summary = event.get("summary", "")
        text = f"{title} {summary}".lower()

        # Check conflict signals
        for signal_id, rule in self.rules.get("conflict_signals", {}).items():
            if self._matches_rule(event, rule, text):
                signals.append(self._create_signal(event, "conflict", signal_id, rule))

        # Check gap signals
        for signal_id, rule in self.rules.get("gap_signals", {}).items():
            if self._matches_rule(event, rule, text):
                signals.append(self._create_signal(event, "gap", signal_id, rule))

        return signals

    def _matches_rule(self, event: Dict[str, Any], rule: Dict[str, Any], text: str) -> bool:
        """Check if event matches a detection rule."""
        # Check source filter
        sources = rule.get("sources", [])
        if sources and event.get("source") not in sources:
            return False

        # Check event type filter
        event_types = rule.get("event_types", [])
        if event_types and event.get("source_type") not in event_types:
            return False

        # Check patterns
        patterns = rule.get("patterns", [])
        if not patterns:
            return False

        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True

        return False

    def _create_signal(self, event: Dict[str, Any], category: str, signal_id: str, rule: Dict[str, Any]) -> Dict[str, Any]:
        """Create a detection signal from a matching event."""
        import uuid

        return {
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            "source": event.get("source"),
            "competitor": event.get("competitor"),
            "category": category,
            "signal_type": signal_id,
            "severity": rule.get("severity", "medium"),
            "title": f"{rule.get('description', signal_id)}: {event.get('title', '')[:80]}",
            "summary": event.get("summary", "")[:300],
            "url": event.get("url", ""),
            "raw_payload": {
                "original_event": event.get("raw_payload", {}),
                "matched_rule": signal_id,
                "matched_patterns": [
                    p for p in rule.get("patterns", []) if re.search(p, f"{event.get('title', '')} {event.get('summary', '')}", re.IGNORECASE)
                ],
            },
            "tags": [category, signal_id, event.get("competitor", "")],
        }

    def _deduplicate_signals(self, signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Deduplicate signals by competitor + signal_type + time window."""
        deduped = {}
        for signal in signals:
            key = f"{signal['competitor']}:{signal['signal_type']}"
            if key not in deduped:
                deduped[key] = signal
        return list(deduped.values())


class GapAnalyzer:
    """Analyze accumulated signals to identify persistent gaps and opportunities."""

    def __init__(self, station):
        self.station = station
        self.db_path = station.db_path

    def get_connection(self):
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    async def identify_gaps(self, days: int = 30) -> List[Dict[str, Any]]:
        """Identify gaps from accumulated signals."""
        conn = self.get_connection()
        try:
            # Get gap signals from the last N days
            cursor = conn.execute(
                """
                SELECT * FROM events 
                WHERE category = 'gap' 
                AND timestamp >= datetime('now', ?)
                ORDER BY timestamp DESC
                """,
                (f"-{days} days",),
            )
            gap_events = [dict(row) for row in cursor.fetchall()]

            # Group by competitor and signal type
            gaps = {}
            for event in gap_events:
                raw = json.loads(event.get("raw_payload", "{}"))
                signal_type = raw.get("matched_rule", "unknown")
                competitor = event.get("competitor", "unknown")
                key = f"{competitor}:{signal_type}"

                if key not in gaps:
                    gaps[key] = {
                        "competitor": competitor,
                        "gap_type": signal_type,
                        "count": 0,
                        "first_seen": event["timestamp"],
                        "last_seen": event["timestamp"],
                        "evidence_urls": [],
                        "descriptions": [],
                    }
                gaps[key]["count"] += 1
                gaps[key]["evidence_urls"].append(event.get("url", ""))
                gaps[key]["descriptions"].append(event.get("summary", ""))

            # Convert to list and filter by frequency
            gap_list = []
            for key, gap in gaps.items():
                if gap["count"] >= 2:  # At least 2 occurrences
                    gap_list.append({
                        "competitor": gap["competitor"],
                        "gap_type": gap["gap_type"],
                        "description": f"Missing {gap['gap_type'].replace('_', ' ')} - {gap['count']} signals",
                        "evidence_urls": gap["evidence_urls"][:5],
                        "first_seen": gap["first_seen"],
                        "last_seen": gap["last_seen"],
                        "frequency": gap["count"],
                        "severity": self._calculate_severity(gap["count"]),
                        "status": "open",
                    })

            return sorted(gap_list, key=lambda x: x["frequency"], reverse=True)

        finally:
            conn.close()

    def _calculate_severity(self, count: int) -> str:
        if count >= 10:
            return "critical"
        elif count >= 5:
            return "high"
        elif count >= 3:
            return "medium"
        return "low"

    async def update_gap_database(self, gaps: List[Dict[str, Any]]):
        """Update the gaps database with new/updated gaps."""
        if not gaps:
            return

        conn = self.get_connection()
        try:
            for gap in gaps:
                # Check if gap already exists
                cursor = conn.execute(
                    "SELECT id, frequency FROM gaps WHERE competitor = ? AND gap_type = ? AND status != 'shipped'",
                    (gap["competitor"], gap["gap_type"]),
                )
                existing = cursor.fetchone()

                if existing:
                    # Update existing gap
                    conn.execute(
                        """
                        UPDATE gaps SET 
                            frequency = ?, last_seen = ?, severity = ?, 
                            evidence_urls = ?, updated_at = datetime('now')
                        WHERE id = ?
                        """,
                        (
                            gap["frequency"],
                            gap["last_seen"],
                            gap["severity"],
                            json.dumps(gap["evidence_urls"]),
                            existing["id"],
                        ),
                    )
                else:
                    # Insert new gap
                    conn.execute(
                        """
                        INSERT INTO gaps (competitor, gap_type, description, evidence_urls, 
                                         first_seen, last_seen, frequency, severity, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            gap["competitor"],
                            gap["gap_type"],
                            gap["description"],
                            json.dumps(gap["evidence_urls"]),
                            gap["first_seen"],
                            gap["last_seen"],
                            gap["frequency"],
                            gap["severity"],
                            gap["status"],
                        ),
                    )

            conn.commit()
            logger.info(f"Updated gap database with {len(gaps)} gaps")

        finally:
            conn.close()