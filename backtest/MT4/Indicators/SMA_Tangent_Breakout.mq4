//+------------------------------------------------------------------+
//|  SMA_Tangent_Breakout.mq4                                        |
//|  20SMA接線ブレイクアウト インジケーター                              |
//|  FxCompany  AI孫正義                                               |
//+------------------------------------------------------------------+
//
// 【表示内容】
//   ・20SMA  : グレー実線（常時）
//   ・平行時  : ライムグリーンの太線でハイライト
//   ・接線    : 現在バーの接線を点線（FLAT時=緑 / TREND時=青/赤）
//   ・右上HUD : 傾き(pips/N本)・FLAT判定・連続本数・日足始値との位置関係
//+------------------------------------------------------------------+

#property copyright   "FxCompany"
#property version     "1.00"
#property indicator_chart_window
#property indicator_buffers 4
#property indicator_plots   4

// ── バッファ定義 ──────────────────────────────────────────────────────────────
#property indicator_label1  "20SMA"
#property indicator_type1   DRAW_LINE
#property indicator_color1  clrSilver
#property indicator_style1  STYLE_SOLID
#property indicator_width1  1

#property indicator_label2  "SMA Flat"
#property indicator_type2   DRAW_LINE
#property indicator_color2  clrLimeGreen
#property indicator_style2  STYLE_SOLID
#property indicator_width2  3

#property indicator_label3  "SMA Up"
#property indicator_type3   DRAW_LINE
#property indicator_color3  clrDodgerBlue
#property indicator_style3  STYLE_SOLID
#property indicator_width3  2

#property indicator_label4  "SMA Down"
#property indicator_type4   DRAW_LINE
#property indicator_color4  clrOrangeRed
#property indicator_style4  STYLE_SOLID
#property indicator_width4  2

// ── 入力パラメータ ────────────────────────────────────────────────────────────
input int    SMA_Period        = 20;    // SMA期間
input int    Slope_Window      = 3;     // 傾き計算バー数
input double Flat_Threshold    = 0.030; // 平行判定閾値（円）: この値未満なら「平行」
input int    Min_Flat_Streak   = 6;     // 連続平行必要本数（準備OKの条件）
input int    Tangent_Extend    = 20;    // 接線を左右に何本延ばすか
input int    Panel_Corner      = CORNER_RIGHT_UPPER; // パネル位置
input int    Panel_X           = 10;    // パネルX（右端からの距離px）
input int    Panel_Y           = 20;    // パネルY（上端からの距離px）
input int    Font_Size         = 11;    // フォントサイズ

// ── バッファ配列 ──────────────────────────────────────────────────────────────
double Buf_SMA[];
double Buf_Flat[];
double Buf_Up[];
double Buf_Down[];

// ── オブジェクト名 ────────────────────────────────────────────────────────────
#define OBJ_PREFIX        "SMATAN_"
#define OBJ_TANGENT       OBJ_PREFIX + "Tangent"
#define OBJ_PANEL_BG      OBJ_PREFIX + "PanelBG"
#define OBJ_LBL_SLOPE     OBJ_PREFIX + "Slope"
#define OBJ_LBL_STATUS    OBJ_PREFIX + "Status"
#define OBJ_LBL_STREAK    OBJ_PREFIX + "Streak"
#define OBJ_LBL_DAILY     OBJ_PREFIX + "Daily"
#define OBJ_LBL_TITLE     OBJ_PREFIX + "Title"

//+------------------------------------------------------------------+
//| OnInit                                                            |
//+------------------------------------------------------------------+
int OnInit()
{
   SetIndexBuffer(0, Buf_SMA);
   SetIndexBuffer(1, Buf_Flat);
   SetIndexBuffer(2, Buf_Up);
   SetIndexBuffer(3, Buf_Down);

   // 空値の設定（描画しないバー）
   SetIndexEmptyValue(1, EMPTY_VALUE);
   SetIndexEmptyValue(2, EMPTY_VALUE);
   SetIndexEmptyValue(3, EMPTY_VALUE);

   IndicatorShortName(StringFormat(
      "SMA接線[%d] flat<%.3f %d本", SMA_Period, Flat_Threshold, Min_Flat_Streak));

   // パネル作成
   CreatePanel();

   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| OnDeinit                                                          |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   ObjectsDeleteAll(0, OBJ_PREFIX);
   ChartRedraw();
}

