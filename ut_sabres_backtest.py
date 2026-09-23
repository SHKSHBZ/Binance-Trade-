"""
UT Bot Alerts + MA Sabres -- mechanical backtest on BTCUSDT.

STRATEGY (as specified)
-----------------------
Indicators:
  * UT Bot Alerts   -- Key Value (sensitivity) a = 2, ATR period c = 1.
                       Gives an ATR trailing stop and Buy/Sell crossover signals.
  * MA Sabres       -- baseline MA (default TEMA, length 50) used as the dynamic
                       trend filter. "Blue" regime = baseline rising, "Red" = falling.

Long setup (enter at the CLOSE of the signalling candle):
  * MA Sabres regime Blue  (baseline rising)  AND  close > baseline  ("above the cloud")
  * UT Bot prints a confirmed Buy.

Short setup (mirror):
  * MA Sabres regime Red   (baseline falling) AND  close < baseline
  * UT Bot prints a confirmed Sell.

Risk & management:
  * Stop-loss  = recent swing low (long) / swing high (short), lookback SWING_LOOKBACK.
  * Take-profit = none fixed. Trail until a candle CLOSES back through the baseline MA
                  (close < baseline exits a long; close > baseline exits a short).
                  A protective stop still applies intrabar if hit first.

Execution assumptions (stated, not hidden):
  * Entry filled at the signal candle's close (signals are close-confirmed / non-repainting).
  * Protective stop is exchange-side; if a candle's range touches it, it fills there first.
  * Baseline-cross exit fills at that candle's close.
  * Commission charged both sides; risk-based position sizing (RISK_PCT of capital).
"""

import numpy as np
import pandas as pd

from data_loader import load_ohlcv

# ---- account / execution -------------------------------------------------
STARTING_CAPITAL = 1000.0
RISK_PCT = 0.01           # fraction of capital risked to the stop per trade
COMMISSION_PCT = 0.0004   # per side
STOP_SLIPPAGE_PCT = 0.0   # set 0.001 to price in realistic stop slippage

# ---- indicator parameters ------------------------------------------------
UT_KEY = 2.0              # UT Bot sensitivity (a)
UT_ATR = 1                # UT Bot ATR period (c)
MA_TYPE = "TEMA"          # baseline MA type
MA_LEN = 50               # baseline MA length
SWING_LOOKBACK = 10       # bars used to find the recent swing for the stop
ALLOW_LONG = True
ALLOW_SHORT = True


# ---- indicator maths -----------------------------------------------------
def _ema(x: np.ndarray, length: int) -> np.ndarray:
    alpha = 2.0 / (length + 1.0)
    out = np.empty_like(x)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = alpha * x[i] + (1 - alpha) * out[i - 1]
    return out


def _rma(x: np.ndarray, length: int) -> np.ndarray:
    alpha = 1.0 / length
    out = np.empty_like(x)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = alpha * x[i] + (1 - alpha) * out[i - 1]
    return out


def baseline_ma(close: np.ndarray, ma_type: str, length: int) -> np.ndarray:
    """Baseline used by MA Sabres. TEMA is the script default."""
    if ma_type == "EMA":
        return _ema(close, length)
    if ma_type == "SMA":
        s = pd.Series(close).rolling(length, min_periods=1).mean()
        return s.to_numpy()
    if ma_type == "SMMA (RMA)":
        return _rma(close, length)
    # TEMA (default): 3*e1 - 3*e2 + e3
    e1 = _ema(close, length)
    e2 = _ema(e1, length)
    e3 = _ema(e2, length)
    return 3 * e1 - 3 * e2 + e3


def true_range(h, l, c) -> np.ndarray:
    prev_c = np.roll(c, 1)
    prev_c[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))
    return tr


def ut_bot(h, l, c, key=UT_KEY, atr_period=UT_ATR):
    """Standard UT Bot Alerts: ATR trailing stop + Buy/Sell crossovers.

    Mirrors the common Pine v4/v5 implementation:
      src = close; ema(src, 1) == src so the crossover is close vs. trailing stop.
    Returns (trailing_stop, buy[bool], sell[bool]).
    """
    n = len(c)
    atr = _rma(true_range(h, l, c), atr_period)
    nloss = key * atr

    stop = np.zeros(n)
    stop[0] = c[0] - nloss[0]
    for i in range(1, n):
        prev = stop[i - 1]
        if c[i] > prev and c[i - 1] > prev:
            stop[i] = max(prev, c[i] - nloss[i])
        elif c[i] < prev and c[i - 1] < prev:
            stop[i] = min(prev, c[i] + nloss[i])
        elif c[i] > prev:
            stop[i] = c[i] - nloss[i]
        else:
            stop[i] = c[i] + nloss[i]

    buy = np.zeros(n, dtype=bool)
    sell = np.zeros(n, dtype=bool)
    for i in range(1, n):
        cross_up = c[i - 1] <= stop[i - 1] and c[i] > stop[i]
        cross_dn = c[i - 1] >= stop[i - 1] and c[i] < stop[i]
        buy[i] = c[i] > stop[i] and cross_up
        sell[i] = c[i] < stop[i] and cross_dn
    return stop, buy, sell


