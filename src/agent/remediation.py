"""Remediation / trust-gate agent — the literal implementation of the
Decision-dimension trust calibration that Fastweb+Vodafone named as the
blocker on the path to Autonomous Networks Level 4: a confidence-gated
policy deciding when the network can act on its own vs. when it must wait
for a human, plus the immutable audit trail of every decision made.
"""

from __future__ import annotations

import datetime

from src.agent.schemas import AuditRecord, Diagnosis, Incident, RemediationDecision
from src.agent.store import IncidentStore
from src.config import AUTO_APPROVE_THRESHOLD


def decide(diagnosis: Diagnosis, threshold: float = AUTO_APPROVE_THRESHOLD) -> RemediationDecision:
    if diagnosis.confidence >= threshold and diagnosis.risk_level != "high":
        gate = "AUTO"
        rationale = (
            f"Confidence {diagnosis.confidence:.2f} meets the {threshold:.2f} auto-approve "
            f"threshold and risk is {diagnosis.risk_level} — AURA proceeds without waiting for a human."
        )
    else:
        gate = "NEEDS_APPROVAL"
        if diagnosis.risk_level == "high":
            rationale = "Risk level is high — always routed to a human regardless of confidence."
        else:
            rationale = (
                f"Confidence {diagnosis.confidence:.2f} is below the {threshold:.2f} auto-approve "
                f"threshold — routed to a human for approval before acting."
            )

    return RemediationDecision(
        gate=gate,
        threshold=threshold,
        confidence=diagnosis.confidence,
        rationale=rationale,
    )


def _now() -> str:
    return datetime.datetime.utcnow().isoformat()


def apply_remediation(
    store: IncidentStore,
    incident: Incident,
    decision: RemediationDecision,
    actor: str,
    approved: bool = True,
) -> None:
    if decision.gate == "AUTO":
        status = "auto_healed"
        action = "auto_healed"
    elif approved:
        status = "approved"
        action = "approved"
    else:
        status = "rejected"
        action = "rejected"

    store.update_status(incident.id, status)
    store.append_audit(
        AuditRecord(
            incident_id=incident.id,
            site_id=incident.site_id,
            action=action,
            actor=actor,
            gate=decision.gate,
            confidence=decision.confidence,
            detail=decision.rationale,
            timestamp=_now(),
        )
    )
