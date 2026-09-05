"""
SMC V2 live bot (Variant C) -- Binance USD-M Futures TESTNET, multi-symbol.

Runs the exact strategy validated in backtest_engine.py / backtest_portfolio.py
by driving smc_engine.SMCEngine once per symbol. If this bot does something,
the backtest does it too -- that equivalence is the whole point of the
shared engine, and it is checked by validate_engine.py.

Single-symbol BTC backtest (the only symbol with real historical data in
this repo -- see fetch_data.py to get the others):
    2025:  79 trades, 43.0% win rate, +105.4%, 9.5% max drawdown
    2026:  30 trades, 40.0% win rate,  +66.3%, 4.8% max drawdown
    with 0.1% stop slippage + funding: +65.4% and +52.5%
ETH/SOL/BNB/XRP have NOT been backtested. Their inclusion here is
untested territory -- see the caveats at the bottom of this file.

Order lifecycle per symbol, per trade:
    setup arms  ->  LIMIT entry rests at the 50% OB midpoint
    filled      ->  STOP_MARKET and TAKE_PROFIT_MARKET placed, closePosition
    unfilled    ->  cancelled after 96 bars (24h)

Guards, shared across the whole portfolio (not per symbol):
    - a portfolio-wide correlation cap on concurrent open positions
      (default 2 of 5) -- these coins move together, so 5 independent
      1%-risk positions is not 5% risk, it is closer to one 5% crypto-beta
      bet the moment a market-wide move hits every stop at once
    - a 3% daily loss circuit breaker on total account balance
    - a 2.0 minimum reward:risk, checked per symbol at fill time

TESTNET ONLY by default. Read the caveats at the bottom of this file
before even thinking about TESTNET=false.
"""

import json
import os
import time
import traceback
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import pandas as pd
from dotenv import load_dotenv

from binance.client import Client

from smc_engine import SMCEngine, SMCParams, position_size

load_dotenv()

TESTNET = os.getenv("TESTNET", "true").lower() != "false"
API_KEY = os.getenv("BINANCE_TESTNET_API_KEY")
API_SECRET = os.getenv("BINANCE_TESTNET_SECRET_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SYMBOLS = [s.strip().upper() for s in
           os.getenv("SYMBOLS", "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT").split(",") if s.strip()]
MAX_CONCURRENT_POSITIONS = int(os.getenv("MAX_CONCURRENT_POSITIONS", "2"))

INTERVAL = Client.KLINE_INTERVAL_15MINUTE
POLL_SECONDS = 20
STATE_FILE = "state_v2.json"

# Sizing is env-configurable. Defaults are the survivable settings the
# research established (1% risk, 10x): higher risk raises return AND
# drawdown one-for-one, and 10x already covers every stop distance the
# strategy uses -- more leverage only deepens drawdown. See research/.
RISK_PER_TRADE_PCT = float(os.getenv("RISK_PER_TRADE_PCT", "0.01"))
LEVERAGE = int(os.getenv("LEVERAGE", "10"))
PARAMS = SMCParams(risk_per_trade_pct=RISK_PER_TRADE_PCT, leverage=LEVERAGE)

if not API_KEY or not API_SECRET:
    raise SystemExit("Missing BINANCE_TESTNET_API_KEY / BINANCE_TESTNET_SECRET_KEY in .env")

client = Client(API_KEY, API_SECRET, testnet=TESTNET, requests_params={"timeout": 20})

recent_logs = []


# ---------------------------------------------------------------- utilities
def log(msg: str, notify: bool = False):
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {msg}"
    print(line, flush=True)
    recent_logs.insert(0, line)
    del recent_logs[80:]
    if notify:
        send_telegram(msg)


def send_telegram(msg: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": TELEGRAM_CHAT_ID, "text": msg}).encode()
        urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=10)
    except Exception as exc:
        print(f"telegram failed: {exc}", flush=True)


class Filters:
    """Exchange precision rules -- orders are rejected without these."""

    def __init__(self, symbol: str):
        info = client.futures_exchange_info()
        spec = next(s for s in info["symbols"] if s["symbol"] == symbol)
        self.tick = float(next(f for f in spec["filters"]
                               if f["filterType"] == "PRICE_FILTER")["tickSize"])
        lot = next(f for f in spec["filters"]
                   if f["filterType"] in ("LOT_SIZE", "MARKET_LOT_SIZE"))
        self.step = float(lot["stepSize"])
        self.min_qty = float(lot["minQty"])
        self.qty_dp = spec["quantityPrecision"]
        self.price_dp = spec["pricePrecision"]

    def price(self, p: float) -> float:
        return round(round(p / self.tick) * self.tick, self.price_dp)

    def qty(self, q: float) -> float:
        return round(int(q / self.step) * self.step, self.qty_dp)


