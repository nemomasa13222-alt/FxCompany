//+------------------------------------------------------------------+
//| FxDemoEA.mq4                                                      |
//| USDJPY 30分足 レンジブレイク戦略  v2.00                            |
//| 完全自律型 — MT4 Strategy Tester / OANDA MT4 対応                  |
//|                                                                    |
//| パラメータ（バックテスト採用値）:                                    |
//|   RangeBars=6  RangePipsMax=25  MinHoldBars=3                      |
//|                                                                    |
//| エントリー条件:                                                     |
//|   1. 直近6本のclose幅 <= 25pips（レンジ圧縮）                      |
//|   2. 直前足closeがレンジ高値/安値をブレイク                         |
//|   3. USD-JPY通貨強弱差の符号がブレイク方向と一致                    |
//|                                                                    |
//| 損切り: レンジ中値                                                  |
//| 利確 : 3本以上保有 & 含み益 & 前足closeがリジェクション              |
//|                                                                    |
//| 取引履歴: MQL4\Files\FxDemo\trades\trades.csv に自動書き出し        |
//+------------------------------------------------------------------+
#property copyright "FxCompany"
#property version   "2.00"
#property strict

//── パラメータ ──────────────────────────────────────────────────────
extern int    RangeBars      = 6;     // レンジ形成バー数
extern double RangePipsMax   = 25.0;  // 最大レンジ幅 (pips)
extern int    MinHoldBars    = 3;     // 最低保有バー数
extern int    StrengthWindow = 20;    // 通貨強弱ウィンドウ (M30本数)
extern double RiskPct        = 0.5;   // 1トレードリスク (口座残高%)
extern double MinLot         = 0.01;
extern double MaxLot         = 100.0;
extern int    Slippage       = 3;
extern int    MagicNumber    = 20260519;
extern bool   EnableStrength = true;  // 強弱フィルター ON/OFF

//── 12通貨ペア定義 ──────────────────────────────────────────────────
#define N_PAIRS 12
string PAIRS[N_PAIRS] = {
    "USDJPY","EURJPY","GBPJPY","AUDJPY","NZDJPY","CHFJPY",
    "GBPUSD","AUDUSD","NZDUSD","EURGBP","EURAUD","AUDNZD"
};
string BASE[N_PAIRS]  = {"USD","EUR","GBP","AUD","NZD","CHF","GBP","AUD","NZD","EUR","EUR","AUD"};
string QUOTE[N_PAIRS] = {"JPY","JPY","JPY","JPY","JPY","JPY","USD","USD","USD","GBP","AUD","NZD"};

// 7通貨インデックス: 0=AUD 1=CHF 2=EUR 3=GBP 4=JPY 5=NZD 6=USD
#define IDX_JPY 4
#define IDX_USD 6

//── 取引履歴ファイル ────────────────────────────────────────────────
string TRADES_CSV = "FxDemo\\trades\\trades.csv";
string LAST_TKT   = "FxDemo\\trades\\last_ticket.txt";

//── グローバル ──────────────────────────────────────────────────────
double   g_PipSize = 0.01;
datetime g_LastBar = 0;

//+------------------------------------------------------------------+
int OnInit()
{
    g_PipSize = (Digits == 3 || Digits == 5) ? 10.0 * Point : Point;

    FolderCreate("FxDemo\\trades\\");
    InitTradesCSV();

    Print("FxDemoEA v2.00 起動",
          " | 残高=", AccountBalance(),
          " | bars=", RangeBars,
          " pips=", RangePipsMax,
          " hold=", MinHoldBars,
          " strength=", EnableStrength);
    return INIT_SUCCEEDED;
}

void OnDeinit(const int reason) {}

//+------------------------------------------------------------------+
void OnTick()
{
    // 新バー確定時のみ処理
    if(Time[0] == g_LastBar) return;
    g_LastBar = Time[0];

    ExportClosedTrades();   // 決済済みトレードをCSVに記録
    ManagePosition();       // 保有ポジションの利確チェック
    if(!HasPosition()) CheckEntry();
}

