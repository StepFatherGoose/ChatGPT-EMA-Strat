# EMA/RSI Backtesting Module

This repository includes a standalone backtesting CLI in `backtest.py` with pluggable components for:

- **Signal generation** from EMA crossover + RSI filter
- **Execution timing model** (`next_open` or `next_close`)
- **Trading frictions** (commission + slippage in bps)
- **Baseline benchmark** comparison against **SPY**
- **Performance report output**: CAGR, max drawdown, Sharpe, win rate, and exposure

## Requirements

- Python 3.9+
- `pandas`, `numpy`
- `yfinance` (only required when using live ticker download instead of `--csv`)

Example install:

```bash
pip install pandas numpy yfinance
```

## CLI usage

### 1) Backtest SPY with default settings

```bash
python backtest.py \
  --symbol SPY \
  --start 2019-01-01 \
  --end 2024-12-31 \
  --output-dir results/backtests \
  --tag spy_default
```

### 2) Backtest QQQ with custom EMA/RSI + costs + next close execution

```bash
python backtest.py \
  --symbol QQQ \
  --ema-fast 10 \
  --ema-slow 30 \
  --rsi-period 14 \
  --rsi-overbought 68 \
  --rsi-oversold 35 \
  --execution-model next_close \
  --commission-bps 2 \
  --slippage-bps 3 \
  --start 2018-01-01 \
  --end 2024-12-31 \
  --output-dir results/backtests \
  --tag qqq_custom
```

### 3) Backtest from a local CSV file

CSV should include at least `Date`, `Open`, and `Close` columns.

```bash
python backtest.py \
  --symbol SPY \
  --csv data/spy_daily.csv \
  --execution-model next_open \
  --output-dir results/backtests \
  --tag spy_csv
```

## Output artifacts

All output is written to `results/backtests/`:

- `<tag>_<timestamp>.csv` with daily signals/positions/returns/costs/equity
- `<tag>_<timestamp>.json` with performance summary for strategy and SPY benchmark

