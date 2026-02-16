from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import plotly.express as px


def find_latest_snapshot(results_dir: Path) -> Path:
    files = sorted(results_dir.glob("snapshot_*.csv"))
    if not files:
        raise FileNotFoundError(f"No snapshot CSV files found in {results_dir}")
    return files[-1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build EMAtrix local 2D/3D charts from latest snapshot CSV")
    parser.add_argument("--results-dir", default="results", help="Directory with snapshot_YYYY-MM-DD.csv files")
    parser.add_argument("--input", default="", help="Optional explicit snapshot CSV path")
    parser.add_argument("--output-dir", default="dashboards", help="Output directory for generated HTML charts")
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    snapshot_path = Path(args.input) if args.input else find_latest_snapshot(results_dir)
    df = pd.read_csv(snapshot_path)

    # Add analysis-friendly derived columns.
    df["dist_to_ema200_pct"] = ((df["close"] - df["ema_200"]) / df["ema_200"]) * 100
    df["dist_to_ema48_pct"] = ((df["close"] - df["ema_48"]) / df["ema_48"]) * 100

    fig2d = px.scatter(
        df,
        x="dist_to_ema200_pct",
        y="rsi_14",
        color="dist_to_ema48_pct",
        hover_data=["symbol", "close", "ema_48", "ema_200", "volume"],
        title="EMAtrix 2D View: Distance to EMA200 vs RSI(14)",
    )

    fig3d = px.scatter_3d(
        df,
        x="dist_to_ema200_pct",
        y="dist_to_ema48_pct",
        z="rsi_14",
        color="rsi_14",
        size="volume",
        hover_name="symbol",
        title="EMAtrix 3D View: EMA Distance + RSI",
    )

    out2d = output_dir / "ematrix_2d_latest.html"
    out3d = output_dir / "ematrix_3d_latest.html"
    fig2d.write_html(out2d, include_plotlyjs="cdn")
    fig3d.write_html(out3d, include_plotlyjs="cdn")

    print(f"Built dashboard artifacts from {snapshot_path}:")
    print(f"- {out2d}")
    print(f"- {out3d}")


if __name__ == "__main__":
    main()
