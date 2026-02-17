from __future__ import annotations

import os
from dataclasses import dataclass

import requests
from dotenv import load_dotenv


@dataclass
class KalshiConfig:
    base_url: str
    email: str
    password: str


def load_kalshi_config() -> KalshiConfig:
    load_dotenv()
    return KalshiConfig(
        base_url=os.getenv("KALSHI_BASE_URL", "https://demo-api.kalshi.co").strip(),
        email=os.getenv("KALSHI_EMAIL", "").strip(),
        password=os.getenv("KALSHI_PASSWORD", "").strip(),
    )


def check_kalshi_demo_connection() -> None:
    cfg = load_kalshi_config()
    print("Kalshi demo config check")
    print(f"- Base URL: {cfg.base_url}")
    print(f"- Email set: {bool(cfg.email)}")
    print(f"- Password set: {bool(cfg.password)}")

    # Public endpoint check (does not require credentials).
    # If Kalshi changes endpoint contracts, this keeps the scaffold lightweight.
    health_url = f"{cfg.base_url.rstrip('/')}/trade-api/v2/exchange/status"
    try:
        response = requests.get(health_url, timeout=20)
        print(f"- API status endpoint HTTP: {response.status_code}")
    except Exception as exc:
        print(f"- API status check warning: {exc}")

    if not cfg.email or not cfg.password:
        print("\nNext step: add KALSHI_EMAIL and KALSHI_PASSWORD to .env when ready.")
        return

    print("\nCredentials are present. Authentication wiring is the next implementation step.")


if __name__ == "__main__":
    check_kalshi_demo_connection()
