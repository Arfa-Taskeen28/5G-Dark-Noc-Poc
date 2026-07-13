import numpy as np
import pandas as pd

from src.config import (
    N_SITES,
    N_DAYS,
    FREQ_MINUTES,
    KPIS,
    KPI_BASELINE,
    FAULT_TYPES,
    FAULT_PROBABILITY_PER_SITE,
    MIN_FAULT_DURATION_HOURS,
    MAX_FAULT_DURATION_HOURS,
    RANDOM_SEED,
)


def _seasonal_component(timestamps, amplitude):
    hour_of_day = np.asarray(timestamps.hour) + np.asarray(timestamps.minute) / 60.0
    daily = np.sin((hour_of_day / 24.0) * 2 * np.pi - np.pi / 2)
    day_of_week = np.asarray(timestamps.dayofweek)
    weekday_scale = np.where(day_of_week < 5, 1.0, 0.7)
    return amplitude * daily * weekday_scale


def _inject_fault(values, rng, fault_type, start_idx, duration_steps, direction_sign):
    end_idx = min(start_idx + duration_steps, len(values))
    span = end_idx - start_idx
    if span <= 0:
        return values, (None, None)

    if fault_type == "gradual_degradation":
        ramp = np.linspace(0, 1, span)
        magnitude = direction_sign * ramp * values[start_idx:end_idx].std() * 4
        values[start_idx:end_idx] += magnitude
    elif fault_type == "sudden_spike":
        values[start_idx:end_idx] += direction_sign * abs(values[start_idx:end_idx].std()) * 6
    elif fault_type == "sudden_drop":
        values[start_idx:end_idx] -= abs(direction_sign) * abs(values[start_idx:end_idx].std()) * 6

    return values, (start_idx, end_idx)


def generate_site_kpi_data(site_id, timestamps, rng):
    n = len(timestamps)
    df = pd.DataFrame({"timestamp": timestamps, "site_id": site_id})
    fault_windows = {}

    for kpi in KPIS:
        params = KPI_BASELINE[kpi]
        seasonal = _seasonal_component(timestamps, params["daily_amplitude"])
        noise = rng.normal(0, params["noise_std"], size=n)
        values = params["mean"] + seasonal + noise

        fault_windows[kpi] = []
        if rng.random() < FAULT_PROBABILITY_PER_SITE:
            fault_type = rng.choice(FAULT_TYPES)
            duration_hours = rng.uniform(MIN_FAULT_DURATION_HOURS, MAX_FAULT_DURATION_HOURS)
            duration_steps = int(duration_hours * 60 / FREQ_MINUTES)
            start_idx = rng.integers(0, max(1, n - duration_steps))
            direction_sign = 1 if kpi in ("latency_ms", "packet_loss_pct", "prb_utilization_pct") else -1
            values, window = _inject_fault(values, rng, fault_type, start_idx, duration_steps, direction_sign)
            if window[0] is not None:
                fault_windows[kpi].append({"type": fault_type, "start": window[0], "end": window[1]})

        if kpi == "packet_loss_pct":
            values = np.clip(values, 0, 100)
        elif kpi == "prb_utilization_pct":
            values = np.clip(values, 0, 100)
        elif kpi == "throughput_mbps":
            values = np.clip(values, 0, None)
        elif kpi == "latency_ms":
            values = np.clip(values, 0, None)

        df[kpi] = values
        df[f"{kpi}_is_fault"] = 0
        for w in fault_windows[kpi]:
            df.loc[w["start"] : w["end"] - 1, f"{kpi}_is_fault"] = 1

    return df


def generate_dataset(n_sites=N_SITES, n_days=N_DAYS, freq_minutes=FREQ_MINUTES, seed=RANDOM_SEED):
    rng = np.random.default_rng(seed)
    timestamps = pd.date_range(
        start="2026-01-01", periods=int(n_days * 24 * 60 / freq_minutes), freq=f"{freq_minutes}min"
    )

    all_sites = []
    for i in range(n_sites):
        site_id = f"site_{i:03d}"
        site_df = generate_site_kpi_data(site_id, timestamps, rng)
        all_sites.append(site_df)

    return pd.concat(all_sites, ignore_index=True)


if __name__ == "__main__":
    df = generate_dataset()
    df.to_csv("data/raw/simulated_kpis.csv", index=False)
    print(f"Generated {len(df)} rows across {df['site_id'].nunique()} sites")
