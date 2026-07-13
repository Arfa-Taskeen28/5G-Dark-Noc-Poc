import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.config import KPIS
from src.explain import add_explanations

st.set_page_config(page_title="Dark NOC — Predictive Fault Detection", layout="wide")

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "processed" / "scored_predictions.csv"


@st.cache_data
def load_data():
    df = pd.read_csv(DATA_PATH, parse_dates=["timestamp"])
    return df


st.title("Predictive Fault & Anomaly Detection — Dark NOC PoC")
st.caption(
    "Forecasts network KPI behavior per site, flags anomalies with a confidence score, "
    "and explains why — closing the trust gap that blocks autonomous decision-making."
)

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

col1, col2 = st.columns([1, 1])
with col1:
    site_id = st.selectbox("Site", sorted(df["site_id"].unique()))
with col2:
    kpi = st.selectbox("KPI", KPIS)

site_df = df[df["site_id"] == site_id].sort_values("timestamp")

fig = go.Figure()
fig.add_trace(go.Scatter(x=site_df["timestamp"], y=site_df[kpi], name="Actual", line=dict(color="#4C78A8")))
fig.add_trace(
    go.Scatter(x=site_df["timestamp"], y=site_df[f"{kpi}_pred"], name="Predicted", line=dict(color="#F58518", dash="dash"))
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
st.plotly_chart(fig, use_container_width=True)

st.subheader("Flagged Anomalies")
site_anomalies = site_df[site_df["is_anomaly"] == 1].copy()

if site_anomalies.empty:
    st.info("No anomalies flagged for this site in the selected window.")
else:
    site_anomalies = add_explanations(site_anomalies)
    display_cols = ["timestamp", "anomaly_confidence", "explanation"] + [
        f"{k}_zscore" for k in KPIS
    ]
    st.dataframe(
        site_anomalies[display_cols].sort_values("anomaly_confidence", ascending=False),
        use_container_width=True,
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
