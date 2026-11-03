//+------------------------------------------------------------------+
//| USDJPY_Speed_Denial_Break.mq4                                   |
//| Rolling-60m speed bias + countertrend-denial rebreak             |
//| FxCompany                                                        |
//+------------------------------------------------------------------+
#property copyright "FxCompany"
#property version   "1.04"
#property strict
#property indicator_chart_window
#property indicator_buffers 6

//--- Pattern settings (same initial values as the validated analysis)
extern int    InpLookbackBars       = 30;    // Prior high/low lookback (M1 bars)
extern double InpMinBreakPips       = 0.5;   // Minimum break beyond prior extreme
extern double InpMinRejectionPips   = 5.0;   // Minimum rejection wick
extern int    InpExpiryMinutes      = 60;    // Rebreak waiting time
extern int    InpCooldownMinutes    = 15;    // Same-side signal cooldown

//--- Speed bias settings
extern int    InpMinSpeedBars       = 45;    // Minimum completed M1 bars in rolling 60m
extern bool   InpRequireSpeedMatch  = true;  // Only strong arrow when speed agrees

//--- Display and alerts
extern int    InpMaxBarsToScan      = 5000;
extern double InpArrowOffsetPips    = 2.0;
extern bool   InpShowBlockedSignals = true;
extern bool   InpEnablePopupAlert   = true;
extern bool   InpEnableSoundAlert   = true;
extern string InpAlertSound         = "alert.wav";
extern bool   InpShowPanel          = true;

//--- Colors
extern color  InpLongColor          = C'0,255,190';
extern color  InpShortColor         = C'255,70,100';
extern color  InpRejectionColor     = C'255,185,45';
extern color  InpBlockedColor       = C'125,140,160';
extern color  InpPanelBackground    = C'5,22,38';
extern color  InpPanelBorder        = C'20,90,115';

//--- Indicator buffers
double LongEntryBuf[];
double ShortEntryBuf[];
double LongRejectionBuf[];
double ShortRejectionBuf[];
double LongBlockedBuf[];
double ShortBlockedBuf[];

string PANEL_PREFIX = "FXC_SPEED_DENIAL_";
string g_last_alert_key = "";
int g_panel_x=20, g_panel_y=30;
const int PANEL_W=430, PANEL_H=332;
bool g_dragging=false, g_mouse_down=false, g_old_scroll=true;
bool g_old_mouse=false, g_old_foreground=false;
int g_drag_dx=0, g_drag_dy=0;
string g_position_key;

void SavePanelPosition()
{
   GlobalVariableSet(g_position_key+"X",g_panel_x);
   GlobalVariableSet(g_position_key+"Y",g_panel_y);
}
void MovePanel(int x,int y)
{
   int w=(int)ChartGetInteger(0,CHART_WIDTH_IN_PIXELS);
   int h=(int)ChartGetInteger(0,CHART_HEIGHT_IN_PIXELS,0);
   x=MathMax(0,MathMin(x,MathMax(0,w-PANEL_W)));
   y=MathMax(0,MathMin(y,MathMax(0,h-PANEL_H)));
   int dx=x-g_panel_x, dy=y-g_panel_y;
   for(int i=ObjectsTotal(0,0,-1)-1;i>=0;i--)
   {
      string n=ObjectName(0,i,0,-1);
      if(StringFind(n,PANEL_PREFIX)!=0) continue;
      ObjectSetInteger(0,n,OBJPROP_XDISTANCE,ObjectGetInteger(0,n,OBJPROP_XDISTANCE)+dx);
      ObjectSetInteger(0,n,OBJPROP_YDISTANCE,ObjectGetInteger(0,n,OBJPROP_YDISTANCE)+dy);
   }
   g_panel_x=x; g_panel_y=y;
   ChartRedraw();
}
void OnChartEvent(const int id,const long &lparam,const double &dparam,const string &sparam)
{
   if(id==CHARTEVENT_CHART_CHANGE) { MovePanel(g_panel_x,g_panel_y); return; }
   if(id!=CHARTEVENT_MOUSE_MOVE || !InpShowPanel) return;
   int x=(int)lparam, y=(int)dparam;
   bool down=((StringToInteger(sparam)&1)!=0);
   if(down && !g_mouse_down && x>=g_panel_x && x<=g_panel_x+PANEL_W
      && y>=g_panel_y && y<=g_panel_y+36)
   {
      g_dragging=true; g_drag_dx=x-g_panel_x; g_drag_dy=y-g_panel_y;
      g_old_scroll=(bool)ChartGetInteger(0,CHART_MOUSE_SCROLL);
      ChartSetInteger(0,CHART_MOUSE_SCROLL,false);
   }
   if(g_dragging)
   {
      if(down) MovePanel(x-g_drag_dx,y-g_drag_dy);
      else { g_dragging=false; ChartSetInteger(0,CHART_MOUSE_SCROLL,g_old_scroll); SavePanelPosition(); }
   }
   g_mouse_down=down;
}

