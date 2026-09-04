"""
SMC LuxAlgo — faithful Python port of "Smart Money Concepts [LuxAlgo]"
=====================================================================
This is a line-for-line reimplementation of the *detection* logic in
LuxAlgo's TradingView Pine v5 indicator (SMC_Pine_Script.txt), rebuilt as
a stateful, bar-by-bar engine so its output can be measured statistically
instead of only looked at on a chart.

WHY A REWRITE (vs. the older smc_labeler.py)
--------------------------------------------
smc_labeler.py was a loose approximation and drifted from the real
indicator in seven ways (dual structure, swing method, order-block
selection, OB mitigation/expiry, EQH/EQL, premium/discount, FVG
significance filter). This module reproduces the actual algorithm:

  * Dual structure   — a fast INTERNAL swing (length 5) and a slow SWING
                       (length 50) tracked simultaneously.
  * Swing detection  — LuxAlgo's `leg()`: a rolling backward-looking
                       ta.highest / ta.lowest, NOT a centred fractal that
                       needs future candles. A pivot at bar b is only
                       *confirmed* `length` bars later, so there is no
                       look-ahead.
  * Order blocks     — high-volatility candles are neutralised with an ATR
                       (or cumulative-mean-range) filter, then the most
                       extreme parsed candle in the leg is chosen.
  * OB mitigation    — an order block is removed the moment price closes
                       (or wicks) back through it. Dead blocks stop being
                       counted as live setups.
  * FVG              — 3-candle imbalance with LuxAlgo's auto significance
                       threshold (running mean of |bar delta%| * 2).
  * EQH / EQL        — equal highs / lows within a threshold * ATR.
  * Trailing extremes — strong / weak highs & lows, and premium / discount
                       / equilibrium levels.

WHAT IS DEFERRED
----------------
Pure chart rendering with no analytical meaning is not ported: the
daily/weekly/monthly MTF level lines and the visual box/line/label
drawing. Everything that classifies a candle is here.

Pine semantics preserved
-------------------------
`x[n]` = value n bars ago. `var` = persists across bars. The historical
arrays LuxAlgo `.push()`es each bar are indexed here directly by bar
index into numpy arrays (identical result, no copies). `ta.crossover`
uses both current and previous values of each operand, so pivot levels
carry a one-bar history.

Usage
-----
    from data_loader import load_ohlcv
    from smc_luxalgo import label_smc_luxalgo

    df = load_ohlcv("BTCUSDT_15m_2023_to_2025.csv")
    labeled, result = label_smc_luxalgo(df)     # df with SMC columns
    labeled.to_csv("btc_smc_labeled.csv")
    print(result.summary())                     # counts of every event

`result.order_blocks` and `result.fair_value_gaps` hold the full life of
every zone (formed bar, mitigated/filled bar) for backtesting entries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict

import numpy as np
import pandas as pd

# --- constants, mirroring the Pine source -------------------------------
BULLISH = +1
BEARISH = -1

BULLISH_LEG = 1
BEARISH_LEG = 0

ATR = "Atr"
RANGE = "Cumulative Mean Range"
CLOSE = "Close"
HIGHLOW = "High/Low"


# --- records ------------------------------------------------------------
@dataclass
class OrderBlock:
    bar_index: int          # candle the block sits on
    bar_time: pd.Timestamp
    bar_high: float
    bar_low: float
    bias: int               # BULLISH or BEARISH
    internal: bool
    created_index: int = -1              # bar the OB became KNOWN (the break bar)
    created_time: Optional[pd.Timestamp] = None
    mitigated_index: Optional[int] = None
    mitigated_time: Optional[pd.Timestamp] = None

    def as_dict(self) -> Dict:
        return {
            "kind": "internal" if self.internal else "swing",
            "bias": "bullish" if self.bias == BULLISH else "bearish",
            "bar_index": self.bar_index,
            "bar_time": self.bar_time,
            "top": self.bar_high,
            "bottom": self.bar_low,
            "created_index": self.created_index,
            "created_time": self.created_time,
            "mitigated_index": self.mitigated_index,
            "mitigated_time": self.mitigated_time,
        }


@dataclass
class FairValueGap:
    bar_index: int          # 3rd candle of the imbalance (detection bar)
    bar_time: pd.Timestamp
    top: float
    bottom: float
    bias: int
    filled_index: Optional[int] = None
    filled_time: Optional[pd.Timestamp] = None

    def as_dict(self) -> Dict:
        return {
            "bias": "bullish" if self.bias == BULLISH else "bearish",
            "bar_index": self.bar_index,
            "bar_time": self.bar_time,
            "top": self.top,
            "bottom": self.bottom,
            "filled_index": self.filled_index,
            "filled_time": self.filled_time,
        }


@dataclass
class _Pivot:
    """LuxAlgo `pivot` UDT: a confirmed swing point that price may cross."""
    current_level: float = np.nan
    last_level: float = np.nan
    crossed: bool = False
    bar_index: int = -1
    bar_time: Optional[pd.Timestamp] = None
    prev_level: float = np.nan   # value one bar ago, for ta.crossover


@dataclass
class SMCResult:
    df: pd.DataFrame
    order_blocks: List[Dict] = field(default_factory=list)
    fair_value_gaps: List[Dict] = field(default_factory=list)

    def summary(self) -> str:
        d = self.df
        def c(col):
            return int(d[col].sum()) if col in d else 0
        lines = [
            "SMC LuxAlgo labeling summary",
            "-" * 40,
            f"bars                     {len(d):>8,}",
            f"swing pivots  (H / L)    {int(d['swing_pivot_high'].notna().sum()):>4} / "
            f"{int(d['swing_pivot_low'].notna().sum())}",
            f"internal piv. (H / L)    {int(d['internal_pivot_high'].notna().sum()):>4} / "
            f"{int(d['internal_pivot_low'].notna().sum())}",
            f"swing  BOS   (bull/bear) {c('swing_bull_bos'):>4} / {c('swing_bear_bos')}",
            f"swing  CHoCH (bull/bear) {c('swing_bull_choch'):>4} / {c('swing_bear_choch')}",
            f"intern BOS   (bull/bear) {c('internal_bull_bos'):>4} / {c('internal_bear_bos')}",
            f"intern CHoCH (bull/bear) {c('internal_bull_choch'):>4} / {c('internal_bear_choch')}",
            f"order blocks (int/swing) {sum(1 for o in self.order_blocks if o['kind']=='internal'):>4} / "
            f"{sum(1 for o in self.order_blocks if o['kind']=='swing')}",
            f"fair value gaps          {len(self.fair_value_gaps):>8}",
            f"equal highs / lows       {c('equal_high'):>4} / {c('equal_low')}",
        ]
        return "\n".join(lines)


# --- vectorised primitives (Pine ta.* helpers) --------------------------
def _true_range(h, l, c) -> np.ndarray:
    prev_c = np.concatenate(([np.nan], c[:-1]))
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))
    tr[0] = h[0] - l[0]
    return tr


def _rma(x: np.ndarray, n: int) -> np.ndarray:
    """Wilder's RMA (ta.rma): SMA-seeded EMA with alpha = 1/n."""
    out = np.full(len(x), np.nan)
    if len(x) < n:
        return out
    seed = np.mean(x[:n])
    out[n - 1] = seed
    for i in range(n, len(x)):
        out[i] = (out[i - 1] * (n - 1) + x[i]) / n
    return out


