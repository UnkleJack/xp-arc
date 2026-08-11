"""
GRC Supervisor — Primary Governance, Risk & Compliance Station.

Integrates with CISO Assistant (intuitem/ciso-assistant-community) via REST API.
Owns: risk, control, compliance_assessment, audit_log, policy, evidence entities.
All write operations go through CISO Assistant API (source of truth).

API endpoints verified from /api/schema/ (OpenAPI spec).
Working endpoints: assets, applied-controls, incidents, vulnerabilities, threats,
reference-controls, evidences, policies.
"""

import json
import os
import requests
from datetime import datetime
from ..core.station import StationChef
from ..core.pool import compute_payload_hash


class GRCSupervisor(StationChef):
    """Primary GRC station — writes to CISO Assistant via API."""

    station_id = "grc_supervisor"
    name = "GRC Supervisor"
    handles_types = [
        'risk',
        'control',
        'compliance_assessment',
        'audit_log',
        'policy',
        'evidence',
    ]
    sla_seconds = 120
    is_primary = True

    # CISO Assistant API base (already includes /api)
    API_BASE = "https://localhost:8443/api"
    TOKEN = os.environ.get("XP_ARC_CISO_TOKEN", "dev-token-change-in-production")

    def __init__(self, pool):
        super().__init__(pool)
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Token {self.TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        self.session.verify = False  # self-signed cert

    def _api(self, method: str, endpoint: str, **kwargs) -> dict:
        """Call CISO Assistant API."""
        url = f"{self.API_BASE}{endpoint}"
        try:
            resp = self.session.request(method, url, timeout=30, **kwargs)
            resp.raise_for_status()
            return resp.json() if resp.content else {}
        except requests.exceptions.RequestException as e:
            self.log(f"API error {method} {endpoint}: {e}")
            raise

    def _unique_name(self, base: str, prefix: str = "XP-ARC") -> str:
        """Generate unique name to avoid duplicate errors."""
        return f"{prefix} {base} {datetime.now().strftime('%Y%m%d-%H%M%S')}"

    # ─── Risk Management (using Assets) ────────────────────────────────

    def create_risk(self, entity_id: int, entity_value: str) -> dict:
        """Create risk as Asset in CISO Assistant."""
        try:
            data = json.loads(entity_value)
        except json.JSONDecodeError:
            data = {"name": entity_value[:100]}

        payload = {
            "name": self._unique_name(data.get("name", entity_value[:50])),
            "asset_class": data.get("asset_class", ""),
            "owner": data.get("owner", []),
            "description": data.get("description", ""),
        }
        result = self._api("POST", "/assets/", json=payload)
        return {
            'entity_type': 'risk',
            'entity_value': json.dumps({"ciso_id": result.get("id"), **payload}),
            'relationships': [],
            'confidence': 0.95,
            'notes': f"Created risk (asset) in CISO Assistant: {result.get('id')}",
        }

    def read_risk(self, ciso_id: str) -> dict:
        return self._api("GET", f"/assets/{ciso_id}/")

    def list_risks(self, params: dict = None) -> dict:
        return self._api("GET", "/assets/", params=params)

    # ─── Controls (using Applied Controls) ─────────────────────────────

    def create_control(self, entity_id: int, entity_value: str) -> dict:
        """Create applied control in CISO Assistant."""
        try:
            data = json.loads(entity_value)
        except json.JSONDecodeError:
            data = {"name": entity_value[:100]}

        payload = {
            "name": self._unique_name(data.get("name", entity_value[:50])),
            "description": data.get("description", ""),
        }
        result = self._api("POST", "/applied-controls/", json=payload)
        return {
            'entity_type': 'control',
            'entity_value': json.dumps({"ciso_id": result.get("id"), **payload}),
            'relationships': [],
            'confidence': 0.95,
            'notes': f"Created applied control in CISO Assistant: {result.get('id')}",
        }

    def list_controls(self, params: dict = None) -> dict:
        return self._api("GET", "/applied-controls/", params=params)

    # ─── Compliance Assessments ────────────────────────────────────────

    def create_assessment(self, entity_id: int, entity_value: str) -> dict:
        """Create compliance assessment (requires framework UUID - may fail without loaded library)."""
        try:
            data = json.loads(entity_value)
        except json.JSONDecodeError:
            data = {"name": entity_value[:50]}

        payload = {
            "name": self._unique_name(data.get("name", entity_value[:50])),
            "description": data.get("description", ""),
            # framework is required but needs loaded library UUID
            # skipping for now - would need library loaded first
        }
        try:
            result = self._api("POST", "/compliance-assessments/", json=payload)
            return {
                'entity_type': 'compliance_assessment',
                'entity_value': json.dumps({"ciso_id": result.get("id"), **payload}),
                'relationships': [],
                'confidence': 0.95,
                'notes': f"Created compliance assessment in CISO Assistant: {result.get('id')}",
            }
        except requests.exceptions.HTTPError as e:
            # Return degraded result if framework missing
            return {
                'entity_type': 'compliance_assessment',
                'entity_value': json.dumps({"error": "framework_required", **payload}),
                'relationships': [],
                'confidence': 0.5,
                'notes': f"Compliance assessment requires loaded framework library: {e}",
            }

    def list_assessments(self, params: dict = None) -> dict:
        return self._api("GET", "/compliance-assessments/", params=params)

    # ─── Audit Logs (using Incidents) ──────────────────────────────────

    def create_audit_log(self, entity_id: int, entity_value: str) -> dict:
        """Create incident (audit log) in CISO Assistant."""
        try:
            data = json.loads(entity_value)
        except json.JSONDecodeError:
            data = {"name": entity_value}

        payload = {
            "name": self._unique_name(data.get("name", entity_value[:100])),
            "description": data.get("description", ""),
            "incident_type": data.get("incident_type", "security"),
            "severity": data.get("severity", "medium"),
            "status": data.get("status", "open"),
            "detection_date": data.get("detection_date", datetime.now().date().isoformat()),
        }
        result = self._api("POST", "/incidents/", json=payload)
        return {
            'entity_type': 'audit_log',
            'entity_value': json.dumps({"ciso_id": result.get("id"), **payload}),
            'relationships': [],
            'confidence': 0.95,
            'notes': f"Created incident (audit log) in CISO Assistant: {result.get('id')}",
        }

    def list_audit_logs(self, params: dict = None) -> dict:
        return self._api("GET", "/incidents/", params=params)

    # ─── Policies (using Reference Controls) ───────────────────────────

    def create_policy(self, entity_id: int, entity_value: str) -> dict:
        """Create reference control (policy) in CISO Assistant."""
        try:
            data = json.loads(entity_value)
        except json.JSONDecodeError:
            data = {"name": entity_value[:100]}

        payload = {
            "name": self._unique_name(data.get("name", entity_value[:100])),
            "description": data.get("content", ""),
            "category": data.get("category", "policy"),
            "provider": data.get("provider", "internal"),
        }
        result = self._api("POST", "/reference-controls/", json=payload)
        return {
            'entity_type': 'policy',
            'entity_value': json.dumps({"ciso_id": result.get("id"), **payload}),
            'relationships': [],
            'confidence': 0.95,
            'notes': f"Created reference control (policy) in CISO Assistant: {result.get('id')}",
        }

    def list_policies(self, params: dict = None) -> dict:
        return self._api("GET", "/reference-controls/", params=params)

    # ─── Evidence ────────────────────────────────────────────────────────

    def create_evidence(self, entity_id: int, entity_value: str) -> dict:
        """Create evidence in CISO Assistant."""
        try:
            data = json.loads(entity_value)
        except json.JSONDecodeError:
            data = {"name": entity_value[:100]}

        payload = {
            "name": self._unique_name(data.get("name", entity_value[:100])),
            "description": data.get("description", ""),
        }
        result = self._api("POST", "/evidences/", json=payload)
        return {
            'entity_type': 'evidence',
            'entity_value': json.dumps({"ciso_id": result.get("id"), **payload}),
            'relationships': [],
            'confidence': 0.95,
            'notes': f"Created evidence in CISO Assistant: {result.get('id')}",
        }

    def list_evidence(self, params: dict = None) -> dict:
        return self._api("GET", "/evidences/", params=params)

    # ─── Station Interface ──────────────────────────────────────────────

    def process(self, entity_id: int, entity_type: str, entity_value: str) -> dict:
        """Route entity to appropriate CISO Assistant API operation."""
        self.log(f"Processing {entity_type}: {entity_id}")

        handlers = {
            'risk': self.create_risk,
            'control': self.create_control,
            'compliance_assessment': self.create_assessment,
            'audit_log': self.create_audit_log,
            'policy': self.create_policy,
            'evidence': self.create_evidence,
        }

        handler = handlers.get(entity_type)
        if not handler:
            raise ValueError(f"Unknown GRC entity type: {entity_type}")

        return handler(entity_id, entity_value)

    def sync_from_ciso(self, entity_type: str = None) -> dict:
        """Pull current state from CISO Assistant into local pool."""
        self.log(f"Syncing from CISO Assistant: {entity_type or 'all'}")

        sync_map = {
            'risk': ('/assets/', 'risk'),
            'control': ('/applied-controls/', 'control'),
            'compliance_assessment': ('/compliance-assessments/', 'compliance_assessment'),
            'audit_log': ('/incidents/', 'audit_log'),
            'policy': ('/reference-controls/', 'policy'),
            'evidence': ('/evidences/', 'evidence'),
        }

        results = {"synced": 0, "errors": []}

        for etype, (endpoint, pool_type) in sync_map.items():
            if entity_type and etype != entity_type:
                continue
            try:
                data = self._api("GET", endpoint)
                for item in data.get("results", data):
                    self.pool.add_entity(
                        type=pool_type,
                        value=json.dumps({"ciso_id": item.get("id"), **item}),
                        source=f"ciso-sync-{etype}",
                    )
                    results["synced"] += 1
            except Exception as e:
                results["errors"].append(f"{etype}: {e}")

        return results