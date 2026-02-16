# EMAtrix (US Daily EMA/RSI Scanner)

EMAtrix runs a daily post-market scan for US stocks and flags symbols in this research band:

- `close > ema_200`
- `close < ema_48`
- `rsi_14 < 55`

It also builds a yellow watchlist for symbols within a configurable tolerance of entering the green band.

## Free API option (now default)

You asked for a free online API path. EMAtrix now supports:

- `DATA_PROVIDER=stooq` (**default**, free/no key)
- `DATA_PROVIDER=alpaca` (if you prefer Alpaca)

Stooq mode uses:
- SEC public company ticker list for symbol discovery
- Stooq daily CSV endpoint for OHLCV bars

## Quick start (non-technical)

```bash
./setup_and_run.sh
```

What this does:
1. Creates `.venv`
2. Installs dependencies
3. Creates `.env` from `.env.example` if missing
4. Runs config check
5. Runs safe dry-run (`--dry-run --max-symbols 200`)

## Main commands

```bash
python scanner.py --check-config
python scanner.py --dry-run --max-symbols 200
python scanner.py
```

## Output files

- `results/scan_YYYY-MM-DD.csv` (green band)
- `results/yellow_YYYY-MM-DD.csv` (near-green)
- `results/snapshot_YYYY-MM-DD.csv` (full latest snapshot, visualization-ready)

## 2D + 3D charts

After you have a snapshot CSV:

```bash
python build_dashboard.py
```

Creates:
- `dashboards/ematrix_2d_latest.html`
- `dashboards/ematrix_3d_latest.html`

## Environment variables

Core:
- `DATA_PROVIDER=stooq|alpaca`
- `LOOKBACK_DAYS`
- `SYMBOL_LIMIT`
- `YELLOW_TOLERANCE_PCT`
- `RESULTS_DIR`

Stooq mode:
- `STOOQ_SYMBOL_SOURCE=sec`

Alpaca mode:
- `ALPACA_API_KEY`
- `ALPACA_API_SECRET`
- `ALPACA_BASE_URL`
- `ALPACA_DATA_URL`
- `ALPACA_DATA_FEED`

Optional integrations:
- `DISCORD_WEBHOOK_URL`
- `GOOGLE_SHEET_ID`
- `GOOGLE_SERVICE_ACCOUNT_FILE`

Kalshi demo scaffold:
- `KALSHI_BASE_URL`
- `KALSHI_EMAIL`
- `KALSHI_PASSWORD`

## Google Sheets dashboard tabs

When configured, EMAtrix updates:
- `scan_YYYY_MM_DD`
- `dashboard_summary`
- `dashboard_green`
- `dashboard_yellow`
- `dashboard_snapshot`

## Discord notifications

When configured, EMAtrix sends:
1. Daily summary
2. New entries
3. Remaining in band
4. Exited band

## Schedule suggestion

Run at ~6:00 PM ET on market weekdays.
