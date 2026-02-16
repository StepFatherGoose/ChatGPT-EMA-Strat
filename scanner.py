from __future__ import annotations

import argparse
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
    exchanges = [e.strip().upper() for e in os.getenv("UNIVERSE_EXCHANGES", "NYSE,NASDAQ,AMEX").split(",") if e.strip()]
    config = {
        "data_provider": os.getenv("DATA_PROVIDER", "stooq").strip().lower(),
        "alpaca_api_key": os.getenv("ALPACA_API_KEY", "").strip(),
        "alpaca_api_secret": os.getenv("ALPACA_API_SECRET", "").strip(),
        "alpaca_base_url": os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets").strip(),
        "alpaca_data_url": os.getenv("ALPACA_DATA_URL", "https://data.alpaca.markets").strip(),
        "data_feed": os.getenv("ALPACA_DATA_FEED", "iex").strip(),
        "stooq_symbol_source": os.getenv("STOOQ_SYMBOL_SOURCE", "sec").strip().lower(),
        "symbol_limit": int(os.getenv("SYMBOL_LIMIT", "400")),
        "lookback_days": int(os.getenv("LOOKBACK_DAYS", "320")),
        "include_etfs": os.getenv("INCLUDE_ETFS", "true").strip().lower() == "true",
        "universe_exchanges": exchanges or ["NYSE", "NASDAQ", "AMEX"],
        "yellow_tolerance_pct": float(os.getenv("YELLOW_TOLERANCE_PCT", "10")),
        "discord_webhook_url": os.getenv("DISCORD_WEBHOOK_URL", "").strip(),
        "google_sheet_id": os.getenv("GOOGLE_SHEET_ID", "").strip(),
        "google_service_account_file": os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip(),
        "results_dir": os.getenv("RESULTS_DIR", "results").strip(),
    }
    return config


def validate_config(cfg: dict) -> tuple[bool, list[str]]:
    messages: list[str] = []
    ok = True

    if cfg["data_provider"] not in {"alpaca", "stooq"}:
        ok = False
        messages.append("DATA_PROVIDER must be one of: alpaca, stooq")

    if cfg["data_provider"] == "alpaca":
        if not cfg["alpaca_api_key"]:
            ok = False
            messages.append("Missing ALPACA_API_KEY (required for DATA_PROVIDER=alpaca)")
        if not cfg["alpaca_api_secret"]:
            ok = False
            messages.append("Missing ALPACA_API_SECRET (required for DATA_PROVIDER=alpaca)")

    if cfg["google_sheet_id"] and not cfg["google_service_account_file"]:
        messages.append("GOOGLE_SHEET_ID set but GOOGLE_SERVICE_ACCOUNT_FILE missing")
    if cfg["google_service_account_file"] and not Path(cfg["google_service_account_file"]).exists():
        messages.append("GOOGLE_SERVICE_ACCOUNT_FILE path does not exist")

    if cfg["yellow_tolerance_pct"] <= 0:
        ok = False
        messages.append("YELLOW_TOLERANCE_PCT must be > 0")

    if cfg["symbol_limit"] <= 0:
        ok = False
        messages.append("SYMBOL_LIMIT must be > 0")

    return ok, messages


def print_config_check(cfg: dict) -> bool:
    ok, messages = validate_config(cfg)
    print("EMAtrix config check")
    print(f"- Data provider: {cfg['data_provider']}")
    print(f"- Exchanges: {', '.join(cfg['universe_exchanges'])}")
    print(f"- Symbol limit: {cfg['symbol_limit']}")
    print(f"- Data feed: {cfg['data_feed']}")
    print(f"- Results dir: {cfg['results_dir']}")
    print(f"- Google configured: {bool(cfg['google_sheet_id'] and cfg['google_service_account_file'])}")
    print(f"- Discord configured: {bool(cfg['discord_webhook_url'])}")
    if messages:
        print("\nConfig notes:")
        for msg in messages:
            print(f"- {msg}")
    print(f"\nStatus: {'PASS' if ok else 'FAIL'}")
    return ok


def alpaca_headers(cfg: dict) -> dict:
    return {
        "APCA-API-KEY-ID": cfg["alpaca_api_key"],
        "APCA-API-SECRET-KEY": cfg["alpaca_api_secret"],
    }


def get_us_universe_alpaca(cfg: dict) -> List[str]:
    url = f"{cfg['alpaca_base_url'].rstrip('/')}/v2/assets"
    params = {"status": "active", "asset_class": "us_equity"}
    response = requests.get(url, headers=alpaca_headers(cfg), params=params, timeout=60)
    response.raise_for_status()
    assets = response.json()

    allowed_exchanges = set(cfg["universe_exchanges"])
    symbols = []
    for asset in assets:
        if not asset.get("tradable"):
            continue
        if asset.get("exchange") not in allowed_exchanges:
            continue
        symbol = asset.get("symbol")
        if symbol:
            symbols.append(symbol)
    return sorted(set(symbols))