//+------------------------------------------------------------------+
double PipSize()
{
   if(Digits == 3 || Digits == 5)
      return Point * 10.0;
   return Point;
}

//+------------------------------------------------------------------+
datetime MinuteOpen(const datetime value)
{
   return (datetime)((long)value / 60 * 60);
}

//+------------------------------------------------------------------+
int SpeedBiasAt(const datetime reference_time,
                double &up_speed,
                double &down_speed,
                double &up_ratio,
                double &down_ratio,
                int &bar_count,
                datetime &period_start)
{
   up_speed = 0.0;
   down_speed = 0.0;
   up_ratio = 0.0;
   down_ratio = 0.0;
   bar_count = 0;

   // Use the 60 minutes immediately before the current M1 candle.
   // Example: at 10:37, aggregate completed M1 candles from 09:37 to 10:36.
   datetime period_end = MinuteOpen(reference_time);
   period_start = period_end - 3600;
   if(period_end <= 0)
      return 0;

   int newest = iBarShift(NULL, PERIOD_M1, period_end - 1, false);
   int oldest = iBarShift(NULL, PERIOD_M1, period_start, false);
   if(newest < 0 || oldest < 0 || oldest < newest)
      return 0;

   double pip = PipSize();
   double up_sum = 0.0;
   double down_sum = 0.0;
   int up_count = 0;
   int down_count = 0;

   for(int shift = newest; shift <= oldest; shift++)
   {
      datetime bar_time = iTime(NULL, PERIOD_M1, shift);
      if(bar_time < period_start || bar_time >= period_end)
         continue;

      double body = iClose(NULL, PERIOD_M1, shift) - iOpen(NULL, PERIOD_M1, shift);
      bar_count++;
      if(body > 0.0)
      {
         up_sum += body / pip;
         up_count++;
      }
      else if(body < 0.0)
      {
         down_sum += (-body) / pip;
         down_count++;
      }
   }

   if(up_count > 0)
      up_speed = up_sum / up_count;
   if(down_count > 0)
      down_speed = down_sum / down_count;
   if(bar_count > 0)
   {
      up_ratio = 100.0 * up_count / bar_count;
      down_ratio = 100.0 * down_count / bar_count;
   }

   if(bar_count < InpMinSpeedBars || up_count == 0 || down_count == 0)
      return 0;

   double epsilon = 0.000001;
   if(up_speed > down_speed + epsilon)
      return 1;
   if(down_speed > up_speed + epsilon)
      return -1;
   return 0;
}

//+------------------------------------------------------------------+
void DeletePanel()
{
   int total = ObjectsTotal(0, 0, -1);
   for(int i = total - 1; i >= 0; i--)
   {
      string name = ObjectName(0, i, 0, -1);
      if(StringFind(name, PANEL_PREFIX, 0) == 0)
         ObjectDelete(0, name);
   }
}

