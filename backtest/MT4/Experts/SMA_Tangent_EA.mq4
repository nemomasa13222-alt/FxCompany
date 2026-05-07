//+------------------------------------------------------------------+
//|  SMA_Tangent_EA.mq4                                              |
//|  20SMA接線ブレイクアウト Expert Advisor                            |
//|  FxCompany  AI孫正義                                               |
//+------------------------------------------------------------------+
//
// 【動作条件】
//   チャート足: M15（15分足）推奨
//   通貨ペア  : USDJPY
//   モデル    : Every tick（高精度）または Open prices only（高速）
//
// 【戦略ロジック】
//   準備: 20SMAがMin_Flat_Streak本以上連続で平行（傾き < Flat_Threshold）
//   方向: 当日始値より上 → ロングのみ / 下 → ショートのみ
//   エントリー: 準備OK × 価格がSMAをクロス × クールダウン経過
//   損切: エントリーからSL_Pips固定
//   利確: エントリーからTP_Pips固定
//+------------------------------------------------------------------+

#property copyright "FxCompany"
#property version   "1.00"
#property strict

// ── 入力パラメータ ────────────────────────────────────────────────────────────
input int    SMA_Period      = 20;      // SMA期間
input int    Slope_Window    = 3;       // 傾き計算バー数
input double Flat_Threshold  = 0.030;  // 平行判定閾値（円）
input int    Min_Flat_Streak = 6;       // 連続平行必要本数
input int    Cooldown_Bars   = 8;       // エントリー後クールダウン（バー数）
input double TP_Pips         = 5.0;    // 利確（pips）
input double SL_Pips         = 2.0;    // 損切（pips）
input double Risk_Pct        = 0.5;    // 1トレードリスク（口座残高の%）
input double Min_Lot         = 0.01;   // 最小ロット
input double Max_Lot         = 100.0;  // 最大ロット
input int    Slippage        = 3;      // スリッページ（points）
input int    Magic           = 20250101; // マジックナンバー
input string Comment_        = "SMA_TAN"; // 注文コメント

// ── グローバル変数 ────────────────────────────────────────────────────────────
datetime g_LastBarTime  = 0;    // 新バー検出用
int      g_CooldownLeft = 0;    // クールダウン残バー数
double   g_PipSize      = 0.01; // 1pip のサイズ（USD/JPY = 0.01）

