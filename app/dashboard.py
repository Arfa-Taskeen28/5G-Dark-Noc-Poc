import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.config import KPIS
from src.explain import add_explanations
from src.agent import IncidentStore, diagnose_incident, decide, apply_remediation, chat

st.set_page_config(page_title="AURA — Dark NOC Copilot", layout="wide")

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "processed" / "scored_predictions.csv"


def _has_api_key() -> bool:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    try:
        return bool(st.secrets.get("ANTHROPIC_API_KEY", ""))
    except Exception:
        return False


@st.cache_data
def load_data():
    return pd.read_csv(DATA_PATH, parse_dates=["timestamp"])


@st.cache_resource
def get_store():
    return IncidentStore()


st.title("AURA — Predictive Fault Detection & Autonomous Remediation Copilot")
st.caption(
    "Forecasts network KPI behavior, flags anomalies with a confidence score, diagnoses root cause "
    "against a vetted playbook, and gates remediation on trust — closing the Decision-dimension gap "
    "that blocks progress to Autonomous Networks Level 4."
)

with st.sidebar:
    if _has_api_key():
        st.success("Claude-powered diagnosis & chat")
    else:
        st.warning("Demo mode — no ANTHROPIC_API_KEY set.\nDiagnoses use the grounded playbook directly.")

if not DATA_PATH.exists():
    st.error(
        "No scored predictions found. Run the pipeline first:\n\n"
        "python -m src.data_simulation\n"
        "python -m src.features\n"
        "python -m src.forecasting\n"
        "python -m src.anomaly"
    )
    st.stop()

df = load_data()
store = get_store()
store.sync(df)

tab_overview, tab_copilot = st.tabs(["Fault Timeline", "AURA Copilot"])

with tab_overview:
    col1, col2 = st.columns([1, 1])
    with col1:
        site_id = st.selectbox("Site", sorted(df["site_id"].unique()))
    with col2:
        kpi = st.selectbox("KPI", KPIS)

    site_df = df[df["site_id"] == site_id].sort_values("timestamp")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=site_df["timestamp"], y=site_df[kpi], name="Actual", line=dict(color="#4C78A8")))
    fig.add_trace(
        go.Scatter(
            x=site_df["timestamp"], y=site_df[f"{kpi}_pred"], name="Predicted", line=dict(color="#F58518", dash="dash")
        )
    )

    anomalies = site_df[site_df["is_anomaly"] == 1]
    if not anomalies.empty:
        fig.add_trace(
            go.Scatter(
                x=anomalies["timestamp"],
                y=anomalies[kpi],
                name="Anomaly",
                mode="markers",
                marker=dict(color="red", size=9, symbol="x"),
            )
        )

    fig.update_layout(height=450, xaxis_title="Time", yaxis_title=kpi, legend=dict(orientation="h"))
    st.plotly_chart(fig, width='stretch')

    st.subheader("Flagged Anomalies")
    site_anomalies = site_df[site_df["is_anomaly"] == 1].copy()

    if site_anomalies.empty:
        st.info("No anomalies flagged for this site in the selected window.")
    else:
        site_anomalies = add_explanations(site_anomalies)
        display_cols = ["timestamp", "anomaly_confidence", "explanation"] + [f"{k}_zscore" for k in KPIS]
        st.dataframe(
            site_anomalies[display_cols].sort_values("anomaly_confidence", ascending=False),
            width='stretch',
        )

    st.subheader("Network-Wide Summary")
    summary = (
        df.groupby("site_id")["is_anomaly"]
        .sum()
        .reset_index()
        .rename(columns={"is_anomaly": "anomaly_count"})
        .sort_values("anomaly_count", ascending=False)
    )
    st.bar_chart(summary.set_index("site_id").head(15))

