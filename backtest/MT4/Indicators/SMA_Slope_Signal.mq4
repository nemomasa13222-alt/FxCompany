//+------------------------------------------------------------------+
//|  SMA_Slope_Signal.mq4                                            |
//|  20SMA平均傾きゼロクロス 転換シグナルインジケーター                  |
//|  FxCompany  AI孫正義                                               |
//+------------------------------------------------------------------+
//
// 【サブウィンドウ表示】
//   グリーン  : 平均傾き > 0（上昇トレンド中）
//   レッド    : 平均傾き < 0（下降トレンド中）
//   ゼロクロス: メインチャートに矢印シグナル
//     上向き矢印（青）= ゼロを下→上 = ロングシグナル（波の底）
//     下向き矢印（赤）= ゼロを上→下 = ショートシグナル（波の頂点）
//+------------------------------------------------------------------+

#property copyright "FxCompany"
#property version   "1.00"
#property strict
#property indicator_separate_window
#property indicator_buffers 2
#property indicator_plots   2

#property indicator_label1  "Slope Pos"
#property indicator_type1   DRAW_HISTOGRAM
#property indicator_color1  clrLimeGreen
#property indicator_width1  2

#property indicator_label2  "Slope Neg"
#property indicator_type2   DRAW_HISTOGRAM
#property indicator_color2  clrOrangeRed
#property indicator_width2  2

#property indicator_level1  0.0
#property indicator_levelcolor clrSilver
#property indicator_levelstyle STYLE_SOLID

// ── 入力パラメータ ────────────────────────────────────────────────────────────
input int    SMA_Period    = 20;    // SMA期間
input int    Slope_Window  = 3;     // 生傾き計算バー数
input int    Smooth_Period = 5;     // 傾き平均化期間
input color  Clr_Long      = clrDodgerBlue;  // ロング矢印の色
input color  Clr_Short     = clrOrangeRed;   // ショート矢印の色
input int    Arrow_Size    = 2;     // 矢印サイズ（1-5）

// ── バッファ ──────────────────────────────────────────────────────────────────
double Buf_Pos[];   // 正の傾き（グリーンヒストグラム）
double Buf_Neg[];   // 負の傾き（レッドヒストグラム）

#define SIG_PREFIX "SLOPE_SIG_"

//+------------------------------------------------------------------+
int OnInit()
{
   SetIndexBuffer(0, Buf_Pos);
   SetIndexBuffer(1, Buf_Neg);
   SetIndexEmptyValue(0, EMPTY_VALUE);
   SetIndexEmptyValue(1, EMPTY_VALUE);

   IndicatorShortName(StringFormat(
      "SlopeSignal[SMA%d S%d Sm%d]", SMA_Period, Slope_Window, Smooth_Period));
   IndicatorDigits(5);

   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   ObjectsDeleteAll(0, SIG_PREFIX);
   ChartRedraw(0);
}

//+------------------------------------------------------------------+
int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double &open[], const double &high[],
                const double &low[],  const double &close[],
                const long &tick_volume[], const long &volume[],
                const int &spread[])
{
   int min_bars = SMA_Period + Slope_Window + Smooth_Period + 3;
   if(rates_total < min_bars) return(0);

   int limit = (prev_calculated <= 0) ? rates_total - min_bars : 3;

   // ── 計算ループ ────────────────────────────────────────────────────────────
   // smooth_slope[i] = MA( SMA[i]-SMA[i+Slope_Window], Smooth_Period )
   // raw_slope[j] = iMA(j) - iMA(j+Slope_Window)
   // smooth[i] = average of raw_slope[i..i+Smooth_Period-1]

   for(int i = limit; i >= 0; i--)
   {
      // 平均傾きを計算
      double sum = 0;
      for(int k = 0; k < Smooth_Period; k++)
      {
         double s_cur  = iMA(NULL, 0, SMA_Period, 0, MODE_SMA, PRICE_CLOSE, i + k);
         double s_prev = iMA(NULL, 0, SMA_Period, 0, MODE_SMA, PRICE_CLOSE, i + k + Slope_Window);
         sum += (s_cur - s_prev);
      }
      double smooth = sum / Smooth_Period;

      // バッファへ設定
      if(smooth > 0) { Buf_Pos[i] = smooth; Buf_Neg[i] = EMPTY_VALUE; }
      else           { Buf_Pos[i] = EMPTY_VALUE; Buf_Neg[i] = smooth; }

      // ゼロクロス検出（i+1=1本前が存在する場合）
      if(i + 1 < rates_total - min_bars + 1)
      {
         double sum_prev = 0;
         for(int k = 0; k < Smooth_Period; k++)
         {
            double sp_cur  = iMA(NULL, 0, SMA_Period, 0, MODE_SMA, PRICE_CLOSE, i+1+k);
            double sp_prev = iMA(NULL, 0, SMA_Period, 0, MODE_SMA, PRICE_CLOSE, i+1+k+Slope_Window);
            sum_prev += (sp_cur - sp_prev);
         }
         double smooth_prev = sum_prev / Smooth_Period;

         string sig_name = SIG_PREFIX + TimeToStr(time[i], TIME_DATE|TIME_MINUTES);

         // 下→上クロス = ロングシグナル（青↑矢印）
         if(smooth_prev < 0 && smooth >= 0)
            DrawArrow(sig_name+"L", time[i],
                      iMA(NULL,0,SMA_Period,0,MODE_SMA,PRICE_CLOSE,i) - 10*Point,
                      233, Clr_Long, Arrow_Size, 0); // 233 = Wingdings上矢印

         // 上→下クロス = ショートシグナル（赤↓矢印）
         else if(smooth_prev > 0 && smooth <= 0)
            DrawArrow(sig_name+"S", time[i],
                      iMA(NULL,0,SMA_Period,0,MODE_SMA,PRICE_CLOSE,i) + 10*Point,
                      234, Clr_Short, Arrow_Size, 0); // 234 = Wingdings下矢印
      }
   }

   ChartRedraw(0);
   return(rates_total);
}

//+------------------------------------------------------------------+
//| メインチャートに矢印を描画                                          |
//+------------------------------------------------------------------+
void DrawArrow(string name, datetime dt, double price,
               int arrow_code, color clr, int size, int subwindow)
{
   if(ObjectFind(0, name) >= 0) return; // 既存はスキップ

   if(ObjectCreate(0, name, OBJ_ARROW, subwindow, dt, price))
   {
      ObjectSetInteger(0, name, OBJPROP_ARROWCODE, arrow_code);
      ObjectSetInteger(0, name, OBJPROP_COLOR,     clr);
      ObjectSetInteger(0, name, OBJPROP_WIDTH,     size);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_BACK,       true);
   }
}
//+------------------------------------------------------------------+