# ---- backtest ------------------------------------------------------------
def run(data_file, start=None, end=None, stop_slippage=STOP_SLIPPAGE_PCT,
        ma_type=MA_TYPE, ma_len=MA_LEN, swing_lb=SWING_LOOKBACK):
    df = load_ohlcv(data_file, start, end)
    o, h, l, c = (df["open"].values, df["high"].values,
                  df["low"].values, df["close"].values)
    times = df.index
    n = len(c)

    ma = baseline_ma(c, ma_type, ma_len)
    ma_rising = np.concatenate([[False], ma[1:] > ma[:-1]])
    stop_line, ut_buy, ut_sell = ut_bot(h, l, c)

    long_signal = ut_buy & ma_rising & (c > ma)
    short_signal = ut_sell & (~ma_rising) & (c < ma)

    capital = STARTING_CAPITAL
    peak = capital
    max_dd = 0.0
    trades = []

    pos = None  # dict when in a trade
    warmup = ma_len * 3  # let TEMA settle

    for i in range(warmup, n):
        # ---- manage an open position first ----
        if pos is not None:
            d = pos["dir"]
            exit_price = exit_reason = None
            if d == "LONG":
                if l[i] <= pos["stop"]:
                    exit_price, exit_reason = pos["stop"], "STOP"
                elif c[i] < ma[i]:
                    exit_price, exit_reason = c[i], "MA_CROSS"
            else:
                if h[i] >= pos["stop"]:
                    exit_price, exit_reason = pos["stop"], "STOP"
                elif c[i] > ma[i]:
                    exit_price, exit_reason = c[i], "MA_CROSS"

            if exit_price is not None:
                fill = exit_price
                if exit_reason == "STOP" and stop_slippage:
                    fill = (exit_price * (1 - stop_slippage) if d == "LONG"
                            else exit_price * (1 + stop_slippage))
                qty = pos["qty"]
                gross = (qty * (fill - pos["entry"]) if d == "LONG"
                         else qty * (pos["entry"] - fill))
                comm = qty * pos["entry"] * COMMISSION_PCT + qty * fill * COMMISSION_PCT
                net = gross - comm
                capital += net
                peak = max(peak, capital)
                dd = (peak - capital) / peak * 100 if peak > 0 else 0.0
                max_dd = max(max_dd, dd)
                r = net / pos["risk_amt"] if pos["risk_amt"] > 0 else 0.0
                trades.append({
                    "dir": d, "time": pos["time"], "exit_time": times[i],
                    "entry": pos["entry"], "stop": pos["stop"],
                    "exit": fill, "exit_r": exit_reason,
                    "qty": qty, "pnl": net, "R": r, "bal": capital,
                })
                pos = None
                if capital <= 0:
                    break
            else:
                continue  # still holding; no new entry while in a trade

        if pos is not None:
            continue

        # ---- look for a fresh entry at this candle's close ----
        go_long = ALLOW_LONG and long_signal[i]
        go_short = ALLOW_SHORT and short_signal[i]
        if not (go_long or go_short):
            continue

        entry = c[i]
        lo = max(0, i - swing_lb)
        if go_long:
            stop = float(np.min(l[lo:i + 1]))
            direction = "LONG"
        else:
            stop = float(np.max(h[lo:i + 1]))
            direction = "SHORT"

        stop_dist = abs(entry - stop)
        if stop_dist <= 0:
            continue
        risk_amt = capital * RISK_PCT
        qty = risk_amt / stop_dist
        if qty <= 0:
            continue

        pos = {"dir": direction, "time": times[i], "entry": entry,
               "stop": stop, "qty": qty, "risk_amt": risk_amt}

    return trades, capital, max_dd


def summarize(label, trades, final, mdd):
    wins = [t for t in trades if t["pnl"] > 0]
    wr = len(wins) / len(trades) * 100 if trades else 0.0
    ret = (final - STARTING_CAPITAL) / STARTING_CAPITAL * 100
    avg_r = np.mean([t["R"] for t in trades]) if trades else 0.0
    gains = sum(t["pnl"] for t in wins)
    losses = -sum(t["pnl"] for t in trades if t["pnl"] <= 0)
    pf = (gains / losses) if losses > 0 else float("inf")
    longs = sum(1 for t in trades if t["dir"] == "LONG")
    print(f"{label:<16} trades={len(trades):<4} (L{longs}/S{len(trades)-longs})  "
          f"WR={wr:5.1f}%  avgR={avg_r:+5.2f}  PF={pf:4.2f}  "
          f"return={ret:+9.1f}%  maxDD={mdd:5.1f}%")
    return len(trades), ret


if __name__ == "__main__":
    print("UT Bot (key=2, ATR=1) + MA Sabres (TEMA-50 baseline) -- BTCUSDT 15m\n")

    print("== In-sample 2025 ==")
    t25, f25, d25 = run("BTCUSDT_15m_2023_to_2025.csv", "2025-01-01", "2025-12-31")
    summarize("2025", t25, f25, d25)

    print("\n== Out-of-sample 2026 ==")
    t26, f26, d26 = run("BTCUSDT_15m_Jan_to_Jul2026.csv")
    summarize("2026", t26, f26, d26)

    print("\n== Full 2023-2025 sample ==")
    tall, fall, dall = run("BTCUSDT_15m_2023_to_2025.csv")
    summarize("2023-2025", tall, fall, dall)

    print("\nWith 0.1% stop slippage:")
    t25c, f25c, d25c = run("BTCUSDT_15m_2023_to_2025.csv", "2025-01-01",
                           "2025-12-31", stop_slippage=0.001)
    summarize("2025 costed", t25c, f25c, d25c)