//── 通貨強弱フィルター ──────────────────────────────────────────────
// 戻り値: 正 = USD強い / 負 = JPY強い
double CalcStrength()
{
    double score[7];
    int    cnt[7];
    ArrayInitialize(score, 0.0);
    ArrayInitialize(cnt,   0);

    for(int p = 0; p < N_PAIRS; p++)
    {
        double c_now  = iClose(PAIRS[p], PERIOD_M30, 1);
        double c_prev = iClose(PAIRS[p], PERIOD_M30, StrengthWindow + 1);
        if(c_now <= 0 || c_prev <= 0) continue;

        double lr = MathLog(c_now / c_prev);
        int bi = CurrIdx(BASE[p]);
        int qi = CurrIdx(QUOTE[p]);
        if(bi < 0 || qi < 0) continue;

        score[bi] += lr; cnt[bi]++;
        score[qi] -= lr; cnt[qi]++;
    }

    double usd = (cnt[IDX_USD] > 0) ? score[IDX_USD] / cnt[IDX_USD] : 0.0;
    double jpy = (cnt[IDX_JPY] > 0) ? score[IDX_JPY] / cnt[IDX_JPY] : 0.0;
    return usd - jpy;
}

int CurrIdx(string c)
{
    if(c == "AUD") return 0;
    if(c == "CHF") return 1;
    if(c == "EUR") return 2;
    if(c == "GBP") return 3;
    if(c == "JPY") return 4;
    if(c == "NZD") return 5;
    if(c == "USD") return 6;
    return -1;
}

//── エントリー判定 ──────────────────────────────────────────────────
void CheckEntry()
{
    // レンジ: Bar[2]〜Bar[RangeBars+1] の close で形成
    double rng_high = Close[2];
    double rng_low  = Close[2];
    for(int i = 3; i <= RangeBars + 1; i++)
    {
        if(Close[i] > rng_high) rng_high = Close[i];
        if(Close[i] < rng_low)  rng_low  = Close[i];
    }

    double rng_pips = (rng_high - rng_low) / g_PipSize;
    if(rng_pips > RangePipsMax || rng_pips <= 0) return;

    // ブレイク判定（Bar[1] の close）
    bool broke_up = (Close[1] > rng_high);
    bool broke_dn = (Close[1] < rng_low);
    if(!broke_up && !broke_dn) return;

    // 通貨強弱フィルター
    if(EnableStrength)
    {
        double str = CalcStrength();
        if(broke_up && str <= 0) return;
        if(broke_dn && str >= 0) return;
    }

    // 損切り = レンジ中値
    double rng_mid = NormalizeDouble((rng_high + rng_low) / 2.0, Digits);

    int    otype;
    double entry, sl;

    if(broke_up) { otype = OP_BUY;  entry = Ask; sl = rng_mid; }
    else         { otype = OP_SELL; entry = Bid; sl = rng_mid; }

    double sl_dist = MathAbs(entry - sl);
    if(sl_dist <= 0) return;

    double lot = CalcLot(sl_dist);
    if(lot <= 0) return;

    int ticket = OrderSend(Symbol(), otype, lot, entry, Slippage,
                           sl, 0, "RB_M30", MagicNumber, 0,
                           otype == OP_BUY ? clrGreen : clrRed);
    if(ticket > 0)
        Print("ENTRY ticket=", ticket,
              (otype == OP_BUY ? " BUY" : " SELL"),
              " lot=", DoubleToStr(lot, 2),
              " entry=", DoubleToStr(entry, Digits),
              " sl=", DoubleToStr(sl, Digits),
              " rng=", DoubleToStr(rng_pips, 1), "p");
    else
        Print("OrderSend失敗 error=", GetLastError());
}

//── ポジション管理（利確判定） ──────────────────────────────────────
void ManagePosition()
{
    int ticket = FindTicket();
    if(ticket < 0) return;
    if(!OrderSelect(ticket, SELECT_BY_TICKET)) return;

    int otype = OrderType();

    // 保有バー数
    int bars_held = iBarShift(Symbol(), PERIOD_M30, OrderOpenTime(), false);
    if(bars_held < MinHoldBars) return;

    // 含み益チェック
    double cur = (otype == OP_BUY) ? Bid : Ask;
    if(otype == OP_BUY  && cur <= OrderOpenPrice()) return;
    if(otype == OP_SELL && cur >= OrderOpenPrice()) return;

    // 前足リジェクション
    bool reject = (otype == OP_BUY) ? (Close[1] < Close[2])
                                     : (Close[1] > Close[2]);
    if(!reject) return;

    double cp = (otype == OP_BUY) ? Bid : Ask;
    bool   ok = OrderClose(ticket, OrderLots(), cp, Slippage, clrWhite);
    if(ok)
        Print("CLOSE ticket=", ticket,
              " bars=", bars_held,
              " pnl=", DoubleToStr(OrderProfit(), 0), "円");
    else
        Print("OrderClose失敗 error=", GetLastError());
}

