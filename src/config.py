N_SITES = 30
N_DAYS = 60
FREQ_MINUTES = 15

KPIS = ["throughput_mbps", "latency_ms", "packet_loss_pct", "prb_utilization_pct"]

KPI_BASELINE = {
    "throughput_mbps": {"mean": 500.0, "daily_amplitude": 200.0, "noise_std": 15.0},
    "latency_ms": {"mean": 20.0, "daily_amplitude": 5.0, "noise_std": 1.5},
    "packet_loss_pct": {"mean": 0.5, "daily_amplitude": 0.2, "noise_std": 0.1},
    "prb_utilization_pct": {"mean": 55.0, "daily_amplitude": 25.0, "noise_std": 4.0},
}

FAULT_TYPES = ["gradual_degradation", "sudden_spike", "sudden_drop"]
FAULT_PROBABILITY_PER_SITE = 0.5
MIN_FAULT_DURATION_HOURS = 4
MAX_FAULT_DURATION_HOURS = 48

RANDOM_SEED = 42

ANOMALY_ZSCORE_THRESHOLD = 3.0
