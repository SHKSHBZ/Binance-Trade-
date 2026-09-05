"""
Trade journal — a permanent, human-readable record of what the bot DECIDED
and why, written the moment it decides, so its decision-making can be
reviewed and tested later.

This is an audit log, not part of the trading logic. It never raises into
the bot: a journal failure must never stop a trade or a fill from being
handled, so every write is wrapped and swallowed.

One JSON object per line (JSONL), append-only. Events, in order of a
trade's life:

  PLANNED    the bot armed a setup: direction, the exact limit level it is
             waiting for price to tap, stop, target, reward:risk, size, and
             the reason (the sweep + CHoCH that produced it). Written BEFORE
             anything fills -- this is the bot's stated intention.
  FILLED     price tapped the level and the limit filled -> position open.
  CANCELLED  the plan expired unfilled (price never tapped the level in the
             24h window) -> the intention did not trigger.
  CLOSED     the position closed (stop or target) -> the outcome, with pnl
             if known.

Review it with:  python3 view_journal.py
"""

import json
import os
from datetime import datetime, timezone

JOURNAL_FILE = os.getenv("JOURNAL_FILE", "trade_journal.jsonl")


def _write(record: dict):
    try:
        record["ts"] = datetime.now(timezone.utc).isoformat()
        with open(JOURNAL_FILE, "a") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
    except Exception as exc:               # never let journaling break the bot
        print(f"[journal] write failed: {exc}", flush=True)


def planned(symbol, setup, target, rr, qty, notional, mode):
    """The bot's stated intention, written the moment it arms -- before fill."""
    _write({
        "event": "PLANNED",
        "mode": mode,                       # TESTNET / LIVE
        "symbol": symbol,
        "direction": setup.direction,       # LONG / SHORT
        "plan": (f"wait for price to tap {setup.limit_price:.2f}; a resting "
                 f"{'BUY' if setup.direction == 'LONG' else 'SELL'} limit "
                 f"then fills (no candle-colour trigger)"),
        "entry_level": round(float(setup.limit_price), 2),
        "stop": round(float(setup.stop_price), 2),
        "target": round(float(target), 2) if target is not None else None,
        "reward_risk": round(float(rr), 2) if rr is not None else None,
        "qty": qty,
        "notional": round(float(notional), 2),
        "reason": {
            "sweep_time": str(setup.sweep_time),
            "sweep_extreme": round(float(setup.sweep_extreme), 2),
            "choch_time": str(setup.choch_time),
            "order_block": [round(float(setup.ob_low), 2),
                            round(float(setup.ob_high), 2)],
        },
    })


def filled(symbol, side, qty, entry):
    _write({"event": "FILLED", "symbol": symbol, "side": side,
            "qty": qty, "fill_price": round(float(entry), 2),
            "note": "price tapped the level; the planned trade triggered"})


def cancelled(symbol, reason):
    _write({"event": "CANCELLED", "symbol": symbol, "reason": reason,
            "note": "plan expired -- price never tapped the level in the window"})


def closed(symbol, reason, pnl=None):
    _write({"event": "CLOSED", "symbol": symbol, "reason": reason,
            "pnl": round(float(pnl), 2) if pnl is not None else None})
