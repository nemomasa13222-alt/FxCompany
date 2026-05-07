# -*- coding: utf-8 -*-
"""
経済指標カレンダーをMQL4コードに埋め込む
Strategy Tester対応版（FileOpenが不要）
実行: python mt4/make_embed_mq4.py
"""
import pandas as pd
from pathlib import Path

BASE  = Path(__file__).parent
CSV   = BASE / "EcoCalendar.csv"
OUT   = BASE / "indicators" / "EcoCalendarEmbed.mq4"

df = pd.read_csv(CSV)
n  = len(df)

def mql_str(s: str) -> str:
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'

lines = [
    "//+------------------------------------------------------------------+",
    "//|  EcoCalendarEmbed.mq4                                            |",
    "//|  米国経済指標 チャート表示インジケーター                           |",
    "//|  Strategy Tester対応版 -- データ埋め込み方式（FileOpen不要）      |",
    "//|  FxCompany                                                       |",
    "//+------------------------------------------------------------------+",
    '#property copyright "FxCompany"',
    '#property version   "2.0"',
    '#property strict',
    '#property indicator_chart_window',
    "",
    "input color ColorHigh   = clrRed;    // 最重要(H)の色",
    "input color ColorMedium = clrOrange; // 重要(M)の色",
    "input int   LineWidth   = 1;",
    "input bool  ShowLabel   = true;",
    "input int   LabelSize   = 8;",
    "",
    f"#define EVENT_COUNT {n}",
    "",
]

# 日時配列
lines.append("const string g_dt[EVENT_COUNT] = {")
lines.append(",\n".join(f"  {mql_str(r['datetime'])}" for _, r in df.iterrows()))
lines.append("};")
lines.append("")

# 指標名配列
lines.append("const string g_name[EVENT_COUNT] = {")
lines.append(",\n".join(f"  {mql_str(r['name'])}" for _, r in df.iterrows()))
lines.append("};")
lines.append("")

# 重要度配列
lines.append("const string g_level[EVENT_COUNT] = {")
lines.append(",\n".join(f"  {mql_str(r['importance'])}" for _, r in df.iterrows()))
lines.append("};")
lines.append("")

lines += [
    "//+------------------------------------------------------------------+",
    "int OnInit()   { DrawEvents(); return INIT_SUCCEEDED; }",
    "void OnDeinit(const int reason) { DeleteAll(); }",
    "",
    "int OnCalculate(const int rates_total, const int prev_calculated,",
    "                const datetime &t[], const double &o[], const double &h[],",
    "                const double &l[], const double &c[],",
    "                const long &tv[], const long &v[], const int &s[])",
    "{",
    "   if(prev_calculated == 0) DrawEvents();",
    "   return rates_total;",
    "}",
    "",
    "void OnChartEvent(const int id, const long &lp,",
    "                  const double &dp, const string &sp)",
    "{",
    "   if(id == CHARTEVENT_CHART_CHANGE) DrawEvents();",
    "}",
    "",
    "//+------------------------------------------------------------------+",
    "void DrawEvents()",
    "{",
    "   DeleteAll();",
    "   double hi    = ChartGetDouble(0, CHART_PRICE_MAX);",
    "   double lo    = ChartGetDouble(0, CHART_PRICE_MIN);",
    "   double lbl_y = hi - (hi - lo) * 0.04;",
    "   int drawn = 0;",
    "",
    "   for(int i = 0; i < EVENT_COUNT; i++)",
    "   {",
    '      datetime evt = StringToTime(g_dt[i]);',
    "      if(evt == 0) continue;",
    "",
    '      color  clr  = (g_level[i] == "high") ? ColorHigh : ColorMedium;',
    '      string base = "EC_" + IntegerToString(i);',
    "",
    "      // 縦線",
    '      ObjectCreate(0, base+"_L", OBJ_VLINE, 0, evt, 0);',
    '      ObjectSetInteger(0, base+"_L", OBJPROP_COLOR, clr);',
    '      ObjectSetInteger(0, base+"_L", OBJPROP_WIDTH, LineWidth);',
    '      ObjectSetInteger(0, base+"_L", OBJPROP_STYLE, STYLE_DOT);',
    '      ObjectSetInteger(0, base+"_L", OBJPROP_BACK,  true);',
    '      ObjectSetString(0,  base+"_L", OBJPROP_TOOLTIP, g_name[i]+"\\n"+g_dt[i]);',
    "",
    "      // ラベル",
    "      if(ShowLabel)",
    "      {",
    '         string mark = (g_level[i] == "high") ? "[H]" : "[M]";',
    '         ObjectCreate(0, base+"_T", OBJ_TEXT, 0, evt, lbl_y);',
    '         ObjectSetString(0,  base+"_T", OBJPROP_TEXT,     mark+" "+g_name[i]);',
    '         ObjectSetInteger(0, base+"_T", OBJPROP_COLOR,    clr);',
    '         ObjectSetInteger(0, base+"_T", OBJPROP_FONTSIZE, LabelSize);',
    '         ObjectSetDouble(0,  base+"_T", OBJPROP_ANGLE,    90);',
    '         ObjectSetInteger(0, base+"_T", OBJPROP_BACK,     false);',
    '         ObjectSetString(0,  base+"_T", OBJPROP_TOOLTIP,  g_name[i]+"\\n"+g_dt[i]);',
    "      }",
    "      drawn++;",
    "   }",
    '   Comment(StringFormat("EcoCalendar %d件 [H=最重要  M=重要]", drawn));',
    "   ChartRedraw();",
    "}",
    "",
    "//+------------------------------------------------------------------+",
    "void DeleteAll()",
    "{",
    "   int total = ObjectsTotal(0, -1, -1);",
    "   for(int i = total - 1; i >= 0; i--)",
    "   {",
    '      string nm = ObjectName(0, i, -1, -1);',
    '      if(StringFind(nm, "EC_") == 0) ObjectDelete(0, nm);',
    "   }",
    "}",
    "//+------------------------------------------------------------------+",
]

OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"生成完了: {OUT.name}  ({n}件埋め込み)")
