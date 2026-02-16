from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
from typing import Iterable, List

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv


def load_config() -> dict:
    load_dotenv()
    config = {
        "alpaca_api_key": os.getenv("ALPACA_API_KEY", "").strip(),
        "alpaca_api_secret": os.getenv("ALPACA_API_SECRET", "").strip(),
        "alpaca_base_url": os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets").strip(),
        "alpaca_data_url": os.getenv("ALPACA_DATA_URL", "https://data.alpaca.markets").strip(),
        "lookback_days": int(os.getenv("LOOKBACK_DAYS", "320")),
        "discord_webhook_url": os.getenv("DISCORD_WEBHOOK_URL", "").strip(),
        "google_sheet_id": os.getenv("GOOGLE_SHEET_ID", "").strip(),
        "google_service_account_file": os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip(),
        "results_dir": os.getenv("RESULTS_DIR", "results").strip(),
    }

    if not config["alpaca_api_key"] or not config["alpaca_api_secret"]:
        raise ValueError("Missing ALPACA_API_KEY/ALPACA_API_SECRET in environment.")

    return config


def alpaca_headers(cfg: dict) -> dict:
    return {
        "APCA-API-KEY-ID": cfg["alpaca_api_key"],
        "APCA-API-SECRET-KEY": cfg["alpaca_api_secret"],
    }


def get_nyse_universe(cfg: dict) -> List[str]:
    """Fetch active tradable US equities on NYSE from Alpaca assets endpoint."""
    url = f"{cfg['alpaca_base_url'].rstrip('/')}/v2/assets"
    params = {"status": "active", "asset_class": "us_equity"}
    response = requests.get(url, headers=alpaca_headers(cfg), params=params, timeout=60)
    response.raise_for_status()
    assets = response.json()

    symbols = [
        a["symbol"]
        for a in assets
        if a.get("exchange") == "NYSE" and a.get("tradable")
    ]
    symbols = sorted(set(symbols))
    return symbols


def chunked(items: Iterable[str], size: int) -> Iterable[List[str]]:
    bucket: List[str] = []
    for item in items:
        bucket.append(item)
        if len(bucket) >= size:
            yield bucket
            bucket = []
    if bucket:
        yield bucket


def fetch_daily_bars(cfg: dict, symbols: List[str]) -> pd.DataFrame:
    """Fetch daily bars using Alpaca v2 stocks bars endpoint in batches."""
    if not symbols:
        return pd.DataFrame()

    end = dt.datetime.now(dt.timezone.utc)
    start = end - dt.timedelta(days=cfg["lookback_days"])

    all_rows: List[dict] = []
    base_url = f"{cfg['alpaca_data_url'].rstrip('/')}/v2/stocks/bars"

    for batch in chunked(symbols, 200):
        params = {
            "symbols": ",".join(batch),
            "timeframe": "1Day",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "adjustment": "split",
            "limit": 10000,
            "feed": "iex",
        }

        next_page_token = None
        while True:
            if next_page_token:
                params["page_token"] = next_page_token
            response = requests.get(base_url, headers=alpaca_headers(cfg), params=params, timeout=90)
            response.raise_for_status()
            payload = response.json()

            bars = payload.get("bars", {})
            for symbol, rows in bars.items():
                for row in rows:
                    all_rows.append(
                        {
                            "symbol": symbol,
                            "timestamp": row["t"],
                            "open": row["o"],
                            "high": row["h"],
                            "low": row["l"],
                            "close": row["c"],
                            "volume": row["v"],
                        }
                    )

            next_page_token = payload.get("next_page_token")
            if not next_page_token:
                break

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values(["symbol", "timestamp"])
    return df


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    out = df.copy()

    def _calc(group: pd.DataFrame) -> pd.DataFrame:
        g = group.copy()
        close = g["close"]

        for span in (13, 48, 100, 200):
            g[f"ema_{span}"] = close.ewm(span=span, adjust=False).mean()

        delta = close.diff()
        gain = np.where(delta > 0, delta, 0.0)
        loss = np.where(delta < 0, -delta, 0.0)
        avg_gain = pd.Series(gain, index=g.index).ewm(alpha=1 / 14, adjust=False).mean()
        avg_loss = pd.Series(loss, index=g.index).ewm(alpha=1 / 14, adjust=False).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        g["rsi_14"] = rsi

        return g

    out = out.groupby("symbol", group_keys=False).apply(_calc)
    return out


