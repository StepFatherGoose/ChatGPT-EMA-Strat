# EMAtrix (US Daily EMA/RSI Scanner)

EMAtrix runs a **daily post-market scan** for US tradable equities and flags symbols in a research band:

- `close > ema_200`
- `close < ema_48`
- `rsi_14 < 55` (Wilder RSI)

It also builds a **yellow watchlist** for symbols within a configurable tolerance of entering the green band.

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

1. Create/activate a Python virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy env template and fill values:

```bash
cp .env.example .env
```

## Environment variables

Required:

- `ALPACA_API_KEY`
- `ALPACA_API_SECRET`

Optional:

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

## Run manually

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

## Scheduling

Suggested scheduler target: **6:00 PM ET on market weekdays**.

Example cron (set host timezone appropriately):

```cron
0 18 * * 1-5 cd /path/to/ChatGPT-EMA-Strat && /path/to/venv/bin/python scanner.py >> scanner.log 2>&1
```

## Notes

- This is a research scanner, not execution automation.
- Full snapshot exports are designed as the data foundation for future charting (2D and 3D views).
