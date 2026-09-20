"""
Trader Mayne "Structure & OTE" Playbook -- faithful, causal backtest.

HTF (Daily): trend + Break of Structure (BOS), range + 50% (premium/discount),
             POI = Order Block (last opposite candle before the BOS move),
             target = next external liquidity (nearest daily swing beyond).
LTF (H1/M30): entry INSIDE the POI via a liquidity sweep + reclaim
             (price wicks beyond the OB edge grabbing stops, closes back in).
Stop: beyond the swept wick. Target: HTF external liquidity. Min 2:1 RR.

Long only in a bullish BOS (buy discount); short only in a bearish BOS (sell
premium). One trade per setup. Honest fees + slippage + min-stop filter.
Scored with trade_stats + a random-direction null. Instrument-agnostic.

Run:  python3 mayne_playbook.py
"""
import _paths  # noqa: F401
import numpy as np
import pandas as pd
from data_loader import load_ohlcv
from trade_stats import summarize_trades

CAP = 1000.0
MAKER, TAKER, SLIP = 0.0002, 0.0004, 0.0003
PD = 3            # daily swing strength
OB_LOOKBACK = 10  # days back to find the order block before a BOS
MIN_RR = 2.0
MIN_RISK_FRAC = 0.0005
POI_WAIT = 400    # LTF bars a setup stays valid waiting for entry


def confirmed_pivots(h, l, half):
    n = len(h); ph = np.full(n, np.nan); pl = np.full(n, np.nan)
    for i in range(half, n - half):
        if h[i] == h[i-half:i+half+1].max(): ph[i] = h[i]
        if l[i] == l[i-half:i+half+1].min(): pl[i] = l[i]
    kh = np.full(n, np.nan); kl = np.full(n, np.nan)
    for i in range(half, n - half):
        if not np.isnan(ph[i]) and i+half < n: kh[i+half] = ph[i]
        if not np.isnan(pl[i]) and i+half < n: kl[i+half] = pl[i]
    return kh, kl


def build_daily_setups(d):
    """Return per-day active setup arrays (causal: known at that day's close)."""
    o = d["open"].values; h = d["high"].values; l = d["low"].values; c = d["close"].values
    n = len(d)
    kh, kl = confirmed_pivots(h, l, PD)
    highs = []; lows = []      # confirmed swing values seen so far
    bias = np.zeros(n); ob_lo = np.full(n, np.nan); ob_hi = np.full(n, np.nan)
    mid = np.full(n, np.nan); tgt = np.full(n, np.nan); rng_lo = np.full(n, np.nan)
    rng_hi = np.full(n, np.nan); sid = np.zeros(n)
    cur_bias = 0; setup_id = 0
    a_oblo = a_obhi = a_mid = a_tgt = a_rlo = a_rhi = np.nan
    for i in range(n):
        if not np.isnan(kh[i]): highs.append(kh[i])
        if not np.isnan(kl[i]): lows.append(kl[i])
        # invalidate active setup if structure breaks the other way
        if cur_bias == 1 and not np.isnan(a_rlo) and c[i] < a_rlo:
            cur_bias = 0
        if cur_bias == -1 and not np.isnan(a_rhi) and c[i] > a_rhi:
            cur_bias = 0
        # detect a fresh BOS
        if len(highs) >= 1 and len(lows) >= 1:
            last_sh = highs[-1]; last_sl = lows[-1]
            if cur_bias != 1 and c[i] > last_sh:            # bullish BOS
                # order block = last down candle in the lookback
                ob = np.nan
                for k in range(i, max(i-OB_LOOKBACK, 0)-1, -1):
                    if c[k] < o[k]:
                        a_oblo, a_obhi = l[k], h[k]; ob = k; break
                if not np.isnan(a_oblo):
                    a_rlo, a_rhi = last_sl, last_sh
                    a_mid = 0.5*(a_rlo + a_rhi)
                    above = [x for x in highs if x > a_rhi]
                    a_tgt = min(above) if above else a_rhi + (a_rhi - a_rlo)
                    cur_bias = 1; setup_id += 1
            elif cur_bias != -1 and c[i] < last_sl:          # bearish BOS
                ob = np.nan
                for k in range(i, max(i-OB_LOOKBACK, 0)-1, -1):
                    if c[k] > o[k]:
                        a_oblo, a_obhi = l[k], h[k]; ob = k; break
                if not np.isnan(a_oblo):
                    a_rlo, a_rhi = last_sl, last_sh
                    a_mid = 0.5*(a_rlo + a_rhi)
                    below = [x for x in lows if x < a_rlo]
                    a_tgt = max(below) if below else a_rlo - (a_rhi - a_rlo)
                    cur_bias = -1; setup_id += 1
        bias[i] = cur_bias; ob_lo[i] = a_oblo if cur_bias else np.nan
        ob_hi[i] = a_obhi if cur_bias else np.nan; mid[i] = a_mid if cur_bias else np.nan
        tgt[i] = a_tgt if cur_bias else np.nan; rng_lo[i] = a_rlo if cur_bias else np.nan
        rng_hi[i] = a_rhi if cur_bias else np.nan; sid[i] = setup_id if cur_bias else 0
    return pd.DataFrame({"bias": bias, "ob_lo": ob_lo, "ob_hi": ob_hi, "mid": mid,
                         "tgt": tgt, "rng_lo": rng_lo, "rng_hi": rng_hi, "sid": sid},
                        index=d.index)