class SMCLuxAlgo:
    """Bar-by-bar port of the LuxAlgo SMC indicator.

    Construct, then call `run(df)`; state is reset on each run.
    """

    def __init__(
        self,
        swing_length: int = 50,
        internal_length: int = 5,
        equal_length: int = 3,
        equal_threshold: float = 0.1,
        order_block_filter: str = ATR,          # ATR or RANGE
        order_block_mitigation: str = HIGHLOW,  # CLOSE or HIGHLOW
        fvg_auto_threshold: bool = True,
        internal_confluence_filter: bool = False,
    ):
        self.swing_length = swing_length
        self.internal_length = internal_length
        self.equal_length = equal_length
        self.equal_threshold = equal_threshold
        self.order_block_filter = order_block_filter
        self.order_block_mitigation = order_block_mitigation
        self.fvg_auto_threshold = fvg_auto_threshold
        self.internal_confluence_filter = internal_confluence_filter

    # -- leg / pivot detection (vectorised) ------------------------------
    def _leg(self, size: int) -> np.ndarray:
        """Port of `leg(size)`.

        newLegHigh = high[size] > ta.highest(size)
        newLegLow  = low[size]  < ta.lowest(size)
        leg flips to BEARISH_LEG(0) on a new high pivot, BULLISH_LEG(1) on
        a new low pivot, and holds otherwise (a `var`).
        """
        h, l = self._high, self._low
        n = self.n
        # ta.highest(size)/lowest(size): extremum over the `size` bars
        # ending at the current bar (inclusive).
        hh = pd.Series(h).rolling(size).max().values
        ll = pd.Series(l).rolling(size).min().values
        high_back = np.concatenate((np.full(size, np.nan), h[:-size])) if size < n else np.full(n, np.nan)
        low_back = np.concatenate((np.full(size, np.nan), l[:-size])) if size < n else np.full(n, np.nan)

        leg = np.zeros(n, dtype=int)
        cur = 0
        for i in range(n):
            new_high = not np.isnan(high_back[i]) and not np.isnan(hh[i]) and high_back[i] > hh[i]
            new_low = not np.isnan(low_back[i]) and not np.isnan(ll[i]) and low_back[i] < ll[i]
            if new_high:
                cur = BEARISH_LEG
            elif new_low:
                cur = BULLISH_LEG
            leg[i] = cur
        return leg

    # -- main entry point ------------------------------------------------
    def run(self, df: pd.DataFrame) -> SMCResult:
        required = {"open", "high", "low", "close"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"df is missing columns: {sorted(missing)}")

        self.df = df
        self.n = len(df)
        self._time = df.index
        self._open = df["open"].to_numpy(float)
        self._high = df["high"].to_numpy(float)
        self._low = df["low"].to_numpy(float)
        self._close = df["close"].to_numpy(float)

        n = self.n
        h, l, c = self._high, self._low, self._close

        # --- volatility filter for order blocks (parsed high/low) --------
        tr = _true_range(h, l, c)
        atr = _rma(tr, 200)
        bar_idx = np.arange(n, dtype=float)
        cum_mean_range = np.cumsum(tr) / np.where(bar_idx == 0, 1, bar_idx)
        vol = atr if self.order_block_filter == ATR else cum_mean_range
        vol = np.where(np.isnan(vol), cum_mean_range, vol)   # before ATR warms up
        high_vol = (h - l) >= (2.0 * vol)
        self._parsed_high = np.where(high_vol, l, h)
        self._parsed_low = np.where(high_vol, h, l)
        self._atr = np.where(np.isnan(atr), cum_mean_range, atr)

        # --- precompute leg change flags for each structure --------------
        legs = {
            "swing": self._leg(self.swing_length),
            "internal": self._leg(self.internal_length),
            "equal": self._leg(self.equal_length),
        }
        sizes = {"swing": self.swing_length, "internal": self.internal_length,
                 "equal": self.equal_length}
        change = {k: np.concatenate(([0], np.diff(v))) for k, v in legs.items()}

        # --- state ------------------------------------------------------
        swing_high = _Pivot(); swing_low = _Pivot()
        internal_high = _Pivot(); internal_low = _Pivot()
        equal_high = _Pivot(); equal_low = _Pivot()
        swing_trend = 0
        internal_trend = 0
        trailing = {"top": np.nan, "bottom": np.nan, "bar_index": -1,
                    "bar_time": None, "last_top_time": None, "last_bottom_time": None}

        internal_obs: List[OrderBlock] = []
        swing_obs: List[OrderBlock] = []
        all_obs: List[OrderBlock] = []
        fvgs: List[FairValueGap] = []
        all_fvgs: List[FairValueGap] = []

        # --- output columns ---------------------------------------------
        out = {k: np.full(n, np.nan) for k in (
            "swing_pivot_high", "swing_pivot_low",
            "internal_pivot_high", "internal_pivot_low",
            "fvg_bull_top", "fvg_bull_bottom", "fvg_bear_top", "fvg_bear_bottom",
            "premium_top", "premium_bottom", "equilibrium",
            "discount_top", "discount_bottom",
            "trailing_top", "trailing_bottom",
        )}
        bcols = ("swing_bull_bos", "swing_bear_bos", "swing_bull_choch", "swing_bear_choch",
                 "internal_bull_bos", "internal_bear_bos", "internal_bull_choch",
                 "internal_bear_choch", "equal_high", "equal_low",
                 "internal_ob_mitigated", "swing_ob_mitigated",
                 "fvg_bull_new", "fvg_bear_new", "fvg_filled")
        outb = {k: np.zeros(n, dtype=bool) for k in bcols}
        scol = {k: np.array([None] * n, dtype=object) for k in (
            "swing_trend", "internal_trend", "strong_weak_high", "strong_weak_low")}

        def get_pivot(kind, is_low):
            if kind == "equal":
                return equal_low if is_low else equal_high
            if kind == "internal":
                return internal_low if is_low else internal_high
            return swing_low if is_low else swing_high

        # ================================================================
        #  bar-by-bar execution — mirrors the Pine execution block
        # ================================================================
        for i in range(n):

            # (1) trailing extremes -------------------------------------
            if np.isnan(trailing["top"]):
                trailing["top"], trailing["bottom"] = h[i], l[i]
                trailing["last_top_time"] = trailing["last_bottom_time"] = self._time[i]
                trailing["bar_time"] = self._time[i]
                trailing["bar_index"] = i
            else:
                if h[i] >= trailing["top"]:
                    trailing["top"] = h[i]; trailing["last_top_time"] = self._time[i]
                if l[i] <= trailing["bottom"]:
                    trailing["bottom"] = l[i]; trailing["last_bottom_time"] = self._time[i]

            # (2) delete filled FVGs (before new detection) --------------
            for fvg in fvgs[:]:
                if (l[i] < fvg.bottom and fvg.bias == BULLISH) or \
                   (h[i] > fvg.top and fvg.bias == BEARISH):
                    fvg.filled_index = i
                    fvg.filled_time = self._time[i]
                    fvgs.remove(fvg)
                    outb["fvg_filled"][i] = True

            # (3) getCurrentStructure for swing, internal, equal ---------
            self._get_structure("swing", i, sizes, change, get_pivot, out,
                                 trailing, swing_trend, swing_high, swing_low)
            self._get_structure("internal", i, sizes, change, get_pivot, out,
                                 trailing, internal_trend, internal_high, internal_low)
            self._get_structure("equal", i, sizes, change, get_pivot, out,
                                 trailing, None, equal_high, equal_low, outb)

            # (4) displayStructure — internal, then swing ----------------
            internal_trend = self._display_structure(
                True, i, internal_high, internal_low, internal_trend,
                swing_high, swing_low, internal_obs, all_obs, outb)
            swing_trend = self._display_structure(
                False, i, swing_high, swing_low, swing_trend,
                swing_high, swing_low, swing_obs, all_obs, outb)

            # (5) order-block mitigation ---------------------------------
            self._mitigate_obs(internal_obs, i, True, outb)
            self._mitigate_obs(swing_obs, i, False, outb)

            # (6) new fair value gap -------------------------------------
            if i >= 2:
                self._detect_fvg(i, fvgs, all_fvgs, outb, out)

            # (7) per-bar scalar outputs ---------------------------------
            scol["swing_trend"][i] = (
                "bullish" if swing_trend == BULLISH else
                "bearish" if swing_trend == BEARISH else None)
            scol["internal_trend"][i] = (
                "bullish" if internal_trend == BULLISH else
                "bearish" if internal_trend == BEARISH else None)
            scol["strong_weak_high"][i] = (
                "strong_high" if swing_trend == BEARISH else "weak_high")
            scol["strong_weak_low"][i] = (
                "strong_low" if swing_trend == BULLISH else "weak_low")

            out["trailing_top"][i] = trailing["top"]
            out["trailing_bottom"][i] = trailing["bottom"]

            # premium / discount / equilibrium (from trailing range)
            top, bot = trailing["top"], trailing["bottom"]
            if not np.isnan(top) and not np.isnan(bot):
                out["premium_top"][i] = top
                out["premium_bottom"][i] = 0.95 * top + 0.05 * bot
                out["equilibrium"][i] = 0.5 * (top + bot)
                out["discount_top"][i] = 0.95 * bot + 0.05 * top
                out["discount_bottom"][i] = bot

        # --- assemble result -------------------------------------------
        result_df = df.copy()
        for k, v in out.items():
            result_df[k] = v
        for k, v in outb.items():
            result_df[k] = v
        for k, v in scol.items():
            result_df[k] = v

        return SMCResult(
            df=result_df,
            order_blocks=[o.as_dict() for o in all_obs],
            fair_value_gaps=[f.as_dict() for f in all_fvgs],
        )

    # -- getCurrentStructure --------------------------------------------
    def _get_structure(self, kind, i, sizes, change, get_pivot, out, trailing,
                        trend, pivot_high, pivot_low, outb=None):
        size = sizes[kind]
        ch = change[kind][i]
        if ch == 0:
            return
        pivot_low_event = ch == +1     # startOfBullishLeg -> a swing LOW
        pivot_high_event = ch == -1    # startOfBearishLeg -> a swing HIGH
        src = i - size                 # bar the extreme actually sits on
        if src < 0:
            return

        if pivot_low_event:
            p = pivot_low
            if kind == "equal":
                if not np.isnan(p.current_level) and \
                   abs(p.current_level - self._low[src]) < self.equal_threshold * self._atr[i]:
                    outb["equal_low"][i] = True
            p.last_level = p.current_level
            p.current_level = self._low[src]
            p.crossed = False
            p.bar_index = src
            p.bar_time = self._time[src]
            if kind == "swing":
                out["swing_pivot_low"][i] = self._low[src]
                trailing["bottom"] = p.current_level
                trailing["bar_time"] = p.bar_time
                trailing["bar_index"] = p.bar_index
                trailing["last_bottom_time"] = p.bar_time
            elif kind == "internal":
                out["internal_pivot_low"][i] = self._low[src]
        else:  # pivot_high_event
            p = pivot_high
            if kind == "equal":
                if not np.isnan(p.current_level) and \
                   abs(p.current_level - self._high[src]) < self.equal_threshold * self._atr[i]:
                    outb["equal_high"][i] = True
            p.last_level = p.current_level
            p.current_level = self._high[src]
            p.crossed = False
            p.bar_index = src
            p.bar_time = self._time[src]
            if kind == "swing":
                out["swing_pivot_high"][i] = self._high[src]
                trailing["top"] = p.current_level
                trailing["bar_time"] = p.bar_time
                trailing["bar_index"] = p.bar_index
                trailing["last_top_time"] = p.bar_time
            elif kind == "internal":
                out["internal_pivot_high"][i] = self._high[src]

    # -- displayStructure -----------------------------------------------
    def _display_structure(self, internal, i, pivot_high, pivot_low, trend,
                           swing_high, swing_low, obs, all_obs, outb):
        c = self._close
        bullish_bar = bearish_bar = True
        if internal and self.internal_confluence_filter:
            o, hi, lo = self._open[i], self._high[i], self._low[i]
            bullish_bar = (hi - max(c[i], o)) > min(c[i], o - lo)
            bearish_bar = (hi - max(c[i], o)) < min(c[i], o - lo)

        # --- bullish break: close crosses OVER the high pivot -----------
        p = pivot_high
        extra = True
        if internal:
            extra = (p.current_level != swing_high.current_level) and bullish_bar
        if (not np.isnan(p.current_level) and not p.crossed and extra and
                not np.isnan(p.prev_level) and
                c[i] > p.current_level and c[i - 1] <= p.prev_level):
            is_choch = trend == BEARISH
            if internal:
                outb["internal_bull_choch"][i] = is_choch
                outb["internal_bull_bos"][i] = not is_choch
            else:
                outb["swing_bull_choch"][i] = is_choch
                outb["swing_bull_bos"][i] = not is_choch
            p.crossed = True
            trend = BULLISH
            self._store_ob(p, internal, BULLISH, i, obs, all_obs)

        # --- bearish break: close crosses UNDER the low pivot -----------
        p = pivot_low
        extra = True
        if internal:
            extra = (p.current_level != swing_low.current_level) and bearish_bar
        if (not np.isnan(p.current_level) and not p.crossed and extra and
                not np.isnan(p.prev_level) and
                c[i] < p.current_level and c[i - 1] >= p.prev_level):
            is_choch = trend == BULLISH
            if internal:
                outb["internal_bear_choch"][i] = is_choch
                outb["internal_bear_bos"][i] = not is_choch
            else:
                outb["swing_bear_choch"][i] = is_choch
                outb["swing_bear_bos"][i] = not is_choch
            p.crossed = True
            trend = BEARISH
            self._store_ob(p, internal, BEARISH, i, obs, all_obs)

        # snapshot pivot levels for next bar's ta.crossover
        pivot_high.prev_level = pivot_high.current_level
        pivot_low.prev_level = pivot_low.current_level
        return trend

    # -- storeOrdeBlock --------------------------------------------------
    def _store_ob(self, p, internal, bias, i, obs, all_obs):
        if p.bar_index < 0 or p.bar_index >= i:
            return
        if bias == BEARISH:
            seg = self._parsed_high[p.bar_index:i]
            if len(seg) == 0:
                return
            idx = p.bar_index + int(np.argmax(seg))
        else:
            seg = self._parsed_low[p.bar_index:i]
            if len(seg) == 0:
                return
            idx = p.bar_index + int(np.argmin(seg))
        ob = OrderBlock(
            bar_index=idx, bar_time=self._time[idx],
            bar_high=float(self._parsed_high[idx]),
            bar_low=float(self._parsed_low[idx]),
            bias=bias, internal=internal,
            created_index=i, created_time=self._time[i],
        )
        if len(obs) >= 100:
            obs.pop()
        obs.insert(0, ob)   # unshift
        all_obs.append(ob)

    # -- deleteOrderBlocks (mitigation) ----------------------------------
    def _mitigate_obs(self, obs, i, internal, outb):
        bearish_src = self._close[i] if self.order_block_mitigation == CLOSE else self._high[i]
        bullish_src = self._close[i] if self.order_block_mitigation == CLOSE else self._low[i]
        for ob in obs[:]:
            crossed = False
            if bearish_src > ob.bar_high and ob.bias == BEARISH:
                crossed = True
            elif bullish_src < ob.bar_low and ob.bias == BULLISH:
                crossed = True
            if crossed:
                ob.mitigated_index = i
                ob.mitigated_time = self._time[i]
                obs.remove(ob)
                outb["internal_ob_mitigated" if internal else "swing_ob_mitigated"][i] = True

    # -- drawFairValueGaps (detection only) ------------------------------
    def _detect_fvg(self, i, fvgs, all_fvgs, outb, out):
        # same-timeframe port: lastClose=close[1], last2High=high[2], etc.
        last_close = self._close[i - 1]
        last_open = self._open[i - 1]
        cur_high, cur_low = self._high[i], self._low[i]
        last2_high, last2_low = self._high[i - 2], self._low[i - 2]

        bar_delta_pct = (last_close - last_open) / (last_open * 100) if last_open else 0.0
        if self.fvg_auto_threshold:
            # running mean of |bar delta%| * 2  (ta.cum(abs(...))/bar_index * 2)
            self._fvg_delta_sum = getattr(self, "_fvg_delta_sum", 0.0) + abs(bar_delta_pct)
            threshold = (self._fvg_delta_sum / i) * 2 if i > 0 else 0.0
        else:
            threshold = 0.0

        bull = cur_low > last2_high and last_close > last2_high and bar_delta_pct > threshold
        bear = cur_high < last2_low and last_close < last2_low and -bar_delta_pct > threshold

        if bull:
            fvg = FairValueGap(i, self._time[i], top=cur_low, bottom=last2_high, bias=BULLISH)
            fvgs.insert(0, fvg); all_fvgs.append(fvg)
            outb["fvg_bull_new"][i] = True
            out["fvg_bull_top"][i] = cur_low
            out["fvg_bull_bottom"][i] = last2_high
        if bear:
            fvg = FairValueGap(i, self._time[i], top=last2_low, bottom=cur_high, bias=BEARISH)
            fvgs.insert(0, fvg); all_fvgs.append(fvg)
            outb["fvg_bear_new"][i] = True
            out["fvg_bear_top"][i] = last2_low
            out["fvg_bear_bottom"][i] = cur_high


