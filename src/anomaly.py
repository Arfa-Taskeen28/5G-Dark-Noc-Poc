import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from src.config import KPIS, ANOMALY_ZSCORE_THRESHOLD


def compute_residual_zscores(df, kpis=KPIS):
    df = df.copy()
    for kpi in kpis:
        residual_col = f"{kpi}_residual"
        mean = df[residual_col].mean()
        std = df[residual_col].std() or 1e-6
        df[f"{kpi}_zscore"] = (df[residual_col] - mean) / std
    return df


def zscore_flags(df, kpis=KPIS, threshold=ANOMALY_ZSCORE_THRESHOLD):
    df = df.copy()
    for kpi in kpis:
        df[f"{kpi}_zflag"] = (df[f"{kpi}_zscore"].abs() > threshold).astype(int)
    return df


def fit_isolation_forest(df, kpis=KPIS, contamination=0.05):
    residual_cols = [f"{kpi}_residual" for kpi in kpis]
    model = IsolationForest(contamination=contamination, random_state=42, n_estimators=200)
    model.fit(df[residual_cols])
    return model, residual_cols


def score_isolation_forest(df, model, residual_cols):
    df = df.copy()
    raw_scores = model.decision_function(df[residual_cols])
    df["iso_forest_score"] = raw_scores
    df["iso_forest_flag"] = (model.predict(df[residual_cols]) == -1).astype(int)
    return df


def compute_confidence_score(df):
    df = df.copy()
    zscore_cols = [c for c in df.columns if c.endswith("_zscore")]
    max_abs_z = df[zscore_cols].abs().max(axis=1)
    z_component = np.clip(max_abs_z / (ANOMALY_ZSCORE_THRESHOLD * 2), 0, 1)

    iso_min, iso_max = df["iso_forest_score"].min(), df["iso_forest_score"].max()
    iso_range = (iso_max - iso_min) or 1e-6
    iso_component = 1 - (df["iso_forest_score"] - iso_min) / iso_range

    df["anomaly_confidence"] = (0.5 * z_component + 0.5 * iso_component).clip(0, 1)
    df["is_anomaly"] = ((df["anomaly_confidence"] > 0.6) | (df["iso_forest_flag"] == 1)).astype(int)
    return df


def run_anomaly_pipeline(df, kpis=KPIS, iso_model=None, residual_cols=None):
    df = compute_residual_zscores(df, kpis)
    df = zscore_flags(df, kpis)

    if iso_model is None:
        iso_model, residual_cols = fit_isolation_forest(df, kpis)

    df = score_isolation_forest(df, iso_model, residual_cols)
    df = compute_confidence_score(df)
    return df, iso_model, residual_cols


if __name__ == "__main__":
    test_df = pd.read_csv("data/processed/test_predictions.csv", parse_dates=["timestamp"])
    scored_df, iso_model, residual_cols = run_anomaly_pipeline(test_df)

    joblib.dump({"model": iso_model, "residual_cols": residual_cols}, "models/isolation_forest.pkl")
    scored_df.to_csv("data/processed/scored_predictions.csv", index=False)

    n_flagged = scored_df["is_anomaly"].sum()
    print(f"Flagged {n_flagged} / {len(scored_df)} rows as anomalies")
