"""
Turn a list of backtest trades into the numbers that actually tell you whether
an edge is real: expectancy, R-multiples, Sharpe, Kelly, max drawdown, and a
Monte-Carlo "is this luck?" test.

The point of this module is the thing we were missing: every headline result
comes back with a confidence range attached, so "2025 made +$1,000" can be read
as "...but shuffle the trade order and the outcome ranges from X to Y, and Z%
of orderings lose money." That is how you tell a real edge from one good run.

A "trade" here is any dict with at least:  pnl.  If it also has entry, stop and
qty (the engine backtest provides these), R-multiples are exact; otherwise R is
approximated from pnl alone and Sharpe/Kelly still work.

Usage as a library:
    from trade_stats import summarize_trades
    stats = summarize_trades(trades, starting_capital=1000.0)
    print(stats.report())

Usage as a script (runs the standard Variant-C scenarios):
    python3 trade_stats.py
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


# ----------------------------------------------------------------------------
# per-trade R-multiples
# ----------------------------------------------------------------------------
def r_multiples(trades):
    """R = profit measured in units of the amount risked on that trade.

    +2R means we made twice what we were risking; -1R is a full stop-out. This
    is the unit that lets you compare trades of different sizes on one scale.
    """
    rs = []
    for t in trades:
        risk = None
        if all(k in t for k in ("entry", "stop", "qty")):
            risk = abs(t["entry"] - t["stop"]) * t["qty"]
        if risk and risk > 0:
            rs.append(t["pnl"] / risk)
    return np.array(rs, dtype=float)


def _trades_per_year(trades):
    times = [t["time"] for t in trades if "time" in t]
    if len(times) < 2:
        return None
    span_days = (max(times) - min(times)).total_seconds() / 86400.0
    if span_days <= 0:
        return None
    return len(trades) / (span_days / 365.25)


# ----------------------------------------------------------------------------
# the summary
# ----------------------------------------------------------------------------
@dataclass
class TradeStats:
    label: str
    n: int
    win_rate: float
    net: float
    ret_pct: float
    max_dd_pct: float
    expectancy_usd: float
    expectancy_r: float          # mean R per trade -- the core edge number
    avg_win_r: float
    avg_loss_r: float
    payoff: float                # avg win / avg loss (in R)
    sharpe_per_trade: float
    sharpe_annual: float | None
    kelly_full: float            # math-optimal fraction of capital to risk
    kelly_quarter: float         # the fraction a sane person actually uses
    # Monte-Carlo (resample trade outcomes, fixed 1% risk, compounded)
    mc_median_ret: float = 0.0
    mc_p05_ret: float = 0.0
    mc_p95_ret: float = 0.0
    mc_prob_profit: float = 0.0
    edge_confidence: float = 0.0    # 100% - p(no-edge could produce this)
    trades_per_year: float | None = None
    _notes: list = field(default_factory=list)

    def report(self) -> str:
        L = []
        A = L.append
        A(f"=== {self.label} ===")
        A(f"  trades              {self.n}")
        A(f"  win rate            {self.win_rate:5.1f}%")
        A(f"  net / return        ${self.net:+,.2f}  ({self.ret_pct:+.1f}%)")
        A(f"  max drawdown        {self.max_dd_pct:.1f}%")
        A("")
        A(f"  expectancy / trade  ${self.expectancy_usd:+,.2f}   "
          f"({self.expectancy_r:+.3f}R)   <- the edge, per trade")
        A(f"  avg win / avg loss  +{self.avg_win_r:.2f}R / {self.avg_loss_r:.2f}R"
          f"   payoff {self.payoff:.2f}:1")
        sa = "n/a" if self.sharpe_annual is None else f"{self.sharpe_annual:.2f}"
        A(f"  Sharpe              {self.sharpe_per_trade:.3f} per trade   "
          f"{sa} annualized   (>1 good, >2 strong)")
        A(f"  Kelly (full)        {self.kelly_full*100:+.1f}% of capital per trade")
        A(f"  Kelly (1/4, usable) {self.kelly_quarter*100:+.1f}%   "
          f"<- vs our fixed 1%")
        A("")
        A(f"  Monte-Carlo (shuffle trade order 5000x, risk 1%/trade):")
        A(f"    median outcome    {self.mc_median_ret:+.1f}%")
        A(f"    5th..95th pct     {self.mc_p05_ret:+.1f}% .. {self.mc_p95_ret:+.1f}%")
        A(f"    chance of profit  {self.mc_prob_profit:4.1f}%")
        A(f"    edge is real      {self.edge_confidence:4.1f}%  "
          f"<- confidence a zero-edge strategy could NOT have done this")
        for note in self._notes:
            A(f"  note: {note}")
        return "\n".join(L)


def summarize_trades(trades, starting_capital=1000.0, label="scenario",
                     mc_runs=5000, mc_risk=0.01, seed=7) -> TradeStats:
    n = len(trades)
    if n == 0:
        return TradeStats(label, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, None, 0, 0,
                          _notes=["no trades"])

    pnls = np.array([t["pnl"] for t in trades], dtype=float)
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    win_rate = len(wins) / n * 100.0
    net = float(pnls.sum())
    final = starting_capital + net
    ret_pct = (final - starting_capital) / starting_capital * 100.0

    # max drawdown from the realized equity curve
    equity = starting_capital + np.cumsum(pnls)
    peak = np.maximum.accumulate(np.concatenate([[starting_capital], equity]))
    dd = (peak[1:] - equity) / np.where(peak[1:] > 0, peak[1:], 1) * 100.0
    max_dd = float(dd.max()) if len(dd) else 0.0

    # R-multiples (exact when geometry is present, else approximate from pnl)
    rs = r_multiples(trades)
    notes = []
    if len(rs) != n:
        # fall back: express each pnl as R using the average risked amount
        avg_risk = np.mean(np.abs(pnls[pnls != 0])) or 1.0
        rs = pnls / avg_risk
        notes.append("R approximated from pnl (trade geometry not in records)")

    expectancy_usd = float(pnls.mean())
    expectancy_r = float(rs.mean())
    win_r = rs[rs > 0]
    loss_r = rs[rs < 0]
    avg_win_r = float(win_r.mean()) if len(win_r) else 0.0
    avg_loss_r = float(loss_r.mean()) if len(loss_r) else 0.0
    payoff = (avg_win_r / abs(avg_loss_r)) if avg_loss_r != 0 else 0.0

    # Sharpe: reward per unit of variability, in R units
    sd_r = float(rs.std(ddof=1)) if n > 1 else 0.0
    sharpe_per_trade = (expectancy_r / sd_r) if sd_r > 0 else 0.0
    tpy = _trades_per_year(trades)
    sharpe_annual = sharpe_per_trade * math.sqrt(tpy) if tpy else None

    # Kelly: with win prob p and payoff b (avg win / avg loss),
    #   f* = p - (1-p)/b   -- fraction of capital to risk for max growth
    p = len(wins) / n
    b = payoff
    kelly_full = (p - (1 - p) / b) if b > 0 else 0.0
    kelly_quarter = kelly_full / 4.0

    # ---- Monte-Carlo: is the headline result luck? ----
    rng = np.random.default_rng(seed)
    # (1) bootstrap the ACTUAL outcomes -> range of what this edge could produce
    idx = rng.integers(0, n, size=(mc_runs, n))
    samples = rs[idx]                                   # (mc_runs, n)
    finals = (np.prod(1.0 + mc_risk * samples, axis=1) - 1.0) * 100.0
    mc_median = float(np.median(finals))
    mc_p05 = float(np.percentile(finals, 5))
    mc_p95 = float(np.percentile(finals, 95))
    mc_prob_profit = float((finals > 0).mean() * 100.0)

    # (2) significance: could a strategy with NO edge (mean R = 0) have produced
    #     an expectancy this good by chance? Center the outcomes to zero mean
    #     (the null hypothesis), resample, and see how often the null beats us.
    null_rs = rs - rs.mean()
    null_means = null_rs[rng.integers(0, n, size=(mc_runs, n))].mean(axis=1)
    p_luck = float((null_means >= expectancy_r).mean())   # one-sided p-value
    edge_confidence = (1.0 - p_luck) * 100.0

    if n < 30:
        notes.append(f"only {n} trades -- statistics are weak; treat as a hint")
    # a sane strategy loses about 1R when stopped; if the average loss is far
    # bigger, the stops are not controlling risk (the known stop-geometry bug)
    if avg_loss_r < -1.6:
        notes.append(f"avg loss is {avg_loss_r:.1f}R -- stops are NOT capping risk "
                     "at ~1R (stop-geometry problem; see STOPLOSS findings)")
    # realized-$ and R-expectancy should agree in sign; if not, R is distorted
    if (net > 0) != (expectancy_r > 0):
        notes.append("realized profit and per-trade R disagree in sign -- "
                     "a few trades with distorted stop distance dominate R")

    return TradeStats(
        label=label, n=n, win_rate=win_rate, net=net, ret_pct=ret_pct,
        max_dd_pct=max_dd, expectancy_usd=expectancy_usd, expectancy_r=expectancy_r,
        avg_win_r=avg_win_r, avg_loss_r=avg_loss_r, payoff=payoff,
        sharpe_per_trade=sharpe_per_trade, sharpe_annual=sharpe_annual,
        kelly_full=kelly_full, kelly_quarter=kelly_quarter,
        mc_median_ret=mc_median, mc_p05_ret=mc_p05, mc_p95_ret=mc_p95,
        mc_prob_profit=mc_prob_profit, edge_confidence=edge_confidence,
        trades_per_year=tpy, _notes=notes,
    )


# ----------------------------------------------------------------------------
# script: run the standard scenarios through the new lens
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    from backtest_engine import run, STARTING_CAPITAL
    from smc_engine import SMCParams

    ap = argparse.ArgumentParser(description="math-complete backtest report")
    ap.add_argument("--stop", default="atr",
                    choices=["atr", "sweep", "fixed", "ob_prev", "sr"],
                    help="stop rule (default atr -- the sane, risk-capping one)")
    args = ap.parse_args()

    # ATR stop with a floor so no microscopic stops -> R-multiples are meaningful
    params = SMCParams(stop_mode=args.stop, stop_atr_mult=0.5, stop_min_points=150.0)

    print("Math-complete backtest report -- Variant C strategy")
    print(f"Stop rule: {args.stop} (floored)   Risk: 1%/trade\n")
    print("Reading each year not just by profit, but by whether the profit is")
    print("statistically real. Watch the 'edge is real' line: below ~90% means")
    print("a strategy with no edge at all could plausibly have produced it.\n")

    scenarios = [
        ("2023", "BTCUSDT_15m_2023_to_2025.csv", "2023-01-01", "2023-12-31"),
        ("2024", "BTCUSDT_15m_2023_to_2025.csv", "2024-01-01", "2024-12-31"),
        ("2025", "BTCUSDT_15m_2023_to_2025.csv", "2025-01-01", "2025-12-31"),
        ("2026 (Jan-Jul)", "BTCUSDT_15m_Jan_to_Jul2026.csv", None, None),
    ]
    all_trades = []
    for label, f, s, e in scenarios:
        try:
            trades, final, mdd = run(f, s, e, params=params)
        except FileNotFoundError:
            print(f"=== {label} ===\n  data file {f} not found, skipping\n")
            continue
        all_trades += trades
        print(summarize_trades(trades, STARTING_CAPITAL, label=label).report())
        print()

    if all_trades:
        print(summarize_trades(all_trades, STARTING_CAPITAL,
                               label="ALL YEARS POOLED").report())
        print()