def latest_snapshot(ind_df: pd.DataFrame) -> pd.DataFrame:
    if ind_df.empty:
        return ind_df

    latest = ind_df.sort_values(["symbol", "timestamp"]).groupby("symbol", as_index=False).tail(1)
    latest = latest.reset_index(drop=True)
    return latest


def filter_setup(latest: pd.DataFrame) -> pd.DataFrame:
    if latest.empty:
        return latest

    filt = latest[
        (latest["close"] > latest["ema_200"])
        & (latest["close"] < latest["ema_48"])
        & (latest["rsi_14"] < 55)
    ].copy()

    filt["distance_to_ema_48_pct"] = ((filt["close"] - filt["ema_48"]) / filt["ema_48"]) * 100
    filt["distance_to_ema_200_pct"] = ((filt["close"] - filt["ema_200"]) / filt["ema_200"]) * 100

    cols = [
        "timestamp",
        "symbol",
        "close",
        "ema_13",
        "ema_48",
        "ema_100",
        "ema_200",
        "rsi_14",
        "distance_to_ema_48_pct",
        "distance_to_ema_200_pct",
        "volume",
    ]
    return filt[cols].sort_values(["rsi_14", "distance_to_ema_48_pct"]).reset_index(drop=True)


def build_yellow_watchlist(latest: pd.DataFrame, green_symbols: set[str], tolerance_pct: float = 10.0) -> pd.DataFrame:
    """Find symbols that are close to entering the green band within tolerance."""
    if latest.empty:
        return latest

    candidates = latest[~latest["symbol"].isin(green_symbols)].copy()
    if candidates.empty:
        return candidates

    above_ema200_gap_pct = np.where(
        candidates["close"] >= candidates["ema_200"],
        0.0,
        ((candidates["ema_200"] - candidates["close"]) / candidates["ema_200"]) * 100,
    )
    below_ema48_gap_pct = np.where(
        candidates["close"] <= candidates["ema_48"],
        0.0,
        ((candidates["close"] - candidates["ema_48"]) / candidates["ema_48"]) * 100,
    )
    rsi_gap_pct = np.where(
        candidates["rsi_14"] <= 55,
        0.0,
        ((candidates["rsi_14"] - 55) / 55) * 100,
    )

    candidates["gap_above_ema200_pct"] = above_ema200_gap_pct
    candidates["gap_below_ema48_pct"] = below_ema48_gap_pct
    candidates["gap_rsi55_pct"] = rsi_gap_pct
    candidates["max_gap_pct"] = candidates[
        ["gap_above_ema200_pct", "gap_below_ema48_pct", "gap_rsi55_pct"]
    ].max(axis=1)

    yellow = candidates[candidates["max_gap_pct"] <= tolerance_pct].copy()
    yellow["status"] = "yellow"

    cols = [
        "timestamp",
        "symbol",
        "status",
        "close",
        "ema_48",
        "ema_200",
        "rsi_14",
        "gap_above_ema200_pct",
        "gap_below_ema48_pct",
        "gap_rsi55_pct",
        "max_gap_pct",
        "volume",
    ]
    return yellow[cols].sort_values(["max_gap_pct", "rsi_14"]).reset_index(drop=True)


