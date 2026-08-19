//+------------------------------------------------------------------+
//|                                       EMA20_FVG_Sniper_EA.mq5   |
//|  Port of binance_live_bot.py (EMA20 + FVG Sniper) to MQL5       |
//|                                                                  |
//|  WARNING: every backtest of this exact strategy (BTCUSDT, 1H,   |
//|  real historical data) has come out negative or flat across     |
//|  every period tested: -60.6% (2023-2025), -8.7% (2025), -5.0%   |
//|  (Jan-Jul 2026). GOLD and ETH have never been tested with this  |
//|  logic at all. Run on a DEMO account only. Do not treat this as |
//|  a proven profitable system.                                    |
//|                                                                  |
//|  Usage: attach this SAME EA separately to a BTCUSD chart, a     |
//|  XAUUSD (Gold) chart, and an ETHUSD chart -- one instance per   |
//|  chart, each trading only the symbol it's attached to. Confirm  |
//|  the exact symbol name your Exness account uses (it may have a  |
//|  suffix like BTCUSDm, XAUUSDm, ETHUSDm) via Market Watch before |
//|  attaching.                                                      |
//+------------------------------------------------------------------+
#property copyright "Backtest-derived, unverified profitable"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>
CTrade trade;

//--- Inputs (mirrors binance_live_bot.py exactly)
input ENUM_TIMEFRAMES TF               = PERIOD_H1;   // Timeframe (matches 1H in the Python bot)
input int             EMA_Period       = 20;           // Trend filter EMA period
input double          RiskPercent      = 1.5;          // % of balance risked per trade (matches RISK_PER_TRADE_PCT)
input double          MaxLeverage      = 10.0;         // Leverage cap (matches LEVERAGE)
input double          MarginSafetyCap  = 0.80;         // Matches the Python "Strict 80% Margin Safety Cap"
input int             FVGExpiryHours   = 48;           // FVG discarded if not mitigated within this many hours
input ulong           MagicNumber      = 20260812;     // Unique ID so this EA only manages its own trades
input double          SL_Buffer_Pct    = 0.001;        // 0.1% buffer past the wick, matches the Python bot

//--- Internal state
int emaHandle;
datetime lastBarTime = 0;

struct FVGZone
{
   bool     active;
   bool     isLong;
   double   top;
   double   bottom;
   double   obStop;
   double   target;
   datetime formedTime;
};
FVGZone fvgList[];

//+------------------------------------------------------------------+
int OnInit()
{
   emaHandle = iMA(_Symbol, TF, EMA_Period, 0, MODE_EMA, PRICE_CLOSE);
   if(emaHandle == INVALID_HANDLE)
   {
      Print("Failed to create EMA handle for ", _Symbol);
      return INIT_FAILED;
   }
   trade.SetExpertMagicNumber(MagicNumber);
   ArrayResize(fvgList, 0);
   Print("EMA20+FVG Sniper EA initialized on ", _Symbol, " (", EnumToString(TF), ")");
   Print("WARNING: this strategy has not tested profitable in any backtest run against real data.");
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   IndicatorRelease(emaHandle);
}

//+------------------------------------------------------------------+
void OnTick()
{
   datetime currentBarTime = iTime(_Symbol, TF, 0);
   if(currentBarTime == lastBarTime)
      return; // only evaluate once per new closed bar, matching the Python bot's per-scan logic
   lastBarTime = currentBarTime;

   ProcessStrategy();
   CompactFVGList();
}

