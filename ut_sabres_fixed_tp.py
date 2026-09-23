"""
UT Bot + MA Sabres with FIXED DOLLAR TP / SL (leverage-sized position).

Model requested by the user:
  * Account equity: 2500 USD.
  * Position sized with leverage: notional = equity * LEVERAGE.
  * Take-profit: close the trade at +TP_USD realised profit.
  * Stop-loss:   close the trade at -SL_USD realised loss,
                 with a hard MAX_LOSS_USD cap (used on gap-throughs).
  * Because the position is a fixed notional, a fixed $ target maps to a
    fixed PRICE distance:  price_move = target_usd * entry / notional.
    Higher leverage -> smaller price move needed -> hit sooner (and more often),
    but the TP:SL ratio (e.g. 1000:250 = 4:1) is invariant to leverage.

Entries reuse the exact merged rule set from ut_sabres_backtest:
  long  = UT Buy  & MA baseline rising   & close > baseline
  short = UT Sell & MA baseline falling  & close < baseline

Fill assumptions (stated):
  * Enter at the signal candle's close.
  * TP/SL are exchange-side; a candle whose range touches a level fills there.
  * If one candle's range spans BOTH levels (a gap/violent bar), assume the
    STOP fills first (pessimistic), capped at MAX_LOSS_USD.
  * Commission charged on notional, both sides.
"""

import numpy as np

from data_loader import load_ohlcv
from ut_sabres_backtest import baseline_ma, ut_bot

ACCOUNT = 2500.0
LEVERAGE = 10.0
TP_USD = 1000.0
SL_USD = 250.0
MAX_LOSS_USD = 500.0
COMMISSION_PCT = 0.0004
FORWARD_BARS = 800
MA_TYPE, MA_LEN = "TEMA", 50
UT_KEY, UT_ATR = 2.0, 1


def run(data_file, start=None, end=None, leverage=LEVERAGE, tp_usd=TP_USD,
        sl_usd=SL_USD, max_loss=MAX_LOSS_USD, ut_key=UT_KEY, ut_atr=UT_ATR,
        ma_type=MA_TYPE, ma_len=MA_LEN):
    df = load_ohlcv(data_file, start, end)
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    times = df.index
    n = len(c)

    ma = baseline_ma(c, ma_type, ma_len)
    rising = np.concatenate([[False], ma[1:] > ma[:-1]])
    _, ut_buy, ut_sell = ut_bot(h, l, c, key=ut_key, atr_period=ut_atr)
    longsig = ut_buy & rising & (c > ma)
    shortsig = ut_sell & (~rising) & (c < ma)

    equity = ACCOUNT
    peak = equity
    max_dd = 0.0
    trades = []
    warmup = ma_len * 3
    in_pos_until = warmup - 1

    for i in range(warmup, n):
        if i <= in_pos_until:
            continue
        go_long, go_short = longsig[i], shortsig[i]
        if not (go_long or go_short):
            continue

        entry = c[i]
        notional = equity * leverage        # fixed-notional, leverage-sized
        qty = notional / entry
        # $ targets -> price distances
        tp_dist = tp_usd / qty
        sl_dist = sl_usd / qty
        cap_dist = max_loss / qty
        direction = "LONG" if go_long else "SHORT"

        if direction == "LONG":
            tp_price, sl_price, cap_price = entry + tp_dist, entry - sl_dist, entry - cap_dist
        else:
            tp_price, sl_price, cap_price = entry - tp_dist, entry + sl_dist, entry + cap_dist

        end = min(i + 1 + FORWARD_BARS, n)
        exit_pnl = exit_reason = exit_bar = None
        for j in range(i + 1, end):
            if direction == "LONG":
                hit_sl = l[j] <= sl_price
                hit_tp = h[j] >= tp_price
                gap = l[j] <= cap_price            # blew past the cap
            else:
                hit_sl = h[j] >= sl_price
                hit_tp = l[j] <= tp_price
                gap = h[j] >= cap_price
            if hit_sl and hit_tp:                  # both in one bar -> stop first
                exit_pnl, exit_reason, exit_bar = -sl_usd, "STOP", j
                break
            if hit_sl:
                loss = max_loss if gap else sl_usd  # cap only if it gapped through
                exit_pnl, exit_reason, exit_bar = -loss, ("CAP" if gap else "STOP"), j
                break
            if hit_tp:
                exit_pnl, exit_reason, exit_bar = tp_usd, "TP", j
                break
        if exit_pnl is None:                        # timed out -> mark to last close
            last = c[end - 1]
            exit_pnl = (qty * (last - entry) if direction == "LONG"
                        else qty * (entry - last))
            exit_reason, exit_bar = "TIME", end - 1

        comm = notional * COMMISSION_PCT * 2
        net = exit_pnl - comm
        equity += net
        peak = max(peak, equity)
        dd = (peak - equity) / peak * 100 if peak > 0 else 0.0
        max_dd = max(max_dd, dd)
        trades.append({"dir": direction, "time": times[i], "exit_time": times[exit_bar],
                       "pnl": net, "exit_r": exit_reason, "bal": equity})
        in_pos_until = exit_bar
        if equity <= 0:
            equity = 0.0
            break
    return trades, equity, max_dd


def summarize(label, trades, final, mdd):
    n = len(trades)
    wins = [t for t in trades if t["pnl"] > 0]
    wr = len(wins) / n * 100 if n else 0.0
    ret = (final - ACCOUNT) / ACCOUNT * 100
    tp = sum(1 for t in trades if t["exit_r"] == "TP")
    st = sum(1 for t in trades if t["exit_r"] in ("STOP", "CAP"))
    print(f"{label:<18} trades={n:<4} WR={wr:5.1f}%  TP={tp:<4} SL={st:<4} "
          f"final=${final:8.0f}  return={ret:+8.1f}%  maxDD={mdd:5.1f}%")
    return n, ret


if __name__ == "__main__":
    print(f"Fixed $ TP/SL  |  account=${ACCOUNT:.0f}  TP=${TP_USD:.0f} "
          f"SL=${SL_USD:.0f} cap=${MAX_LOSS_USD:.0f}  (4:1 R:R)\n")
    for lev in (5, 10, 20):
        print(f"--- leverage {lev}x ---")
        for f, lbl, s, e in [
            ("BTCUSDT_15m_2023_to_2025.csv", "15m 2023-25", None, None),
            ("BTCUSDT_1h_2023_to_2025.csv",  "1h 2023-25",  None, None),
            ("BTCUSDT_1h_Jan_to_Jul2026.csv", "1h 2026",     None, None),
        ]:
            t, fin, dd = run(f, s, e, leverage=lev)
            summarize(lbl, t, fin, dd)
        print()