//+------------------------------------------------------------------+
void EnsurePanelBox()
{
   string name=PANEL_PREFIX+"BOX";
   if(ObjectFind(0,name)<0) ObjectCreate(0,name,OBJ_RECTANGLE_LABEL,0,0,0);
   ObjectSetInteger(0,name,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,name,OBJPROP_XDISTANCE,g_panel_x);
   ObjectSetInteger(0,name,OBJPROP_YDISTANCE,g_panel_y);
   ObjectSetInteger(0,name,OBJPROP_XSIZE,PANEL_W);
   ObjectSetInteger(0,name,OBJPROP_YSIZE,PANEL_H);
   ObjectSetInteger(0,name,OBJPROP_BGCOLOR,InpPanelBackground);
   ObjectSetInteger(0,name,OBJPROP_COLOR,InpPanelBorder);
   ObjectSetInteger(0,name,OBJPROP_BORDER_TYPE,BORDER_FLAT);
   ObjectSetInteger(0,name,OBJPROP_BACK,false);
   ObjectSetInteger(0,name,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,name,OBJPROP_HIDDEN,true);
   ObjectSetInteger(0,name,OBJPROP_ZORDER,10);
   ObjectSetString(0,name,OBJPROP_TOOLTIP,"上部のタイトルをドラッグして移動");
}

//+------------------------------------------------------------------+
void SetPanelLabel(const string suffix,
                   const int x,
                   const int y,
                   const string text,
                   const color text_color,
                   const int font_size)
{
   string name = PANEL_PREFIX + suffix;
   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);

   ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, name, OBJPROP_ANCHOR, ANCHOR_LEFT_UPPER);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, g_panel_x+x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, g_panel_y+y);
   ObjectSetInteger(0, name, OBJPROP_COLOR, text_color);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, font_size);
   ObjectSetString(0, name, OBJPROP_FONT, "Meiryo");
   ObjectSetString(0, name, OBJPROP_TEXT, text);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
}

//+------------------------------------------------------------------+
// Generic filled panel block.
void SetPanelBox(const string suffix,const int x,const int y,
                 const int width,const int height,
                 const color bg,const color border)
{
   string name = PANEL_PREFIX+suffix;
   if(ObjectFind(0,name)<0) ObjectCreate(0,name,OBJ_RECTANGLE_LABEL,0,0,0);
   ObjectSetInteger(0,name,OBJPROP_CORNER,CORNER_LEFT_UPPER);
   ObjectSetInteger(0,name,OBJPROP_XDISTANCE,g_panel_x+x);
   ObjectSetInteger(0,name,OBJPROP_YDISTANCE,g_panel_y+y);
   ObjectSetInteger(0,name,OBJPROP_XSIZE,width);
   ObjectSetInteger(0,name,OBJPROP_YSIZE,height);
   ObjectSetInteger(0,name,OBJPROP_BGCOLOR,bg);
   ObjectSetInteger(0,name,OBJPROP_COLOR,border);
   ObjectSetInteger(0,name,OBJPROP_BORDER_TYPE,BORDER_FLAT);
   ObjectSetInteger(0,name,OBJPROP_BACK,false);
   ObjectSetInteger(0,name,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,name,OBJPROP_HIDDEN,true);
   ObjectSetInteger(0,name,OBJPROP_ZORDER,11);
}

void SetPanelLine(const string suffix,const int x,const int y,
                  const int width,const color line_color)
{
   SetPanelBox(suffix,x,y,width,1,line_color,line_color);
}

