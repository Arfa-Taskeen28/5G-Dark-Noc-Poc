import numpy as np
import pandas as pd

from src.config import KPIS


def explain_row(row, kpis=KPIS, top_n=2):
    contributions = []
    for kpi in kpis:
        z = row.get(f"{kpi}_zscore", 0)
        contributions.append((kpi, abs(z), z))

    contributions.sort(key=lambda x: x[1], reverse=True)
    top = [c for c in contributions[:top_n] if c[1] > 1.0]

    if not top:
        return "No single KPI stands out; anomaly driven by a combined multi-KPI pattern."

    parts = []
    for kpi, _, z in top:
        direction = "spiked above" if z > 0 else "dropped below"
        parts.append(f"{kpi.replace('_', ' ')} {direction} expected range (z={z:.1f})")

    return "Flagged because " + " and ".join(parts) + "."


def add_explanations(df, kpis=KPIS, top_n=2):
    df = df.copy()
    df["explanation"] = df.apply(lambda row: explain_row(row, kpis, top_n), axis=1)
    return df


if __name__ == "__main__":
    scored_df = pd.read_csv("data/processed/scored_predictions.csv", parse_dates=["timestamp"])
    anomalies = scored_df[scored_df["is_anomaly"] == 1].copy()
    anomalies = add_explanations(anomalies)
    anomalies.to_csv("data/processed/explained_anomalies.csv", index=False)
    print(anomalies[["timestamp", "site_id", "anomaly_confidence", "explanation"]].head(10).to_string())