def fetch_klines(symbol: str, limit: int) -> pd.DataFrame:
    """Closed candles only -- the in-progress candle is dropped."""
    raw = client.futures_klines(symbol=symbol, interval=INTERVAL, limit=min(limit, 1500))
    df = pd.DataFrame(raw, columns=[
        "open_time", "open", "high", "low", "close", "volume", "close_time",
        "qav", "trades", "tbb", "tbq", "ignore"])
    df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms")
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)
    df = df.set_index("timestamp")[["open", "high", "low", "close", "volume"]]
    return df.iloc[:-1]


def usdt_balance() -> float:
    for b in client.futures_account_balance():
        if b["asset"] == "USDT":
            return float(b["balance"])
    return 0.0


def open_position(symbol: str):
    for p in client.futures_position_information(symbol=symbol):
        amt = float(p["positionAmt"])
        if amt != 0:
            return {"side": "LONG" if amt > 0 else "SHORT", "qty": abs(amt),
                    "entry": float(p["entryPrice"]),
                    "upnl": float(p.get("unRealizedProfit", 0.0))}
    return None


# ----------------------------------------------------------- per-symbol unit
class SymbolWorker:
    """Everything needed to run the sequence for ONE symbol.

    Holds no shared portfolio state (balance, circuit breaker, the
    concurrency cap) -- that lives in Portfolio, which is what makes the
    cap meaningful across symbols rather than accidental.
    """

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.filters = Filters(symbol)
        self.engine = SMCEngine(PARAMS)
        self.last_bar_time = None
        self.entry_order_id = None
        self.armed = None
        self.armed_at = None
        self.pending_target = None
        self.pending_rr = None
        self.current_position = None
        try:
            client.futures_change_leverage(symbol=symbol, leverage=PARAMS.leverage)
        except Exception as exc:
            log(f"[{symbol}] could not set leverage: {exc}")

    # -- engine -------------------------------------------------------------
    def refresh_engine(self, df: pd.DataFrame, blocked_now: bool):
        """Replay history through a fresh engine up to the latest closed bar.

        Cold-start caveat, stated plainly: history is replayed as if no
        position was ever held, because the bot cannot know what it was
        doing before it started. A long-running instance and a freshly
        restarted one can therefore disagree about which pools are still
        live. Restarts are cheap but not perfectly free.
        """
        self.engine = SMCEngine(PARAMS)
        self.engine.prepare(df)
        n = len(df)
        armed = None
        armed_idx = None
        for bar in range(self.engine.start_bar(), n):
            is_last = (bar == n - 1)
            blocked = (armed is not None) or (blocked_now and is_last)
            setup = self.engine.step(bar, blocked)
            if setup is not None:
                armed, armed_idx = setup, bar
            elif armed is not None and (bar - armed_idx) > PARAMS.retest_window_bars:
                armed, armed_idx = None, None
                self.engine.clear_armed()
        return armed, (df.index[armed_idx] if armed_idx is not None else None)

    # -- orders ---------------------------------------------------------
    def place_entry(self, setup, balance: float) -> bool:
        target, rr = self.engine.compute_target(setup)
        if target is None or rr is None or rr < PARAMS.min_rr:
            log(f"[{self.symbol}] setup rejected: R:R {rr if rr else 0:.2f} below {PARAMS.min_rr}")
            return False

        qty_raw, notional = position_size(balance, setup.limit_price, setup.stop_price, PARAMS)
        qty = self.filters.qty(qty_raw)
        if qty < self.filters.min_qty:
            log(f"[{self.symbol}] setup rejected: size {qty} below exchange minimum "
                f"{self.filters.min_qty}")
            return False

        side = "BUY" if setup.direction == "LONG" else "SELL"
        price = self.filters.price(setup.limit_price)
        try:
            order = client.futures_create_order(
                symbol=self.symbol, side=side, type="LIMIT", timeInForce="GTC",
                quantity=qty, price=price)
        except Exception as exc:
            log(f"[{self.symbol}] entry order rejected by exchange: {exc}", notify=True)
            return False

        self.entry_order_id = order["orderId"]
        self.armed = setup
        self.armed_at = datetime.now(timezone.utc)
        self.pending_target = target
        self.pending_rr = rr

        log(f"ARMED {setup.direction} {self.symbol}\n"
            f"  limit {price}  stop {self.filters.price(setup.stop_price)}  "
            f"target {self.filters.price(target)}\n"
            f"  R:R {rr:.2f}  qty {qty}  notional ${notional:,.0f}\n"
            f"  sweep {setup.sweep_time}  CHoCH {setup.choch_time}", notify=True)
        return True

    def place_exits(self, setup, target: float):
        opposite = "SELL" if setup.direction == "LONG" else "BUY"
        stop = self.filters.price(setup.stop_price)
        tp = self.filters.price(target)
        for kind, order_type, trigger in (("stop", "STOP_MARKET", stop),
                                          ("target", "TAKE_PROFIT_MARKET", tp)):
            try:
                client.futures_create_order(symbol=self.symbol, side=opposite,
                                            type=order_type, stopPrice=trigger,
                                            closePosition=True)
                log(f"  [{self.symbol}] {kind} order placed @ {trigger}")
            except Exception as exc:
                log(f"[{self.symbol}] FAILED to place {kind} order: {exc}", notify=True)

    def cancel_entry(self, reason: str):
        if self.entry_order_id is None:
            return
        try:
            client.futures_cancel_order(symbol=self.symbol, orderId=self.entry_order_id)
            log(f"[{self.symbol}] entry order cancelled -- {reason}")
        except Exception as exc:
            log(f"[{self.symbol}] cancel failed (likely already gone): {exc}")
        self.entry_order_id = None
        self.armed = None
        self.armed_at = None

    def cancel_all(self):
        try:
            client.futures_cancel_all_open_orders(symbol=self.symbol)
        except Exception as exc:
            log(f"[{self.symbol}] cancel-all failed: {exc}")

    def as_state(self):
        return {"armed": self.armed.as_dict() if self.armed else None,
                "entry_order_id": self.entry_order_id}


