#!/usr/bin/env python3
"""SPY intraday analysis for first-30-minute move vs. high-of-day timing.

Usage:
    python spy_first30_hod_analysis.py --input spy_1min.csv --output-dir outputs

Expected CSV columns (case-insensitive):
    - timestamp (or datetime)
    - open
    - high

Optional:
    - timezone of timestamps can be provided with --input-tz if naive.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

RTH_TZ = "America/New_York"
DEFAULT_THRESHOLDS = [0.005, 0.0075, 0.01, 0.0125, 0.015]


@dataclass(frozen=True)
class AnalysisConfig:
    input_csv: Path
    output_dir: Path
    thresholds: list[float]
    input_tz: str | None = None


def parse_args() -> AnalysisConfig:
    parser = argparse.ArgumentParser(
        description=(
            "Analyze whether positive move in first 30 minutes predicts that "
            "the day high was established before 10:00 ET."
        )
    )
    parser.add_argument("--input", required=True, type=Path, help="Path to 1-minute CSV data")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("analysis_output"),
        help="Directory to write summary CSV and chart",
    )
    parser.add_argument(
        "--thresholds",
        type=float,
        nargs="*",
        default=DEFAULT_THRESHOLDS,
        help="Thresholds for (first30_high - session_open)/session_open",
    )
    parser.add_argument(
        "--input-tz",
        default=None,
        help=(
            "Timezone name for naive input timestamps (e.g. America/New_York). "
            "If omitted, naive timestamps are assumed to already be ET."
        ),
    )

    args = parser.parse_args()
    return AnalysisConfig(
        input_csv=args.input,
        output_dir=args.output_dir,
        thresholds=sorted(set(args.thresholds)),
        input_tz=args.input_tz,
    )


def _find_col(columns: Iterable[str], candidates: list[str]) -> str | None:
    normalized = {c.lower().strip(): c for c in columns}
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]
    return None


def load_and_prepare_data(input_csv: Path, input_tz: str | None) -> pd.DataFrame:
    if not input_csv.exists():
        raise FileNotFoundError(f"Input file not found: {input_csv}")

    df = pd.read_csv(input_csv)
    if df.empty:
        raise ValueError("Input CSV is empty.")

    ts_col = _find_col(df.columns, ["timestamp", "datetime", "date", "time"])
    open_col = _find_col(df.columns, ["open"])
    high_col = _find_col(df.columns, ["high"])

    missing = [
        name
        for name, col in [("timestamp", ts_col), ("open", open_col), ("high", high_col)]
        if col is None
    ]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    out = df[[ts_col, open_col, high_col]].copy()
    out.columns = ["timestamp", "open", "high"]

    out["timestamp"] = pd.to_datetime(out["timestamp"], errors="coerce")
    out = out.dropna(subset=["timestamp", "open", "high"]).copy()

    # Handle timezone conversion safely.
    if out["timestamp"].dt.tz is None:
        source_tz = input_tz or RTH_TZ
        out["timestamp"] = out["timestamp"].dt.tz_localize(source_tz)

    out["timestamp"] = out["timestamp"].dt.tz_convert(RTH_TZ)

    # Handle duplicate bars safely by keeping the first observed bar per minute.
    out = out.sort_values("timestamp")
    out = out.drop_duplicates(subset=["timestamp"], keep="first")

    # Keep only regular trading hours 9:30 to 16:00 ET.
    out = out.set_index("timestamp").sort_index()
    out = out.between_time("09:30", "16:00", inclusive="both")

    # Remove days with missing key bars/windows.
    out["session_date"] = out.index.tz_convert(RTH_TZ).date
    return out


def compute_daily_metrics(rth_df: pd.DataFrame) -> pd.DataFrame:
    records: list[dict] = []

    for session_date, day_df in rth_df.groupby("session_date", sort=True):
        day_df = day_df.sort_index()

        # Require exact 9:30 open bar.
        open_bar_ts = day_df.between_time("09:30", "09:30").index
        if len(open_bar_ts) == 0:
            continue

        session_open_ts = open_bar_ts[0]
        session_open = float(day_df.loc[session_open_ts, "open"])

        # 9:30 <= t < 10:00 first 30 minutes (exclude 10:00).
        first30_df = day_df.between_time("09:30", "09:59", inclusive="both")
        if first30_df.empty:
            continue

        first30_high = float(first30_df["high"].max())

        # Full RTH day high: 9:30 <= t <= 16:00.
        day_high = float(day_df["high"].max())
        day_high_time = day_df.index[day_df["high"] == day_high][0]

        records.append(
            {
                "session_date": pd.Timestamp(session_date),
                "session_open": session_open,
                "first30_high": first30_high,
                "day_high": day_high,
                "day_high_time": day_high_time,
            }
        )

    if not records:
        return pd.DataFrame(
            columns=["session_date", "session_open", "first30_high", "day_high", "day_high_time"]
        )

    daily = pd.DataFrame.from_records(records).sort_values("session_date").reset_index(drop=True)
    daily["first30_move_pct"] = (daily["first30_high"] - daily["session_open"]) / daily["session_open"]
    daily["hod_in_first30"] = daily["day_high_time"].dt.time < pd.Timestamp("10:00", tz=RTH_TZ).time()
    return daily


def summarize_thresholds(daily: pd.DataFrame, thresholds: list[float]) -> pd.DataFrame:
    rows: list[dict] = []

    for threshold in thresholds:
        qualifying = daily[daily["first30_move_pct"] >= threshold]
        qualifying_days = int(len(qualifying))
        successes = int(qualifying["hod_in_first30"].sum()) if qualifying_days else 0
        probability = (successes / qualifying_days) if qualifying_days else np.nan

        rows.append(
            {
                "threshold": threshold,
                "qualifying_days": qualifying_days,
                "high_established_first30_days": successes,
                "probability": probability,
            }
        )

    return pd.DataFrame(rows)


def plot_probabilities(summary: pd.DataFrame, output_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(summary["threshold"], summary["probability"], marker="o")
    ax.set_title("Probability HOD Established in First 30 Minutes vs Threshold")
    ax.set_xlabel("Threshold: (first30_high - session_open) / session_open")
    ax.set_ylabel("Probability")
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def main() -> None:
    config = parse_args()
    config.output_dir.mkdir(parents=True, exist_ok=True)

    rth_df = load_and_prepare_data(config.input_csv, config.input_tz)
    daily = compute_daily_metrics(rth_df)
    if daily.empty:
        raise ValueError(
            "No valid sessions found after filtering. Check that data contains 1-minute RTH bars with 9:30 open."
        )

    summary = summarize_thresholds(daily, config.thresholds)

    summary_csv = config.output_dir / "threshold_summary.csv"
    daily_csv = config.output_dir / "daily_metrics.csv"
    plot_png = config.output_dir / "threshold_probability.png"

    summary.to_csv(summary_csv, index=False)
    daily.to_csv(daily_csv, index=False)
    plot_probabilities(summary, plot_png)

    print("\nSummary table:")
    print(summary.to_string(index=False))
    print(f"\nSaved summary: {summary_csv}")
    print(f"Saved daily metrics: {daily_csv}")
    print(f"Saved chart: {plot_png}")


if __name__ == "__main__":
    main()
