"""
SMC FVG + EMA 5/13/21 + RSI + Volume Confirmation Backtester
==============================================================
Strategy:
1. Detect Fair Value Gaps (FVGs) on the 1H timeframe.
2. Trend filter: EMA 5/13/21 stack alignment
   - LONG: EMA5 > EMA13 > EMA21 (bullish stack)
   - SHORT: EMA5 < EMA13 < EMA21 (bearish stack)
3. Momentum confirmation: RSI(14)
   - LONG: RSI > 50 (bullish momentum), RSI < 70 (not overbought)
   - SHORT: RSI < 50 (bearish momentum), RSI > 30 (not oversold)
4. Volume confirmation: the impulse candle that created the FVG must
   have volume above its rolling average (real participation, not a
   low-liquidity wick).
5. Wait for price to pull back and mitigate the FVG.
6. Stop Loss beyond the Order Block. Target at 1.5R.
"""

import pandas as pd
import numpy as np
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "DATA")
DATA_FILE = "BTCUSDT_1h_Jan_to_Jul2026.csv"

STARTING_CAPITAL = 200.0
LEVERAGE = 10
RISK_PER_TRADE_PCT = 0.05
COMMISSION_PCT = 0.0004

EMA_FAST = 5
EMA_MID = 13
EMA_SLOW = 21

RSI_PERIOD = 14
RSI_LONG_MIN = 50
RSI_LONG_MAX = 70
RSI_SHORT_MAX = 50
RSI_SHORT_MIN = 30

VOLUME_MA_PERIOD = 20
VOLUME_MULT = 1.0  # impulse candle volume must be >= VOLUME_MULT * rolling avg

FORWARD_BARS = 200
FVG_EXPIRY_BARS = 48


