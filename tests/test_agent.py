import pandas as pd
import pytest

from src.config import KPIS
from src.agent import playbooks
from src.agent.copilot import diagnose_incident
from src.agent.remediation import decide
from src.agent.schemas import Diagnosis, Incident, KpiReading
from src.agent.store import build_incidents


def _make_scored_df():
    n = 10
    timestamps = pd.date_range("2026-01-01", periods=n, freq="15min")
    data = {"site_id": ["site_A"] * n, "timestamp": timestamps}

    for kpi in KPIS:
        data[kpi] = [100.0] * n
        data[f"{kpi}_pred"] = [100.0] * n
        data[f"{kpi}_zscore"] = [0.0] * n

    # Inject a gradual ramp on latency_ms over steps 3-6 (contiguous anomaly window).
    ramp = [0.0, 0.0, 0.0, 2.0, 3.5, 4.8, 6.0, 0.0, 0.0, 0.0]
    data["latency_ms_zscore"] = ramp

    data["is_anomaly"] = [1 if i in (3, 4, 5, 6) else 0 for i in range(n)]
    data["anomaly_confidence"] = [0.8 if i in (3, 4, 5, 6) else 0.1 for i in range(n)]

    return pd.DataFrame(data)


def test_build_incidents_groups_contiguous_window():
    df = _make_scored_df()
    incidents = build_incidents(df)

    assert len(incidents) == 1
    incident = incidents[0]
    assert incident.site_id == "site_A"
    assert incident.dominant_kpi == "latency_ms"


def test_build_incidents_infers_gradual_degradation_for_ramp():
    df = _make_scored_df()
    incidents = build_incidents(df)
    assert incidents[0].fault_signature == "gradual_degradation"


def test_build_incidents_no_anomalies_returns_empty():
    df = _make_scored_df()
    df["is_anomaly"] = 0
    incidents = build_incidents(df)
    assert incidents == []


def _make_diagnosis(confidence, risk_level):
    return Diagnosis(
        root_cause="test",
        runbook=["step 1"],
        blast_radius="test",
        risk_level=risk_level,
        recommended_action="step 1",
        confidence=confidence,
        source="demo",
    )


def test_decide_auto_when_confidence_high_and_risk_not_high():
    decision = decide(_make_diagnosis(confidence=0.9, risk_level="medium"), threshold=0.85)
    assert decision.gate == "AUTO"


def test_decide_needs_approval_when_confidence_low():
    decision = decide(_make_diagnosis(confidence=0.5, risk_level="medium"), threshold=0.85)
    assert decision.gate == "NEEDS_APPROVAL"


def test_decide_needs_approval_when_risk_high_regardless_of_confidence():
    decision = decide(_make_diagnosis(confidence=0.99, risk_level="high"), threshold=0.85)
    assert decision.gate == "NEEDS_APPROVAL"


def _make_incident(dominant_kpi="throughput_mbps", fault_signature="sudden_drop"):
    readings = [
        KpiReading(kpi=k, value=1.0, predicted=1.0, zscore=0.0) for k in KPIS
    ]
    return Incident(
        id="test-incident",
        site_id="site_A",
        timestamp="2026-01-01T00:00:00",
        dominant_kpi=dominant_kpi,
        fault_signature=fault_signature,
        severity="high",
        detection_confidence=0.7,
        explanation="test explanation",
        readings=readings,
    )


def test_diagnose_incident_demo_mode_grounds_in_playbook(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    incident = _make_incident()

    diagnosis = diagnose_incident(incident)

    expected = playbooks.lookup(incident.dominant_kpi, incident.fault_signature)
    assert diagnosis.source == "demo"
    assert diagnosis.root_cause == expected["root_cause"]
    assert diagnosis.risk_level == expected["risk_level"]