//+------------------------------------------------------------------+
//| OnCalculate                                                       |
//+------------------------------------------------------------------+
int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double   &open[],
                const double   &high[],
                const double   &low[],
                const double   &close[],
                const long     &tick_volume[],
                const long     &volume[],
                const int      &spread[])
{
   if(rates_total < SMA_Period + Slope_Window + Min_Flat_Streak + 2)
      return(0);

   int limit = (prev_calculated <= 0) ? rates_total - SMA_Period - 1 : 1;

   // ── SMA・傾き・連続flat計算 ──────────────────────────────────────────
   // 連続flat本数を全バー分計算するには全バー走査が必要
   // 高速化のため prev_calculated が 0 でなければ最新バーのみ更新
   if(prev_calculated <= 0)
   {
      // 初回 or 再計算: 全バーを走査
      int streak = 0;
      for(int i = rates_total - SMA_Period - Slope_Window - 1; i >= 0; i--)
      {
         double sma    = iMA(NULL, 0, SMA_Period, 0, MODE_SMA, PRICE_CLOSE, i);
         double sma_n  = iMA(NULL, 0, SMA_Period, 0, MODE_SMA, PRICE_CLOSE, i + Slope_Window);
         double slope  = sma - sma_n;

         Buf_SMA[i] = sma;

         bool is_flat = (MathAbs(slope) < Flat_Threshold);

         if(is_flat)
            streak++;
         else
            streak = 0;

         // 色分けバッファ
         bool ready = (streak >= Min_Flat_Streak);
         if(is_flat && ready)
         {
            Buf_Flat[i] = sma;
            Buf_Up[i]   = EMPTY_VALUE;
            Buf_Down[i] = EMPTY_VALUE;
         }
         else if(slope > 0)
         {
            Buf_Flat[i] = EMPTY_VALUE;
            Buf_Up[i]   = sma;
            Buf_Down[i] = EMPTY_VALUE;
         }
         else
         {
            Buf_Flat[i] = EMPTY_VALUE;
            Buf_Up[i]   = EMPTY_VALUE;
            Buf_Down[i] = sma;
         }
      }
   }
   else
   {
      // 差分更新: 最新数バーのみ
      int recalc_bars2 = MathMin(Min_Flat_Streak + Slope_Window + 5, rates_total - SMA_Period - 1);
      for(int k = recalc_bars2; k >= 0; k--)
      {
         double sma2 = iMA(NULL, 0, SMA_Period, 0, MODE_SMA, PRICE_CLOSE, k);
         Buf_SMA[k] = sma2;
      }

      // 現在バーの色と接線は最新バー（i=0）で判定
      int streak2 = 0;
      for(int m = Min_Flat_Streak + Slope_Window + 2; m >= 0; m--)
      {
         double sma3   = Buf_SMA[m];
         double sma_n2 = iMA(NULL, 0, SMA_Period, 0, MODE_SMA, PRICE_CLOSE, m + Slope_Window);
         double slope2 = sma3 - sma_n2;
         bool is_flat2 = (MathAbs(slope2) < Flat_Threshold);

         if(is_flat2) streak2++;
         else         streak2 = 0;

         bool ready2 = (streak2 >= Min_Flat_Streak);
         if(is_flat2 && ready2)
         { Buf_Flat[m] = sma3; Buf_Up[m] = EMPTY_VALUE; Buf_Down[m] = EMPTY_VALUE; }
         else if(slope2 > 0)
         { Buf_Flat[m] = EMPTY_VALUE; Buf_Up[m] = sma3; Buf_Down[m] = EMPTY_VALUE; }
         else
         { Buf_Flat[m] = EMPTY_VALUE; Buf_Up[m] = EMPTY_VALUE; Buf_Down[m] = sma3; }
      }
   }

   // ── 現在バーの接線描画 & HUD更新 ────────────────────────────────────
   double cur_sma   = iMA(NULL, 0, SMA_Period, 0, MODE_SMA, PRICE_CLOSE, 0);
   double prev_sma  = iMA(NULL, 0, SMA_Period, 0, MODE_SMA, PRICE_CLOSE, Slope_Window);
   double slope_now = cur_sma - prev_sma;
   bool   flat_now  = (MathAbs(slope_now) < Flat_Threshold);

   // 連続flat本数（現在）
   int cur_streak = 0;
   for(int j = 0; j < rates_total - SMA_Period; j++)
   {
      double s = iMA(NULL, 0, SMA_Period, 0, MODE_SMA, PRICE_CLOSE, j);
      double p = iMA(NULL, 0, SMA_Period, 0, MODE_SMA, PRICE_CLOSE, j + Slope_Window);
      if(MathAbs(s - p) < Flat_Threshold)
         cur_streak++;
      else
         break;
   }

   // 接線を描画
   DrawTangentLine(time, cur_sma, slope_now, flat_now, cur_streak);

   // 日足始値フィルター
   double daily_open = iOpen(NULL, PERIOD_D1, 0);
   double cur_close  = close[0];
   string daily_pos  = (cur_close > daily_open) ? "始値↑ Long有効" : "始値↓ Short有効";
   color  daily_clr  = (cur_close > daily_open) ? clrLimeGreen : clrOrangeRed;

   // HUD更新
   UpdateHUD(slope_now, flat_now, cur_streak, daily_pos, daily_clr);

   ChartRedraw();
   return(rates_total);
}

