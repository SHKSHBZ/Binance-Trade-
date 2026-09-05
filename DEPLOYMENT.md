# Deploying the bot to your server (testnet)

The bot must run on a machine that can reach Binance and stay online. This
walks through a clean testnet deployment on a Linux server.

## 1. Prerequisites

- Python 3.10+
- A Binance **Futures testnet** account and API key/secret:
  https://testnet.binancefuture.com → API Key. (Free, fake money.)
- The server's clock in sync (`sudo timedatectl set-ntp true`) — Binance
  rejects requests whose timestamp drifts.

## 2. Get the code and install

```bash
git clone https://github.com/SHKSHBZ/Binance-Trade-.git
cd Binance-Trade-
git checkout claude/create-repo-branch-kww7ib
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## 3. Configure

```bash
cp .env.example .env
nano .env        # paste your TESTNET key + secret; leave TESTNET=true
```

Start with **`SYMBOLS=BTCUSDT`** only — it is the sole backtested symbol.
Sizing defaults to 1% risk / 10x (the survivable settings). 2% is the
aggressive-but-sane ceiling; do not go higher on a real account later.

## 4. Smoke test (one manual run)

```bash
source .venv/bin/activate
python3 binance_live_bot_v2.py
```

You should see a startup line: `SMC V2 (Variant C) started [TESTNET] on
BTCUSDT ... balance $...`. If you see a keys error, `.env` isn't loaded.
If you see a proxy/timeout error, the server can't reach Binance. Let it
run a few minutes, confirm it polls without tracebacks, then Ctrl-C.

## 5. Run it persistently (systemd)

Create `/etc/systemd/system/smcbot.service` (adjust the paths and `User`):

```ini
[Unit]
Description=SMC V2 testnet bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=YOUR_USER
WorkingDirectory=/home/YOUR_USER/Binance-Trade-
ExecStart=/home/YOUR_USER/Binance-Trade-/.venv/bin/python3 binance_live_bot_v2.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now smcbot
sudo systemctl status smcbot          # is it running?
journalctl -u smcbot -f               # live logs
```

`Restart=always` brings it back after a crash or reboot. On restart the
engine replays history cold (it can't know a position it held before
start) — restarts are cheap but not perfectly free; avoid restarting while
a position is open if you can.

## 6. What to watch

- `state_v2.json` in the working dir — a live snapshot (balance, armed
  setups, positions, recent logs). `cat state_v2.json | python3 -m json.tool`.
- Optional Telegram alerts: set `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`
  in `.env` to get pinged on ARMED / FILLED / circuit-breaker events.

## 7. The point of the testnet run

Collect **30–40 trades on BTCUSDT**, then compare against the backtest:

- **Fill rate** — do the resting limit orders actually fill? This is the
  single biggest thing the backtest assumes and cannot prove.
- **Win rate** — should land near the backtested ~40%. Below ~33% (breakeven
  at 2:1), the edge isn't there in live conditions.

Only after testnet confirms both should real money (`TESTNET=false`, real
keys) even be a conversation — and read the caveats at the bottom of
`binance_live_bot_v2.py` first.

## Safety rails already in the bot

- Testnet by default; refuses to start without keys.
- 3% daily-loss circuit breaker (halts new entries for the day).
- Max 2 concurrent positions (correlation cap).
- 2:1 minimum reward:risk, checked at fill.
- Exchange-side stop and take-profit on every fill (survives a bot crash).
- Trades only closed candles (no look-ahead).
