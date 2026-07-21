"""
GRC Commis — Fallback / Read-Only Governance, Risk & Compliance Station.

Reads from CISO Assistant API only. Exports reports, generates gap analyses,
provides evidence for Aboyeur QA validation. No write operations.

API endpoints verified from /api/schema/ (OpenAPI spec).
"""

import json
import requests
from ..core.station import StationChef


class GRCCommis(StationChef):
    """Fallback GRC station — read-only from CISO Assistant."""

    station_id = "grc_commis"
    name = "GRC Commis"
    handles_types = [
        'risk',
        'control',
        'compliance_assessment',
        'audit_log',
        'policy',
        'evidence',
    ]
    sla_seconds = 60
    is_primary = False  # fallback only

    API_BASE = "https://localhost:8443/api"
    TOKEN = "46fa00f0ade973f81056797f1eca52513083bab2bc932bcf3481c779382e86f1"

    def __init__(self, pool):
        super().__init__(pool)
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Token {self.TOKEN}",
            "Accept": "application/json",
        })
        self.session.verify = False

    def _api(self, method: str, endpoint: str, **kwargs) -> dict:
        url = f"{self.API_BASE}{endpoint}"
        try:
            resp = self.session.request(method, url, timeout=30, **kwargs)
            resp.raise_for_status()
            return resp.json() if resp.content else {}
        except requests.exceptions.RequestException as e:
            self.log(f"API error {method} {endpoint}: {e}")
            raise

    # ─── Read Operations (verified endpoints) ────────────────────────

    def get_risk(self, ciso_id: str) -> dict:
        return self._api("GET", f"/risk-scenarios/{ciso_id}/")

    def list_risks(self, params: dict = None) -> list:
        data = self._api("GET", "/risk-scenarios/", params=params)
        return data.get("results", data)

    def get_control(self, ciso_id: str) -> dict:
        return self._api("GET", f"/applied-controls/{ciso_id}/")

    def list_controls(self, params: dict = None) -> list:
        data = self._api("GET", "/applied-controls/", params=params)
        return data.get("results", data)

    def get_assessment(self, ciso_id: str) -> dict:
        return self._api("GET", f"/compliance-assessments/{ciso_id}/")

    def list_assessments(self, params: dict = None) -> list:
        data = self._api("GET", "/compliance-assessments/", params=params)
        return data.get("results", data)

    def get_audit_log(self, ciso_id: str) -> dict:
        return self._api("GET", f"/incidents/{ciso_id}/")

    def list_audit_logs(self, params: dict = None) -> list:
        data = self._api("GET", "/incidents/", params=params)
        return data.get("results", data)

    def get_policy(self, ciso_id: str) -> dict:
        return self._api("GET", f"/reference-controls/{ciso_id}/")

    def list_policies(self, params: dict = None) -> list:
        data = self._api("GET", "/reference-controls/", params=params)
        return data.get("results", data)

    def get_evidence(self, ciso_id: str) -> dict:
        return self._api("GET", f"/evidences/{ciso_id}/")

    def list_evidence(self, params: dict = None) -> list:
        data = self._api("GET", "/evidences/", params=params)
        return data.get("results", data)

    # ─── Export / Report Generation ────────────────────────────────────

    def export_risk_register(self, format: str = "json") -> dict:
        """Export all risks as risk register."""
        risks = self.list_risks({"page_size": 1000})
        if format == "json":
            return {"risks": risks, "count": len(risks), "exported_by": self.station_id}
        return {"error": "Unsupported format"}

    def export_compliance_gap_report(self, framework: str = "iso27001-2022") -> dict:
        """Generate compliance gap report for a framework."""
        assessments = self.list_assessments({"framework": framework})
        gaps = []
        for a in assessments:
            if a.get("status") != "compliant":
                gaps.append({
                    "requirement": a.get("requirement"),
                    "control": a.get("control"),
                    "gap": a.get("gap_description"),
                    "severity": a.get("severity", "medium"),
                })
        return {
            "framework": framework,
            "total_requirements": len(assessments),
            "gaps_found": len(gaps),
            "gaps": gaps,
            "exported_by": self.station_id,
        }

    def export_audit_pack(self, audit_log_id: str) -> dict:
        """Compile full audit pack for an audit log."""
        audit = self.get_audit_log(audit_log_id)
        evidence = self.list_evidence({"incident": audit_log_id})
        return {
            "audit_log": audit,
            "evidence": evidence,
            "exported_by": self.station_id,
        }

    def validate_entity_exists(self, entity_type: str, ciso_id: str) -> bool:
        """Aboyeur QA hook: verify entity exists in CISO Assistant."""
        try:
            getattr(self, f"get_{entity_type}")(ciso_id)
            return True
        except Exception:
            return False

    # ─── Station Interface ──────────────────────────────────────────────

    def process(self, entity_id: int, entity_type: str, entity_value: str) -> dict:
        """Read-only: fetch current state from CISO Assistant for validation."""
        self.log(f"Validating {entity_type} via CISO Assistant read")

        # Parse ciso_id from entity_value if it's JSON
        try:
            data = json.loads(entity_value)
            ciso_id = data.get("ciso_id")
        except json.JSONDecodeError:
            return {
                'entity_type': entity_type,
                'entity_value': entity_value,
                'relationships': [],
                'confidence': 0.0,
                'notes': 'No ciso_id in entity_value — cannot validate',
            }

        if not ciso_id:
            return {
                'entity_type': entity_type,
                'entity_value': entity_value,
                'relationships': [],
                'confidence': 0.0,
                'notes': 'Missing ciso_id — cannot validate against CISO Assistant',
            }

        # Validate existence
        exists = self.validate_entity_exists(entity_type, ciso_id)
        confidence = 1.0 if exists else 0.0

        return {
            'entity_type': entity_type,
            'entity_value': entity_value,
            'relationships': [],
            'confidence': confidence,
            'notes': f"CISO Assistant validation: {'FOUND' if exists else 'NOT FOUND'} (ciso_id={ciso_id})",
        }