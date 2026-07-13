# AI-Native Networks — Predictive Fault & Anomaly Detection (Dark NOC PoC)

5G Academy 2026 (Fastweb + Vodafone track) project. Forecasts network KPI behavior per site,
flags anomalies with a confidence score, and explains why — targeting the "Decision" trust gap
on the path to TM Forum Autonomous Networks Level 4.

Link to run- https://5g-dark-noc-poc-nyhejhxs6zsbcuffqupphf.streamlit.app/

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows
pip install -r requirements.txt
```

## Run

```bash
streamlit run app/dashboard.py
```

## Project layout

- `src/data_simulation.py` — synthetic per-site KPI time series with injected faults
- `src/features.py` — feature engineering (rolling stats, lags, time encodings)
- `src/forecasting.py` — XGBoost + Optuna forecasting model
- `src/anomaly.py` — residual-based + Isolation Forest anomaly scoring
- `src/explain.py` — feature-importance based explanation for flagged anomalies
- `app/dashboard.py` — Streamlit demo dashboard
- `tests/` — unit tests
