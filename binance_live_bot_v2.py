"""
SMC V2 live bot (Variant C) -- Binance USD-M Futures TESTNET.

Runs the exact strategy validated in backtest_engine.py by driving the
same smc_engine.SMCEngine. If this bot does something, the backtest does
it too -- that equivalence is the whole point of the shared engine, and
it is checked by validate_engine.py.

    2025:  79 trades, 43.0% win rate, +105.4%, 9.5% max drawdown
    2026:  30 trades, 40.0% win rate,  +66.3%, 4.8% max drawdown
    with 0.1% stop slippage + funding: +65.4% and +52.5%

Order lifecycle per trade:
    setup arms  ->  LIMIT entry rests at the 50% OB midpoint
    filled      ->  STOP_MARKET and TAKE_PROFIT_MARKET placed, closePosition
    unfilled    ->  cancelled after 96 bars (24h)

Guards: one position at a time, 3% daily loss circuit breaker, and a
minimum 2.0 reward:risk checked at fill time.

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

SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
INTERVAL = Client.KLINE_INTERVAL_15MINUTE
POLL_SECONDS = 20
STATE_FILE = "state_v2.json"

PARAMS = SMCParams()

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
    del recent_logs[60:]
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


def fetch_klines(limit: int) -> pd.DataFrame:
    """Closed candles only -- the in-progress candle is dropped."""
    raw = client.futures_klines(symbol=SYMBOL, interval=INTERVAL, limit=min(limit, 1500))
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


def open_position():
    for p in client.futures_position_information(symbol=SYMBOL):
        amt = float(p["positionAmt"])
        if amt != 0:
            return {"side": "LONG" if amt > 0 else "SHORT", "qty": abs(amt),
                    "entry": float(p["entryPrice"]),
                    "upnl": float(p.get("unRealizedProfit", 0.0))}
    return None


# ------------------------------------------------------------------ the bot
class Bot:
    def __init__(self):
        self.filters = Filters(SYMBOL)
        self.engine = SMCEngine(PARAMS)
        self.last_bar_time = None
        self.entry_order_id = None
        self.armed = None
        self.armed_at = None
        self.day = None
        self.day_start_balance = None
        self.halted = False
        try:
            client.futures_change_leverage(symbol=SYMBOL, leverage=PARAMS.leverage)
        except Exception as exc:
            log(f"could not set leverage: {exc}")

    # -- engine -----------------------------------------------------------
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

    # -- orders -----------------------------------------------------------
    def place_entry(self, setup, balance: float):
        target, rr = self.engine.compute_target(setup)
        if target is None or rr is None or rr < PARAMS.min_rr:
            log(f"setup rejected: R:R {rr if rr else 0:.2f} below {PARAMS.min_rr}")
            return False

        qty_raw, notional = position_size(balance, setup.limit_price, setup.stop_price, PARAMS)
        qty = self.filters.qty(qty_raw)
        if qty < self.filters.min_qty:
            log(f"setup rejected: size {qty} below exchange minimum {self.filters.min_qty}")
            return False

        side = "BUY" if setup.direction == "LONG" else "SELL"
        price = self.filters.price(setup.limit_price)
        try:
            order = client.futures_create_order(
                symbol=SYMBOL, side=side, type="LIMIT", timeInForce="GTC",
                quantity=qty, price=price)
        except Exception as exc:
            log(f"entry order rejected by exchange: {exc}", notify=True)
            return False

        self.entry_order_id = order["orderId"]
        self.armed = setup
        self.armed_at = datetime.now(timezone.utc)
        self.pending_target = target
        self.pending_rr = rr
        self.pending_qty = qty

        log(f"ARMED {setup.direction} {SYMBOL}\n"
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
                client.futures_create_order(symbol=SYMBOL, side=opposite,
                                            type=order_type, stopPrice=trigger,
                                            closePosition=True)
                log(f"  {kind} order placed @ {trigger}")
            except Exception as exc:
                log(f"FAILED to place {kind} order: {exc}", notify=True)

    def cancel_entry(self, reason: str):
        if self.entry_order_id is None:
            return
        try:
            client.futures_cancel_order(symbol=SYMBOL, orderId=self.entry_order_id)
            log(f"entry order cancelled -- {reason}")
        except Exception as exc:
            log(f"cancel failed (likely already gone): {exc}")
        self.entry_order_id = None
        self.armed = None
        self.armed_at = None

    def cancel_all(self):
        try:
            client.futures_cancel_all_open_orders(symbol=SYMBOL)
        except Exception as exc:
            log(f"cancel-all failed: {exc}")

    # -- guards -----------------------------------------------------------
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
                log(f"CIRCUIT BREAKER: down {PARAMS.daily_loss_limit_pct*100:.0f}% today "
                    f"(${self.day_start_balance:,.2f} -> ${balance:,.2f}). "
                    f"No new entries until tomorrow.", notify=True)

    # -- state ------------------------------------------------------------
    def save_state(self, balance, position, df):
        state = {
            "updated": datetime.now(timezone.utc).isoformat(),
            "mode": "TESTNET" if TESTNET else "LIVE",
            "symbol": SYMBOL,
            "balance": balance,
            "halted_today": self.halted,
            "last_closed_bar": str(df.index[-1]) if len(df) else None,
            "position": position,
            "armed": self.armed.as_dict() if self.armed else None,
            "entry_order_id": self.entry_order_id,
            "logs": recent_logs[:40],
        }
        try:
            with open(STATE_FILE, "w") as fh:
                json.dump(state, fh, indent=2, default=str)
        except Exception as exc:
            print(f"state write failed: {exc}", flush=True)

    # -- main loop --------------------------------------------------------
    def tick(self):
        df = fetch_klines(PARAMS.required_bars + 50)
        if len(df) < 200:
            log("not enough history yet")
            return

        balance = usdt_balance()
        position = open_position()
        self.check_circuit_breaker(balance)

        latest = df.index[-1]
        new_bar = latest != self.last_bar_time

        # position closed while we weren't looking -> tidy up resting orders
        if position is None and self.armed is not None and self.entry_order_id is None:
            self.cancel_all()
            self.armed = None

        if position is not None:
            if self.entry_order_id is not None:
                # the limit filled: attach exchange-side stop and target
                log(f"FILLED {position['side']} {position['qty']} @ {position['entry']}",
                    notify=True)
                self.place_exits(self.armed, self.pending_target)
                self.entry_order_id = None
            if new_bar:
                self.last_bar_time = latest
                self.save_state(balance, position, df)
            return

        # entry order still resting -- expire it if the window has passed
        if self.entry_order_id is not None:
            still_open = False
            try:
                o = client.futures_get_order(symbol=SYMBOL, orderId=self.entry_order_id)
                still_open = o["status"] in ("NEW", "PARTIALLY_FILLED")
            except Exception as exc:
                log(f"order status check failed: {exc}")
            if not still_open:
                self.entry_order_id = None
                self.armed = None
            elif self.armed_at:
                age_bars = (datetime.now(timezone.utc) - self.armed_at).total_seconds() / 900
                if age_bars > PARAMS.retest_window_bars:
                    self.cancel_entry("24h fill window expired")

        if not new_bar:
            return
        self.last_bar_time = latest

        blocked = (self.entry_order_id is not None) or self.halted
        setup, armed_time = self.refresh_engine(df, blocked)

        if setup is not None and self.entry_order_id is None and not self.halted:
            fresh = armed_time is not None and armed_time >= df.index[-1]
            if fresh:
                self.place_entry(setup, balance)

        self.save_state(balance, position, df)

    def run(self):
        log(f"SMC V2 (Variant C) started on {SYMBOL} "
            f"[{'TESTNET' if TESTNET else 'LIVE'}] balance ${usdt_balance():,.2f}",
            notify=True)
        while True:
            try:
                self.tick()
            except Exception:
                log(f"tick failed:\n{traceback.format_exc()}")
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    Bot().run()

# ---------------------------------------------------------------------------
# Before switching TESTNET=false, know what has NOT been established:
#
#   * 109 trades across two periods on one symbol. A third of the profit
#     sits in a handful of trades.
#   * Three bugs surfaced while building this -- two look-ahead errors and a
#     date-parsing fault that scrambled 36% of rows. Each made results look
#     better than reality until caught. There may be a fourth.
#   * The backtest assumes a resting limit fills whenever price touches its
#     level. Real queue position may not cooperate. This is the single
#     largest unmodelled risk and testnet is what measures it.
#   * Funding, real fill quality and exchange downtime are absent from the
#     backtest entirely.
#
# Run on testnet for 30-40 trades, then compare actual fill rate and win rate
# against 40%. If fills come in well below expectation, or the win rate sits
# under ~33%, the edge is not there.
# ---------------------------------------------------------------------------
