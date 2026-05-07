//+------------------------------------------------------------------+
//|  EcoCalendar.mq4                                                 |
//|  米国経済指標 チャート表示インジケーター                           |
//|  FxCompany                                                       |
//+------------------------------------------------------------------+
#property copyright "FxCompany"
#property version   "1.0"
#property strict
#property indicator_chart_window

//--- 入力パラメータ
input string   FileName       = "EcoCalendar.csv";  // CSVファイル名（MQL4/Files/内）
input int      DaysAhead      = 7;                   // 何日先まで表示するか
input int      HoursBehind    = 2;                   // 何時間前まで遡って表示するか
input color    ColorHigh      = clrRed;              // 最重要指標の色
input color    ColorMedium    = clrOrange;           // 重要指標の色
input int      LineWidth       = 1;                   // ラインの太さ
input ENUM_LINE_STYLE LineStyle = STYLE_DOT;         // ラインスタイル
input int      LabelFontSize  = 8;                   // ラベルフォントサイズ
input bool     ShowLabel      = true;                // 指標名を表示するか
input double   LabelOffset    = 0.0;                 // ラベル位置オフセット（0=自動）

//--- 内部変数
#define MAX_EVENTS 500
string  g_dt[MAX_EVENTS];
string  g_name[MAX_EVENTS];
string  g_level[MAX_EVENTS];
int     g_count = 0;
datetime g_last_load = 0;

//+------------------------------------------------------------------+
int OnInit()
{
   EventSetTimer(60);  // 1分ごとに再描画
   LoadCSV();
   DrawEvents();
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   DeleteAllObjects();
}

//+------------------------------------------------------------------+
int OnCalculate(const int rates_total, const int prev_calculated,
                const datetime &time[], const double &open[],
                const double &high[], const double &low[],
                const double &close[], const long &tick_volume[],
                const long &volume[], const int &spread[])
{
   // チャートスクロール時も再描画
   if(prev_calculated == 0) DrawEvents();
   return rates_total;
}

//+------------------------------------------------------------------+
void OnTimer()
{
   DrawEvents();
}

//+------------------------------------------------------------------+
void OnChartEvent(const int id, const long &lparam,
                  const double &dparam, const string &sparam)
{
   if(id == CHARTEVENT_CHART_CHANGE) DrawEvents();
}

//+------------------------------------------------------------------+
void LoadCSV()
{
   g_count = 0;
   int handle = FileOpen(FileName, FILE_READ | FILE_CSV | FILE_ANSI, ',');
   if(handle == INVALID_HANDLE)
   {
      Comment("EcoCalendar: CSVファイルが見つかりません\n"
              "MQL4\\Files\\" + FileName + " を配置してください");
      return;
   }

   // ヘッダー行をスキップ
   if(!FileIsEnding(handle))
      FileReadString(handle);  // datetime
   if(!FileIsEnding(handle))
      FileReadString(handle);  // name
   if(!FileIsEnding(handle))
      FileReadString(handle);  // importance

   while(!FileIsEnding(handle) && g_count < MAX_EVENTS)
   {
      string dt    = FileReadString(handle);
      string nm    = FileReadString(handle);
      string level = FileReadString(handle);

      if(dt == "") continue;
      g_dt[g_count]    = dt;
      g_name[g_count]  = nm;
      g_level[g_count] = level;
      g_count++;
   }
   FileClose(handle);
   g_last_load = TimeCurrent();
}

//+------------------------------------------------------------------+
datetime ParseMT4Time(const string s)
{
   // "2024.01.15 15:30" → datetime
   // MQL4のStringToTime は "YYYY.MM.DD HH:MM" 形式に対応
   return StringToTime(s);
}

//+------------------------------------------------------------------+
void DrawEvents()
{
   DeleteAllObjects();

   datetime now      = TimeCurrent();
   datetime from_dt  = now - (datetime)(HoursBehind * 3600);
   datetime to_dt    = now + (datetime)(DaysAhead  * 86400);

   // チャートの価格レンジ取得（ラベル位置計算用）
   double chart_max  = ChartGetDouble(0, CHART_PRICE_MAX);
   double chart_min  = ChartGetDouble(0, CHART_PRICE_MIN);
   double label_price = (LabelOffset != 0.0) ? LabelOffset
                       : chart_max - (chart_max - chart_min) * 0.05;

   int drawn = 0;
   for(int i = 0; i < g_count; i++)
   {
      datetime evt_time = ParseMT4Time(g_dt[i]);
      if(evt_time == 0)        continue;
      if(evt_time < from_dt)   continue;
      if(evt_time > to_dt)     continue;

      color  clr  = (g_level[i] == "high") ? ColorHigh : ColorMedium;
      string base = "EcoCal_" + IntegerToString(i);

      // 縦線
      string line_name = base + "_L";
      ObjectCreate(0, line_name, OBJ_VLINE, 0, evt_time, 0);
      ObjectSetInteger(0, line_name, OBJPROP_COLOR,  clr);
      ObjectSetInteger(0, line_name, OBJPROP_WIDTH,  LineWidth);
      ObjectSetInteger(0, line_name, OBJPROP_STYLE,  LineStyle);
      ObjectSetInteger(0, line_name, OBJPROP_BACK,   true);
      ObjectSetString(0,  line_name, OBJPROP_TOOLTIP, g_name[i] + "\n" + g_dt[i]);

      // ラベル
      if(ShowLabel)
      {
         string lbl_name = base + "_T";
         string disp     = "[" + (g_level[i]=="high" ? "★" : "☆") + "] " + g_name[i];
         ObjectCreate(0, lbl_name, OBJ_TEXT, 0, evt_time, label_price);
         ObjectSetString(0,  lbl_name, OBJPROP_TEXT,      disp);
         ObjectSetInteger(0, lbl_name, OBJPROP_COLOR,     clr);
         ObjectSetInteger(0, lbl_name, OBJPROP_FONTSIZE,  LabelFontSize);
         ObjectSetString(0,  lbl_name, OBJPROP_FONT,      "Arial");
         ObjectSetDouble(0,  lbl_name, OBJPROP_ANGLE,     90);
         ObjectSetInteger(0, lbl_name, OBJPROP_BACK,      false);
         ObjectSetString(0,  lbl_name, OBJPROP_TOOLTIP,   g_name[i] + "\n" + g_dt[i]);
      }
      drawn++;
   }

   // 左上にステータス表示
   string status = StringFormat(
      "EcoCalendar  表示:%d件  [★=最重要  ☆=重要]  次の%d日間",
      drawn, DaysAhead);
   Comment(status);

   ChartRedraw();
}

//+------------------------------------------------------------------+
void DeleteAllObjects()
{
   int total = ObjectsTotal(0, -1, -1);
   for(int i = total - 1; i >= 0; i--)
   {
      string name = ObjectName(0, i, -1, -1);
      if(StringFind(name, "EcoCal_") == 0)
         ObjectDelete(0, name);
   }
}
//+------------------------------------------------------------------+