def run(ltf_file, start=None, end=None, force_dir=None, seed=None,
        target_mode="ext", rr_fixed=3.0):
    df = load_ohlcv(ltf_file, start, end)
    o = df["open"].values; h = df["high"].values; l = df["low"].values; c = df["close"].values
    t = df.index; n = len(c)
    d = df.resample("1D").agg(open=("open","first"), high=("high","max"),
                              low=("low","min"), close=("close","last")).dropna()
    setups = build_daily_setups(d)
    # causal map: an LTF bar uses the setup known as of the PREVIOUS day's close
    day = df.index.normalize()
    prev = {}
    days = list(setups.index)
    for col in setups.columns:
        prev[col] = pd.Series(day).map({days[i]: setups[col].values[i-1] if i >= 1 else np.nan
                                        for i in range(len(days))}).values
    bias = prev["bias"]; ob_lo = prev["ob_lo"]; ob_hi = prev["ob_hi"]
    mid = prev["mid"]; tgt = prev["tgt"]; sid = prev["sid"]

    rng = np.random.default_rng(seed)
    capital = CAP; trades = []; busy = -1; done_sid = -1

    for i in range(1, n-1):
        if i <= busy: continue
        s = sid[i]
        if np.isnan(s) or s == 0 or s == done_sid: continue
        direction = entry = stop = target = None
        if bias[i] == 1 and c[i] <= mid[i]:               # bullish: buy discount
            # price inside/at OB and sweeps below OB low then reclaims
            if l[i] < ob_lo[i] and c[i] > ob_lo[i]:
                direction = "LONG"; entry = c[i]; stop = l[i]*(1-SLIP*0); stop = l[i]; target = tgt[i]
        elif bias[i] == -1 and c[i] >= mid[i]:            # bearish: sell premium
            if h[i] > ob_hi[i] and c[i] < ob_hi[i]:
                direction = "SHORT"; entry = c[i]; stop = h[i]; target = tgt[i]
        if direction is None: continue
        if abs(entry-stop)/entry < MIN_RISK_FRAC: continue
        if target_mode == "fixed":                        # fixed RR target instead of external
            risk0 = abs(entry-stop)
            target = entry + rr_fixed*risk0 if direction == "LONG" else entry - rr_fixed*risk0
        if force_dir == "random":
            risk = abs(entry-stop)
            direction = "LONG" if rng.random() < 0.5 else "SHORT"
            if direction == "LONG": stop = entry-risk; target = entry+2*risk
            else: stop = entry+risk; target = entry-2*risk
        if direction == "LONG" and not (stop < entry < target): continue
        if direction == "SHORT" and not (target < entry < stop): continue
        rr = abs(target-entry)/abs(entry-stop)
        if rr < MIN_RR: continue

        qty = (capital*0.01)/abs(entry-stop)
        exit_px = exit_r = None; j = i+1
        while j < n:
            if direction == "LONG":
                if l[j] <= stop: exit_px, exit_r = stop, "STOP"; break
                if h[j] >= target: exit_px, exit_r = target, "TARGET"; break
            else:
                if h[j] >= stop: exit_px, exit_r = stop, "STOP"; break
                if l[j] <= target: exit_px, exit_r = target, "TARGET"; break
            j += 1
        if exit_px is None: j = n-1; exit_px, exit_r = c[j], "END"
        if exit_r in ("STOP","END"): exit_px *= (1-SLIP) if direction=="LONG" else (1+SLIP)
        gross = qty*(exit_px-entry) if direction=="LONG" else qty*(entry-exit_px)
        fee = qty*entry*TAKER + qty*exit_px*(MAKER if exit_r=="TARGET" else TAKER)
        capital = max(capital+gross-fee, 0.0)
        trades.append({"dir":direction,"time":t[i],"entry":entry,"stop":stop,"target":target,
                       "qty":qty,"notional":qty*entry,"pnl":gross-fee,"exit_r":exit_r,"rr":rr})
        busy = j; done_sid = s
        if capital <= 0: break
    return trades


def report(name, ltf_file, years):
    print(f"\n===== MAYNE PLAYBOOK on {name} (HTF=Daily, LTF={ltf_file.split('_')[1]}) =====")
    pooled = []
    for label, s, e in years:
        tr = run(ltf_file, s, e); pooled += tr
        st = summarize_trades(tr, CAP, label=str(label))
        rr = np.mean([x["rr"] for x in tr]) if tr else 0
        print(f"  {label}: n={st.n:<3} win={st.win_rate:4.1f}%  avgRR={rr:.1f}  ret={st.ret_pct:+8.1f}%  expR={st.expectancy_r:+.3f}")
    ps = summarize_trades(pooled, CAP)
    print(f"  POOLED: n={ps.n:<3} win={ps.win_rate:4.1f}%  ret={ps.ret_pct:+7.1f}%  expR={ps.expectancy_r:+.3f}  edge={ps.edge_confidence:.0f}%")
    return ps, pooled


if __name__ == "__main__":
    GOLD = [(y, f"{y}-01-01", f"{y}-12-31") for y in range(2020, 2027)]
    report("GOLD", "XAUUSD_1h.csv", GOLD)