void UpdatePanel(const datetime reference_time,
                 const bool pending_long,
                 const double pending_long_level,
                 const datetime pending_long_time,
                 const bool pending_short,
                 const double pending_short_level,
                 const datetime pending_short_time)
{
   if(!InpShowPanel)
   {
      DeletePanel();
      return;
   }

   EnsurePanelBox();

   double up_speed, down_speed, up_ratio, down_ratio;
   int speed_bars;
   datetime speed_start;
   int bias = SpeedBiasAt(reference_time, up_speed, down_speed,
                          up_ratio, down_ratio, speed_bars, speed_start);

   color buy_color = C'255,80,90';
   color sell_color = C'65,145,255';
   color caption_color = C'178,200,218';
   color muted_color = C'205,215,225';
   color block_bg = C'19,49,78';
   color line_color = C'24,70,102';

   string bias_text = "中立";
   color bias_color = clrSilver;
   if(speed_bars < InpMinSpeedBars) bias_text = "データ不足";
   else if(bias > 0) { bias_text = "▲ 買い優勢"; bias_color = buy_color; }
   else if(bias < 0) { bias_text = "▼ 売り優勢"; bias_color = sell_color; }

   string period_text = TimeToString(speed_start,TIME_MINUTES)+"-"
                        +TimeToString(speed_start+3600,TIME_MINUTES)
                        +" | "+IntegerToString(speed_bars)+"/60本";

   string up_text = "--";
   string down_text = "--";
   string delta_text = "--";
   if(speed_bars >= InpMinSpeedBars)
   {
      up_text = DoubleToString(up_speed,2)+" pips/本";
      down_text = DoubleToString(down_speed,2)+" pips/本";
      delta_text = DoubleToString(MathAbs(up_speed-down_speed),2);
   }

   string pattern_main = "待機中";
   string detail = "";
   string badge_text = "シグナルなし";
   color pattern_color = clrWhite;
   color badge_bg = C'28,49,71';
   color badge_text_color = clrWhite;
   int remain_long = 0, remain_short = 0;
   if(pending_long)
      remain_long = MathMax(0, InpExpiryMinutes - (int)((reference_time - pending_long_time) / 60));
   if(pending_short)
      remain_short = MathMax(0, InpExpiryMinutes - (int)((reference_time - pending_short_time) / 60));

   if(pending_long && pending_short)
   {
      pattern_main = "買い・売り待ち";
      detail = "買 "+DoubleToString(pending_long_level,Digits)
               +" / 売 "+DoubleToString(pending_short_level,Digits);
      pattern_color = InpRejectionColor;
      badge_text = "両待ち";
      badge_bg = C'73,57,25';
   }
   else if(pending_long)
   {
      pattern_main = "買い待ち";
      detail = DoubleToString(pending_long_level,Digits)+"  残り"+IntegerToString(remain_long)+"分";
      pattern_color = buy_color;
      badge_text = "買い";
      badge_bg = C'88,35,42';
   }
   else if(pending_short)
   {
      pattern_main = "売り待ち";
      detail = DoubleToString(pending_short_level,Digits)+"  残り"+IntegerToString(remain_short)+"分";
      pattern_color = sell_color;
      badge_text = "売り";
      badge_bg = C'24,57,97';
   }

   // Font-safe, grid-aligned layout. Every row has >= 34px vertical spacing.
   // Display-only change; speed calculations and signal logic are untouched.
   SetPanelLabel("TITLE",16,10,"USDJPY | M1",clrWhite,10);
   SetPanelLabel("PERIOD",16,42,period_text,caption_color,9);
   SetPanelLine("LINE_TOP",16,76,398,line_color);

   // Bias and delta are separate columns; the central gutter is 24px wide.
   SetPanelLabel("BIAS_CAPTION",16,88,"速度優勢方向",caption_color,9);
   SetPanelLabel("BIAS",16,119,bias_text,bias_color,12);
   SetPanelLabel("DELTA_CAPTION",285,88,"速度差 (pips/本)",caption_color,8);
   SetPanelLabel("DELTA_VALUE",304,121,delta_text,clrWhite,12);
   // Keep the legacy object empty. Placing the unit below the value can
   // overlap on another PC when Windows/MT4 font scaling is larger.
   SetPanelLabel("DELTA_UNIT",304,147,"",caption_color,8);

   // Each speed is a separate, full-height line in a single blue card.
   SetPanelBox("SPEED_PANEL",16,174,398,86,block_bg,block_bg);
   SetPanelLabel("UP_CAPTION",27,183,"▲ 上昇速度",buy_color,9);
   SetPanelLabel("UP_VALUE",250,183,up_text,clrWhite,9);
   SetPanelLabel("DOWN_CAPTION",27,220,"▼ 下落速度",sell_color,9);
   SetPanelLabel("DOWN_VALUE",250,220,down_text,clrWhite,9);

   // Explicit bottom padding: status and detail must stay within the panel.
   SetPanelLine("LINE_BOTTOM",16,272,398,line_color);
   SetPanelLabel("PATTERN_CAPTION",16,278,"再ブレイク",caption_color,8);
   SetPanelLabel("PATTERN_MAIN",16,298,pattern_main,pattern_color,10);
   SetPanelLabel("PATTERN_DETAIL",175,302,detail,caption_color,8);

   // Legacy badge objects are hidden so older builds cannot leave debris.
   SetPanelBox("PATTERN_BADGE",0,0,1,1,InpPanelBackground,InpPanelBackground);
   SetPanelLabel("PATTERN_BADGE_TEXT",0,0,"",caption_color,8);

   ChartRedraw();
}

