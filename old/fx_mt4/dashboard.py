"""
fx_mt4/dashboard.py  ─ FXデモ GitHub Pages ダッシュボード生成

出力: docs/fx_demo/index.html
"""
import sys, json
from pathlib import Path
from datetime import datetime, date
import pandas as pd
import numpy as np
sys.path.insert(0, str(Path(__file__).parent.parent))

from fx_mt4.config import MT4_FILES, INITIAL_CAPITAL, LOT_SIZE

TRADES_CSV  = MT4_FILES / "trades" / "trades.csv"
STATUS_FILE = MT4_FILES / "status" / "status.json"
OUT_DIR     = Path(__file__).parent.parent / "docs" / "fx_demo"
OUT_HTML    = OUT_DIR / "index.html"


def load_trades() -> pd.DataFrame:
    if not TRADES_CSV.exists():
        return pd.DataFrame(columns=["close_time","type","pips","profit",
                                      "open_price","close_price","hold_hours"])
    df = pd.read_csv(TRADES_CSV, parse_dates=["close_time","open_time"])
    return df.sort_values("close_time").reset_index(drop=True)


def load_status() -> dict:
    if not STATUS_FILE.exists():
        return {"balance": INITIAL_CAPITAL, "equity": INITIAL_CAPITAL, "positions": []}
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except:
        return {"balance": INITIAL_CAPITAL, "equity": INITIAL_CAPITAL, "positions": []}