def compute_rsi(closes, period):
    delta = np.diff(closes, prepend=closes[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)

    avg_gain = np.zeros(len(closes))
    avg_loss = np.zeros(len(closes))

    avg_gain[period] = gain[1:period+1].mean()
    avg_loss[period] = loss[1:period+1].mean()

    for i in range(period + 1, len(closes)):
        avg_gain[i] = (avg_gain[i-1] * (period - 1) + gain[i]) / period
        avg_loss[i] = (avg_loss[i-1] * (period - 1) + loss[i]) / period

    rs = np.divide(avg_gain, avg_loss, out=np.full_like(avg_gain, np.inf), where=avg_loss != 0)
    rsi = 100 - (100 / (1 + rs))
    rsi[:period] = 50  # neutral until warmed up
    return rsi


def simulate_ema_rsi_vol():
    fpath = os.path.join(DATA_DIR, DATA_FILE)
    df = pd.read_csv(fpath)
    df['timestamp'] = pd.to_datetime(df['timestamp'], dayfirst=True, format='mixed')
    df.set_index('timestamp', inplace=True)
    df.sort_index(inplace=True)

    df['ema5'] = df['close'].ewm(span=EMA_FAST, adjust=False).mean()
    df['ema13'] = df['close'].ewm(span=EMA_MID, adjust=False).mean()
    df['ema21'] = df['close'].ewm(span=EMA_SLOW, adjust=False).mean()
    df['vol_ma'] = df['volume'].rolling(VOLUME_MA_PERIOD).mean()

    closes = df['close'].values
    df['rsi'] = compute_rsi(closes, RSI_PERIOD)

    lows = df['low'].values
    highs = df['high'].values
    opens = df['open'].values
    volumes = df['volume'].values
    vol_ma = df['vol_ma'].values
    times = df.index
    ema5 = df['ema5'].values
    ema13 = df['ema13'].values
    ema21 = df['ema21'].values
    rsi = df['rsi'].values

    capital = STARTING_CAPITAL
    peak = capital
    max_dd = 0
    trades = []

    active_fvgs = []
    last_trade_bar = 0

    warmup = max(EMA_SLOW, RSI_PERIOD, VOLUME_MA_PERIOD) + 2

    for bar in range(warmup, len(closes)):
        # 1. Detect New FVGs, gated by volume confirmation on the impulse candle (bar-1)
        impulse_vol_ok = (not np.isnan(vol_ma[bar-1])) and volumes[bar-1] >= vol_ma[bar-1] * VOLUME_MULT

        if lows[bar] > highs[bar-2] and closes[bar-1] > opens[bar-1] and impulse_vol_ok:
            gap_bottom = highs[bar-2]
            gap_top = lows[bar]
            ob_stop = min(lows[bar-2], lows[bar-1], lows[bar]) - 10
            target = highs[bar] + abs(highs[bar] - ob_stop) * 1.5

            active_fvgs.append({
                'dir': 'LONG', 'top': gap_top, 'bottom': gap_bottom,
                'ob_stop': ob_stop, 'target': target,
                'expiry': bar + FVG_EXPIRY_BARS, 'mitigated': False
            })

        elif highs[bar] < lows[bar-2] and closes[bar-1] < opens[bar-1] and impulse_vol_ok:
            gap_bottom = highs[bar]
            gap_top = lows[bar-2]
            ob_stop = max(highs[bar-2], highs[bar-1], highs[bar]) + 10
            target = lows[bar] - abs(ob_stop - lows[bar]) * 1.5

            active_fvgs.append({
                'dir': 'SHORT', 'top': gap_top, 'bottom': gap_bottom,
                'ob_stop': ob_stop, 'target': target,
                'expiry': bar + FVG_EXPIRY_BARS, 'mitigated': False
            })

        active_fvgs = [f for f in active_fvgs if bar <= f['expiry'] and not f['mitigated']]

        if bar - last_trade_bar < 6:
            continue

        # 2. EMA trend filter
        bullish_stack = ema5[bar] > ema13[bar] > ema21[bar]
        bearish_stack = ema5[bar] < ema13[bar] < ema21[bar]

        # 3. RSI momentum filter
        rsi_ok_long = RSI_LONG_MIN < rsi[bar] < RSI_LONG_MAX
        rsi_ok_short = RSI_SHORT_MIN < rsi[bar] < RSI_SHORT_MAX

        for fvg in active_fvgs:
            direction = None

            if fvg['dir'] == 'LONG' and bullish_stack and rsi_ok_long:
                if lows[bar] <= fvg['top'] and highs[bar] > fvg['top']:
                    direction = 'LONG'
                    entry_price = fvg['top']

            elif fvg['dir'] == 'SHORT' and bearish_stack and rsi_ok_short:
                if highs[bar] >= fvg['bottom'] and lows[bar] < fvg['bottom']:
                    direction = 'SHORT'
                    entry_price = fvg['bottom']

            if direction:
                fvg['mitigated'] = True
                stop_price = fvg['ob_stop']
                target_price = fvg['target']

                stop_dist = abs(entry_price - stop_price)
                if stop_dist == 0:
                    continue

                risk_amt = capital * RISK_PER_TRADE_PCT
                pos_usd = min((risk_amt / stop_dist) * entry_price, capital * LEVERAGE)
                qty = pos_usd / entry_price

                exit_p = exit_r = None
                end = min(bar + FORWARD_BARS, len(closes))

                for j in range(bar + 1, end):
                    if direction == "SHORT":
                        if highs[j] >= stop_price:
                            exit_p, exit_r = stop_price, "STOP"
                            break
                        if lows[j] <= target_price:
                            exit_p, exit_r = target_price, "TARGET"
                            break
                    else:
                        if lows[j] <= stop_price:
                            exit_p, exit_r = stop_price, "STOP"
                            break
                        if highs[j] >= target_price:
                            exit_p, exit_r = target_price, "TARGET"
                            break

                if exit_p is None:
                    exit_p, exit_r = closes[end-1], "TIME"

                if direction == "LONG":
                    pnl = qty * (exit_p - entry_price)
                else:
                    pnl = qty * (entry_price - exit_p)

                comm = qty * entry_price * COMMISSION_PCT + qty * exit_p * COMMISSION_PCT
                net = pnl - comm

                capital += net
                if capital <= 0:
                    capital = 0
                if capital > peak:
                    peak = capital
                dd = (peak - capital) / peak * 100 if peak > 0 else 0
                if dd > max_dd:
                    max_dd = dd

                trades.append({
                    'dir': direction,
                    'time': times[bar],
                    'entry': entry_price,
                    'stop': stop_price,
                    'target': target_price,
                    'rsi': rsi[bar],
                    'pnl': net,
                    'bal': capital,
                    'exit_r': exit_r
                })

                last_trade_bar = bar
                break

        if capital <= 0:
            break

    return trades, capital, max_dd


if __name__ == "__main__":
    print("Running SMC FVG + EMA 5/13/21 + RSI + Volume Confirmation Strategy...")
    print(f"Config: EMA {EMA_FAST}/{EMA_MID}/{EMA_SLOW} | RSI({RSI_PERIOD}) | Vol MA({VOLUME_MA_PERIOD}) "
          f"| Risk: {RISK_PER_TRADE_PCT*100}% | Leverage: {LEVERAGE}x")
    print(f"Data: {DATA_FILE}\n")

    trades, final, mdd = simulate_ema_rsi_vol()
    wins = len([t for t in trades if t['pnl'] > 0])

    print("TRADE LOG:")
    for i, t in enumerate(trades):
        m = "+" if t['pnl'] >= 0 else "-"
        print(f"#{i+1:<3} {t['dir']:<5} {str(t['time'])[:16]} Entry: ${t['entry']:.0f} Stop: ${t['stop']:.0f} "
              f"Target: ${t['target']:.0f} RSI: {t['rsi']:.0f} -> {t['exit_r']} {m}${abs(t['pnl']):.2f} (Bal: ${t['bal']:.2f})")

    print(f"\nTrades: {len(trades)} | Wins: {wins} | WinRate: {wins/len(trades)*100 if trades else 0:.1f}%")
    print(f"Final Capital: ${final:.2f} (from ${STARTING_CAPITAL:.2f}) | Max DD: {mdd:.1f}%")