//+------------------------------------------------------------------+
//| 接線の描画                                                         |
//+------------------------------------------------------------------+
void DrawTangentLine(const datetime &time[],
                     double sma_val, double slope,
                     bool is_flat, int streak)
{
   // バー間の秒数
   long bar_sec = (long)Period() * 60;

   // 接線の始点（Tangent_Extend本前）と終点（Tangent_Extend本後）
   // slope はSlope_Window本分の変化量 → 1本あたり slope/Slope_Window
   double slope_per_bar = slope / (double)Slope_Window;
   double past_val  = sma_val - slope_per_bar * Tangent_Extend;
   double future_val = sma_val + slope_per_bar * Tangent_Extend;
   datetime past_time   = time[0] - bar_sec * Tangent_Extend;
   datetime future_time = time[0] + bar_sec * Tangent_Extend;

   // 色の決定
   color line_color;
   if(is_flat && streak >= Min_Flat_Streak)
      line_color = clrLimeGreen;
   else if(slope > 0)
      line_color = clrDodgerBlue;
   else
      line_color = clrOrangeRed;

   // 既存オブジェクトを削除して再描画
   ObjectDelete(0, OBJ_TANGENT);
   if(ObjectCreate(0, OBJ_TANGENT, OBJ_TREND, 0,
                   past_time, past_val, future_time, future_val))
   {
      ObjectSetInteger(0, OBJ_TANGENT, OBJPROP_COLOR,    line_color);
      ObjectSetInteger(0, OBJ_TANGENT, OBJPROP_STYLE,    STYLE_DOT);
      ObjectSetInteger(0, OBJ_TANGENT, OBJPROP_WIDTH,    2);
      ObjectSetInteger(0, OBJ_TANGENT, OBJPROP_RAY_LEFT,  false);
      ObjectSetInteger(0, OBJ_TANGENT, OBJPROP_RAY_RIGHT, false);
      ObjectSetInteger(0, OBJ_TANGENT, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, OBJ_TANGENT, OBJPROP_BACK,     false);
   }
}

//+------------------------------------------------------------------+
//| パネル作成（初回）                                                  |
//+------------------------------------------------------------------+
void CreatePanel()
{
   int panel_w = 220;
   int panel_h = 120;

   // 背景
   ObjectDelete(0, OBJ_PANEL_BG);
   if(ObjectCreate(0, OBJ_PANEL_BG, OBJ_RECTANGLE_LABEL, 0, 0, 0))
   {
      ObjectSetInteger(0, OBJ_PANEL_BG, OBJPROP_CORNER,   Panel_Corner);
      ObjectSetInteger(0, OBJ_PANEL_BG, OBJPROP_XDISTANCE, Panel_X);
      ObjectSetInteger(0, OBJ_PANEL_BG, OBJPROP_YDISTANCE, Panel_Y);
      ObjectSetInteger(0, OBJ_PANEL_BG, OBJPROP_XSIZE,     panel_w);
      ObjectSetInteger(0, OBJ_PANEL_BG, OBJPROP_YSIZE,     panel_h);
      ObjectSetInteger(0, OBJ_PANEL_BG, OBJPROP_BGCOLOR,   C'15,30,70');
      ObjectSetInteger(0, OBJ_PANEL_BG, OBJPROP_BORDER_COLOR, clrSteelBlue);
      ObjectSetInteger(0, OBJ_PANEL_BG, OBJPROP_BORDER_TYPE,  BORDER_FLAT);
      ObjectSetInteger(0, OBJ_PANEL_BG, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, OBJ_PANEL_BG, OBJPROP_BACK,       false);
   }

   // タイトル
   CreateLabel(OBJ_LBL_TITLE, 0, "20SMA 接線モニター", Panel_X + panel_w - 10, Panel_Y + 8,
               clrSteelBlue, Font_Size - 1, Panel_Corner, ANCHOR_RIGHT_UPPER);
}