# ---------------------------------------------------------------- portfolio
class Portfolio:
    """Owns the shared guards: the circuit breaker and the concurrency cap.

    A symbol's own logic never decides whether it's ALLOWED to enter --
    that call is made here, exactly once per tick, using the state of the
    whole book. This mirrors run_portfolio() in backtest_portfolio.py,
    which is regression-tested against the single-symbol backtest.
    """

    def __init__(self, symbols):
        self.workers = {s: SymbolWorker(s) for s in symbols}
        self.day = None
        self.day_start_balance = None
        self.halted = False

    def check_circuit_breaker(self, balance: float):
        today = datetime.now(timezone.utc).date()
        if today != self.day:
            self.day = today
            self.day_start_balance = balance
            self.halted = False
            return
        if self.day_start_balance and not self.halted:
            if balance <= self.day_start_balance * (1 - PARAMS.daily_loss_limit_pct):
                self.halted = True
                log(f"CIRCUIT BREAKER: portfolio down "
                    f"{PARAMS.daily_loss_limit_pct*100:.0f}% today "
                    f"(${self.day_start_balance:,.2f} -> ${balance:,.2f}). "
                    f"No new entries on any symbol until tomorrow.", notify=True)

    def save_state(self, balance: float, positions: dict):
        state = {
            "updated": datetime.now(timezone.utc).isoformat(),
            "mode": "TESTNET" if TESTNET else "LIVE",
            "symbols": list(self.workers.keys()),
            "max_concurrent_positions": MAX_CONCURRENT_POSITIONS,
            "balance": balance,
            "halted_today": self.halted,
            "positions": positions,
            "workers": {s: w.as_state() for s, w in self.workers.items()},
            "logs": recent_logs[:50],
        }
        try:
            with open(STATE_FILE, "w") as fh:
                json.dump(state, fh, indent=2, default=str)
        except Exception as exc:
            print(f"state write failed: {exc}", flush=True)

    # -- pass 1: reconcile each symbol against the exchange, one tick -----
    def _reconcile(self, w: SymbolWorker, df: pd.DataFrame):
        """Detect fills, tidy up closed positions, expire stale resting
        orders. Never places a new order -- that's pass 2's job, once the
        true portfolio-wide committed count is known."""
        position = open_position(w.symbol)
        w.current_position = position

        if position is None and w.armed is not None and w.entry_order_id is None:
            w.cancel_all()
            w.armed = None

        if position is not None and w.entry_order_id is not None:
            log(f"FILLED {position['side']} {position['qty']} {w.symbol} "
                f"@ {position['entry']}", notify=True)
            w.place_exits(w.armed, w.pending_target)
            w.entry_order_id = None
            return

        if position is None and w.entry_order_id is not None:
            still_open = False
            try:
                o = client.futures_get_order(symbol=w.symbol, orderId=w.entry_order_id)
                still_open = o["status"] in ("NEW", "PARTIALLY_FILLED")
            except Exception as exc:
                log(f"[{w.symbol}] order status check failed: {exc}")
            if not still_open:
                w.entry_order_id = None
                w.armed = None
            elif w.armed_at:
                age_bars = (datetime.now(timezone.utc) - w.armed_at).total_seconds() / 900
                if age_bars > PARAMS.retest_window_bars:
                    w.cancel_entry("24h fill window expired")

    # -- pass 2: look for a new entry, gated by the shared cap ------------
    def _seek_entry(self, w: SymbolWorker, df: pd.DataFrame, balance: float,
                    committed: int) -> bool:
        """Returns True if a new order was placed (caller increments committed)."""
        if w.current_position is not None or w.entry_order_id is not None:
            return False  # already committed, nothing to seek

        new_bar = df.index[-1] != w.last_bar_time
        if not new_bar:
            return False
        w.last_bar_time = df.index[-1]

        at_cap = committed >= MAX_CONCURRENT_POSITIONS
        blocked = self.halted or at_cap
        setup, armed_time = w.refresh_engine(df, blocked)

        if setup is None or self.halted or at_cap:
            return False
        fresh = armed_time is not None and armed_time >= df.index[-1]
        if not fresh:
            return False
        return w.place_entry(setup, balance)

    def run(self):
        log(f"SMC V2 (Variant C) started [{'TESTNET' if TESTNET else 'LIVE'}] "
            f"on {', '.join(self.workers)}  "
            f"max concurrent {MAX_CONCURRENT_POSITIONS}/{len(self.workers)}  "
            f"balance ${usdt_balance():,.2f}", notify=True)
        while True:
            try:
                balance = usdt_balance()
                self.check_circuit_breaker(balance)

                dfs = {}
                for sym, w in self.workers.items():
                    df = fetch_klines(sym, PARAMS.required_bars + 50)
                    dfs[sym] = df
                    if len(df) < 200:
                        log(f"[{sym}] not enough history yet")
                        continue
                    self._reconcile(w, df)

                # true committed exposure, from exchange state, not deltas
                committed = sum(1 for w in self.workers.values()
                               if w.current_position is not None
                               or w.entry_order_id is not None)

                positions = {}
                for sym, w in self.workers.items():
                    df = dfs[sym]
                    if len(df) >= 200:
                        if self._seek_entry(w, df, balance, committed):
                            committed += 1
                    positions[sym] = w.as_state()

                self.save_state(balance, positions)
            except Exception:
                log(f"tick failed:\n{traceback.format_exc()}")
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    Portfolio(SYMBOLS).run()

