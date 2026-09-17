"""
Convert raw Exness/MT5 XAUUSD exports into the DATA/ loader format.

The MT5 exports vary: comma-thousands in prices ("1,518.46"), two date
styles (2020.01.02 and 2022-06-24), <ANGLE> or bare headers, VOL blank.
This normalizes all of them to: timestamp,open,high,low,close,volume
(volume = TICKVOL, the only real volume MT5 gives on this symbol).

Point SRC at the raw uploads and run once. Output lands in DATA/.
"""
import os
import numpy as np
import pandas as pd

# raw source files (edit to wherever the exports live)
SRC = os.environ.get("GOLD_SRC", ".")
FILES = {
    "XAUUSD_30m.csv": "XAUUSDm_M30_202001020100_202609162200.csv",
    "XAUUSD_1h.csv":  "XAUUSDm_H1_202001020100_202609162200.csv",
    "XAUUSD_15m.csv": "XAUUSDm_M15_202206241300_202609162200.csv",
    "XAUUSD_4h.csv":  "XAUUSDm_H4_202001020000_202609162000.csv",
}
DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "DATA")


def num(x):
    if isinstance(x, str):
        x = x.replace(",", "").replace('"', '').strip()
    try:
        return float(x)
    except (ValueError, TypeError):
        return np.nan


def convert(src_path, out_name):
    df = pd.read_csv(src_path)
    df.columns = [c.strip().strip("<>").upper() for c in df.columns]
    d = df["DATE"].astype(str).str.replace(".", "-", regex=False)
    ts = pd.to_datetime(d + " " + df["TIME"].astype(str), format="mixed")
    out = pd.DataFrame({
        "timestamp": ts.dt.strftime("%Y-%m-%d %H:%M:%S"),
        "open": df["OPEN"].map(num), "high": df["HIGH"].map(num),
        "low": df["LOW"].map(num), "close": df["CLOSE"].map(num),
        "volume": df["TICKVOL"].map(num) if "TICKVOL" in df.columns else np.nan,
    }).dropna(subset=["open", "high", "low", "close"])
    out = out.drop_duplicates("timestamp").sort_values("timestamp")
    out.to_csv(os.path.join(DATA, out_name), index=False)
    print(f"{out_name:16} rows={len(out):>7}  "
          f"{out['timestamp'].iloc[0]} -> {out['timestamp'].iloc[-1]}")


if __name__ == "__main__":
    for out_name, src in FILES.items():
        p = os.path.join(SRC, src)
        if os.path.exists(p):
            convert(p, out_name)
        else:
            print(f"skip {out_name}: source not found ({p})")