//+------------------------------------------------------------------+
//| Core strategy logic -- mirrors scan_for_trades() in the Python  |
//| bot as closely as MQL5 allows.                                   |
//+------------------------------------------------------------------+
void ProcessStrategy()
{
   double high[], low[], open[], close[];
   datetime barTime[];
   ArraySetAsSeries(high, true);
   ArraySetAsSeries(low, true);
   ArraySetAsSeries(open, true);
   ArraySetAsSeries(close, true);
   ArraySetAsSeries(barTime, true);

   int need = 10;
   if(CopyHigh(_Symbol, TF, 0, need, high) < need) return;
   if(CopyLow(_Symbol, TF, 0, need, low) < need) return;
   if(CopyOpen(_Symbol, TF, 0, need, open) < need) return;
   if(CopyClose(_Symbol, TF, 0, need, close) < need) return;
   if(CopyTime(_Symbol, TF, 0, need, barTime) < need) return;

   double emaBuf[];
   ArraySetAsSeries(emaBuf, true);
   if(CopyBuffer(emaHandle, 0, 0, 5, emaBuf) < 5) return;

   // Index 1 = last fully closed bar (index 0 is the still-forming current bar).
   // 3-candle FVG pattern uses indices [3]=oldest, [2]=middle, [1]=newest closed,
   // matching bar-2/bar-1/bar in the Python bot's array convention.

   // Bullish FVG
   if(low[1] > high[3] && close[2] > open[2])
   {
      double gapBottom = high[3];
      double gapTop    = low[1];
      double obStop    = MathMin(low[3], MathMin(low[2], low[1])) - (close[1] * SL_Buffer_Pct);
      double target     = gapTop + MathAbs(gapTop - obStop) * 1.5;
      AddFVG(true, gapTop, gapBottom, obStop, target, barTime[1]);
   }
   // Bearish FVG
   else if(high[1] < low[3] && close[2] < open[2])
   {
      double gapBottom = high[1];
      double gapTop    = low[3];
      double obStop    = MathMax(high[3], MathMax(high[2], high[1])) + (close[1] * SL_Buffer_Pct);
      double target     = gapBottom - MathAbs(obStop - gapBottom) * 1.5;
      AddFVG(false, gapTop, gapBottom, obStop, target, barTime[1]);
   }

   ExpireOldFVGs(barTime[1]);

   // Sniper Limit: skip entries while a position is already open on this symbol/magic
   if(HasOpenPosition())
      return;

   double currentPrice = close[1];
   double ema = emaBuf[1];
   bool trendLong = currentPrice > ema;

   for(int i = ArraySize(fvgList) - 1; i >= 0; i--)
   {
      if(!fvgList[i].active) continue;

      bool touchedLong  = fvgList[i].isLong  && low[1]  <= fvgList[i].top;
      bool touchedShort = !fvgList[i].isLong && high[1] >= fvgList[i].bottom;
      if(!touchedLong && !touchedShort) continue;

      fvgList[i].active = false; // mitigated -- consumed either way

      if(fvgList[i].isLong && trendLong && currentPrice >= fvgList[i].obStop)
      {
         ExecuteTrade(true, currentPrice, fvgList[i].obStop, fvgList[i].target);
         return;
      }
      else if(!fvgList[i].isLong && !trendLong && currentPrice <= fvgList[i].obStop)
      {
         ExecuteTrade(false, currentPrice, fvgList[i].obStop, fvgList[i].target);
         return;
      }
   }
}

//+------------------------------------------------------------------+
void AddFVG(bool isLong, double top, double bottom, double obStop, double target, datetime formedTime)
{
   // Skip duplicates of an already-tracked zone at the same level/direction
   for(int i = 0; i < ArraySize(fvgList); i++)
   {
      if(fvgList[i].active && fvgList[i].isLong == isLong && MathAbs(fvgList[i].top - top) < _Point)
         return;
   }
   int n = ArraySize(fvgList);
   ArrayResize(fvgList, n + 1);
   fvgList[n].active     = true;
   fvgList[n].isLong     = isLong;
   fvgList[n].top        = top;
   fvgList[n].bottom     = bottom;
   fvgList[n].obStop     = obStop;
   fvgList[n].target     = target;
   fvgList[n].formedTime = formedTime;
}