//+------------------------------------------------------------------+
//| Expert initialization                                             |
//+------------------------------------------------------------------+
int OnInit()
{
   // USD/JPYのpipサイズ判定（3桁 or 2桁）
   g_PipSize = (Digits == 3 || Digits == 5) ? 10.0 * Point : Point;

   Print(StringFormat(
      "SMA_Tangent_EA 初期化完了 | SMA%d flat:%.3f streak:%d "
      "TP:%.1fpips SL:%.1fpips risk:%.1f%%",
      SMA_Period, Flat_Threshold, Min_Flat_Streak,
      TP_Pips, SL_Pips, Risk_Pct));

   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization                                           |
//+------------------------------------------------------------------+
void OnDeinit(const int reason) {}

//+------------------------------------------------------------------+
//| Expert tick function（新バーごとに処理）                           |
//+------------------------------------------------------------------+
void OnTick()
{
   // 新バーが開いた時だけ処理
   if(Time[0] == g_LastBarTime) return;
   g_LastBarTime = Time[0];

   // クールダウンカウントダウン
   if(g_CooldownLeft > 0) g_CooldownLeft--;

   // 既存ポジションの管理（必要なら手動TP/SL補正はここで）
   ManageOpenPosition();

   // 新規エントリーチェック
   CheckEntry();
}

//+------------------------------------------------------------------+
//| 既存ポジション管理                                                  |
//| ※ TP/SL は OrderSend 時に設定済み。追加ロジックがあればここに書く。 |
//+------------------------------------------------------------------+
void ManageOpenPosition()
{
   // 現状は OrderSend 時の TP/SL に任せる
   // 将来: トレーリングストップ等を追加する場合はここ
}

//+------------------------------------------------------------------+
//| エントリーチェック                                                  |
//+------------------------------------------------------------------+
void CheckEntry()
{
   // 既にポジションがあればスキップ
   if(HasOpenPosition()) return;

   // クールダウン中はスキップ
   if(g_CooldownLeft > 0) return;

   // SMA・傾き・flat_streak を計算
   double sma_cur  = GetSMA(0);
   double sma_prev = GetSMA(Slope_Window);
   if(sma_cur == 0 || sma_prev == 0) return;

   double slope    = sma_cur - sma_prev;
   int    streak   = GetFlatStreak();

   // 準備完了チェック（1本前の状態で判定: look-ahead防止）
   if(streak < Min_Flat_Streak) return;

   // 日足始値フィルター
   double daily_open = iOpen(Symbol(), PERIOD_D1, 0);
   double close_cur  = Close[0]; // 直前バーのclose（バー確定済み）
   // 実際はClose[1]（確定済みバー）を使うのが安全
   double close_check = Close[1];

   // SMAクロス検出（バー[1]→バー[0]の変化）
   double sma1 = GetSMA(1);  // 1本前のSMA
   bool   cross_up = (Close[2] < sma1 && Close[1] >= GetSMA(0));
   bool   cross_dn = (Close[2] > sma1 && Close[1] <= GetSMA(0));

   // シンプルクロス: 前バーとのSMA比較
   bool above_now  = (Close[1] > GetSMA(1));
   bool above_prev = (Close[2] > GetSMA(2));
   cross_up = (!above_prev && above_now);
   cross_dn = ( above_prev && !above_now);

   // エントリー方向
   int direction = 0; // 1=long, -1=short

   if(cross_up && close_check > daily_open)
      direction = 1;  // ロング
   else if(cross_dn && close_check < daily_open)
      direction = -1; // ショート

   if(direction == 0) return;

   // TP/SL の計算
   double ask   = Ask;
   double bid   = Bid;
   double tp_d  = TP_Pips * g_PipSize;
   double sl_d  = SL_Pips * g_PipSize;

   double entry_price, tp_price, sl_price;
   int    order_type;

   if(direction == 1) // ロング
   {
      entry_price = ask;
      tp_price    = NormalizeDouble(entry_price + tp_d, Digits);
      sl_price    = NormalizeDouble(entry_price - sl_d, Digits);
      order_type  = OP_BUY;
   }
   else // ショート
   {
      entry_price = bid;
      tp_price    = NormalizeDouble(entry_price - tp_d, Digits);
      sl_price    = NormalizeDouble(entry_price + sl_d, Digits);
      order_type  = OP_SELL;
   }

   // ロットサイズ計算
   double lot = CalcLot(sl_d);
   if(lot <= 0) return;

   // 注文送信
   int ticket = OrderSend(
      Symbol(),
      order_type,
      lot,
      entry_price,
      Slippage,
      sl_price,
      tp_price,
      Comment_,
      Magic,
      0,
      (direction == 1) ? clrLimeGreen : clrOrangeRed
   );

   if(ticket < 0)
   {
      Print(StringFormat("OrderSend失敗 error=%d dir=%d lot=%.2f entry=%.3f sl=%.3f tp=%.3f",
                         GetLastError(), direction, lot, entry_price, sl_price, tp_price));
   }
   else
   {
      g_CooldownLeft = Cooldown_Bars;
      Print(StringFormat("エントリー ticket=%d %s lot=%.2f entry=%.3f sl=%.3f tp=%.3f streak=%d",
                         ticket,
                         (direction==1)?"BUY":"SELL",
                         lot, entry_price, sl_price, tp_price, streak));
   }
}

//+------------------------------------------------------------------+
//| ヘルパー: SMAを取得（index=0が現在バー）                            |
//+------------------------------------------------------------------+
double GetSMA(int shift)
{
   return iMA(Symbol(), 0, SMA_Period, 0, MODE_SMA, PRICE_CLOSE, shift);
}

//+------------------------------------------------------------------+
//| ヘルパー: 連続flat本数を取得（現在バーから遡る）                    |
//+------------------------------------------------------------------+
int GetFlatStreak()
{
   int streak = 0;
   for(int i = 1; i <= Min_Flat_Streak + Slope_Window + 5; i++)
   {
      double s  = GetSMA(i);
      double sn = GetSMA(i + Slope_Window);
      if(s == 0 || sn == 0) break;
      if(MathAbs(s - sn) < Flat_Threshold)
         streak++;
      else
         break;
   }
   return streak;
}

//+------------------------------------------------------------------+
//| ヘルパー: Magicナンバーが一致するオープンポジションがあるか         |
//+------------------------------------------------------------------+
bool HasOpenPosition()
{
   for(int i = 0; i < OrdersTotal(); i++)
   {
      if(OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
         if(OrderSymbol() == Symbol() && OrderMagicNumber() == Magic)
            return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| ロットサイズ計算                                                    |
//| risk_amount = 残高 × Risk_Pct% を SL距離 で割る                   |
//+------------------------------------------------------------------+
double CalcLot(double sl_distance)
{
   double balance       = AccountBalance();
   double risk_amount   = balance * Risk_Pct / 100.0;

   // 1ロットあたりの1点変動価値（口座通貨ベース）
   double tick_val      = MarketInfo(Symbol(), MODE_TICKVALUE);  // 1tick per 1lot
   double tick_size     = MarketInfo(Symbol(), MODE_TICKSIZE);
   // pip_value_per_lot = (1pip / tick_size) * tick_val
   double pip_val_lot   = (g_PipSize / tick_size) * tick_val;

   // 損失pips 計算
   double sl_pips       = sl_distance / g_PipSize;

   if(pip_val_lot <= 0 || sl_pips <= 0) return 0;

   double lot = risk_amount / (sl_pips * pip_val_lot);

   // ロット正規化
   double min_lot  = MarketInfo(Symbol(), MODE_MINLOT);
   double max_lot  = MarketInfo(Symbol(), MODE_MAXLOT);
   double lot_step = MarketInfo(Symbol(), MODE_LOTSTEP);

   lot = MathFloor(lot / lot_step) * lot_step;
   lot = MathMax(lot, MathMax(min_lot, Min_Lot));
   lot = MathMin(lot, MathMin(max_lot, Max_Lot));

   return NormalizeDouble(lot, 2);
}

//+------------------------------------------------------------------+