def save_csv(df: pd.DataFrame, results_dir: str) -> Path:
    output_dir = Path(results_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    date_label = dt.datetime.now().strftime("%Y-%m-%d")
    path = output_dir / f"scan_{date_label}.csv"
    df.to_csv(path, index=False)
    return path


def push_google_sheet(df: pd.DataFrame, cfg: dict) -> None:
    if not cfg["google_sheet_id"] or not cfg["google_service_account_file"]:
        return

    import gspread

    gc = gspread.service_account(filename=cfg["google_service_account_file"])
    sh = gc.open_by_key(cfg["google_sheet_id"])

    tab_name = dt.datetime.now().strftime("scan_%Y_%m_%d")
    rows = [df.columns.tolist()] + df.fillna("").astype(str).values.tolist()

    try:
        ws = sh.worksheet(tab_name)
        ws.clear()
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=tab_name, rows=max(1000, len(rows) + 20), cols=max(20, len(df.columns) + 2))

    ws.update(rows, value_input_option="USER_ENTERED")


def push_google_dashboard(green_df: pd.DataFrame, yellow_df: pd.DataFrame, cfg: dict) -> None:
    if not cfg["google_sheet_id"] or not cfg["google_service_account_file"]:
        return

    import gspread

    gc = gspread.service_account(filename=cfg["google_service_account_file"])
    sh = gc.open_by_key(cfg["google_sheet_id"])

    summary_rows = [
        ["metric", "value"],
        ["updated_at_utc", dt.datetime.now(dt.timezone.utc).isoformat()],
        ["green_count", len(green_df)],
        ["yellow_count", len(yellow_df)],
        ["green_rule", "close > ema_200 AND close < ema_48 AND rsi_14 < 55"],
        ["yellow_rule", "within 10% of entering green rule"],
    ]

    tabs = {
        "dashboard_summary": summary_rows,
        "dashboard_green": [green_df.assign(status="green").columns.tolist()]
        + green_df.assign(status="green").fillna("").astype(str).values.tolist(),
        "dashboard_yellow": [yellow_df.columns.tolist()] + yellow_df.fillna("").astype(str).values.tolist(),
    }

    for tab_name, rows in tabs.items():
        try:
            ws = sh.worksheet(tab_name)
            ws.clear()
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=tab_name, rows=max(1000, len(rows) + 20), cols=max(20, len(rows[0]) + 2))

        ws.update(rows, value_input_option="USER_ENTERED")


def send_discord_alert(df: pd.DataFrame, cfg: dict, csv_path: Path) -> None:
    webhook = cfg["discord_webhook_url"]
    if not webhook:
        return

    total = len(df)
    top = ", ".join(df["symbol"].head(20).tolist()) if total else "None"

    content = (
        "📉 **NYSE EMA Scan Complete**\n"
        f"Rule: Close > EMA200, Close < EMA48, RSI14 < 55\n"
        f"Matches: **{total}**\n"
        f"Top symbols: {top}\n"
        f"CSV: `{csv_path}`"
    )

    response = requests.post(webhook, json={"content": content}, timeout=30)
    response.raise_for_status()


def main() -> None:
    cfg = load_config()

    print("Loading NYSE universe from Alpaca assets...")
    universe = get_nyse_universe(cfg)
    print(f"Universe size: {len(universe)} symbols")

    print("Fetching daily bars...")
    bars = fetch_daily_bars(cfg, universe)
    if bars.empty:
        raise RuntimeError("No bars returned from Alpaca.")

    print("Computing indicators...")
    indicators = compute_indicators(bars)
    latest = latest_snapshot(indicators)

    print("Filtering setup criteria...")
    picks = filter_setup(latest)
    yellow = build_yellow_watchlist(latest, set(picks["symbol"].tolist()), tolerance_pct=10.0)

    csv_path = save_csv(picks, cfg["results_dir"])
    print(f"Saved {len(picks)} matches to {csv_path}")

    push_google_sheet(picks, cfg)
    push_google_dashboard(picks, yellow, cfg)
    send_discord_alert(picks, cfg, csv_path)

    # Console summary
    print("\nTop 20 results:")
    if picks.empty:
        print("No matches today.")
    else:
        display_cols = ["symbol", "close", "ema_48", "ema_200", "rsi_14"]
        print(picks[display_cols].head(20).to_string(index=False))


if __name__ == "__main__":
    main()
