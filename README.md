# EMAtrix (US Daily EMA/RSI Scanner)

EMAtrix runs a **daily post-market scan** for US tradable equities and flags symbols in a research band:

- `close > ema_200`
- `close < ema_48`
- `rsi_14 < 55` (Wilder RSI)

It also builds a **yellow watchlist** for symbols within a configurable tolerance of entering the green band.

## What’s new for non-technical setup

- `setup_and_run.sh` creates a local virtual environment, installs dependencies, checks config, and runs a safe dry-run.
- `scanner.py --check-config` gives a guided config validation report.
- `scanner.py --dry-run` writes CSV outputs but skips Google Sheets and Discord notifications.
- `build_dashboard.py` generates local 2D and 3D HTML charts from the latest snapshot CSV.
- `kalshi_demo.py` is a starter scaffold for Kalshi demo configuration checks.

## Quick start (recommended)

```bash
./setup_and_run.sh
```

If `.env` does not exist, the script creates it from `.env.example` and stops so you can add your keys.

After adding keys, run again.

## Outputs

- Local CSV files:
  - `results/scan_YYYY-MM-DD.csv` (green band)
  - `results/yellow_YYYY-MM-DD.csv` (near-green)
  - `results/snapshot_YYYY-MM-DD.csv` (full latest-feature snapshot for all symbols)
- Google Sheets dashboard tabs (optional)
- Discord notifications (optional)

## Why this design

- Uses Alpaca assets API for a broker-like US tradable universe.
- Uses Alpaca daily market bars for indicator calculations.
- Exports full snapshot features so the data is ready for future 2D/3D analytics and visualization tooling.
- Tracks state across runs for **new / remaining / exited** green-band notifications.

## Setup

### 1) Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and fill your credentials.

## Environment variables

Required:

- `ALPACA_API_KEY`
- `ALPACA_API_SECRET`

Optional scanner settings:

- `ALPACA_BASE_URL` (default: `https://paper-api.alpaca.markets`)
- `ALPACA_DATA_URL` (default: `https://data.alpaca.markets`)
- `ALPACA_DATA_FEED` (default: `iex`)
- `LOOKBACK_DAYS` (default: `320`)
- `UNIVERSE_EXCHANGES` (default: `NYSE,NASDAQ,AMEX`)
- `INCLUDE_ETFS` (`true`/`false`, default: `true`)
- `YELLOW_TOLERANCE_PCT` (default: `10`)
- `DISCORD_WEBHOOK_URL`
- `GOOGLE_SHEET_ID`
- `GOOGLE_SERVICE_ACCOUNT_FILE`
- `RESULTS_DIR` (default: `results`)

Kalshi demo scaffold (optional):

- `KALSHI_BASE_URL` (default: `https://demo-api.kalshi.co`)
- `KALSHI_EMAIL`
- `KALSHI_PASSWORD`

## Run scanner

### Config check

```bash
python scanner.py --check-config
```

### Safe first run (no external notifications)

```bash
python scanner.py --dry-run --max-symbols 200
```

### Full run

```bash
python scanner.py
```

## Google Sheets tabs

When Google Sheets integration is enabled, EMAtrix updates these tabs:

- `scan_YYYY_MM_DD` (daily green symbols)
- `dashboard_summary`
- `dashboard_green`
- `dashboard_yellow`
- `dashboard_snapshot` (full latest symbol feature table)

## Discord notifications

When webhook integration is enabled, EMAtrix sends:

1. Daily overall summary
2. New companies entering green band
3. Companies remaining in green band
4. Companies exited from green band

## Local 2D + 3D chart generation

After you have at least one `snapshot_*.csv` file:

```bash
python build_dashboard.py
```

Outputs:

- `dashboards/ematrix_2d_latest.html`
- `dashboards/ematrix_3d_latest.html`

Open those HTML files in your browser.

## Kalshi demo scaffold check

```bash
python kalshi_demo.py
```

This currently checks environment setup and a public API status endpoint. Auth wiring is intentionally deferred until you provide credentials.

## Scheduling

Suggested scheduler target: **6:00 PM ET on market weekdays**.

Example cron (set host timezone appropriately):

```cron
0 18 * * 1-5 cd /path/to/ChatGPT-EMA-Strat && /path/to/venv/bin/python scanner.py >> scanner.log 2>&1
```

## Notes

- This is a research scanner, not execution automation.
- Full snapshot exports are designed as the data foundation for future charting (2D and 3D views).
