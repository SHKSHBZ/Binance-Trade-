//+------------------------------------------------------------------+
//|                                            PriorDayLevels.mq5     |
//|  Marks the previous day's key levels + alerts on a liquidity      |
//|  sweep. For MetaTrader 5 (Exness and any MT5 broker).             |
//|                                                                   |
//|  Draws, updated at each new day:                                  |
//|    - Previous day HIGH wick  and LOW wick                         |
//|    - Previous day BODY high  and BODY low (max/min of open,close) |
//|    - Previous day CLOSE                                            |
//|    - Current day OPEN                                              |
//|  Alerts when price SWEEPS the prior-day high or low (wicks beyond  |
//|  then the candle closes back inside) -- your liquidity-sweep cue.  |
//+------------------------------------------------------------------+
#property copyright   "built for a real-time trader"
#property version     "1.00"
#property indicator_chart_window
#property indicator_plots 0

//--- what to show
input bool   ShowWick      = true;              // show prior-day high/low wick
input bool   ShowBody      = true;              // show prior-day body high/low
input bool   ShowClose     = true;              // show prior-day close
input bool   ShowOpen      = true;              // show current-day open
input bool   AlertOnSweep  = true;              // alert on a high/low sweep
input bool   PushAlerts    = false;             // also send push to phone
//--- colours
input color  WickColor     = clrTomato;         // high/low wick lines
input color  BodyColor     = clrOrange;         // body high/low lines
input color  CloseColor    = clrDodgerBlue;     // prior close line
input color  OpenColor     = clrSilver;         // current open line
input int    LineWidth     = 1;

string PFX = "PDL_";           // object-name prefix

//+------------------------------------------------------------------+
int OnInit()
  {
   return(INIT_SUCCEEDED);
  }
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   ObjectsDeleteAll(0, PFX);
   ChartRedraw();
  }
//+------------------------------------------------------------------+
//| draw or move one horizontal ray for "today"                      |
//+------------------------------------------------------------------+
void DrawLevel(string tag, double price, color col, string text, bool show)
  {
   string name = PFX + tag;
   if(!show || price <= 0.0)
     { ObjectDelete(0, name); ObjectDelete(0, name+"_t"); return; }

   datetime dayStart = iTime(_Symbol, PERIOD_D1, 0);   // start of today
   datetime dayEnd   = dayStart + PeriodSeconds(PERIOD_D1);

   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, OBJ_TREND, 0, dayStart, price, dayEnd, price);
   ObjectSetInteger(0, name, OBJPROP_TIME, 0, dayStart);
   ObjectSetDouble (0, name, OBJPROP_PRICE, 0, price);
   ObjectSetInteger(0, name, OBJPROP_TIME, 1, dayEnd);
   ObjectSetDouble (0, name, OBJPROP_PRICE, 1, price);
   ObjectSetInteger(0, name, OBJPROP_COLOR, col);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, LineWidth);
   ObjectSetInteger(0, name, OBJPROP_RAY_RIGHT, true);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_BACK, true);

   // price label at the right edge
   string tn = name + "_t";
   if(ObjectFind(0, tn) < 0)
      ObjectCreate(0, tn, OBJ_TEXT, 0, dayEnd, price);
   ObjectSetInteger(0, tn, OBJPROP_TIME, 0, dayEnd);
   ObjectSetDouble (0, tn, OBJPROP_PRICE, 0, price);
   ObjectSetString (0, tn, OBJPROP_TEXT, "  "+text+" "+DoubleToString(price, _Digits));
   ObjectSetInteger(0, tn, OBJPROP_COLOR, col);
   ObjectSetInteger(0, tn, OBJPROP_ANCHOR, ANCHOR_LEFT);
   ObjectSetInteger(0, tn, OBJPROP_SELECTABLE, false);
  }
//+------------------------------------------------------------------+
void FireAlert(string msg)
  {
   Alert(_Symbol+" "+msg);
   if(PushAlerts) SendNotification(_Symbol+" "+msg);
  }
//+------------------------------------------------------------------+
int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double &open[],
                const double &high[],
                const double &low[],
                const double &close[],
                const long &tick_volume[],
                const long &volume[],
                const int &spread[])
  {
   //--- prior-day (D1 shift 1) values
   double pdh = iHigh (_Symbol, PERIOD_D1, 1);
   double pdl = iLow  (_Symbol, PERIOD_D1, 1);
   double pdo = iOpen (_Symbol, PERIOD_D1, 1);
   double pdc = iClose(_Symbol, PERIOD_D1, 1);
   double tdo = iOpen (_Symbol, PERIOD_D1, 0);      // today's open
   if(pdh <= 0.0) return(rates_total);
   double bodyHi = MathMax(pdo, pdc);
   double bodyLo = MathMin(pdo, pdc);

   DrawLevel("HWick", pdh,    WickColor,  "PD High wick", ShowWick);
   DrawLevel("LWick", pdl,    WickColor,  "PD Low wick",  ShowWick);
   DrawLevel("HBody", bodyHi, BodyColor,  "PD Body high", ShowBody);
   DrawLevel("LBody", bodyLo, BodyColor,  "PD Body low",  ShowBody);
   DrawLevel("Close", pdc,    CloseColor, "PD Close",     ShowClose);
   DrawLevel("Open",  tdo,    OpenColor,  "Day Open",     ShowOpen);
   ChartRedraw();

   //--- sweep alert: run once per just-CLOSED bar on the working timeframe
   if(AlertOnSweep && rates_total > 2)
     {
      static datetime lastBar = 0;
      datetime curBar = time[rates_total-1];
      if(curBar != lastBar)
        {
         lastBar = curBar;
         int k = rates_total - 2;               // the bar that just closed
         // sweep of prior-day HIGH: wick above, close back below -> short cue
         if(high[k] > pdh && close[k] < pdh)
            FireAlert("SWEPT prior-day HIGH "+DoubleToString(pdh,_Digits)+
                      " and closed back inside (short cue)");
         // sweep of prior-day LOW: wick below, close back above -> long cue
         if(low[k] < pdl && close[k] > pdl)
            FireAlert("SWEPT prior-day LOW "+DoubleToString(pdl,_Digits)+
                      " and closed back inside (long cue)");
        }
     }
   return(rates_total);
  }
//+------------------------------------------------------------------+
