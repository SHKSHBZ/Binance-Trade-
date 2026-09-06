"""
SMC V2 strategy engine -- Variant C.

SINGLE SOURCE OF TRUTH for the strategy. The backtest and the live bot
both drive this same class, bar by bar, so live behaviour cannot diverge
from what was validated. An earlier version of this file re-implemented
the logic separately and silently disagreed with the backtest on 43 of
79 setups -- hence the equivalence check in validate_engine.py, which
must pass before the bot is allowed near an exchange.

The engine is STATEFUL: it consumes one closed 15m candle at a time and
carries the sequence forward, exactly as the backtest does. State that
matters (liquidity pools and their exhaustion, LTF trend, the pending
sequence, the armed setup) lives in the instance.

The sequence (Variant C), 15m execution with a 4H bias:

  1. SWEEP   price wicks through a 4H swing high/low (a liquidity pool)
  2. CHoCH   within 32 bars, 15m structure breaks the opposite way
  3. OB      last opposite-colour candle followed by an FVG (displacement)
  4. FILL    limit at the 50% midpoint of that OB, valid 96 bars, taken
             only if the nearest opposing pool offers R:R >= 2

Stop  = the sweep wick -/+ 0.3%.  Target = nearest unswept opposing pool.
"""

from dataclasses import dataclass
from typing import Optional, List, Dict

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SMCParams:
    htf_rule: str = "4h"
    htf_swing_lookback: int = 2
    ltf_swing_lookback: int = 3
    htf_pool_expiry_htf_bars: int = 20
    choch_window_bars: int = 32
    retest_window_bars: int = 96
    ob_search_back_bars: int = 30
    stop_buffer_pct: float = 0.003
    stop_mode: str = "sweep"        # "sweep" (orig) | "ob_prev" | "atr"
    stop_atr_mult: float = 0.5      # for stop_mode == "atr"
    stop_min_pct: float = -1.0      # reject setups whose stop is closer than
                                    # this fraction of entry (negative = off,
                                    # preserving the original behaviour)
    min_rr: float = 2.0
    ltf_bars_per_htf: int = 16

    risk_per_trade_pct: float = 0.01
    leverage: int = 10
    margin_safety_cap: float = 0.80
    daily_loss_limit_pct: float = 0.03

    @property
    def pool_life_bars(self) -> int:
        return self.htf_pool_expiry_htf_bars * self.ltf_bars_per_htf

    @property
    def required_bars(self) -> int:
        """History needed to prime the engine before its output is trustworthy."""
        return self.pool_life_bars + self.choch_window_bars + self.retest_window_bars + 300


@dataclass
class Setup:
    direction: str
    limit_price: float
    stop_price: float
    target_price: Optional[float]
    rr: Optional[float]
    sweep_time: pd.Timestamp
    sweep_extreme: float
    choch_time: pd.Timestamp
    ob_time: pd.Timestamp
    ob_high: float
    ob_low: float
    armed_bar: int

    def as_dict(self) -> Dict:
        d = dict(self.__dict__)
        for k in ("sweep_time", "choch_time", "ob_time"):
            d[k] = str(d[k])
        return d


def detect_fractal_swings(highs, lows, lb: int):
    """Confirmed swing points. A swing at i is only knowable at bar i+lb."""
    swing_lows, swing_highs = [], []
    for i in range(lb, len(lows) - lb):
        wl = lows[i - lb:i + lb + 1]
        wh = highs[i - lb:i + lb + 1]
        if lows[i] == wl.min() and list(wl).count(lows[i]) == 1:
            swing_lows.append(i)
        if highs[i] == wh.max() and list(wh).count(highs[i]) == 1:
            swing_highs.append(i)
    return swing_lows, swing_highs


def build_htf_pools(df: pd.DataFrame, p: SMCParams) -> List[Dict]:
    """Liquidity pools from HTF fractals.

    confirm_time avoids look-ahead: a fractal at i needs bars i+1..i+lb to
    close, so the pool is knowable only once bar i+lb has closed, i.e. at
    the open of bar i+lb+1.
    """
    htf = df.resample(p.htf_rule).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna()
    if len(htf) < p.htf_swing_lookback * 2 + 2:
        return []

    highs, lows, times = htf["high"].values, htf["low"].values, htf.index
    lo_idx, hi_idx = detect_fractal_swings(highs, lows, p.htf_swing_lookback)

    pools = []
    for i in lo_idx:
        c = i + p.htf_swing_lookback + 1
        if c < len(times):
            pools.append({"confirm_time": times[c], "level": float(lows[i]), "kind": "low"})
    for i in hi_idx:
        c = i + p.htf_swing_lookback + 1
        if c < len(times):
            pools.append({"confirm_time": times[c], "level": float(highs[i]), "kind": "high"})
    pools.sort(key=lambda x: x["confirm_time"])
    return pools


