"""
Download historical klines from Binance into DATA/.

Run this on your own machine -- the sandbox this repo was developed in
blocks outbound calls to api.binance.com, which is why DATA/ only has
BTCUSDT. Nothing here needs an API key; klines are a public endpoint.

    python3 fetch_data.py                          # all five, 15m, 2 years
    python3 fetch_data.py --symbols ETHUSDT XRPUSDT
    python3 fetch_data.py --interval 1h --days 1095

Output matches the loader's expected schema exactly:
    timestamp,open,high,low,close,volume    with ISO timestamps
"""

import argparse
import os
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "DATA")
BASE = "https://fapi.binance.com/fapi/v1/klines"   # USD-M futures, what the bot trades
LIMIT = 1500

DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]


def fetch(symbol: str, interval: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    rows = []
    cursor = start_ms
    while cursor < end_ms:
        params = {"symbol": symbol, "interval": interval,
                  "startTime": cursor, "limit": LIMIT}
        for attempt in range(5):
            try:
                r = requests.get(BASE, params=params, timeout=30)
                if r.status_code == 429:
                    wait = 2 ** attempt * 5
                    print(f"    rate limited, waiting {wait}s")
                    time.sleep(wait)
                    continue
                r.raise_for_status()
                batch = r.json()
                break
            except Exception as exc:
                if attempt == 4:
                    raise
                print(f"    retry {attempt + 1}: {exc}")
                time.sleep(2 ** attempt)
        if not batch:
            break
        rows.extend(batch)
        cursor = batch[-1][0] + 1
        print(f"    {len(rows):>7,} bars  ...{datetime.fromtimestamp(batch[-1][0]/1000, timezone.utc):%Y-%m-%d}",
              end="\r")
        time.sleep(0.25)          # stay well inside the weight limit
    print()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=[
        "open_time", "open", "high", "low", "close", "volume", "close_time",
        "qav", "trades", "tbb", "tbq", "ignore"])
    df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms")
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)
    df = df[["timestamp", "open", "high", "low", "close", "volume"]]
    df = df.drop_duplicates("timestamp").sort_values("timestamp")
    return df


def sanity(df: pd.DataFrame, symbol: str):
    """Catch corrupt downloads before they poison a backtest."""
    chg = df["close"].pct_change().abs() * 100
    gaps = df["timestamp"].diff().value_counts()
    print(f"    rows {len(df):,}   {df['timestamp'].min():%Y-%m-%d} -> {df['timestamp'].max():%Y-%m-%d}")
    print(f"    max bar move {chg.max():.1f}%   bars >10%: {(chg > 10).sum()}   "
          f"duplicate timestamps: {df['timestamp'].duplicated().sum()}")
    if len(gaps) > 1:
        irregular = int(gaps.iloc[1:].sum())
        print(f"    irregular intervals: {irregular} (exchange downtime, usually fine)")
    if chg.max() > 25:
        print(f"    WARNING: {symbol} has a >25% single-bar move. Verify against a chart "
              f"before trusting any backtest built on it.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    ap.add_argument("--interval", default="15m")
    ap.add_argument("--days", type=int, default=730)
    args = ap.parse_args()

    os.makedirs(DATA_DIR, exist_ok=True)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=args.days)
    start_ms, end_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)

    print(f"Fetching {args.interval} klines, {args.days} days, from Binance USD-M futures\n")
    for symbol in args.symbols:
        print(f"  {symbol}")
        df = fetch(symbol, args.interval, start_ms, end_ms)
        if df.empty:
            print("    nothing returned -- check the symbol exists on futures\n")
            continue
        sanity(df, symbol)
        out = os.path.join(DATA_DIR, f"{symbol}_{args.interval}_fetched.csv")
        df.to_csv(out, index=False)
        print(f"    -> {out}\n")

    print("Done. Now run:  python3 backtest_portfolio.py")


if __name__ == "__main__":
    main()