with tab_copilot:
    incidents = store.list()
    if not incidents:
        st.info("No incidents detected in the current dataset.")
    else:
        status_priority = {
            "open": 0,
            "diagnosed": 1,
            "pending_approval": 1,
            "approved": 2,
            "auto_healed": 2,
            "rejected": 3,
            "resolved": 4,
        }
        incidents = sorted(incidents, key=lambda i: status_priority.get(i.status, 5))

        incident_ids = [i.id for i in incidents]
        labels = {
            i.id: f"{i.site_id} · {i.dominant_kpi} · {i.fault_signature} · [{i.status}]" for i in incidents
        }
        selected_id = st.selectbox(
            "Incident",
            incident_ids,
            format_func=lambda incident_id: labels[incident_id],
            key="incident_selectbox",
        )
        incident = store.get(selected_id)

        col_a, col_b = st.columns([2, 1])

        with col_a:
            st.markdown(f"**{incident.explanation}**")
            st.caption(f"Site {incident.site_id} · peak at {incident.timestamp} · severity: {incident.severity}")

            readings_df = pd.DataFrame([r.model_dump() for r in incident.readings])
            st.dataframe(readings_df, width='stretch', hide_index=True)

            if incident.diagnosis is None:
                if st.button("Diagnose incident", key=f"diagnose_{incident.id}"):
                    diagnosis = diagnose_incident(incident)
                    store.set_diagnosis(incident.id, diagnosis)
                    st.rerun()
            else:
                diagnosis = incident.diagnosis
                source_badge = "🤖 Claude" if diagnosis.source == "claude" else "📖 Demo (playbook-grounded)"
                st.markdown(f"**Diagnosis** — {source_badge}")
                st.write(f"**Root cause:** {diagnosis.root_cause}")
                st.write(f"**Blast radius:** {diagnosis.blast_radius}")
                st.write(f"**Risk level:** {diagnosis.risk_level}  ·  **Confidence:** {diagnosis.confidence:.2f}")
                st.write("**Runbook:**")
                for i, step in enumerate(diagnosis.runbook, 1):
                    st.write(f"{i}. {step}")

                decision = decide(diagnosis)
                if decision.gate == "AUTO":
                    st.success(f"AUTO-HEALED — {decision.rationale}")
                    if incident.status not in ("auto_healed", "approved", "rejected", "resolved"):
                        apply_remediation(store, incident, decision, actor="aura-agent")
                        st.rerun()
                else:
                    st.warning(f"NEEDS APPROVAL — {decision.rationale}")
                    if incident.status not in ("approved", "rejected", "resolved"):
                        c1, c2 = st.columns(2)
                        if c1.button("Approve", key=f"approve_{incident.id}"):
                            apply_remediation(store, incident, decision, actor="human", approved=True)
                            st.rerun()
                        if c2.button("Reject", key=f"reject_{incident.id}"):
                            apply_remediation(store, incident, decision, actor="human", approved=False)
                            st.rerun()
                    else:
                        st.write(f"Status: **{incident.status}**")

                st.markdown("---")
                st.markdown("**Ask AURA about this incident**")
                history_key = f"chat_history_{incident.id}"
                if history_key not in st.session_state:
                    st.session_state[history_key] = []

                for role, text in st.session_state[history_key]:
                    st.chat_message("user" if role == "user" else "assistant").write(text)

                question = st.chat_input("Ask a question about this incident", key=f"chat_input_{incident.id}")
                if question:
                    answer = chat(incident, diagnosis, question, st.session_state[history_key])
                    st.session_state[history_key].append(("user", question))
                    st.session_state[history_key].append(("assistant", answer))
                    st.rerun()

        with col_b:
            st.markdown("**Audit Trail**")
            trail = store.audit_trail(incident.id)
            if trail:
                trail_df = pd.DataFrame([r.model_dump() for r in trail])
                st.dataframe(trail_df, width='stretch', hide_index=True)
            else:
                st.caption("No actions recorded yet for this incident.")

        st.markdown("---")
        st.markdown("**Full Audit Ledger (all incidents)**")
        full_trail = store.audit_trail()
        if full_trail:
            st.dataframe(pd.DataFrame([r.model_dump() for r in full_trail]), width='stretch', hide_index=True)
        else:
            st.caption("No remediation actions recorded yet.")
