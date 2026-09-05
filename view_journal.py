"""
Read the bot's trade journal as plain English.

    python3 view_journal.py                 # default trade_journal.jsonl
    python3 view_journal.py path/to/file
"""
import json
import sys
from collections import defaultdict

path = sys.argv[1] if len(sys.argv) > 1 else "trade_journal.jsonl"

try:
    lines = [json.loads(x) for x in open(path) if x.strip()]
except FileNotFoundError:
    print(f"no journal yet at {path} — the bot writes it once it plans a trade.")
    sys.exit(0)

counts = defaultdict(int)
for e in lines:
    counts[e.get("event", "?")] += 1

print(f"Trade journal: {path}   ({len(lines)} events)")
print(f"  planned {counts['PLANNED']}   filled {counts['FILLED']}   "
      f"cancelled {counts['CANCELLED']}   closed {counts['CLOSED']}")
if counts["PLANNED"]:
    print(f"  fill rate: {counts['FILLED']}/{counts['PLANNED']} plans triggered "
          f"({100*counts['FILLED']/counts['PLANNED']:.0f}%)")
print("-" * 72)

for e in lines:
    ts = e.get("ts", "")[:19].replace("T", " ")
    ev = e.get("event")
    sym = e.get("symbol", "")
    if ev == "PLANNED":
        r = e["reason"]
        print(f"[{ts}] PLAN  {e['direction']} {sym}")
        print(f"          {e['plan']}")
        print(f"          stop {e['stop']}  target {e['target']}  R:R {e['reward_risk']}"
              f"  qty {e['qty']}  (${e['notional']:,.0f})")
        print(f"          why: sweep @ {r['sweep_time'][:16]} ({r['sweep_extreme']}), "
              f"CHoCH @ {r['choch_time'][:16]}, OB {r['order_block']}")
    elif ev == "FILLED":
        print(f"[{ts}] FILL  {e['side']} {sym} {e['qty']} @ {e['fill_price']}  "
              f"-- {e.get('note','')}")
    elif ev == "CANCELLED":
        print(f"[{ts}] VOID  {sym} -- {e.get('reason','')}")
    elif ev == "CLOSED":
        pnl = e.get("pnl")
        print(f"[{ts}] CLOSE {sym} {e.get('reason','')}"
              + (f"  pnl {pnl:+.2f}" if pnl is not None else ""))
