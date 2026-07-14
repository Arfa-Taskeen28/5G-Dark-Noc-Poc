"""Grounding knowledge base of remediation playbooks.

Real NOC teams work from vetted Methods-of-Procedure (MOPs). We give the agent the
same: a curated library of runbooks per (KPI, fault signature). The agent is
instructed to ground its recommendation in the closest playbook rather than
inventing steps — this is the "grounded RAG" that keeps a GenAI safe in critical
infrastructure and is a core part of the trust story.
"""

from __future__ import annotations

from typing import Dict, List

# Human-readable KPI labels used in narratives.
KPI_LABELS: Dict[str, str] = {
    "throughput_mbps": "downlink throughput",
    "latency_ms": "round-trip latency",
    "packet_loss_pct": "packet loss",
    "prb_utilization_pct": "PRB (radio resource) utilisation",
}

# Playbook library: key = f"{kpi}:{fault_signature}".
# Each entry carries a likely root cause, an ordered runbook, and a default risk.
PLAYBOOKS: Dict[str, Dict] = {
    # ---- Throughput ----
    "throughput_mbps:sudden_drop": {
        "root_cause": "Sudden downlink throughput collapse — typically a transport/backhaul "
        "degradation or a carrier/cell going out of service.",
        "runbook": [
            "Verify backhaul link health and interface counters on the site's aggregation router.",
            "Check for alarms on the affected cell/carrier (RRU, CPRI/eCPRI, optical module).",
            "Fail traffic over to the redundant backhaul path if link errors are confirmed.",
            "Trigger a soft reset of the affected carrier if no transport fault is found.",
            "Confirm throughput recovery against the forecast baseline before closing.",
        ],
        "risk_level": "high",
    },
    "throughput_mbps:gradual_degradation": {
        "root_cause": "Slowly declining throughput — usually growing interference, creeping "
        "congestion, or antenna/feeder degradation.",
        "runbook": [
            "Pull interference (RSSI/SINR) trends for the sector over the degradation window.",
            "Check neighbour-cell load for congestion spillover.",
            "Rebalance carriers / adjust load-balancing thresholds.",
            "Schedule an antenna/feeder VSWR check if interference is ruled out.",
            "Monitor against forecast for sustained recovery.",
        ],
        "risk_level": "medium",
    },
    # ---- Latency ----
    "latency_ms:sudden_spike": {
        "root_cause": "Latency spike — commonly transport congestion, a routing flap, or a "
        "buffering/queue build-up on the user-plane path.",
        "runbook": [
            "Inspect user-plane (UPF/S-GW) queue depth and CPU on the serving node.",
            "Check for routing changes or BGP flaps on the transport path.",
            "Apply/verify QoS scheduling to protect latency-sensitive bearers.",
            "Drain and reroute traffic from the congested path if confirmed.",
            "Validate latency returns to the forecast band.",
        ],
        "risk_level": "high",
    },
    "latency_ms:gradual_degradation": {
        "root_cause": "Gradually rising latency — progressive congestion or resource "
        "exhaustion on the user-plane path.",
        "runbook": [
            "Trend user-plane node utilisation over the window.",
            "Identify top talkers / bearer growth driving the load.",
            "Scale user-plane resources or shift bearers to a less-loaded node.",
            "Re-check QoS policy enforcement.",
            "Confirm recovery to baseline.",
        ],
        "risk_level": "medium",
    },
    # ---- Packet loss ----
    "packet_loss_pct:sudden_spike": {
        "root_cause": "Packet-loss spike — physical-layer errors (bad optics/CPRI), congestion "
        "drops, or a flapping interface.",
        "runbook": [
            "Read interface error/discard counters along the path (CRC, drops).",
            "Check optical Rx power on suspect links against thresholds.",
            "Replace/clean the optical module or reseat the CPRI/eCPRI link if errors persist.",
            "Reroute over the protected path while remediating.",
            "Verify loss returns to <1% against baseline.",
        ],
        "risk_level": "high",
    },
    # ---- PRB utilisation ----
    "prb_utilization_pct:sudden_spike": {
        "root_cause": "PRB utilisation spike — a traffic surge or a neighbouring cell outage "
        "pushing users onto this cell.",
        "runbook": [
            "Confirm whether a neighbour cell is down, concentrating load here.",
            "Enable/tune load balancing and traffic steering to neighbours.",
            "Activate an additional carrier / capacity cell if available.",
            "Apply admission control to protect active sessions during the surge.",
            "Watch utilisation settle below the congestion threshold.",
        ],
        "risk_level": "medium",
    },
    "prb_utilization_pct:gradual_degradation": {
        "root_cause": "Steadily climbing PRB utilisation — organic traffic growth approaching "
        "cell capacity.",
        "runbook": [
            "Confirm the trend is sustained growth, not a transient event.",
            "Tune load-balancing thresholds toward under-utilised neighbours.",
            "Plan/activate additional carrier capacity for the sector.",
            "Flag the site for capacity planning if growth continues.",
            "Verify utilisation eases against the forecast.",
        ],
        "risk_level": "low",
    },
}

# Generic fallback when no exact (kpi, signature) match exists.
_GENERIC = {
    "root_cause": "Anomalous KPI deviation from the forecast baseline of unclear origin.",
    "runbook": [
        "Correlate the flagged KPI with alarms and neighbouring KPIs over the window.",
        "Check transport, radio, and core along the affected path for coincident faults.",
        "Apply the least-disruptive corrective action indicated by the correlation.",
        "Reroute/rebalance traffic if a localised fault is confirmed.",
        "Confirm the KPI returns to its forecast band before closing.",
    ],
    "risk_level": "medium",
}


def lookup(kpi: str, fault_signature: str) -> Dict:
    """Return the closest playbook for a (KPI, fault signature)."""
    return PLAYBOOKS.get(f"{kpi}:{fault_signature}") or _GENERIC


def as_context_block(kpi: str, fault_signature: str) -> str:
    """Render the matched playbook as a text block to ground the LLM prompt."""
    pb = lookup(kpi, fault_signature)
    steps = "\n".join(f"  {i + 1}. {s}" for i, s in enumerate(pb["runbook"]))
    label = KPI_LABELS.get(kpi, kpi)
    return (
        f"Closest vetted playbook — {label} / {fault_signature} "
        f"(default risk: {pb['risk_level']}):\n"
        f"Likely root cause: {pb['root_cause']}\n"
        f"Recommended MOP:\n{steps}"
    )