class SMCEngine:
    """Drive with prepare(df) once, then step(bar_index) for each closed bar.

    `df` is the full 15m series available to the caller. The backtest passes
    the whole history; the live bot passes a rolling window of at least
    params.required_bars candles and re-primes on each new bar. Because both
    paths execute this same code, they agree by construction.
    """

    def __init__(self, params: SMCParams = SMCParams()):
        self.p = params
        self.reset()

    def reset(self):
        self.active_pools: List[Dict] = []
        self._pool_ptr = 0
        self.trend: Optional[str] = None
        self._last_swing_high: Optional[float] = None
        self._last_swing_low: Optional[float] = None
        self.pending_seq: Optional[Dict] = None
        self.armed: Optional[Setup] = None

    # -- setup -------------------------------------------------------------
    def prepare(self, df: pd.DataFrame):
        """Precompute series-level inputs. Call once before stepping."""
        self.df = df
        self.times = df.index
        self.o = df["open"].values
        self.h = df["high"].values
        self.l = df["low"].values
        self.c = df["close"].values
        self.n = len(self.c)

        # ATR(14) on the execution timeframe, for volatility-based stops
        prevc = np.concatenate(([self.c[0]], self.c[:-1]))
        tr = np.maximum(self.h - self.l,
                        np.maximum(np.abs(self.h - prevc), np.abs(self.l - prevc)))
        self._atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().values

        self._pools = build_htf_pools(df, self.p)

        lo_idx, hi_idx = detect_fractal_swings(self.h, self.l, self.p.ltf_swing_lookback)
        self._swing_high_at = np.full(self.n, np.nan)
        self._swing_low_at = np.full(self.n, np.nan)
        for i in hi_idx:
            j = i + self.p.ltf_swing_lookback
            if j < self.n:
                self._swing_high_at[j] = self.h[i]
        for i in lo_idx:
            j = i + self.p.ltf_swing_lookback
            if j < self.n:
                self._swing_low_at[j] = self.l[i]

    def start_bar(self) -> int:
        return max(self.p.ltf_swing_lookback * 2, 20)

    # -- the state machine, one bar at a time ------------------------------
    def step(self, bar: int, blocked: bool) -> Optional[Setup]:
        """Advance one closed candle.

        `blocked` is True when the caller cannot open a new trade right now
        (a position is open, or an order is already resting). It gates BOTH
        entry-hunting and pool consumption, which is what keeps the live bot
        and the backtest on identical paths.

        Returns a Setup on the bar where stages 1-3 complete, else None.
        """
        p = self.p

        while self._pool_ptr < len(self._pools) and \
                self._pools[self._pool_ptr]["confirm_time"] <= self.times[bar]:
            pool = self._pools[self._pool_ptr]
            self.active_pools.append({"level": pool["level"], "kind": pool["kind"],
                                      "formed_bar": bar, "swept": False})
            self._pool_ptr += 1

        for pool in self.active_pools:
            if not pool["swept"] and (bar - pool["formed_bar"]) > p.pool_life_bars:
                pool["swept"] = True     # stale is treated as exhausted

        # --- LTF structure and change-of-character -------------------------
        if not np.isnan(self._swing_high_at[bar]):
            self._last_swing_high = self._swing_high_at[bar]
        if not np.isnan(self._swing_low_at[bar]):
            self._last_swing_low = self._swing_low_at[bar]

        broke_up = self._last_swing_high is not None and self.c[bar] > self._last_swing_high
        broke_down = self._last_swing_low is not None and self.c[bar] < self._last_swing_low
        choch_up = broke_up and self.trend == "bearish"
        choch_down = broke_down and self.trend == "bullish"
        if broke_up:
            self.trend, self._last_swing_high = "bullish", None
        if broke_down:
            self.trend, self._last_swing_low = "bearish", None

        # --- stage 1: sweep -------------------------------------------------
        if self.pending_seq is None and self.armed is None and not blocked:
            for pool in self.active_pools:
                if pool["swept"]:
                    continue
                if pool["kind"] == "low" and self.l[bar] < pool["level"]:
                    pool["swept"] = True
                    self.pending_seq = {"dir": "LONG", "bar": bar,
                                        "extreme": float(self.l[bar]),
                                        "expires": bar + p.choch_window_bars}
                    break
                if pool["kind"] == "high" and self.h[bar] > pool["level"]:
                    pool["swept"] = True
                    self.pending_seq = {"dir": "SHORT", "bar": bar,
                                        "extreme": float(self.h[bar]),
                                        "expires": bar + p.choch_window_bars}
                    break

        # --- stages 2 and 3: CHoCH, then the order block --------------------
        if self.pending_seq is not None:
            if bar > self.pending_seq["expires"]:
                self.pending_seq = None
            else:
                want = choch_up if self.pending_seq["dir"] == "LONG" else choch_down
                if want:
                    ob = self._find_ob(self.pending_seq["bar"], bar,
                                       want_bull=(self.pending_seq["dir"] == "LONG"))
                    setup = None
                    if ob is not None:
                        ob_idx, ob_high, ob_low = ob
                        mid = (ob_high + ob_low) / 2.0
                        extreme = self.pending_seq["extreme"]
                        is_long = self.pending_seq["dir"] == "LONG"
                        # --- stop placement (configurable) ------------------
                        if p.stop_mode == "ob_prev" and ob_idx - 1 >= 0:
                            # low/high of the 15m candle BEFORE the order block
                            stop = self.l[ob_idx - 1] if is_long else self.h[ob_idx - 1]
                        elif p.stop_mode == "atr":
                            buf = p.stop_atr_mult * self._atr[bar]
                            stop = (extreme - buf) if is_long else (extreme + buf)
                        else:  # "sweep" -- original: sweep wick +/- fixed %
                            stop = (extreme * (1 - p.stop_buffer_pct) if is_long
                                    else extreme * (1 + p.stop_buffer_pct))
                        # --- widen the stop to a minimum floor, which also
                        # guarantees it sits on the correct side of entry
                        # (stop_min_pct negative = off, original behaviour) ----
                        dist = (mid - stop) / mid if is_long else (stop - mid) / mid
                        if dist < p.stop_min_pct:
                            stop = (mid * (1 - p.stop_min_pct) if is_long
                                    else mid * (1 + p.stop_min_pct))
                        setup = Setup(
                            direction=self.pending_seq["dir"],
                            limit_price=mid, stop_price=stop,
                            target_price=None, rr=None,
                            sweep_time=self.times[self.pending_seq["bar"]],
                            sweep_extreme=extreme,
                            choch_time=self.times[bar],
                            ob_time=self.times[ob_idx],
                            ob_high=ob_high, ob_low=ob_low,
                            armed_bar=bar,
                        )
                        self.armed = setup
                    self.pending_seq = None
                    if setup is not None:
                        return setup
        return None

    def _find_ob(self, sweep_bar: int, choch_bar: int, want_bull: bool):
        """Last opposite-colour candle followed by an FVG. k+2 may not exceed
        choch_bar, or the search would read a candle that has not printed."""
        start = max(sweep_bar, choch_bar - self.p.ob_search_back_bars)
        for k in range(choch_bar - 2, start - 1, -1):
            if k - 2 < 0 or k + 2 > choch_bar:
                continue
            is_bull_candle = self.c[k] > self.o[k]
            if want_bull and is_bull_candle:
                continue
            if not want_bull and not is_bull_candle:
                continue
            bull_fvg = self.l[k + 2] > self.h[k] and self.c[k + 1] > self.o[k + 1]
            bear_fvg = self.h[k + 2] < self.l[k] and self.c[k + 1] < self.o[k + 1]
            if want_bull and bull_fvg:
                return k, float(self.h[k]), float(self.l[k])
            if (not want_bull) and bear_fvg:
                return k, float(self.h[k]), float(self.l[k])
        return None

    def clear_armed(self):
        self.armed = None

    # -- exit levels -------------------------------------------------------
    def compute_target(self, setup: Setup):
        """Nearest unswept opposing pool, and the resulting reward:risk.

        Evaluated at fill time (as the backtest does), so a target swept
        while the limit rested is replaced rather than traded against a
        level that no longer holds liquidity.
        """
        entry = setup.limit_price
        stop_dist = abs(entry - setup.stop_price)
        if stop_dist <= 0:
            return None, None
        if setup.direction == "LONG":
            cands = [x["level"] for x in self.active_pools
                     if not x["swept"] and x["kind"] == "high" and x["level"] > entry]
            target = min(cands) if cands else None
        else:
            cands = [x["level"] for x in self.active_pools
                     if not x["swept"] and x["kind"] == "low" and x["level"] < entry]
            target = max(cands) if cands else None
        if target is None:
            return None, None
        return float(target), abs(target - entry) / stop_dist


def position_size(balance: float, entry: float, stop: float, p: SMCParams):
    """Size so a stop-out costs exactly risk_per_trade_pct, capped by leverage."""
    stop_dist = abs(entry - stop)
    if stop_dist <= 0 or balance <= 0:
        return 0.0, 0.0
    risk_amt = balance * p.risk_per_trade_pct
    notional = min((risk_amt / stop_dist) * entry,
                   balance * p.leverage * p.margin_safety_cap)
    return notional / entry, notional