def get_us_universe_stooq(cfg: dict) -> List[str]:
    # SEC ticker list is free and public.
    if cfg["stooq_symbol_source"] != "sec":
        raise ValueError("STOOQ_SYMBOL_SOURCE currently supports only: sec")

    response = requests.get("https://www.sec.gov/files/company_tickers.json", timeout=60)
    response.raise_for_status()
    payload = response.json()

    symbols: list[str] = []
    for _, row in payload.items():
        ticker = str(row.get("ticker", "")).strip().upper()
        if not ticker:
            continue
        if "^" in ticker or "/" in ticker or "." in ticker:
            continue
        symbols.append(ticker)

    symbols = sorted(set(symbols))
    return symbols[: cfg["symbol_limit"]]


def get_universe(cfg: dict) -> List[str]:
    if cfg["data_provider"] == "alpaca":
        symbols = get_us_universe_alpaca(cfg)
        return symbols[: cfg["symbol_limit"]]
    return get_us_universe_stooq(cfg)


def chunked(items: Iterable[str], size: int) -> Iterable[List[str]]:
    bucket: List[str] = []
    for item in items:
        bucket.append(item)
        if len(bucket) >= size:
            yield bucket
            bucket = []
    if bucket:
        yield bucket


def fetch_daily_bars_alpaca(cfg: dict, symbols: List[str]) -> pd.DataFrame:
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
            "feed": cfg["data_feed"],
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
    return df.sort_values(["symbol", "timestamp"])


def fetch_daily_bars_stooq(cfg: dict, symbols: List[str]) -> pd.DataFrame:
    if not symbols:
        return pd.DataFrame()

    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=cfg["lookback_days"])
    frames: list[pd.DataFrame] = []

    for symbol in symbols:
        url = f"https://stooq.com/q/d/l/?s={symbol.lower()}.us&i=d"
        try:
            response = requests.get(url, timeout=20)
            if response.status_code != 200 or "Date,Open,High,Low,Close,Volume" not in response.text:
                continue

            df = pd.read_csv(pd.io.common.StringIO(response.text))
            if df.empty:
                continue

            df["Date"] = pd.to_datetime(df["Date"], utc=True, errors="coerce")
            df = df.dropna(subset=["Date", "Close"]).copy()
            df = df[df["Date"] >= cutoff].copy()
            if df.empty:
                continue

            df = df.rename(
                columns={
                    "Date": "timestamp",
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Volume": "volume",
                }
            )
            df["symbol"] = symbol
            frames.append(df[["symbol", "timestamp", "open", "high", "low", "close", "volume"]])
        except Exception:
            continue

    if not frames:
        return pd.DataFrame()

    all_df = pd.concat(frames, ignore_index=True)
    all_df["timestamp"] = pd.to_datetime(all_df["timestamp"], utc=True)
    return all_df.sort_values(["symbol", "timestamp"])


def fetch_daily_bars(cfg: dict, symbols: List[str]) -> pd.DataFrame:
    if cfg["data_provider"] == "alpaca":
        return fetch_daily_bars_alpaca(cfg, symbols)
    return fetch_daily_bars_stooq(cfg, symbols)


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
        g["rsi_14"] = 100 - (100 / (1 + rs))
        return g

    return out.groupby("symbol", group_keys=False).apply(_calc)


def latest_snapshot(ind_df: pd.DataFrame) -> pd.DataFrame:
    if ind_df.empty:
        return ind_df
    return ind_df.sort_values(["symbol", "timestamp"]).groupby("symbol", as_index=False).tail(1).reset_index(drop=True)


