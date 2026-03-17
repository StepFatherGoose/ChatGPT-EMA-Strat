#!/usr/bin/env python3
"""Simple, pluggable EMA/RSI backtesting module.

Features:
- Signal generation from EMA + RSI
- Execution timing model (next_open / next_close)
- Commission/slippage modeling
- Baseline benchmark (SPY)
- Performance report output
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd


@dataclass
class SignalConfig:
    ema_fast: int = 12
    ema_slow: int = 26
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0


@dataclass
class ExecutionConfig:
    model: str = "next_open"  # next_open | next_close


@dataclass
class CostConfig:
    commission_bps: float = 1.0
    slippage_bps: float = 1.0


class EMARsiSignalGenerator:
    def __init__(self, config: SignalConfig):
        self.config = config

    @staticmethod
    def _rsi(close: pd.Series, period: int) -> pd.Series:
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
        avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return rsi.fillna(50)

    def generate(self, df: pd.DataFrame) -> pd.Series:
        close = df["Close"]
        ema_fast = close.ewm(span=self.config.ema_fast, adjust=False).mean()
        ema_slow = close.ewm(span=self.config.ema_slow, adjust=False).mean()
        rsi = self._rsi(close, self.config.rsi_period)

        long_condition = (ema_fast > ema_slow) & (rsi > self.config.rsi_oversold) & (rsi < self.config.rsi_overbought)
        return long_condition.astype(float)


class Backtester:
    def __init__(
        self,
        signal_generator: EMARsiSignalGenerator,
        execution: ExecutionConfig,
        costs: CostConfig,
    ):
        self.signal_generator = signal_generator
        self.execution = execution
        self.costs = costs

    def _position_from_signal(self, signal: pd.Series) -> pd.Series:
        if self.execution.model == "next_open":
            lag = 1
        elif self.execution.model == "next_close":
            lag = 2
        else:
            raise ValueError(f"Unsupported execution model: {self.execution.model}")

        return signal.shift(lag).fillna(0.0)

    def run(self, df: pd.DataFrame) -> pd.DataFrame:
        signal = self.signal_generator.generate(df)
        position = self._position_from_signal(signal)

        # Close-to-close returns for simplicity.
        asset_returns = df["Close"].pct_change().fillna(0.0)
        gross_returns = position * asset_returns

        turnover = position.diff().abs().fillna(position.abs())
        total_bps = self.costs.commission_bps + self.costs.slippage_bps
        costs = turnover * (total_bps / 10_000)

        strategy_returns = gross_returns - costs

        out = pd.DataFrame(
            {
                "Close": df["Close"],
                "signal": signal,
                "position": position,
                "asset_return": asset_returns,
                "strategy_return": strategy_returns,
                "costs": costs,
            }
        )
        out["equity_curve"] = (1 + out["strategy_return"]).cumprod()
        return out


def compute_metrics(returns: pd.Series, position: pd.Series) -> Dict[str, float]:
    returns = returns.fillna(0.0)
    periods = max(len(returns), 1)
    annualization = 252

    equity = (1 + returns).cumprod()
    ending = float(equity.iloc[-1])
    years = periods / annualization
    cagr = (ending ** (1 / years) - 1) if years > 0 else 0.0

    rolling_max = equity.cummax()
    drawdown = equity / rolling_max - 1
    max_drawdown = float(drawdown.min())

    volatility = returns.std(ddof=0) * np.sqrt(annualization)
    sharpe = float((returns.mean() * annualization) / volatility) if volatility > 0 else 0.0

    trades = position.diff().fillna(position).abs() > 0
    trade_returns = returns[trades]
    win_rate = float((trade_returns > 0).mean()) if len(trade_returns) > 0 else 0.0

    exposure = float((position > 0).mean())

    return {
        "CAGR": float(cagr),
        "MaxDrawdown": max_drawdown,
        "Sharpe": sharpe,
        "WinRate": win_rate,
        "Exposure": exposure,
        "TotalReturn": ending - 1,
    }


def load_price_data(symbol: str, csv_path: Optional[str], start: str, end: str) -> pd.DataFrame:
    if csv_path:
        df = pd.read_csv(csv_path, parse_dates=["Date"]).set_index("Date")
    else:
        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError("yfinance is required when --csv is not provided.") from exc

        df = yf.download(symbol, start=start, end=end, auto_adjust=False, progress=False)
        if df.empty:
            raise RuntimeError(f"No data downloaded for symbol={symbol}")

    required = {"Open", "Close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns in data: {missing}")

    return df.sort_index().dropna(subset=["Open", "Close"])


def build_report(strategy_df: pd.DataFrame, benchmark_close: pd.Series) -> Dict[str, Dict[str, float]]:
    strategy_metrics = compute_metrics(strategy_df["strategy_return"], strategy_df["position"])

    benchmark_returns = benchmark_close.pct_change().fillna(0.0)
    benchmark_position = pd.Series(1.0, index=benchmark_returns.index)
    benchmark_metrics = compute_metrics(benchmark_returns, benchmark_position)

    return {
        "strategy": strategy_metrics,
        "benchmark_spy": benchmark_metrics,
    }


def save_outputs(result_df: pd.DataFrame, report: Dict[str, Dict[str, float]], output_dir: str, tag: str) -> None:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    base = out_dir / f"{tag}_{ts}"

    csv_path = base.with_suffix(".csv")
    json_path = base.with_suffix(".json")

    result_df.to_csv(csv_path, index_label="Date")
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"Saved detailed returns to: {csv_path}")
    print(f"Saved report to: {json_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="EMA/RSI backtester with pluggable components")

    parser.add_argument("--symbol", default="SPY", help="Ticker symbol to test")
    parser.add_argument("--csv", default=None, help="Optional CSV with Date/Open/Close columns")
    parser.add_argument("--start", default="2018-01-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default=datetime.utcnow().strftime("%Y-%m-%d"), help="End date YYYY-MM-DD")

    parser.add_argument("--ema-fast", type=int, default=12)
    parser.add_argument("--ema-slow", type=int, default=26)
    parser.add_argument("--rsi-period", type=int, default=14)
    parser.add_argument("--rsi-overbought", type=float, default=70.0)
    parser.add_argument("--rsi-oversold", type=float, default=30.0)

    parser.add_argument("--execution-model", choices=["next_open", "next_close"], default="next_open")
    parser.add_argument("--commission-bps", type=float, default=1.0)
    parser.add_argument("--slippage-bps", type=float, default=1.0)

    parser.add_argument("--benchmark", default="SPY", help="Benchmark ticker (default: SPY)")
    parser.add_argument("--output-dir", default="results/backtests")
    parser.add_argument("--tag", default="backtest")

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    price_df = load_price_data(args.symbol, args.csv, args.start, args.end)

    signal_cfg = SignalConfig(
        ema_fast=args.ema_fast,
        ema_slow=args.ema_slow,
        rsi_period=args.rsi_period,
        rsi_overbought=args.rsi_overbought,
        rsi_oversold=args.rsi_oversold,
    )
    execution_cfg = ExecutionConfig(model=args.execution_model)
    cost_cfg = CostConfig(commission_bps=args.commission_bps, slippage_bps=args.slippage_bps)

    bt = Backtester(EMARsiSignalGenerator(signal_cfg), execution_cfg, cost_cfg)
    strategy_df = bt.run(price_df)

    if args.benchmark.upper() == args.symbol.upper():
        benchmark_close = price_df["Close"].reindex(strategy_df.index)
    else:
        benchmark_df = load_price_data(args.benchmark, None, args.start, args.end)
        benchmark_close = benchmark_df["Close"].reindex(strategy_df.index).ffill().bfill()

    report = build_report(strategy_df, benchmark_close)

    print("Performance report")
    print(json.dumps(report, indent=2))

    save_outputs(strategy_df, report, args.output_dir, args.tag)


if __name__ == "__main__":
    main()
