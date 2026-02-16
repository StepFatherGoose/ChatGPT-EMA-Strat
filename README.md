# EMA Strat Bot (NYSE Daily Scanner)

This project runs a **daily post-market scan** for NYSE-listed stocks and flags symbols that meet:

- Close > 200 EMA
- Close < 48 EMA
- RSI(14) < 55

It supports output to:

- Local CSV
- Google Sheets (optional)
- Discord webhook alerts (optional)

## Why this architecture

- **Universe source:** Alpaca Assets API (active, tradable US equities filtered to NYSE)
- **Price data:** Alpaca Market Data (daily bars)
- **Indicators:** Local pandas calculations (EMA 13/48/100/200 + RSI14)
- **Automation:** Cron / Task Scheduler on your local machine

## Setup

1. Create and activate a Python virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy env template and fill values:

```bash
cp .env.example .env
```

## Environment variables

Required for scanner:

- `ALPACA_API_KEY`
- `ALPACA_API_SECRET`

Optional:

- `ALPACA_BASE_URL` (default: `https://paper-api.alpaca.markets`)
- `ALPACA_DATA_URL` (default: `https://data.alpaca.markets`)
- `LOOKBACK_DAYS` (default: `320`)
- `DISCORD_WEBHOOK_URL`
- `GOOGLE_SHEET_ID`
- `GOOGLE_SERVICE_ACCOUNT_FILE` (path to service account JSON)
- `RESULTS_DIR` (default: `results`)

## Run manually

```bash
python scanner.py
```

Outputs:

- `results/scan_YYYY-MM-DD.csv`
- optional Google Sheet tab update
- optional Discord message with summary and top symbols


## Google Sheets dashboard tabs

When Google Sheets integration is enabled, EMAtrix now updates dedicated dashboard tabs:

- `dashboard_summary`: update timestamp + green/yellow counts and rule definitions.
- `dashboard_green`: symbols currently in the green band (rule match).
- `dashboard_yellow`: symbols within ~10% of entering green based on the largest gap among:
  - getting above EMA200,
  - getting below EMA48,
  - getting RSI14 under 55.

Color labels are logical labels in the data (`green`/`yellow`) so you can apply conditional formatting in Sheets.

## Automate daily after market close

Example cron (6:10 PM ET daily):

```cron
10 18 * * 1-5 cd /path/to/ChatGPT-EMA-Strat && /path/to/venv/bin/python scanner.py >> scanner.log 2>&1
```

## Notes

- This is a **research scanner**, not auto-execution.
- Start with this scan, then wire into a dedicated backtest module for entry/exit rule exploration.
