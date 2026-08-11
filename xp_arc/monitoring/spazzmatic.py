"""
SpaZzMatiC — Adversarial Review Authority.

STATUS: Active (Rule-based + Gemini-backed LLM authority - optional).
Note: The base implementation is rule-based and deterministic.
The optional Gemini-backed LLM authority provides cold-eyes QA with no 
architectural bias toward XP-Arc (Constitution §14.3).

IMPORTANT: The legacy `google.generativeai` package is deprecated and only supports 
older models (gemini-1.x, gemini-pro). Modern API keys typically only grant access
to newer models (gemini-2.x, 3.x) which require the new `google-genai` package.
To enable LLM review: either use an API key with legacy model access, or migrate
to `google-genai` (not yet implemented).

SpaZzMatiC does not build. SpaZzMatiC breaks.

Constitution Article XIV.
"""

import os
import json
import logging
from typing import Optional

# Optional Gemini integration (legacy package - deprecated)
try:
    import google.generativeai as genai
    _GEMINI_AVAILABLE = True
except ImportError:
    _GEMINI_AVAILABLE = False

logger = logging.getLogger("xp_arc.spazzmatic")


class SpaZzMatiC:
    """Independent adversarial review engine.

    Monitors:
    - Zoran's Law violations
    - Aboyeur rejection rate anomalies
    - Orphaned entities (stuck in processing)
    - Status transition violations (from event log)
    - Entity flood / Snowball runaway
    - Safe halt conditions

    Issues findings with severity classifications.
    Can recommend safe halt (60-second veto countdown) and
    trigger Brigade Compression when PRO < 70% or S < 0.5.
    
    Includes optional Gemini-backed adversarial review per Constitution §14.3.
    """

    # Constitutional thresholds
    SAFE_HALT_S_THRESHOLD = 0.5           # S < 0.5 sustained
    SAFE_HALT_SUSTAIN_COUNT = 2           # Must be violated for 2+ measurements
    ABOYEUR_REJECTION_ALARM = 0.10        # >10% rejection rate
    ROUTING_FAILURE_ALARM = 0.05          # >5% routing failures
    ENTITY_FLOOD_THRESHOLD = 450
    ORPHAN_ALARM_COUNT = 3                # 3+ orphans = concern

    def __init__(self, pool, zorans_law):
        self.pool = pool
        self.zorans_law = zorans_law
        self._reviews = 0
        self._safe_halt_recommended = False
        self._s_violation_streak = 0
        self._executive = None  # Set via set_executive() if available

    def set_executive(self, executive):
        """Inject the ExecutiveChef for automatic Brigade Compression."""
        self._executive = executive

    def run_review(self) -> dict:
        """Execute full adversarial review pass.

        Returns:
        {
            'findings': list of findings,
            'safe_halt_recommended': bool,
            'summary': str,
        }
        """
        self._reviews += 1
        findings = []

        findings.extend(self._review_zorans_law())
        findings.extend(self._review_aboyeur_health())
        findings.extend(self._review_pool_integrity())
        findings.extend(self._review_entity_flood())
        findings.extend(self._review_orphans())
        findings.extend(self._review_gemini_adversarial())

        # Write findings to pool
        for f in findings:
            self.pool.add_finding(f['severity'], 'spazzmatic', f['message'], f.get('detail'))

        # Log the review
        self.pool._log_event('spazzmatic_review', 'spazzmatic',
                             f"Review #{self._reviews}: {len(findings)} findings. "
                             f"Safe halt: {self._safe_halt_recommended}")

        severity_counts = {}
        for f in findings:
            severity_counts[f['severity']] = severity_counts.get(f['severity'], 0) + 1

        summary_parts = [f"Review #{self._reviews}"]
        if not findings:
            summary_parts.append("No anomalies detected.")
        else:
            for sev, cnt in sorted(severity_counts.items()):
                summary_parts.append(f"{cnt} {sev}")

        return {
            'findings': findings,
            'safe_halt_recommended': self._safe_halt_recommended,
            'summary': ". ".join(summary_parts),
        }

    def _review_zorans_law(self) -> list:
        """Check Zoran's Law compliance."""
        findings = []
        measurement = self.zorans_law.get_latest()
        if not measurement:
            return findings

        s = measurement['stability_quotient']
        pro = measurement['primary_role_occupancy']

        # Check streak from measurement HISTORY (last 5 measurements)
        # This handles the case where multiple bad measurements are inserted before review runs
        # We initialize from DB history ONLY on the very first review
        if self._reviews == 1 and self._s_violation_streak == 0:
            rows = self.pool.conn.execute("""
                SELECT stability_quotient FROM zorans_metrics 
                ORDER BY id DESC LIMIT 5
            """).fetchall()
            recent_s_values = [r['stability_quotient'] for r in rows]
            
            # Count consecutive S < 0.5 from most recent backwards
            s_violation_streak = 0
            for val in recent_s_values:
                if val < self.SAFE_HALT_S_THRESHOLD:
                    s_violation_streak += 1
                else:
                    break
            if s_violation_streak > 0:
                self._s_violation_streak = s_violation_streak

        # S < 0.5 sustained = safe halt candidate + compression
        if s < self.SAFE_HALT_S_THRESHOLD:
            self._s_violation_streak += 1
            if self._s_violation_streak >= self.SAFE_HALT_SUSTAIN_COUNT:
                self._safe_halt_recommended = True
                # Auto-compress brigade on sustained distress
                if self._executive and not self._executive.is_compressed():
                    self._executive.compress_brigade()
                    self.pool._log_event('spazzmatic_compression', 'spazzmatic',
                                         f"Auto-compressed brigade: S={s:.3f} sustained < 0.5 for "
                                         f"{self._s_violation_streak} measurements")
                findings.append({
                    'severity': 'critical',
                    'message': f"SAFE HALT RECOMMENDED: S={s:.3f} sustained below "
                               f"{self.SAFE_HALT_S_THRESHOLD} for "
                               f"{self._s_violation_streak} measurements",
                    'detail': "Brigade compressed to critical stations. 60-second veto window active.",
                })
            else:
                findings.append({
                    'severity': 'warning',
                    'message': f"S={s:.3f} below distress threshold. "
                               f"Streak: {self._s_violation_streak}/{self.SAFE_HALT_SUSTAIN_COUNT}",
                })
        else:
            self._s_violation_streak = 0
            self._safe_halt_recommended = False

        # S < 1.0 = debt accumulating
        if 0.5 <= s < 1.0:
            findings.append({
                'severity': 'warning',
                'message': f"Cognitive debt accumulating: S={s:.3f}",
                'detail': "System correction rate not keeping pace with ingestion.",
            })

        # PRO check — compression recommended
        if pro < 0.70:
            # Auto-compress brigade on low primary role occupancy
            if self._executive and not self._executive.is_compressed():
                self._executive.compress_brigade()
                self.pool._log_event('spazzmatic_compression', 'spazzmatic',
                                     f"Auto-compressed brigade: PRO={pro:.1%} < 70% threshold. "
                                     f"Active={measurement['active_stations']}, "
                                     f"Primary={measurement['primary_stations']}")
            findings.append({
                'severity': 'warning',
                'message': f"PRO={pro:.1%} below 70% threshold. Compression triggered.",
                'detail': f"Active: {measurement['active_stations']}, "
                          f"Primary: {measurement['primary_stations']}",
            })

        return findings

    def _review_aboyeur_health(self) -> list:
        """Check Aboyeur rejection rates."""
        findings = []

        # Get recent events to calculate rejection rate
        events = self.pool.get_events(100)
        rejections = sum(1 for e in events if e['event_type'] == 'aboyeur_rejection')
        approvals = sum(1 for e in events if e['event_type'] == 'aboyeur_approval')

        total = rejections + approvals
        if total > 0:
            rejection_rate = rejections / total
            if rejection_rate > self.ABOYEUR_REJECTION_ALARM:
                findings.append({
                    'severity': 'warning',
                    'message': f"Aboyeur rejection rate: {rejection_rate:.1%} "
                               f"(threshold: {self.ABOYEUR_REJECTION_ALARM:.0%})",
                    'detail': f"{rejections} rejections / {total} total verifications",
                })

        # Check for circuit breaker events
        circuit_breaks = sum(1 for e in events if e['event_type'] == 'aboyeur_circuit_break')
        if circuit_breaks > 0:
            findings.append({
                'severity': 'critical',
                'message': f"{circuit_breaks} Aboyeur circuit breaker(s) tripped",
                'detail': "Tasks have hit max_rejections. Chef de Cuisine escalation required.",
            })

        return findings

    def _review_pool_integrity(self) -> list:
        """Check for status transition violations in event log."""
        findings = []

        events = self.pool.get_events(200)
        violations = [e for e in events if e['event_type'] == 'status_violation']

        if violations:
            findings.append({
                'severity': 'critical',
                'message': f"{len(violations)} unauthorized status transitions detected",
                'detail': "; ".join(v['message'] for v in violations[:5]),
            })

        return findings

    def _review_entity_flood(self) -> list:
        """Check for Snowball runaway."""
        findings = []
        count = self.pool.count_entities()

        if count > self.ENTITY_FLOOD_THRESHOLD:
            findings.append({
                'severity': 'warning',
                'message': f"Entity count: {count} approaching system limit",
                'detail': "Snowball may be generating excessive entities.",
            })

        return findings

    def _review_orphans(self) -> list:
        """Check for orphaned entities."""
        findings = []
        orphans = self.pool.get_orphaned_entities()

        if len(orphans) >= self.ORPHAN_ALARM_COUNT:
            findings.append({
                'severity': 'warning',
                'message': f"{len(orphans)} orphaned entities detected",
                'detail': "Entities stuck in processing. Plongeur sweep recommended.",
            })

        return findings

    def _review_gemini_adversarial(self) -> list:
        """Gemini-backed adversarial review for deep structural analysis.
        
        Per Constitution §14.3: SpaZzMatiC operates on an independent LLM backbone 
        (Gemini API) to eliminate architectural bias. This is the cold-eyes QA
        that catches what rule-based reviews miss.
        """
        findings = []
        
        if not _GEMINI_AVAILABLE:
            logger.debug("Gemini not available, skipping LLM adversarial review")
            return findings
            
        api_key = os.environ.get("XP_ARC_GEMINI_API_KEY")
        if not api_key:
            logger.debug("XP_ARC_GEMINI_API_KEY not set, skipping LLM adversarial review")
            return findings
            
        try:
            # Configure Gemini
            genai.configure(api_key=api_key)
            # Try to find a compatible model - legacy package only supports older models
            # but the API key may only have access to newer models (gemini-2.x, 3.x)
            model = None
            for model_name in ['gemini-1.5-pro', 'gemini-pro', 'gemini-1.5-flash', 'gemini-1.0-pro']:
                try:
                    model = genai.GenerativeModel(model_name)
                    logger.debug(f"Using Gemini model: {model_name}")
                    break
                except Exception as e:
                    logger.debug(f"Model {model_name} not available: {e}")
                    continue
            if model is None:
                raise RuntimeError(
                    "No compatible Gemini model found. "
                    "The legacy 'google.generativeai' package only supports older models "
                    "(gemini-1.x, gemini-pro). Your API key appears to only have access "
                    "to newer models (gemini-2.x, 3.x) which require the new 'google.genai' package. "
                    "Either: (1) Use an API key with access to legacy models, or "
                    "(2) Install 'google-genai' and migrate the integration."
                )
            
            # Gather context for the review
            measurement = self.zorans_law.get_latest()
            stats = self.pool.get_stats()
            entities = self.pool.get_all_entities()
            edges = self.pool.get_all_edges()
            events = self.pool.get_events(50)
            stations = self.pool.get_active_stations()
            
            # Build context prompt
            context = self._build_gemini_context(measurement, stats, entities, edges, events, stations)
            
            prompt = f"""You are SpaZzMatiC, the Adversarial Review Authority for XP-Arc multi-agent orchestration system.

CONSTITUTIONAL MANDATE: You do not build. You break. You have no architectural bias toward XP-Arc. 
Your job is cold-eyes QA: identify weaknesses, single points of failure, degradation vectors, 
and non-compliance that rule-based checks miss.

CURRENT SYSTEM STATE:
{context}

ANALYSIS REQUIRED:
1. Are there structural weaknesses in the brigade configuration?
2. Is the Snowball cascade properly bounded or showing runaway signs?
3. Are station role assignments correct or are there domain breaches?
4. Is Zoran's Law calculation being gamed via SLA manipulation?
5. Are there silent data loss patterns (entities dropped, edges orphaned)?
6. Is the Aboyeur QA gate actually catching errors or just rubber-stamping?
7. Are there constitutional violations the rule-based checks missed?

Respond with a JSON array of findings, each with:
- severity: "critical" | "warning" | "info"
- category: "structural" | "constitutional" | "operational" | "security"
- message: concise finding description
- detail: expanded analysis
- recommendation: concrete remediation step

If no significant findings, return empty array [].

JSON ONLY - no markdown, no explanation."""

            response = model.generate_content(prompt)
            
            # Parse response
            try:
                response_text = response.text.strip()
                # Extract JSON from potential markdown code blocks
                if '```json' in response_text:
                    response_text = response_text.split('```json')[1].split('```')[0]
                elif '```' in response_text:
                    response_text = response_text.split('```')[1].split('```')[0]
                    
                gemini_findings = json.loads(response_text)
                
                for gf in gemini_findings:
                    findings.append({
                        'severity': gf.get('severity', 'warning'),
                        'message': f"[GEMINI] {gf.get('message', 'Adversarial finding')}",
                        'detail': f"{gf.get('detail', '')} | Recommendation: {gf.get('recommendation', 'N/A')}",
                    })
                    
                logger.info(f"Gemini adversarial review found {len(findings)} findings")
                
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse Gemini response as JSON: {e}")
                # Fallback: add raw response as info finding
                findings.append({
                    'severity': 'info',
                    'message': 'Gemini adversarial review completed (raw response logged)',
                    'detail': f"Response parsing failed: {e}. Raw response logged.",
                })
                
        except Exception as e:
            logger.error(f"Gemini adversarial review failed: {e}")
            # Don't fail the whole review - rule-based findings still stand
            
        return findings

    def _build_gemini_context(self, measurement, stats, entities, edges, events, stations) -> str:
        """Build structured context for Gemini review."""
        if not measurement:
            measurement = {}
            
        # Helper to convert sqlite3.Row to dict
        def row_to_dict(row):
            if hasattr(row, 'keys'):
                return dict(row)
            return row
            
        context = {
            'zorans_law': {
                'stability_quotient': measurement.get('stability_quotient', 'N/A'),
                'primary_role_occupancy': measurement.get('primary_role_occupancy', 'N/A'),
                'system_state': measurement.get('system_state', 'N/A'),
            },
            'pool_stats': {k: dict(v) if hasattr(v, 'keys') else str(v) for k, v in stats.items()},
            'entity_count': len(entities),
            'edge_count': len(edges),
            'station_count': len(stations),
            'stations': [
                {
                    'id': s.get('station_id', 'unknown') if hasattr(s, 'get') else s['station_id'],
                    'name': s.get('name', 'unknown') if hasattr(s, 'get') else s['name'],
                    'handles_types': s.get('handles_types', []) if hasattr(s, 'get') else s['handles_types'],
                    'is_primary': s.get('is_primary', 1) if hasattr(s, 'get') else s['is_primary'],
                }
                for s in stations
            ],
            'recent_events': [
                {
                    'type': e.get('event_type', 'unknown') if hasattr(e, 'get') else e['event_type'],
                    'source': e.get('source', 'unknown') if hasattr(e, 'get') else e['source'],
                    'message': e.get('message', '')[:200] if hasattr(e, 'get') else e['message'][:200],
                }
                for e in events[:10]
            ],
        }
        return json.dumps(context, indent=2)

    def format_report(self) -> str:
        """Human-readable adversarial review report."""
        result = self.run_review()
        lines = [
            "╔══════════════════════════════════════════════╗",
            "║   SpaZzMatiC — ADVERSARIAL REVIEW REPORT    ║",
            "╠══════════════════════════════════════════════╣",
        ]

        if result['safe_halt_recommended']:
            lines.append("║  ⚠ SAFE HALT RECOMMENDED                    ║")
            lines.append("║  60-second veto window active                ║")
            lines.append("╠══════════════════════════════════════════════╣")

        if not result['findings']:
            lines.append("║  No anomalies detected. System nominal.      ║")
        else:
            for f in result['findings']:
                sev = f['severity'].upper()
                msg = f['message'][:42]
                lines.append(f"║  [{sev}] {msg:<40s} ║")

        lines.append("╚══════════════════════════════════════════════╝")
        return "\n".join(lines)