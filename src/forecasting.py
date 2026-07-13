import joblib
import numpy as np
import optuna
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error

from src.config import KPIS

optuna.logging.set_verbosity(optuna.logging.WARNING)

NON_FEATURE_COLS = {"timestamp", "site_id"}


def _feature_columns_for_kpi(df, kpi):
    exclude = set(NON_FEATURE_COLS)
    for other_kpi in KPIS:
        exclude.add(f"{other_kpi}_is_fault")
    exclude.add(f"{kpi}_is_fault")
    exclude.update(k for k in KPIS)  # never leak raw current-timestep KPI values as features
    return [c for c in df.columns if c not in exclude]


def time_split(df, train_frac=0.7):
    df = df.sort_values("timestamp")
    cutoff = df["timestamp"].quantile(train_frac)
    train = df[df["timestamp"] <= cutoff]
    test = df[df["timestamp"] > cutoff]
    return train, test


def tune_and_train(train_df, test_df, kpi, n_trials=15):
    feature_cols = _feature_columns_for_kpi(train_df, kpi)
    X_train, y_train = train_df[feature_cols], train_df[kpi]
    X_test, y_test = test_df[feature_cols], test_df[kpi]

    def objective(trial):
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 50, 300),
            "max_depth": trial.suggest_int("max_depth", 3, 8),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
        }
        model = xgb.XGBRegressor(**params, objective="reg:squarederror", n_jobs=-1, random_state=42)
        model.fit(X_train, y_train)
        preds = model.predict(X_test)
        return mean_absolute_error(y_test, preds)

    study = optuna.create_study(direction="minimize")
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    best_model = xgb.XGBRegressor(
        **study.best_params, objective="reg:squarederror", n_jobs=-1, random_state=42
    )
    best_model.fit(X_train, y_train)

    return best_model, feature_cols, study.best_value


def train_all_kpis(features_df, kpis=KPIS, n_trials=15):
    train_df, test_df = time_split(features_df)
    models = {}
    for kpi in kpis:
        model, feature_cols, mae = tune_and_train(train_df, test_df, kpi, n_trials=n_trials)
        models[kpi] = {"model": model, "feature_cols": feature_cols, "test_mae": mae}
        print(f"{kpi}: test MAE = {mae:.4f}")
    return models, train_df, test_df


def predict_with_residuals(models, df):
    df = df.copy()
    for kpi, bundle in models.items():
        preds = bundle["model"].predict(df[bundle["feature_cols"]])
        df[f"{kpi}_pred"] = preds
        df[f"{kpi}_residual"] = df[kpi] - preds
    return df


if __name__ == "__main__":
    features = pd.read_csv("data/processed/features.csv", parse_dates=["timestamp"])
    models, train_df, test_df = train_all_kpis(features, n_trials=15)
    joblib.dump(models, "models/forecasting_models.pkl")

    test_with_preds = predict_with_residuals(models, test_df)
    test_with_preds.to_csv("data/processed/test_predictions.csv", index=False)
    print("Saved models/forecasting_models.pkl and data/processed/test_predictions.csv")