# ---------------------------------------------------------------------------
# Before switching TESTNET=false, know what has NOT been established:
#
#   * Only BTCUSDT has been backtested. ETH/SOL/BNB/XRP run the identical
#     strategy code on this exchange, but the strategy has never been
#     validated against their price history. Use fetch_data.py and
#     backtest_portfolio.py before trusting them with anything.
#   * 109 BTC trades across two periods. A third of the profit sits in a
#     handful of trades.
#   * Three bugs surfaced while building this -- two look-ahead errors and
#     a date-parsing fault that scrambled 36% of rows -- plus two more in
#     the portfolio driver itself (a one-bar exit-timing divergence and an
#     ambiguous file resolver), both caught by validate_engine.py before
#     they reached this file. There may be another.
#   * The backtest assumes a resting limit fills whenever price touches its
#     level. Real queue position may not cooperate. This is the single
#     largest unmodelled risk and testnet is what measures it.
#   * Funding, real fill quality and exchange downtime are absent from the
#     backtest entirely.
#   * The MAX_CONCURRENT_POSITIONS cap limits how many symbols can be open
#     at once, but does NOT model correlation directly -- two "different"
#     positions can still be the same underlying bet if BTC and ETH are
#     both long at the same time. Watch this on testnet, don't assume it.
#
# Run on testnet for 30-40 trades per symbol, then compare actual fill rate
# and win rate against the backtested ~40%. If fills come in well below
# expectation, or the win rate sits under ~33%, the edge is not there.
# ---------------------------------------------------------------------------