//+------------------------------------------------------------------+
//| ラベル作成ヘルパー                                                  |
//+------------------------------------------------------------------+
void CreateLabel(string name, int subwindow, string text,
                 int x, int y, color clr, int fontsize,
                 int corner, int anchor)
{
   ObjectDelete(0, name);
   if(ObjectCreate(0, name, OBJ_LABEL, subwindow, 0, 0))
   {
      ObjectSetInteger(0, name, OBJPROP_CORNER,    corner);
      ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
      ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
      ObjectSetInteger(0, name, OBJPROP_ANCHOR,    anchor);
      ObjectSetInteger(0, name, OBJPROP_COLOR,     clr);
      ObjectSetInteger(0, name, OBJPROP_FONTSIZE,  fontsize);
      ObjectSetString(0,  name, OBJPROP_FONT,      "Consolas");
      ObjectSetString(0,  name, OBJPROP_TEXT,      text);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_BACK,       false);
   }
}

//+------------------------------------------------------------------+
//| HUD更新                                                            |
//+------------------------------------------------------------------+
void UpdateHUD(double slope, bool is_flat, int streak,
               string daily_pos, color daily_clr)
{
   int panel_w = 220;
   int px      = Panel_X + panel_w - 10;
   int py_base = Panel_Y;

   // 傾き（pips換算）
   double slope_pips = slope * 100.0; // 1円=100pips換算
   string slope_str  = StringFormat("傾き: %+.2f pips/%d本",
                                     slope_pips, Slope_Window);
   color slope_clr   = (MathAbs(slope) < Flat_Threshold) ? clrLimeGreen : clrSilver;

   // 状態テキスト
   string status_str;
   color  status_clr;
   if(is_flat && streak >= Min_Flat_Streak)
   {
      status_str = StringFormat("【READY】準備OK  (%d本連続)", streak);
      status_clr = clrLimeGreen;
   }
   else if(is_flat)
   {
      status_str = StringFormat("【FLAT】  %d / %d本", streak, Min_Flat_Streak);
      status_clr = clrYellow;
   }
   else if(slope > 0)
   {
      status_str = "【TREND UP】 ↑";
      status_clr = clrDodgerBlue;
   }
   else
   {
      status_str = "【TREND DN】 ↓";
      status_clr = clrOrangeRed;
   }

   // 閾値表示
   string param_str = StringFormat("閾値: %.3f円  期間: %d", Flat_Threshold, SMA_Period);

   // ラベル更新
   CreateLabel(OBJ_LBL_SLOPE,  0, slope_str,  px, py_base + 28, slope_clr,  Font_Size,     Panel_Corner, ANCHOR_RIGHT_UPPER);
   CreateLabel(OBJ_LBL_STATUS, 0, status_str, px, py_base + 52, status_clr, Font_Size + 1, Panel_Corner, ANCHOR_RIGHT_UPPER);
   CreateLabel(OBJ_LBL_DAILY,  0, daily_pos,  px, py_base + 78, daily_clr,  Font_Size,     Panel_Corner, ANCHOR_RIGHT_UPPER);
   CreateLabel(OBJ_LBL_STREAK, 0, param_str,  px, py_base + 100, clrGray,   Font_Size - 2, Panel_Corner, ANCHOR_RIGHT_UPPER);
}

//+------------------------------------------------------------------+
