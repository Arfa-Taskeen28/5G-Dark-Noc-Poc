"""Incident Store (L2 -> L3 bridge) — the agent that turns raw anomaly rows into
discrete, trackable incidents and persists their lifecycle (status, diagnosis,
audit trail) across Streamlit reruns.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from src.config import AUDIT_LOG_PATH, KPIS
from src.explain import explain_row
from src.agent import playbooks
from src.agent.schemas import AuditRecord, Diagnosis, Incident, KpiReading

MAX_GAP_STEPS = 2  # contiguous-window tolerance: allow up to this many non-anomalous steps


def _incident_id(site_id: str, start_ts: str, dominant_kpi: str) -> str:
    raw = f"{site_id}|{start_ts}|{dominant_kpi}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _infer_fault_signature(zscores: np.ndarray) -> str:
    """Classify the shape of a z-score trajectory into one of the playbook's
    fault signatures: a sustained ramp is gradual degradation, a short sharp
    onset is a spike or drop depending on sign.
    """
    if len(zscores) == 0:
        return "sudden_spike"

    peak_idx = int(np.argmax(np.abs(zscores)))
    peak = zscores[peak_idx]

    # Ramp check: correlation between position and |z| over the window.
    if len(zscores) >= 4:
        positions = np.arange(len(zscores))
        corr = np.corrcoef(positions, np.abs(zscores))[0, 1]
    else:
        corr = 0.0

    if not np.isnan(corr) and corr > 0.6:
        return "gradual_degradation"
    return "sudden_spike" if peak > 0 else "sudden_drop"


def build_incidents(scored_df: pd.DataFrame, kpis: List[str] = KPIS) -> List[Incident]:
    incidents: List[Incident] = []
    zscore_cols = [f"{k}_zscore" for k in kpis]

    for site_id, site_df in scored_df.groupby("site_id"):
        site_df = site_df.sort_values("timestamp").reset_index(drop=True)
        is_anom = site_df["is_anomaly"].to_numpy()

        windows = []
        start = None
        gap = 0
        for i, flag in enumerate(is_anom):
            if flag:
                if start is None:
                    start = i
                gap = 0
            elif start is not None:
                gap += 1
                if gap > MAX_GAP_STEPS:
                    windows.append((start, i - gap))
                    start = None
                    gap = 0
        if start is not None:
            windows.append((start, len(is_anom) - 1))

        for w_start, w_end in windows:
            window_df = site_df.iloc[w_start : w_end + 1]
            abs_max_per_kpi = window_df[zscore_cols].abs().max()
            dominant_kpi = abs_max_per_kpi.idxmax().replace("_zscore", "")

            peak_row_idx = window_df[f"{dominant_kpi}_zscore"].abs().idxmax()
            peak_row = site_df.loc[peak_row_idx]

            fault_signature = _infer_fault_signature(window_df[f"{dominant_kpi}_zscore"].to_numpy())
            playbook = playbooks.lookup(dominant_kpi, fault_signature)

            readings = [
                KpiReading(
                    kpi=k,
                    value=float(peak_row[k]),
                    predicted=float(peak_row[f"{k}_pred"]),
                    zscore=float(peak_row[f"{k}_zscore"]),
                )
                for k in kpis
            ]

            start_ts = site_df.loc[w_start, "timestamp"]
            incident = Incident(
                id=_incident_id(str(site_id), str(start_ts), dominant_kpi),
                site_id=str(site_id),
                timestamp=str(peak_row["timestamp"]),
                dominant_kpi=dominant_kpi,
                fault_signature=fault_signature,
                severity=playbook["risk_level"],
                detection_confidence=float(window_df["anomaly_confidence"].mean()),
                explanation=explain_row(peak_row, kpis),
                readings=readings,
            )
            incidents.append(incident)

    return incidents


class IncidentStore:
    def __init__(self, path: str = AUDIT_LOG_PATH):
        self.path = Path(path)
        self._incidents: Dict[str, Incident] = {}
        self._audit: List[AuditRecord] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        raw = json.loads(self.path.read_text())
        self._incidents = {i["id"]: Incident(**i) for i in raw.get("incidents", [])}
        self._audit = [AuditRecord(**a) for a in raw.get("audit_trail", [])]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "incidents": [i.model_dump() for i in self._incidents.values()],
            "audit_trail": [a.model_dump() for a in self._audit],
        }
        self.path.write_text(json.dumps(payload, indent=2))

    def sync(self, scored_df: pd.DataFrame, kpis: List[str] = KPIS) -> None:
        for incident in build_incidents(scored_df, kpis):
            if incident.id not in self._incidents:
                self._incidents[incident.id] = incident
        self.save()

    def list(self, status: Optional[str] = None) -> List[Incident]:
        items = list(self._incidents.values())
        if status:
            items = [i for i in items if i.status == status]
        return sorted(items, key=lambda i: i.timestamp, reverse=True)

    def get(self, incident_id: str) -> Optional[Incident]:
        return self._incidents.get(incident_id)

    def update_status(self, incident_id: str, status: str) -> None:
        incident = self._incidents[incident_id]
        incident.status = status
        if status == "resolved":
            incident.resolved_at = datetime.datetime.utcnow().isoformat()
        self.save()

    def set_diagnosis(self, incident_id: str, diagnosis: Diagnosis) -> None:
        self._incidents[incident_id].diagnosis = diagnosis
        self._incidents[incident_id].status = "diagnosed"
        self.save()

    def append_audit(self, record: AuditRecord) -> None:
        self._audit.append(record)
        self.save()

    def audit_trail(self, incident_id: Optional[str] = None) -> List[AuditRecord]:
        records = self._audit
        if incident_id:
            records = [r for r in records if r.incident_id == incident_id]
        return sorted(records, key=lambda r: r.timestamp)
