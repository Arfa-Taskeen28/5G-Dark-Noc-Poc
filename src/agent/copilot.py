"""Diagnosis + Chat agent — the "brain" of AURA.

Grounds every answer in the vetted playbook library (src/agent/playbooks.py) so
a live LLM call can reason and phrase things naturally without inventing facts.
Falls back to a deterministic, playbook-only "demo" path whenever no API key is
configured or the Claude call fails for any reason — a live demo must never
crash on a network hiccup.
"""

from __future__ import annotations

import json
import os
from typing import List, Optional, Tuple

from src.agent import playbooks
from src.agent.schemas import Diagnosis, Incident
from src.config import NOC_AGENT_MODEL

DIAGNOSIS_TOOL = {
    "name": "submit_diagnosis",
    "description": "Submit a structured root-cause diagnosis for a network incident.",
    "input_schema": {
        "type": "object",
        "properties": {
            "root_cause": {"type": "string"},
            "runbook": {"type": "array", "items": {"type": "string"}},
            "blast_radius": {"type": "string"},
            "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
            "recommended_action": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        },
        "required": [
            "root_cause",
            "runbook",
            "blast_radius",
            "risk_level",
            "recommended_action",
            "confidence",
        ],
    },
}


def _get_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return key
    try:
        import streamlit as st

        return st.secrets.get("ANTHROPIC_API_KEY", "")
    except Exception:
        return ""


def _incident_context(incident: Incident) -> str:
    readings = "\n".join(
        f"  - {r.kpi}: actual={r.value:.2f}, predicted={r.predicted:.2f}, z-score={r.zscore:.2f}"
        for r in incident.readings
    )
    return (
        f"Site: {incident.site_id}\n"
        f"Timestamp: {incident.timestamp}\n"
        f"Dominant KPI: {incident.dominant_kpi}\n"
        f"Fault signature: {incident.fault_signature}\n"
        f"Detection confidence: {incident.detection_confidence:.2f}\n"
        f"KPI readings at peak:\n{readings}\n\n"
        f"{playbooks.as_context_block(incident.dominant_kpi, incident.fault_signature)}"
    )


def _demo_diagnosis(incident: Incident) -> Diagnosis:
    pb = playbooks.lookup(incident.dominant_kpi, incident.fault_signature)
    return Diagnosis(
        root_cause=pb["root_cause"],
        runbook=pb["runbook"],
        blast_radius=f"Site {incident.site_id}, sector serving {incident.dominant_kpi.replace('_', ' ')}.",
        risk_level=pb["risk_level"],
        recommended_action=pb["runbook"][0],
        confidence=incident.detection_confidence,
        source="demo",
    )


def diagnose_incident(incident: Incident) -> Diagnosis:
    api_key = _get_api_key()
    if not api_key:
        return _demo_diagnosis(incident)

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=NOC_AGENT_MODEL,
            max_tokens=1024,
            system=(
                "You are AURA, a network operations diagnosis agent for a 5G RAN/core network. "
                "Ground your diagnosis strictly in the incident data and the vetted playbook provided "
                "below — adapt the wording and reasoning to this specific incident, but do not invent "
                "facts, equipment, or steps outside what the playbook and readings support. "
                "Always respond by calling the submit_diagnosis tool."
            ),
            messages=[{"role": "user", "content": _incident_context(incident)}],
            tools=[DIAGNOSIS_TOOL],
            tool_choice={"type": "tool", "name": "submit_diagnosis"},
        )
        tool_use = next(b for b in response.content if b.type == "tool_use")
        data = tool_use.input
        return Diagnosis(**data, source="claude")
    except Exception:
        return _demo_diagnosis(incident)


def chat(incident: Incident, diagnosis: Optional[Diagnosis], question: str, history: List[Tuple[str, str]]) -> str:
    api_key = _get_api_key()
    if not api_key:
        if diagnosis is None:
            return "Run a diagnosis first, then I can answer questions about this incident."
        return (
            f"(Demo mode — grounded answer, no live model)\n\n"
            f"Root cause: {diagnosis.root_cause}\n"
            f"Recommended action: {diagnosis.recommended_action}\n"
            f"Runbook:\n" + "\n".join(f"  {i+1}. {s}" for i, s in enumerate(diagnosis.runbook))
        )

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        context = _incident_context(incident)
        if diagnosis:
            context += (
                f"\n\nCurrent diagnosis: {diagnosis.root_cause}\n"
                f"Recommended action: {diagnosis.recommended_action}\n"
                f"Risk: {diagnosis.risk_level}, confidence: {diagnosis.confidence:.2f}"
            )

        messages = [{"role": "user", "content": f"Incident context:\n{context}"}]
        for role, text in history:
            messages.append({"role": role, "content": text})
        messages.append({"role": "user", "content": question})

        response = client.messages.create(
            model=NOC_AGENT_MODEL,
            max_tokens=512,
            system=(
                "You are AURA, a network operations copilot. Answer the engineer's question about "
                "this specific incident, grounded only in the provided context. Be concise and precise."
            ),
            messages=messages,
        )
        return "".join(b.text for b in response.content if b.type == "text")
    except Exception:
        return "Live chat is unavailable right now. Falling back: " + (
            diagnosis.recommended_action if diagnosis else "no diagnosis available yet."
        )
