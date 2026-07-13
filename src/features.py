import pandas as pd

from src.config import KPIS

ROLLING_WINDOWS = [4, 24, 96]  # steps at 15-min freq: 1h, 6h, 24h
LAGS = [1, 4, 96]


def add_time_features(df):
    df = df.copy()
    df["hour"] = df["timestamp"].dt.hour
    df["day_of_week"] = df["timestamp"].dt.dayofweek
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)
    return df


def add_rolling_and_lag_features(df, kpis=KPIS):
    df = df.sort_values(["site_id", "timestamp"]).copy()
    grouped = df.groupby("site_id")

    for kpi in kpis:
        for window in ROLLING_WINDOWS:
            df[f"{kpi}_roll_mean_{window}"] = grouped[kpi].transform(
                lambda s: s.rolling(window, min_periods=1).mean()
            )
            df[f"{kpi}_roll_std_{window}"] = grouped[kpi].transform(
                lambda s: s.rolling(window, min_periods=1).std()
            ).fillna(0)

        for lag in LAGS:
            df[f"{kpi}_lag_{lag}"] = grouped[kpi].shift(lag)

        df[f"{kpi}_rate_of_change"] = grouped[kpi].diff().fillna(0)

    return df


def build_feature_table(df, kpis=KPIS):
    df = add_time_features(df)
    df = add_rolling_and_lag_features(df, kpis)
    df = df.dropna().reset_index(drop=True)
    return df


if __name__ == "__main__":
    raw = pd.read_csv("data/raw/simulated_kpis.csv", parse_dates=["timestamp"])
    features = build_feature_table(raw)
    features.to_csv("data/processed/features.csv", index=False)
    print(f"Feature table shape: {features.shape}")
