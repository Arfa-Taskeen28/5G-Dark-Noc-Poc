"""Shared data contracts for the agentic layer.

These Pydantic models are the single source of truth used by the agent package,
the FastAPI backend, and the Streamlit UI. Keep them stable — everything builds
against them.
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

# Incident lifecycle:
#   open -> diagnosed -> (auto_healed | pending_approval) -> approved/rejected -> resolved
IncidentStatus = Literal[
    "open",
    "diagnosed",
    "pending_approval",
    "auto_healed",
    "approved",
    "rejected",
    "resolved",
]

RiskLevel = Literal["low", "medium", "high"]
ActionGate = Literal["AUTO", "NEEDS_APPROVAL"]


class KpiReading(BaseModel):
    """One KPI's state at the incident's peak timestamp."""

    kpi: str
    value: float
    predicted: float
    zscore: float


class Incident(BaseModel):
    """A fault episode derived from the L2 anomaly output, ready for the agent."""

    id: str
    site_id: str
    timestamp: str  # ISO-8601
    dominant_kpi: str
    fault_signature: str  # inferred: gradual_degradation | sudden_spike | sudden_drop
    severity: RiskLevel
    detection_confidence: float = Field(ge=0.0, le=1.0)
    explanation: str  # rule-based explanation from src/explain.py (grounding)
    readings: List[KpiReading]
    status: IncidentStatus = "open"
    diagnosis: Optional["Diagnosis"] = None
    resolved_at: Optional[str] = None

    def readings_dict(self) -> Dict[str, KpiReading]:
        return {r.kpi: r for r in self.readings}


class Diagnosis(BaseModel):
    """The agent's structured output for one incident."""

    root_cause: str
    runbook: List[str]  # ordered Method-of-Procedure steps
    blast_radius: str
    risk_level: RiskLevel
    recommended_action: str
    confidence: float = Field(ge=0.0, le=1.0)  # agent's confidence in the fix
    source: Literal["claude", "demo"] = "demo"


class RemediationDecision(BaseModel):
    """Result of the confidence gate."""

    gate: ActionGate
    threshold: float
    confidence: float
    rationale: str


class AuditRecord(BaseModel):
    """One immutable line in the audit trail."""

    incident_id: str
    site_id: str
    action: str  # diagnosed | auto_healed | approved | rejected | resolved
    actor: str  # "aura-agent" or "human"
    gate: Optional[ActionGate] = None
    confidence: Optional[float] = None
    detail: str = ""
    timestamp: str  # ISO-8601


# Resolve the forward reference (Incident -> Diagnosis).
Incident.model_rebuild()