//+------------------------------------------------------------------+
void NotifySignal(const string side,
                  const datetime signal_time,
                  const double level,
                  const double up_speed,
                  const double down_speed)
{
   string key = side + "|" + IntegerToString((int)signal_time)
                + "|" + DoubleToString(level, Digits);
   if(key == g_last_alert_key)
      return;
   g_last_alert_key = key;

   string message = Symbol() + " 1分足 " + side
                    + " 逆張り否定・再ブレイク 価格："
                    + DoubleToString(level, Digits)
                    + " | 上昇速度 " + DoubleToString(up_speed, 2)
                    + " / 下落速度 " + DoubleToString(down_speed, 2) + " pips/分";
   if(InpEnablePopupAlert)
      Alert(message);
   if(InpEnableSoundAlert)
      PlaySound(InpAlertSound);
}

//+------------------------------------------------------------------+
int OnInit()
{
   DeletePanel();
   g_position_key="FXC_PANEL_"+IntegerToString(ChartID())+"_";
   g_panel_x=MathMax(0,(int)ChartGetInteger(0,CHART_WIDTH_IN_PIXELS)-PANEL_W-20);
   if(GlobalVariableCheck(g_position_key+"X")) g_panel_x=(int)GlobalVariableGet(g_position_key+"X");
   if(GlobalVariableCheck(g_position_key+"Y")) g_panel_y=(int)GlobalVariableGet(g_position_key+"Y");
   MovePanel(g_panel_x,g_panel_y);
   g_old_mouse=(bool)ChartGetInteger(0,CHART_EVENT_MOUSE_MOVE);
   g_old_foreground=(bool)ChartGetInteger(0,CHART_FOREGROUND);
   if(InpShowPanel) {
      ChartSetInteger(0,CHART_EVENT_MOUSE_MOVE,true);
      ChartSetInteger(0,CHART_FOREGROUND,false);
   }
   IndicatorShortName("USDJPY 速度＋逆張り否定ブレイク");

   SetIndexBuffer(0, LongEntryBuf);
   SetIndexStyle(0, DRAW_ARROW, STYLE_SOLID, 2, InpLongColor);
   SetIndexArrow(0, 233);
   SetIndexEmptyValue(0, EMPTY_VALUE);
   SetIndexLabel(0, "買い・再ブレイク");

   SetIndexBuffer(1, ShortEntryBuf);
   SetIndexStyle(1, DRAW_ARROW, STYLE_SOLID, 2, InpShortColor);
   SetIndexArrow(1, 234);
   SetIndexEmptyValue(1, EMPTY_VALUE);
   SetIndexLabel(1, "売り・再ブレイク");

   SetIndexBuffer(2, LongRejectionBuf);
   SetIndexStyle(2, DRAW_ARROW, STYLE_SOLID, 1, InpRejectionColor);
   SetIndexArrow(2, 159);
   SetIndexEmptyValue(2, EMPTY_VALUE);
   SetIndexLabel(2, "高値からの反落");

   SetIndexBuffer(3, ShortRejectionBuf);
   SetIndexStyle(3, DRAW_ARROW, STYLE_SOLID, 1, InpRejectionColor);
   SetIndexArrow(3, 159);
   SetIndexEmptyValue(3, EMPTY_VALUE);
   SetIndexLabel(3, "安値からの反発");

   SetIndexBuffer(4, LongBlockedBuf);
   SetIndexStyle(4, DRAW_ARROW, STYLE_SOLID, 1, InpBlockedColor);
   SetIndexArrow(4, 251);
   SetIndexEmptyValue(4, EMPTY_VALUE);
   SetIndexLabel(4, "買い・速度不一致");

   SetIndexBuffer(5, ShortBlockedBuf);
   SetIndexStyle(5, DRAW_ARROW, STYLE_SOLID, 1, InpBlockedColor);
   SetIndexArrow(5, 251);
   SetIndexEmptyValue(5, EMPTY_VALUE);
   SetIndexLabel(5, "売り・速度不一致");

   ArraySetAsSeries(LongEntryBuf, true);
   ArraySetAsSeries(ShortEntryBuf, true);
   ArraySetAsSeries(LongRejectionBuf, true);
   ArraySetAsSeries(ShortRejectionBuf, true);
   ArraySetAsSeries(LongBlockedBuf, true);
   ArraySetAsSeries(ShortBlockedBuf, true);

   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   SavePanelPosition();
   if(g_dragging) ChartSetInteger(0,CHART_MOUSE_SCROLL,g_old_scroll);
   if(InpShowPanel) {
      ChartSetInteger(0,CHART_EVENT_MOUSE_MOVE,g_old_mouse);
      ChartSetInteger(0,CHART_FOREGROUND,g_old_foreground);
   }
   DeletePanel();
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
   int minimum_bars = InpLookbackBars + InpExpiryMinutes + 5;
   if(rates_total < minimum_bars)
      return 0;

   int visible_scan = MathMin(InpMaxBarsToScan, rates_total - InpLookbackBars - 2);
   int process_start = MathMin(rates_total - InpLookbackBars - 2,
                               visible_scan + InpExpiryMinutes + InpLookbackBars + 5);
   if(process_start < 1)
      return 0;

   int clear_to = MathMin(rates_total - 1, visible_scan + 2);
   for(int clear_i = 0; clear_i <= clear_to; clear_i++)
   {
      LongEntryBuf[clear_i] = EMPTY_VALUE;
      ShortEntryBuf[clear_i] = EMPTY_VALUE;
      LongRejectionBuf[clear_i] = EMPTY_VALUE;
      ShortRejectionBuf[clear_i] = EMPTY_VALUE;
      LongBlockedBuf[clear_i] = EMPTY_VALUE;
      ShortBlockedBuf[clear_i] = EMPTY_VALUE;
   }

   double pip = PipSize();
   double offset = InpArrowOffsetPips * pip;

   bool pending_long = false;
   bool pending_short = false;
   double pending_long_level = 0.0;
   double pending_short_level = 0.0;
   datetime pending_long_time = 0;
   datetime pending_short_time = 0;
   datetime last_long_entry = 0;
   datetime last_short_entry = 0;

   datetime cached_minute = 0;
   int cached_bias = 0;
   double cached_up_speed = 0.0;
   double cached_down_speed = 0.0;
   double cached_up_ratio = 0.0;
   double cached_down_ratio = 0.0;
   int cached_bars = 0;
   datetime cached_speed_start = 0;

   bool live_long = false;
   bool live_short = false;
   double live_long_level = 0.0;
   double live_short_level = 0.0;
   double live_long_up_speed = 0.0;
   double live_long_down_speed = 0.0;
   double live_short_up_speed = 0.0;
   double live_short_down_speed = 0.0;

   for(int i = process_start; i >= 0; i--)
   {
      datetime this_minute = MinuteOpen(time[i]);
      if(this_minute != cached_minute)
      {
         cached_minute = this_minute;
         cached_bias = SpeedBiasAt(time[i], cached_up_speed, cached_down_speed,
                                  cached_up_ratio, cached_down_ratio,
                                  cached_bars, cached_speed_start);
      }

      // The older pending level is checked before a new rejection on this bar.
      if(pending_long)
      {
         if(time[i] > pending_long_time + InpExpiryMinutes * 60)
         {
            pending_long = false;
         }
         else if(high[i] >= pending_long_level)
         {
            bool cooldown_ok = (last_long_entry == 0
                                || time[i] - last_long_entry >= InpCooldownMinutes * 60);
            bool speed_ok = (!InpRequireSpeedMatch || cached_bias > 0);
            if(cooldown_ok)
            {
               // Cooldown belongs to the base pattern stream. A speed-mismatch
               // signal is filtered from display, but still consumes cooldown.
               last_long_entry = time[i];
               if(speed_ok)
               {
                  if(i <= visible_scan)
                     LongEntryBuf[i] = low[i] - offset;
                  if(i == 0)
                  {
                     live_long = true;
                     live_long_level = pending_long_level;
                     live_long_up_speed = cached_up_speed;
                     live_long_down_speed = cached_down_speed;
                  }
               }
               else if(InpShowBlockedSignals && i <= visible_scan)
               {
                  LongBlockedBuf[i] = low[i] - offset;
               }
            }
            pending_long = false;
         }
      }

      if(pending_short)
      {
         if(time[i] > pending_short_time + InpExpiryMinutes * 60)
         {
            pending_short = false;
         }
         else if(low[i] <= pending_short_level)
         {
            bool cooldown_ok = (last_short_entry == 0
                                || time[i] - last_short_entry >= InpCooldownMinutes * 60);
            bool speed_ok = (!InpRequireSpeedMatch || cached_bias < 0);
            if(cooldown_ok)
            {
               last_short_entry = time[i];
               if(speed_ok)
               {
                  if(i <= visible_scan)
                     ShortEntryBuf[i] = high[i] + offset;
                  if(i == 0)
                  {
                     live_short = true;
                     live_short_level = pending_short_level;
                     live_short_up_speed = cached_up_speed;
                     live_short_down_speed = cached_down_speed;
                  }
               }
               else if(InpShowBlockedSignals && i <= visible_scan)
               {
                  ShortBlockedBuf[i] = high[i] + offset;
               }
            }
            pending_short = false;
         }
      }

      // A rejection is only confirmed after the M1 candle closes.
      if(i >= 1)
      {
         double prior_high = high[i + 1];
         double prior_low = low[i + 1];
         for(int j = i + 2; j <= i + InpLookbackBars; j++)
         {
            if(high[j] > prior_high)
               prior_high = high[j];
            if(low[j] < prior_low)
               prior_low = low[j];
         }

         bool upper_rejection = (high[i] >= prior_high + InpMinBreakPips * pip
                                 && close[i] <= prior_high
                                 && (high[i] - close[i]) / pip >= InpMinRejectionPips);
         bool lower_rejection = (low[i] <= prior_low - InpMinBreakPips * pip
                                 && close[i] >= prior_low
                                 && (close[i] - low[i]) / pip >= InpMinRejectionPips);

         if(upper_rejection)
         {
            if(i <= visible_scan)
               LongRejectionBuf[i] = high[i] + offset * 0.55;
            pending_long = true;
            pending_long_level = high[i];
            pending_long_time = time[i];
         }

         if(lower_rejection)
         {
            if(i <= visible_scan)
               ShortRejectionBuf[i] = low[i] - offset * 0.55;
            pending_short = true;
            pending_short_level = low[i];
            pending_short_time = time[i];
         }
      }
   }

   UpdatePanel(time[0], pending_long, pending_long_level, pending_long_time,
               pending_short, pending_short_level, pending_short_time);

   if(live_long)
      NotifySignal("買い", time[0], live_long_level,
                   live_long_up_speed, live_long_down_speed);
   if(live_short)
      NotifySignal("売り", time[0], live_short_level,
                   live_short_up_speed, live_short_down_speed);

   return rates_total;
}
//+------------------------------------------------------------------+