# --- convenience API ----------------------------------------------------
def label_smc_luxalgo(df: pd.DataFrame, **kwargs) -> Tuple[pd.DataFrame, SMCResult]:
    """Label an OHLCV DataFrame with LuxAlgo SMC structure.

    Returns (labeled_df, result). `result.summary()` prints event counts;
    `result.order_blocks` / `result.fair_value_gaps` give full zone life
    (formation and mitigation/fill bars) for backtesting.
    """
    engine = SMCLuxAlgo(**kwargs)
    result = engine.run(df)
    return result.df, result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Label OHLCV data with LuxAlgo SMC structure.")
    parser.add_argument("csv", nargs="?", help="CSV in DATA/ (or a path). Omit for a self-test.")
    parser.add_argument("-o", "--out", help="write labeled CSV here")
    parser.add_argument("--start"); parser.add_argument("--end")
    args = parser.parse_args()

    if args.csv:
        from data_loader import load_ohlcv
        df = load_ohlcv(args.csv, start=args.start, end=args.end)
    else:
        # deterministic synthetic self-test (no data file needed)
        rng = np.random.default_rng(0)
        steps = rng.normal(0, 1, 2000).cumsum() + 1000
        idx = pd.date_range("2024-01-01", periods=2000, freq="15min")
        o = steps
        c = steps + rng.normal(0, 0.5, 2000)
        hi = np.maximum(o, c) + np.abs(rng.normal(0, 0.5, 2000))
        lo = np.minimum(o, c) - np.abs(rng.normal(0, 0.5, 2000))
        df = pd.DataFrame({"open": o, "high": hi, "low": lo, "close": c}, index=idx)
        print("No CSV given — running on synthetic data.\n")

    labeled, result = label_smc_luxalgo(df)
    print(result.summary())
    if args.out:
        labeled.to_csv(args.out)
        print(f"\nwrote {args.out}")
