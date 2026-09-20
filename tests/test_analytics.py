import pandas as pd

from vial_analytics import aggregate_per_vial, classify_vials


def _tracks_df(rows):
    return pd.DataFrame(rows, columns=["frame", "time_sec", "vial_id", "x", "y", "radius"])


def test_aggregate_computes_path_length_and_dwell_time():
    df = _tracks_df([
        (0, 0.0, 0, 0, 0, 20),
        (1, 0.1, 0, 3, 4, 20),   # moves exactly 5px
        (2, 0.2, 0, 3, 4, 20),   # stays put
    ])
    agg = aggregate_per_vial(df, fps=10)
    row = agg.iloc[0]
    assert row["frames_tracked"] == 3
    assert row["path_length_px"] == 5.0
    assert row["dwell_time_sec"] == 0.3


def test_classify_flags_size_anomaly():
    rows = []
    for vid in range(10):
        for f in range(5):
            rows.append((f, f / 10, vid, f, f, 20))
    for f in range(5):  # one deliberately oversized vial
        rows.append((f, f / 10, 99, f, f, 60))
    df = _tracks_df(rows)
    agg = classify_vials(aggregate_per_vial(df, fps=10))
    outlier = agg[agg["vial_id"] == 99].iloc[0]
    assert outlier["size_anomaly"]
    assert outlier["disposition"] in {"REVIEW", "REJECT"}


def test_classify_flags_low_confidence_as_excluded():
    df = _tracks_df([(0, 0.0, 5, 0, 0, 20)])  # single-frame track
    agg = classify_vials(aggregate_per_vial(df, fps=10), min_track_frames=3)
    assert agg.iloc[0]["disposition"] == "EXCLUDED"


def test_jam_alert_for_stationary_vial():
    rows = [(f, f / 10, 1, 100, 100, 20) for f in range(10)]  # never moves
    df = _tracks_df(rows)
    agg = classify_vials(aggregate_per_vial(df, fps=10), jam_min_frames=8, jam_max_path_px=15.0)
    assert bool(agg.iloc[0]["jam_alert"]) is True