//+------------------------------------------------------------------+
void ExpireOldFVGs(datetime currentTime)
{
   for(int i = 0; i < ArraySize(fvgList); i++)
   {
      if(!fvgList[i].active) continue;
      double hoursElapsed = (double)(currentTime - fvgList[i].formedTime) / 3600.0;
      if(hoursElapsed >= FVGExpiryHours)
         fvgList[i].active = false;
   }
}

//+------------------------------------------------------------------+
//| Periodically drop dead entries so the array doesn't grow forever |
//+------------------------------------------------------------------+
void CompactFVGList()
{
   if(ArraySize(fvgList) < 50) return;

   FVGZone kept[];
   int k = 0;
   for(int i = 0; i < ArraySize(fvgList); i++)
   {
      if(fvgList[i].active)
      {
         ArrayResize(kept, k + 1);
         kept[k] = fvgList[i];
         k++;
      }
   }
   ArrayFree(fvgList);
   ArrayResize(fvgList, k);
   for(int i = 0; i < k; i++)
      fvgList[i] = kept[i];
}

//+------------------------------------------------------------------+
bool HasOpenPosition()
{
   for(int i = 0; i < PositionsTotal(); i++)
   {
      ulong ticket = PositionGetTicket(i);
      if(PositionSelectByTicket(ticket))
      {
         if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
            PositionGetInteger(POSITION_MAGIC) == (long)MagicNumber)
            return true;
      }
   }
   return false;
}

//+------------------------------------------------------------------+
//| Risk-based position sizing: risk RiskPercent% of balance, capped |
//| by MaxLeverage * MarginSafetyCap notional -- matches the Python  |
//| bot's pos_usd = min((risk_amt/stop_dist)*entry, balance*lev*cap) |
//+------------------------------------------------------------------+
double CalculateLotSize(double entryPrice, double stopPrice)
{
   double stopDistance = MathAbs(entryPrice - stopPrice);
   if(stopDistance <= 0) return 0;

   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double riskAmount = balance * (RiskPercent / 100.0);

   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tickValue <= 0 || tickSize <= 0) return 0;

   double lossPerLot = (stopDistance / tickSize) * tickValue;
   if(lossPerLot <= 0) return 0;

   double riskBasedLots = riskAmount / lossPerLot;

   double contractSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   double maxNotional = balance * MaxLeverage * MarginSafetyCap;
   double maxLotsByNotional = (contractSize > 0 && entryPrice > 0)
                               ? maxNotional / (entryPrice * contractSize)
                               : riskBasedLots;

   double lots = MathMin(riskBasedLots, maxLotsByNotional);

   double minLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double stepLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(stepLot <= 0) stepLot = minLot > 0 ? minLot : 0.01;

   lots = MathFloor(lots / stepLot) * stepLot;
   lots = MathMax(minLot, MathMin(maxLot, lots));

   return lots;
}

//+------------------------------------------------------------------+
void ExecuteTrade(bool isLong, double entryPrice, double stopPrice, double targetPrice)
{
   double lots = CalculateLotSize(entryPrice, stopPrice);
   if(lots <= 0)
   {
      Print("Lot size calculated as 0 -- skipping trade on ", _Symbol);
      return;
   }

   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   double sl = NormalizeDouble(stopPrice, digits);
   double tp = NormalizeDouble(targetPrice, digits);

   bool result;
   if(isLong)
      result = trade.Buy(lots, _Symbol, ask, sl, tp, "EMA20+FVG Sniper");
   else
      result = trade.Sell(lots, _Symbol, bid, sl, tp, "EMA20+FVG Sniper");

   if(!result)
      Print("Order failed on ", _Symbol, ": ", trade.ResultRetcodeDescription());
   else
      Print(isLong ? "LONG" : "SHORT", " ", _Symbol, " lots=", lots, " SL=", sl, " TP=", tp);
}
//+------------------------------------------------------------------+