def filter_green_band(latest: pd.DataFrame) -> pd.DataFrame:
    if latest.empty:
        return latest

    green = latest[
        (latest["close"] > latest["ema_200"])
        & (latest["close"] < latest["ema_48"])
        & (latest["rsi_14"] < 55)
    ].copy()

    green["status"] = "green"
    green["distance_to_ema_48_pct"] = ((green["close"] - green["ema_48"]) / green["ema_48"]) * 100
    green["distance_to_ema_200_pct"] = ((green["close"] - green["ema_200"]) / green["ema_200"]) * 100

    cols = [
        "timestamp",
        "symbol",
        "status",
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
    return green[cols].sort_values(["rsi_14", "distance_to_ema_48_pct"]).reset_index(drop=True)


def build_yellow_watchlist(latest: pd.DataFrame, green_symbols: set[str], tolerance_pct: float) -> pd.DataFrame:
    if latest.empty:
        return latest

    candidates = latest[~latest["symbol"].isin(green_symbols)].copy()
    if candidates.empty:
        return candidates

    candidates["gap_above_ema200_pct"] = np.where(
        candidates["close"] >= candidates["ema_200"],
        0.0,
        ((candidates["ema_200"] - candidates["close"]) / candidates["ema_200"]) * 100,
    )
    candidates["gap_below_ema48_pct"] = np.where(
        candidates["close"] <= candidates["ema_48"],
        0.0,
        ((candidates["close"] - candidates["ema_48"]) / candidates["ema_48"]) * 100,
    )
    candidates["gap_rsi55_pct"] = np.where(
        candidates["rsi_14"] <= 55,
        0.0,
        ((candidates["rsi_14"] - 55) / 55) * 100,
    )
    candidates["max_gap_pct"] = candidates[["gap_above_ema200_pct", "gap_below_ema48_pct", "gap_rsi55_pct"]].max(axis=1)

    yellow = candidates[candidates["max_gap_pct"] <= tolerance_pct].copy()
    yellow["status"] = "yellow"
    cols = [
        "timestamp",
        "symbol",
        "status",
        "close",
        "ema_13",
        "ema_48",
        "ema_100",
        "ema_200",
        "rsi_14",
        "gap_above_ema200_pct",
        "gap_below_ema48_pct",
        "gap_rsi55_pct",
        "max_gap_pct",
        "volume",
    ]
    return yellow[cols].sort_values(["max_gap_pct", "rsi_14"]).reset_index(drop=True)


def save_csv(df: pd.DataFrame, results_dir: str, prefix: str) -> Path:
    output_dir = Path(results_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    date_label = dt.datetime.now().strftime("%Y-%m-%d")
    path = output_dir / f"{prefix}_{date_label}.csv"
    df.to_csv(path, index=False)
    return path


def load_previous_symbols(results_dir: str, prefix: str) -> set[str]:
    output_dir = Path(results_dir)
    if not output_dir.exists():
        return set()

    files = sorted(output_dir.glob(f"{prefix}_*.csv"))
    if len(files) < 2:
        return set()

    previous_file = files[-2]
    try:
        prev = pd.read_csv(previous_file, usecols=["symbol"])
        return set(prev["symbol"].astype(str).tolist())
    except Exception:
        return set()


def classify_band_transitions(current_symbols: set[str], previous_symbols: set[str]) -> tuple[list[str], list[str], list[str]]:
    new_entries = sorted(current_symbols - previous_symbols)
    remaining = sorted(current_symbols & previous_symbols)
    exited = sorted(previous_symbols - current_symbols)
    return new_entries, remaining, exited


def _upsert_sheet_tab(sh, tab_name: str, rows: list[list[str]]) -> None:
    import gspread

    if not rows:
        rows = [[""]]

    try:
        ws = sh.worksheet(tab_name)
        ws.clear()
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=tab_name, rows=max(1000, len(rows) + 20), cols=max(20, len(rows[0]) + 2))

    ws.update(rows, value_input_option="USER_ENTERED")


def push_google_sheet(green_df: pd.DataFrame, yellow_df: pd.DataFrame, latest_snapshot_df: pd.DataFrame, cfg: dict) -> None:
    if not cfg["google_sheet_id"] or not cfg["google_service_account_file"]:
        return

    import gspread

    gc = gspread.service_account(filename=cfg["google_service_account_file"])
    sh = gc.open_by_key(cfg["google_sheet_id"])

    daily_tab_name = dt.datetime.now().strftime("scan_%Y_%m_%d")
    daily_rows = [green_df.columns.tolist()] + green_df.fillna("").astype(str).values.tolist()
    _upsert_sheet_tab(sh, daily_tab_name, daily_rows)

    summary_rows = [
        ["metric", "value"],
        ["updated_at_utc", dt.datetime.now(dt.timezone.utc).isoformat()],
        ["provider", cfg["data_provider"]],
        ["green_count", str(len(green_df))],
        ["yellow_count", str(len(yellow_df))],
        ["green_rule", "close > ema_200 AND close < ema_48 AND rsi_14 < 55"],
        ["yellow_rule", f"within {cfg['yellow_tolerance_pct']:.1f}% of entering green rule"],
    ]
    green_rows = [green_df.columns.tolist()] + green_df.fillna("").astype(str).values.tolist()
    yellow_rows = [yellow_df.columns.tolist()] + yellow_df.fillna("").astype(str).values.tolist()
    snapshot_rows = [latest_snapshot_df.columns.tolist()] + latest_snapshot_df.fillna("").astype(str).values.tolist()

    _upsert_sheet_tab(sh, "dashboard_summary", summary_rows)
    _upsert_sheet_tab(sh, "dashboard_green", green_rows)
    _upsert_sheet_tab(sh, "dashboard_yellow", yellow_rows)
    _upsert_sheet_tab(sh, "dashboard_snapshot", snapshot_rows)


def _send_discord_message(webhook: str, content: str) -> None:
    response = requests.post(webhook, json={"content": content}, timeout=30)
    response.raise_for_status()


def send_discord_alerts(cfg: dict, csv_path: Path, total: int, new_entries: list[str], remaining: list[str], exited: list[str]) -> None:
    webhook = cfg["discord_webhook_url"]
    if not webhook:
        return

    summary = (
        "📉 **EMAtrix Daily Band Scan**\n"
        f"Provider: {cfg['data_provider']}\n"
        "Rule: Close > EMA200, Close < EMA48, RSI14 < 55\n"
        f"Total in green band: **{total}**\n"
        f"CSV: `{csv_path}`"
    )
    _send_discord_message(webhook, summary)

    new_txt = ", ".join(new_entries[:40]) if new_entries else "None"
    remain_txt = ", ".join(remaining[:40]) if remaining else "None"
    exited_txt = ", ".join(exited[:40]) if exited else "None"

    _send_discord_message(webhook, f"🟢 **New companies entering the band**\nCount: **{len(new_entries)}**\nSymbols: {new_txt}")
    _send_discord_message(webhook, f"🟡 **Companies that remain in the band**\nCount: **{len(remaining)}**\nSymbols: {remain_txt}")
    _send_discord_message(webhook, f"🔴 **Companies that exited the band**\nCount: **{len(exited)}**\nSymbols: {exited_txt}")


def run_scan(dry_run: bool = False, max_symbols: int | None = None) -> None:
    cfg = load_config()
    ok, messages = validate_config(cfg)
    if not ok:
        raise ValueError("Invalid config:\n- " + "\n- ".join(messages))

    print(f"Loading US universe using provider={cfg['data_provider']}...")
    universe = get_universe(cfg)
    if max_symbols:
        universe = universe[:max_symbols]
        print(f"Run symbol limit enabled: {max_symbols}")

    print(f"Universe size: {len(universe)} symbols")

    print("Fetching daily bars...")
    bars = fetch_daily_bars(cfg, universe)
    if bars.empty:
        raise RuntimeError("No bars returned from selected provider.")

    print("Computing indicators...")
    indicators = compute_indicators(bars)
    latest = latest_snapshot(indicators)

    print("Filtering green/yellow band criteria...")
    green = filter_green_band(latest)
    yellow = build_yellow_watchlist(latest, set(green["symbol"].tolist()), cfg["yellow_tolerance_pct"])

    green_csv_path = save_csv(green, cfg["results_dir"], "scan")
    yellow_csv_path = save_csv(yellow, cfg["results_dir"], "yellow")
    snapshot_csv_path = save_csv(latest, cfg["results_dir"], "snapshot")
    print(f"Saved {len(green)} green symbols to {green_csv_path}")
    print(f"Saved {len(yellow)} yellow symbols to {yellow_csv_path}")
    print(f"Saved {len(latest)} full snapshot rows to {snapshot_csv_path}")

    previous_symbols = load_previous_symbols(cfg["results_dir"], "scan")
    current_symbols = set(green["symbol"].tolist())
    new_entries, remaining, exited = classify_band_transitions(current_symbols, previous_symbols)

    if dry_run:
        print("Dry run mode enabled: skipping Google Sheets + Discord notifications.")
    else:
        try:
            push_google_sheet(green, yellow, latest, cfg)
        except Exception as exc:
            print(f"Warning: Google Sheets update failed: {exc}")

        try:
            send_discord_alerts(cfg, green_csv_path, len(green), new_entries, remaining, exited)
        except Exception as exc:
            print(f"Warning: Discord update failed: {exc}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="EMAtrix scanner")
    parser.add_argument("--check-config", action="store_true", help="Validate local .env settings and exit")
    parser.add_argument("--dry-run", action="store_true", help="Run scan and write CSVs but skip Google/Discord")
    parser.add_argument("--max-symbols", type=int, default=None, help="Optional symbol cap for testing/dry-runs")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_config()

    if args.check_config:
        passed = print_config_check(cfg)
        if not passed:
            raise SystemExit(1)
        return

    run_scan(dry_run=args.dry_run, max_symbols=args.max_symbols)


if __name__ == "__main__":
    main()
