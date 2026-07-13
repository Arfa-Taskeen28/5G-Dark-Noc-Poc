import pandas as pd

from src.config import KPIS
from src.data_simulation import generate_dataset


def test_generate_dataset_shape():
    df = generate_dataset(n_sites=3, n_days=2)
    expected_rows_per_site = int(2 * 24 * 60 / 15)
    assert len(df) == expected_rows_per_site * 3
    assert df["site_id"].nunique() == 3


def test_generate_dataset_has_kpi_columns():
    df = generate_dataset(n_sites=2, n_days=1)
    for kpi in KPIS:
        assert kpi in df.columns
        assert f"{kpi}_is_fault" in df.columns


def test_kpi_values_within_valid_ranges():
    df = generate_dataset(n_sites=5, n_days=3)
    assert (df["packet_loss_pct"] >= 0).all() and (df["packet_loss_pct"] <= 100).all()
    assert (df["prb_utilization_pct"] >= 0).all() and (df["prb_utilization_pct"] <= 100).all()
    assert (df["throughput_mbps"] >= 0).all()
    assert (df["latency_ms"] >= 0).all()


def test_fault_labels_are_binary():
    df = generate_dataset(n_sites=4, n_days=5)
    for kpi in KPIS:
        col = f"{kpi}_is_fault"
        assert set(df[col].unique()).issubset({0, 1})


def test_timestamps_are_sorted_per_site():
    df = generate_dataset(n_sites=2, n_days=1)
    for site_id, group in df.groupby("site_id"):
        assert group["timestamp"].is_monotonic_increasing
