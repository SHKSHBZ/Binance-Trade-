"""
Causal backtest — SMC Spec v3, Scenario 2 (pullback into an unmitigated
order block, in the Swing-50 trend direction).

CAUSALITY IS THE WHOLE POINT
----------------------------
The labeler (smc_luxalgo.py) is run once over full history, but this
backtest only ever reads its output AS-OF the current bar:
  * an order block is usable only from its `created_index` (the bar its
    structure break confirmed it) and only while unmitigated as of `i`;
  * a swing target level is usable only from its confirmation bar (already
    swing_length bars after the extreme).
Nothing a full-history labeling reveals early is ever read. This is the
exact class of bug the BTC README says bit this project twice.

Single position at a time. Conservative same-bar fills (stop before
target). Reports gross and net (fees + slippage). See SMC_STRATEGY_SPEC_v3.md.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import pandas as pd

import _paths  # noqa: F401  # puts repo root on sys.path

from data_loader import load_ohlcv
from smc_luxalgo import label_smc_luxalgo


# --- indicators (Wilder) ------------------------------------------------
def _rma(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) < n:
        return out
    out[n - 1] = np.mean(x[:n])
    for i in range(n, len(x)):
        out[i] = (out[i - 1] * (n - 1) + x[i]) / n
    return out


def atr(h, l, c, n=14):
    prev = np.concatenate(([np.nan], c[:-1]))
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev), np.abs(l - prev)))
    tr[0] = h[0] - l[0]
    return _rma(tr, n)


def rsi(c, n=14):
    d = np.diff(c, prepend=c[0])
    up = np.where(d > 0, d, 0.0)
    dn = np.where(d < 0, -d, 0.0)
    ru, rd = _rma(up, n), _rma(dn, n)
    rs = np.divide(ru, rd, out=np.full_like(ru, np.nan), where=rd > 0)
    return 100 - 100 / (1 + rs)


def adx(h, l, c, n=14):
    up = h[1:] - h[:-1]
    dn = l[:-1] - l[1:]
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    prev = c[:-1]
    tr = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - prev), np.abs(l[1:] - prev)))
    atr_ = _rma(tr, n)
    pdi = 100 * _rma(plus_dm, n) / np.where(atr_ == 0, np.nan, atr_)
    mdi = 100 * _rma(minus_dm, n) / np.where(atr_ == 0, np.nan, atr_)
    dx = 100 * np.abs(pdi - mdi) / np.where((pdi + mdi) == 0, np.nan, pdi + mdi)
    adx_ = _rma(np.nan_to_num(dx), n)
    return np.concatenate(([np.nan], adx_))   # realign to length n


# --- config -------------------------------------------------------------
@dataclass
class Config:
    swing_length: int = 50           # TUNABLE
    min_rr: float = 2.0              # TUNABLE
    stop_atr_buffer: float = 0.25   # FROZEN
    rejection_ratio: float = 0.66   # FROZEN
    breakeven_R: float = 1.0        # FROZEN
    time_stop_bars: int = 20        # FROZEN
    use_adx_gate: bool = True
    adx_min: float = 25.0
    use_trailing: bool = True
    risk_per_trade: float = 0.01
    fee_per_side: float = 0.0004
    slippage: float = 0.0002
    start_equity: float = 10_000.0


@dataclass
class Trade:
    direction: str
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry: float
    stop: float
    target: float
    exit_price: float
    reason: str
    r_multiple_net: float
    pnl_net: float
    bars_held: int


class Scenario2Backtest:
    def __init__(self, cfg: Config = Config()):
        self.cfg = cfg

    def run(self, df: pd.DataFrame):
        cfg = self.cfg
        labeled, result = label_smc_luxalgo(df, swing_length=cfg.swing_length)

        o = df["open"].to_numpy(float)
        h = df["high"].to_numpy(float)
        l = df["low"].to_numpy(float)
        c = df["close"].to_numpy(float)
        t = df.index
        n = len(c)

        atr14 = atr(h, l, c, 14)
        adx14 = adx(h, l, c, 14)
        trend = labeled["swing_trend"].to_numpy(object)

        # order blocks, sorted so we can scan the ones known as-of a bar
        obs = result.order_blocks
        bull_obs = [ob for ob in obs if ob["bias"] == "bullish"]
        bear_obs = [ob for ob in obs if ob["bias"] == "bearish"]

        # causal swing target levels: (confirm_bar_index, level)
        sh = labeled["swing_pivot_high"].to_numpy(float)
        sl = labeled["swing_pivot_low"].to_numpy(float)
        swing_highs = [(i, sh[i]) for i in range(n) if not np.isnan(sh[i])]
        swing_lows = [(i, sl[i]) for i in range(n) if not np.isnan(sl[i])]
        # internal swings for trailing
        ih = labeled["internal_pivot_high"].to_numpy(float)
        il = labeled["internal_pivot_low"].to_numpy(float)
        internal_highs = [(i, ih[i]) for i in range(n) if not np.isnan(ih[i])]
        internal_lows = [(i, il[i]) for i in range(n) if not np.isnan(il[i])]

        trades: List[Trade] = []
        equity = cfg.start_equity
        equity_curve = [(t[0], equity)]
        skipped_rr = 0
        skipped_adx = 0

        def nearest_target(direction, entry, e):
            if direction == "LONG":
                cands = [lvl for (ci, lvl) in swing_highs if ci <= e and lvl > entry]
                return min(cands) if cands else None
            else:
                cands = [lvl for (ci, lvl) in swing_lows if ci <= e and lvl < entry]
                return max(cands) if cands else None

        def latest_internal(direction, j, price, floor_stop):
            """Most recent internal swing (known as-of j) for trailing."""
            if direction == "LONG":
                cands = [lvl for (ci, lvl) in internal_lows if ci <= j and lvl < price and lvl > floor_stop]
                return max(cands) if cands else None
            else:
                cands = [lvl for (ci, lvl) in internal_highs if ci <= j and lvl > price and lvl < floor_stop]
                return min(cands) if cands else None

        i = max(cfg.swing_length + 20, 210)   # warm up ATR(200) in the labeler too
        while i < n:
            tr = trend[i]
            direction = None
            if tr == "bullish":
                direction = "LONG"
            elif tr == "bearish":
                direction = "SHORT"

            setup = None
            if direction == "LONG":
                rng = h[i] - l[i]
                is_rej = rng > 0 and (c[i] - l[i]) / rng >= cfg.rejection_ratio and c[i] > o[i]
                if is_rej:
                    # an unmitigated bullish OB the bar traded into
                    for ob in bull_obs:
                        if ob["created_index"] <= i and \
                           (ob["mitigated_index"] is None or ob["mitigated_index"] > i) and \
                           l[i] <= ob["top"] and l[i] >= ob["bottom"] - atr14[i]:
                            setup = ob
                            break
            elif direction == "SHORT":
                rng = h[i] - l[i]
                is_rej = rng > 0 and (h[i] - c[i]) / rng >= cfg.rejection_ratio and c[i] < o[i]
                if is_rej:
                    for ob in bear_obs:
                        if ob["created_index"] <= i and \
                           (ob["mitigated_index"] is None or ob["mitigated_index"] > i) and \
                           h[i] >= ob["bottom"] and h[i] <= ob["top"] + atr14[i]:
                            setup = ob
                            break

            if setup is None:
                i += 1
                continue

            # regime gate
            if cfg.use_adx_gate and not (adx14[i] >= cfg.adx_min):
                skipped_adx += 1
                i += 1
                continue

            # entry / stop / target
            a = atr14[i]
            if direction == "LONG":
                entry = c[i] * (1 + cfg.slippage)
                stop = setup["bottom"] - cfg.stop_atr_buffer * a
                target = nearest_target("LONG", entry, i)
            else:
                entry = c[i] * (1 - cfg.slippage)
                stop = setup["top"] + cfg.stop_atr_buffer * a
                target = nearest_target("SHORT", entry, i)

            R = abs(entry - stop)
            if target is None or R <= 0:
                i += 1
                continue
            rr = abs(target - entry) / R
            if rr < cfg.min_rr:
                skipped_rr += 1
                i += 1
                continue

            # ---- simulate the trade forward (causal, bar by bar) ----
            risk_amt = equity * cfg.risk_per_trade
            size = risk_amt / R
            stop_cur = stop
            be_moved = False
            exit_price = None
            reason = None
            j = i + 1
            while j < n:
                reached_1R = (h[j] >= entry + R) if direction == "LONG" else (l[j] <= entry - R)

                if direction == "LONG":
                    if l[j] <= stop_cur:
                        exit_price = stop_cur * (1 - cfg.slippage); reason = "stop"; break
                    if h[j] >= target:
                        exit_price = target; reason = "target"; break
                else:
                    if h[j] >= stop_cur:
                        exit_price = stop_cur * (1 + cfg.slippage); reason = "stop"; break
                    if l[j] <= target:
                        exit_price = target; reason = "target"; break

                # breakeven at +1R
                if not be_moved and reached_1R:
                    stop_cur = entry
                    be_moved = True
                # trailing after BE, on fast internal structure
                if be_moved and cfg.use_trailing:
                    lvl = latest_internal(direction, j, c[j], stop_cur)
                    if lvl is not None:
                        stop_cur = max(stop_cur, lvl) if direction == "LONG" else min(stop_cur, lvl)
                # time stop
                if (j - i) >= cfg.time_stop_bars and not be_moved:
                    exit_price = c[j]; reason = "time"; break
                j += 1

            if exit_price is None:            # ran out of data
                exit_price = c[n - 1]; reason = "eod"; j = n - 1

            gross = size * (exit_price - entry) * (1 if direction == "LONG" else -1)
            fees = cfg.fee_per_side * (size * entry + size * exit_price)
            pnl_net = gross - fees
            equity += pnl_net
            equity_curve.append((t[j], equity))

            trades.append(Trade(
                direction=direction, entry_time=t[i], exit_time=t[j],
                entry=entry, stop=stop, target=target, exit_price=exit_price,
                reason=reason, r_multiple_net=pnl_net / risk_amt,
                pnl_net=pnl_net, bars_held=j - i))

            i = j + 1   # single position: resume after the exit

        return self._report(df, trades, equity_curve, cfg,
                            skipped_rr, skipped_adx)

    # --- stats ----------------------------------------------------------
    def _report(self, df, trades, equity_curve, cfg, skipped_rr, skipped_adx):
        eq = pd.Series([e for _, e in equity_curve],
                       index=[ts for ts, _ in equity_curve])
        peak = eq.cummax()
        max_dd = float(((eq - peak) / peak).min()) if len(eq) > 1 else 0.0

        rs = np.array([t.r_multiple_net for t in trades])
        wins = rs[rs > 0]; losses = rs[rs <= 0]
        gross_win = wins.sum() if len(wins) else 0.0
        gross_loss = -losses.sum() if len(losses) else 0.0
        pf = (gross_win / gross_loss) if gross_loss > 0 else float("inf")

        stats = {
            "period": f"{df.index.min():%Y-%m-%d} -> {df.index.max():%Y-%m-%d}",
            "bars": len(df),
            "trades": len(trades),
            "win_rate": float((rs > 0).mean()) if len(rs) else 0.0,
            "expectancy_R": float(rs.mean()) if len(rs) else 0.0,
            "profit_factor": pf,
            "total_return_pct": (eq.iloc[-1] / cfg.start_equity - 1) * 100 if len(eq) else 0.0,
            "max_drawdown_pct": max_dd * 100,
            "avg_bars_held": float(np.mean([t.bars_held for t in trades])) if trades else 0.0,
            "skipped_low_rr": skipped_rr,
            "skipped_adx": skipped_adx,
            "exits": pd.Series([t.reason for t in trades]).value_counts().to_dict() if trades else {},
        }
        return stats, trades, eq


def _print(tag, stats):
    print(f"\n=== {tag} ===")
    print(f"  period            {stats['period']}   ({stats['bars']:,} bars)")
    print(f"  trades            {stats['trades']}")
    print(f"  win rate          {stats['win_rate']*100:.1f}%")
    print(f"  expectancy        {stats['expectancy_R']:+.3f} R / trade")
    print(f"  profit factor     {stats['profit_factor']:.2f}")
    print(f"  total return      {stats['total_return_pct']:+.1f}%   (1% risk/trade)")
    print(f"  max drawdown      {stats['max_drawdown_pct']:.1f}%")
    print(f"  avg bars held     {stats['avg_bars_held']:.0f}")
    print(f"  skipped (RR/ADX)  {stats['skipped_low_rr']} / {stats['skipped_adx']}")
    print(f"  exits             {stats['exits']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="?", default="BTCUSDT_15m_Jan_to_Jul2026.csv")
    ap.add_argument("--no-adx", action="store_true", help="disable the ADX regime gate")
    ap.add_argument("--swing", type=int, default=50)
    ap.add_argument("--rr", type=float, default=2.0)
    args = ap.parse_args()

    df = load_ohlcv(args.csv)
    cfg = Config(use_adx_gate=not args.no_adx, swing_length=args.swing, min_rr=args.rr)
    stats, trades, eq = Scenario2Backtest(cfg).run(df)
    _print(f"Scenario 2  |  {args.csv}  |  swing={args.swing} rr={args.rr} "
           f"adx_gate={'off' if args.no_adx else 'on'}", stats)