def build_html(df: pd.DataFrame, status: dict) -> str:
    now     = datetime.now().strftime("%Y-%m-%d %H:%M")
    balance = status.get("balance", INITIAL_CAPITAL)
    equity  = status.get("equity",  INITIAL_CAPITAL)
    pos_list= status.get("positions", [])
    ret_pct = (equity - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100

    # 集計
    n = len(df)
    if n > 0:
        wins     = df[df["profit"] > 0]
        wr       = len(wins) / n * 100
        pf_val   = wins["profit"].sum() / abs(df[df["profit"]<=0]["profit"].sum()) if (df["profit"]<=0).any() else 99
        total_p  = df["profit"].sum()
        total_pip= df["pips"].sum()
        eq_curve = df["profit"].cumsum().tolist()
        dates    = df["close_time"].dt.strftime("%m/%d %H:%M").tolist()
        avg_hold = df["hold_hours"].mean()
    else:
        wr = pf_val = total_p = total_pip = avg_hold = 0
        eq_curve = []; dates = []

    # カラー
    ret_color = "#2ecc71" if ret_pct >= 0 else "#e74c3c"
    pnl_color = "#2ecc71" if total_p >= 0 else "#e74c3c"

    # ポジション表示
    if pos_list:
        pos = pos_list[0]
        pos_html = f"""
        <div class="position-card">
          <span class="pos-badge {'long' if pos.get('type')=='BUY' else 'short'}">
            {pos.get('type','?')}
          </span>
          <span>エントリー: {pos.get('open_price','-')}</span>
          <span>含み益: <b style="color:{'#2ecc71' if pos.get('profit',0)>=0 else '#e74c3c'}">
            {pos.get('profit',0):+,.0f}円</b></span>
          <span>経過: {pos.get('open_time','-')}</span>
        </div>"""
    else:
        pos_html = '<div class="position-card none">ポジションなし</div>'

    # トレード履歴テーブル（直近20件）
    if n > 0:
        rows = ""
        for _, r in df.tail(20).iloc[::-1].iterrows():
            color = "#2ecc71" if r["profit"] > 0 else "#e74c3c"
            rows += f"""<tr>
              <td>{r['close_time'].strftime('%m/%d %H:%M') if pd.notna(r['close_time']) else '-'}</td>
              <td class="{'long' if r['type']=='BUY' else 'short'}">{r['type']}</td>
              <td style="color:{color}">{r['pips']:+.1f}p</td>
              <td style="color:{color}">{r['profit']:+,.0f}円</td>
              <td>{r['hold_hours']:.1f}h</td>
            </tr>"""
        table_html = f"""
        <table class="trade-table">
          <thead><tr><th>決済日時</th><th>方向</th><th>pips</th><th>損益</th><th>保有</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>"""
    else:
        table_html = '<p class="no-data">まだトレードはありません</p>'

    # Chart.js用データ
    chart_data = json.dumps(eq_curve)
    chart_labels = json.dumps(dates)

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="1800">
<title>FxDemo ダッシュボード | USDJPY 30分足</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #0f0f23; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; padding: 20px; }}
  .header {{ text-align: center; margin-bottom: 24px; }}
  .header h1 {{ font-size: 1.6rem; color: #fff; }}
  .header .sub {{ color: #888; font-size: 0.85rem; margin-top: 4px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; margin-bottom: 24px; }}
  .card {{ background: #1a1a3e; border-radius: 12px; padding: 20px; text-align: center; }}
  .card .label {{ font-size: 0.75rem; color: #888; margin-bottom: 8px; }}
  .card .value {{ font-size: 1.5rem; font-weight: bold; }}
  .card .value.pos {{ color: #2ecc71; }}
  .card .value.neg {{ color: #e74c3c; }}
  .card .value.neu {{ color: #f1c40f; }}
  .section {{ background: #1a1a3e; border-radius: 12px; padding: 20px; margin-bottom: 20px; }}
  .section h2 {{ font-size: 1rem; color: #aaa; margin-bottom: 16px; border-bottom: 1px solid #333; padding-bottom: 8px; }}
  .position-card {{ background: #16213e; border-radius: 8px; padding: 12px 16px; display: flex; gap: 20px; align-items: center; flex-wrap: wrap; }}
  .position-card.none {{ color: #666; }}
  .pos-badge {{ padding: 4px 12px; border-radius: 20px; font-weight: bold; font-size: 0.85rem; }}
  .pos-badge.long {{ background: #1a5c35; color: #2ecc71; }}
  .pos-badge.short {{ background: #5c1a1a; color: #e74c3c; }}
  .trade-table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
  .trade-table th {{ color: #888; font-weight: normal; padding: 8px; text-align: left; border-bottom: 1px solid #333; }}
  .trade-table td {{ padding: 8px; border-bottom: 1px solid #1f1f3a; }}
  .trade-table td.long {{ color: #2ecc71; }}
  .trade-table td.short {{ color: #e74c3c; }}
  .no-data {{ color: #555; text-align: center; padding: 20px; }}
  canvas {{ max-height: 220px; }}
  .footer {{ text-align: center; color: #444; font-size: 0.75rem; margin-top: 24px; }}
  @media (max-width: 600px) {{ .grid {{ grid-template-columns: repeat(2, 1fr); }} }}
</style>
</head>
<body>
<div class="header">
  <h1>FxDemo ダッシュボード</h1>
  <div class="sub">USDJPY 30分足 レンジブレイク  |  最終更新: {now}</div>
</div>

<div class="grid">
  <div class="card">
    <div class="label">有効証拠金</div>
    <div class="value {'pos' if ret_pct>=0 else 'neg'}">{equity:,.0f}<span style="font-size:0.9rem">円</span></div>
  </div>
  <div class="card">
    <div class="label">収益率</div>
    <div class="value {'pos' if ret_pct>=0 else 'neg'}">{ret_pct:+.2f}<span style="font-size:0.9rem">%</span></div>
  </div>
  <div class="card">
    <div class="label">総損益</div>
    <div class="value {'pos' if total_p>=0 else 'neg'}">{total_p:+,.0f}<span style="font-size:0.9rem">円</span></div>
  </div>
  <div class="card">
    <div class="label">勝率</div>
    <div class="value neu">{wr:.1f}<span style="font-size:0.9rem">%</span></div>
  </div>
  <div class="card">
    <div class="label">PF</div>
    <div class="value neu">{pf_val:.2f}</div>
  </div>
  <div class="card">
    <div class="label">トレード数</div>
    <div class="value neu">{n}<span style="font-size:0.9rem">件</span></div>
  </div>
  <div class="card">
    <div class="label">累計pips</div>
    <div class="value {'pos' if total_pip>=0 else 'neg'}">{total_pip:+.1f}<span style="font-size:0.9rem">p</span></div>
  </div>
  <div class="card">
    <div class="label">平均保有</div>
    <div class="value neu">{avg_hold:.1f}<span style="font-size:0.9rem">h</span></div>
  </div>
</div>

<div class="section">
  <h2>現在のポジション</h2>
  {pos_html}
</div>

{'<div class="section"><h2>累積損益推移</h2><canvas id="eqChart"></canvas></div>' if n > 0 else ''}

<div class="section">
  <h2>直近20件のトレード履歴</h2>
  {table_html}
</div>

<div class="footer">
  初期資金: {INITIAL_CAPITAL:,}円 / ロット: {LOT_SIZE} /
  戦略: bars=6 pips=15 hold=3 / XMTrading Demo
  <br>30分ごと自動更新
</div>

<script>
{'const ctx = document.getElementById("eqChart").getContext("2d"); new Chart(ctx, {type:"line",data:{labels:' + chart_labels + ',datasets:[{label:"累積損益(円)",data:' + chart_data + '.map(v=>v*667),borderColor:"#3498db",backgroundColor:"rgba(52,152,219,0.15)",borderWidth:2,fill:true,tension:0.3,pointRadius:2}]},options:{responsive:true,plugins:{legend:{labels:{color:"#aaa"}}},scales:{x:{ticks:{color:"#666",maxRotation:45,maxTicksLimit:10}},y:{ticks:{color:"#aaa"},grid:{color:"#2a2a4a"}}}}});' if n > 0 else ''}
</script>
</body>
</html>"""


def main():
    print("FxDemoダッシュボード生成中...")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df     = load_trades()
    status = load_status()
    html   = build_html(df, status)
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"保存: {OUT_HTML}")
    print(f"トレード数: {len(df)}件")


if __name__ == "__main__":
    main()
