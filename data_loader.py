"""
Shared, format-safe CSV loader for the DATA/ directory.

WHY THIS EXISTS
---------------
The CSVs in DATA/ do NOT share a timestamp format:

    BTCUSDT_1h_2023_to_2025.csv      ->  2023-01-01 00:00:00   (ISO)
    BTCUSDT_1h_Jan_to_Jul2026.csv    ->  13/02/2026 0:00       (DD/MM/YYYY)

Passing `dayfirst=True, format='mixed'` (needed for the DD/MM files)
to an ISO file silently swaps day and month on every date where BOTH
are <= 12 -- i.e. "2023-01-02" is read as 1 February instead of 2
January. That corrupts ~36% of rows, and because the corruption is a
reordering rather than a parse failure, it raises no error: sorting the
index afterwards simply interleaves the wrong bars, manufacturing fake
intrabar jumps of up to 32% and destroying the real trend structure.

Every backtest in this repo that read a 2023-2025 file with dayfirst
parsing produced numbers computed on scrambled prices. Use this loader
instead of calling pd.to_datetime directly.
"""

import os
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "DATA")


def parse_timestamps(series: pd.Series) -> pd.Series:
    """Parse a timestamp column, detecting ISO vs DD/MM per file."""
    sample = str(series.iloc[1] if len(series) > 1 else series.iloc[0])
    if "-" in sample.split(" ")[0]:
        # ISO YYYY-MM-DD: unambiguous, and dayfirst must NOT be applied
        return pd.to_datetime(series, format="%Y-%m-%d %H:%M:%S")
    # DD/MM/YYYY with variable H:MM padding
    return pd.to_datetime(series, format="mixed", dayfirst=True)


def load_ohlcv(filename: str, start=None, end=None) -> pd.DataFrame:
    """Load a DATA/ CSV with correct timestamps, sorted, optionally sliced."""
    path = filename if os.path.isabs(filename) else os.path.join(DATA_DIR, filename)
    df = pd.read_csv(path)
    df["timestamp"] = parse_timestamps(df["timestamp"])
    df = df.set_index("timestamp").sort_index()
    if start or end:
        df = df.loc[start:end]
    return df


def sanity_report(filename: str) -> dict:
    """Quick integrity check: real BTC rarely moves >5% in one bar."""
    df = load_ohlcv(filename)
    chg = df["close"].pct_change().abs() * 100
    return {
        "file": os.path.basename(filename),
        "rows": len(df),
        "start": df.index.min(),
        "end": df.index.max(),
        "monotonic": bool(df.index.is_monotonic_increasing),
        "duplicate_ts": int(df.index.duplicated().sum()),
        "max_bar_move_pct": float(chg.max()),
        "bars_over_5pct": int((chg > 5).sum()),
        "bars_over_10pct": int((chg > 10).sum()),
    }


if __name__ == "__main__":
    import glob
    print(f"{'file':<36}{'rows':>9}{'max move':>10}{'>5%':>6}{'>10%':>7}  range")
    print("-" * 100)
    for f in sorted(glob.glob(os.path.join(DATA_DIR, "*.csv"))):
        r = sanity_report(f)
        print(f"{r['file']:<36}{r['rows']:>9,}{r['max_bar_move_pct']:>9.1f}%"
              f"{r['bars_over_5pct']:>6}{r['bars_over_10pct']:>7}  "
              f"{str(r['start'])[:10]} -> {str(r['end'])[:10]}")
