# AURA — AI-Native Networks: Predictive Fault Detection & Autonomous Remediation Copilot

5G Academy 2026 (Fastweb + Vodafone track) project. Forecasts network KPI behavior per site,
flags anomalies with a confidence score, diagnoses root cause against a vetted playbook, and
gates remediation on trust — targeting the "Decision" gap on the path to TM Forum Autonomous
Networks Level 4.

Link to run: https://5g-dark-noc-poc-nyhejhxs6zsbcuffqupphf.streamlit.app/

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows
pip install -r requirements.txt
```

## Enable the Claude-powered agent (optional)

Without an API key, AURA runs in **demo mode**: diagnoses are still grounded in the vetted
playbook library (`src/agent/playbooks.py`), just phrased deterministically instead of via a
live LLM call. To get live Claude-generated diagnoses and chat:

**Local:**
```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# edit .streamlit/secrets.toml and paste your key
```
(or set the `ANTHROPIC_API_KEY` environment variable instead)

**Streamlit Community Cloud:** App settings -> Secrets -> paste `ANTHROPIC_API_KEY = "sk-ant-..."`

Any failure in the live call (bad key, network issue) automatically falls back to demo mode —
the live dashboard never crashes on this path.

## Run

```bash
streamlit run app/dashboard.py
```

## Rebuild the data/model pipeline

```bash
python -m src.data_simulation
python -m src.features
python -m src.forecasting
python -m src.anomaly
```

## Project layout

- `src/data_simulation.py` — synthetic per-site KPI time series with injected faults
- `src/features.py` — feature engineering (rolling stats, lags, time encodings)
- `src/forecasting.py` — XGBoost + Optuna forecasting model
- `src/anomaly.py` — residual-based + Isolation Forest anomaly scoring
- `src/explain.py` — feature-importance based explanation for flagged anomalies
- `src/agent/schemas.py` — data contracts for the agentic layer (Incident, Diagnosis, RemediationDecision, AuditRecord)
- `src/agent/playbooks.py` — grounded knowledge base of remediation playbooks per (KPI, fault signature)
- `src/agent/store.py` — groups anomalies into incidents, persists status/diagnosis/audit trail (JSON)
- `src/agent/copilot.py` — diagnosis + chat agent (Claude when a key is set, playbook-grounded demo mode otherwise)
- `src/agent/remediation.py` — confidence-gated trust calibration (AUTO-heal vs. NEEDS_APPROVAL) + audit logging
- `app/dashboard.py` — Streamlit UI: fault timeline + AURA Copilot tab
- `tests/` — unit tests

## Note on persistence

The incident/audit log (`data/processed/audit_log.json`) persists for the life of the running
app instance but resets on a Streamlit Cloud cold restart/redeploy — acceptable for a live PoC
demo, not intended as durable production storage.