//── 決済済みトレードをCSVに記録（GitHub連携用） ─────────────────────
void InitTradesCSV()
{
    if(FileIsExist(TRADES_CSV)) return;
    int fh = FileOpen(TRADES_CSV, FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
    if(fh == INVALID_HANDLE) return;
    FileWrite(fh, "close_time,ticket,type,lots,open_price,close_price,"
                  "profit_yen,pips,open_time,hold_bars");
    FileClose(fh);
}

void ExportClosedTrades()
{
    int last_tkt = 0;
    if(FileIsExist(LAST_TKT))
    {
        int fh = FileOpen(LAST_TKT, FILE_READ | FILE_ANSI);
        if(fh != INVALID_HANDLE)
        {
            last_tkt = (int)StringToInteger(FileReadString(fh));
            FileClose(fh);
        }
    }

    int new_last = last_tkt;

    for(int i = 0; i < OrdersHistoryTotal(); i++)
    {
        if(!OrderSelect(i, SELECT_BY_POS, MODE_HISTORY)) continue;
        if(OrderMagicNumber() != MagicNumber) continue;
        if(OrderTicket() <= last_tkt) continue;
        if(OrderType() > OP_SELL) continue;

        double pip_val = 0.01;  // JPY建て
        double pips    = (OrderClosePrice() - OrderOpenPrice())
                         * (OrderType() == OP_BUY ? 1.0 : -1.0) / pip_val;
        int bars_held  = iBarShift(Symbol(), PERIOD_M30, OrderOpenTime(), false);

        int fh = FileOpen(TRADES_CSV,
                          FILE_READ | FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
        if(fh != INVALID_HANDLE)
        {
            FileSeek(fh, 0, SEEK_END);
            FileWrite(fh,
                TimeToStr(OrderCloseTime(), TIME_DATE|TIME_MINUTES),
                IntegerToString(OrderTicket()),
                (OrderType() == OP_BUY ? "BUY" : "SELL"),
                DoubleToStr(OrderLots(), 2),
                DoubleToStr(OrderOpenPrice(),  5),
                DoubleToStr(OrderClosePrice(), 5),
                DoubleToStr(OrderProfit(),     0),
                DoubleToStr(pips,              1),
                TimeToStr(OrderOpenTime(), TIME_DATE|TIME_MINUTES),
                IntegerToString(bars_held)
            );
            FileClose(fh);
        }
        if(OrderTicket() > new_last) new_last = OrderTicket();
    }

    if(new_last > last_tkt)
    {
        int fh = FileOpen(LAST_TKT, FILE_WRITE | FILE_ANSI);
        if(fh != INVALID_HANDLE)
        {
            FileWriteString(fh, IntegerToString(new_last));
            FileClose(fh);
        }
    }
}

//── ユーティリティ ──────────────────────────────────────────────────
int FindTicket()
{
    for(int i = 0; i < OrdersTotal(); i++)
    {
        if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
        if(OrderSymbol() == Symbol() && OrderMagicNumber() == MagicNumber)
            return OrderTicket();
    }
    return -1;
}

bool HasPosition() { return FindTicket() >= 0; }

double CalcLot(double sl_dist)
{
    double risk  = AccountBalance() * RiskPct / 100.0;
    double tv    = MarketInfo(Symbol(), MODE_TICKVALUE);
    double ts    = MarketInfo(Symbol(), MODE_TICKSIZE);
    double pvlot = (g_PipSize / ts) * tv;
    double sl_p  = sl_dist / g_PipSize;

    if(pvlot <= 0 || sl_p <= 0) return 0;

    double lot  = risk / (sl_p * pvlot);
    double mmin = MarketInfo(Symbol(), MODE_MINLOT);
    double mmax = MarketInfo(Symbol(), MODE_MAXLOT);
    double step = MarketInfo(Symbol(), MODE_LOTSTEP);

    lot = MathFloor(lot / step) * step;
    lot = MathMax(lot, MathMax(mmin, MinLot));
    lot = MathMin(lot, MathMin(mmax, MaxLot));
    return NormalizeDouble(lot, 2);
}
//+------------------------------------------------------------------+
