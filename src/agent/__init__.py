"""Agentic NOC Copilot (L3) — Decide + Act layer on top of the L2 detection pipeline.

Called in-process directly by the Streamlit UI (`app/dashboard.py`) — no separate
backend service:

    from src.agent import IncidentStore, diagnose_incident, decide, apply_remediation, chat
    from src.agent.schemas import Incident, Diagnosis, AuditRecord
"""

from src.agent.schemas import Incident, Diagnosis, AuditRecord, RemediationDecision
from src.agent.store import IncidentStore
from src.agent.copilot import diagnose_incident, chat
from src.agent.remediation import decide, apply_remediation

__all__ = [
    "Incident",
    "Diagnosis",
    "AuditRecord",
    "RemediationDecision",
    "IncidentStore",
    "diagnose_incident",
    "chat",
    "decide",
    "apply_remediation",
]
