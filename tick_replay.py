# -*- coding: utf-8 -*-
"""
ティック足リプレイツール
  data/tick/USDJPY_tick_YYYY.parquet から指定期間のティックを抽出し、
  ブラウザで1分足の形成過程をティック単位で再生できるHTMLを生成する。

  用途: 裁量トレード練習（値動きの追体験） / バックテスト約定挙動のティック単位検証

  実行例:
    python tick_replay.py --start "2026-07-24 09:00" --end "2026-07-24 11:00"
    python tick_replay.py --start "2026-07-24 09:00" --end "2026-07-24 11:00" --tz utc
    python tick_replay.py --start "2026-07-24" --end "2026-07-25" --out data/tick_replay/my_session.html

  --tz jst（既定）: --start/--end を JST として解釈し、チャートもJST表示
  --tz utc        : --start/--end を UTC として解釈し、チャートもUTC表示
"""
import sys; sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import argparse
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pandas as pd

ROOT      = Path(__file__).parent
TICK_DIR  = ROOT / "data" / "tick"
OUT_DIR   = ROOT / "data" / "tick_replay"
VENDOR_JS = ROOT / "vendor" / "lightweight-charts.standalone.production.js"
PAIR      = "USDJPY"

JST = timezone(timedelta(hours=9))

MAX_TICKS = 2_000_000  # これを超える期間は指定不可（HTMLが肥大化しすぎるため）


def parse_args():
    p = argparse.ArgumentParser(description="ティック足リプレイHTML生成")
    p.add_argument("--start", required=True, help='開始日時 例: "2026-07-24 09:00"')
    p.add_argument("--end",   required=True, help='終了日時 例: "2026-07-24 11:00"')
    p.add_argument("--tz", choices=["jst", "utc"], default="jst",
                   help="start/endの解釈・チャート表示タイムゾーン（既定: jst）")
    p.add_argument("--out", default=None, help="出力HTMLパス（省略時は自動命名）")
    return p.parse_args()


def load_ticks(start_utc: pd.Timestamp, end_utc: pd.Timestamp) -> pd.DataFrame:
    years = range(start_utc.year, end_utc.year + 1)
    frames = []
    for y in years:
        f = TICK_DIR / f"{PAIR}_tick_{y}.parquet"
        if not f.exists():
            continue
        df = pd.read_parquet(f)
        df = df[(df.index >= start_utc) & (df.index < end_utc)]
        if not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames).sort_index()
    out = out[~out.index.duplicated(keep="first")]
    return out


def build_payload(df: pd.DataFrame, tz_offset_hours: int):
    """1分足バーとティック（バー所属インデックス付き）のJSON payloadを作る"""
    minute_floor = df.index.floor("min")
    bar_id, bar_times = pd.factorize(minute_floor, sort=True)

    ohlc = df["mid"].groupby(bar_id).agg(["first", "max", "min", "last"])
    ohlc.columns = ["o", "h", "l", "c"]

    bar_sizes = pd.Series(bar_id).groupby(bar_id).size().to_numpy()
    bar_start_tick = bar_sizes.cumsum() - bar_sizes  # 各バーの最初のtickインデックス

    shift = tz_offset_hours * 3600
    bar_t = (bar_times.view("int64") // 10**9 + shift).astype("int64")

    bars = [
        {"t": int(bar_t[i]), "o": round(float(ohlc["o"].iloc[i]), 3),
         "h": round(float(ohlc["h"].iloc[i]), 3), "l": round(float(ohlc["l"].iloc[i]), 3),
         "c": round(float(ohlc["c"].iloc[i]), 3), "s": int(bar_start_tick[i])}
        for i in range(len(bar_t))
    ]

    tick_t = (df.index.view("int64") // 10**6 + shift * 1000).astype("int64")  # ms
    ticks = [
        {"t": int(tick_t[i]), "b": round(float(df["bid"].iloc[i]), 3),
         "a": round(float(df["ask"].iloc[i]), 3), "m": round(float(df["mid"].iloc[i]), 3),
         "g": int(bar_id[i])}
        for i in range(len(df))
    ]
    return bars, ticks


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>ティックリプレイ {pair} {start_label} 〜 {end_label}</title>
<script>{chart_lib_js}</script>
<style>
*{{box-sizing:border-box}}
body{{font-family:"Yu Gothic UI","Hiragino Sans",Meiryo,sans-serif;margin:0;background:#eef2f7;color:#1e293b;-webkit-text-size-adjust:100%}}
.wrap{{max-width:1100px;margin:0 auto;padding:20px}}
.card{{background:#fff;border-radius:12px;padding:20px 24px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
h1{{font-size:18px;margin:0 0 4px}}
.sub{{color:#64748b;font-size:13px;margin-bottom:10px}}
#chart{{width:100%;height:520px;touch-action:pan-y}}
.controls{{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:14px}}
button{{background:#2563eb;color:#fff;border:none;border-radius:8px;padding:10px 18px;font-size:15px;cursor:pointer;min-height:44px;touch-action:manipulation}}
button:hover{{background:#1d4ed8}}
button.secondary{{background:#64748b}}
button.secondary:hover{{background:#475569}}
select{{padding:10px;border-radius:8px;border:1px solid #cbd5e1;font-size:15px;min-height:44px}}
input[type=range]{{flex:1;min-width:150px;min-height:32px}}
.stats{{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}}
.stat{{flex:1 1 120px;background:#f1f5f9;border-radius:8px;padding:10px;text-align:center}}
.stat .label{{font-size:11px;color:#64748b}}
.stat .value{{font-size:17px;font-weight:600;margin-top:2px}}
.progress-label{{font-size:12px;color:#64748b;min-width:150px;text-align:right}}

@media (max-width: 640px) {{
  .wrap{{padding:10px}}
  .card{{padding:14px 14px;border-radius:10px}}
  h1{{font-size:16px}}
  .sub{{font-size:12px}}
  #chart{{height:340px}}
  .controls{{gap:8px}}
  #playBtn, #resetBtn{{flex:1 1 45%}}
  select{{flex:1 1 100%;order:3}}
  input[type=range]{{flex:1 1 100%;order:4}}
  .progress-label{{flex:1 1 100%;order:5;text-align:center}}
  .stats{{gap:6px}}
  .stat{{flex:1 1 45%;padding:8px}}
  .stat .value{{font-size:15px}}
}}
</style>
</head>
<body>
<div class="wrap">
  <div class="card">
    <h1>ティックリプレイ　{pair}</h1>
    <div class="sub">{start_label} 〜 {end_label}（{tz_label}）　全 {n_ticks:,} ティック / {n_bars:,} 本（1分足）</div>
    <div id="chart"></div>
    <div class="controls">
      <button id="playBtn">▶ 再生</button>
      <button id="resetBtn" class="secondary">⏮ 最初から</button>
      <select id="speedSel">
        <option value="1">1x（実速度）</option>
        <option value="5">5x</option>
        <option value="20" selected>20x</option>
        <option value="60">60x</option>
        <option value="300">300x</option>
        <option value="1500">1500x</option>
        <option value="max">MAX（瞬間）</option>
      </select>
      <input type="range" id="seekBar" min="0" max="1000" value="0">
      <span class="progress-label" id="progressLabel">0 / {n_ticks:,}</span>
    </div>
    <div class="stats">
      <div class="stat"><div class="label">現在時刻</div><div class="value" id="curTime">-</div></div>
      <div class="stat"><div class="label">BID</div><div class="value" id="curBid">-</div></div>
      <div class="stat"><div class="label">ASK</div><div class="value" id="curAsk">-</div></div>
      <div class="stat"><div class="label">スプレッド</div><div class="value" id="curSpread">-</div></div>
      <div class="stat"><div class="label">形成中バー O/H/L/C</div><div class="value" id="curBar">-</div></div>
    </div>
  </div>
</div>
<script>
const BARS  = {bars_json};
const TICKS = {ticks_json};
const N = TICKS.length;

const chart = LightweightCharts.createChart(document.getElementById('chart'), {{
  autoSize: true,
  layout: {{ background: {{ color: '#ffffff' }}, textColor: '#1e293b' }},
  grid: {{ vertLines: {{ color: '#f1f5f9' }}, horzLines: {{ color: '#f1f5f9' }} }},
  timeScale: {{ timeVisible: true, secondsVisible: true, borderColor: '#e2e8f0' }},
  rightPriceScale: {{ borderColor: '#e2e8f0' }},
  handleScroll: {{ vertTouchDrag: false }},
}});
const series = chart.addCandlestickSeries({{
  upColor: '#26a69a', downColor: '#ef5350',
  borderUpColor: '#26a69a', borderDownColor: '#ef5350',
  wickUpColor: '#26a69a', wickDownColor: '#ef5350',
}});

let curIdx = -1;      // 最後に処理したtickのインデックス
let curBarId = -1;
let o=0,h=0,l=0,c=0;
let playing = false;
let simMs = 0;        // 累積シミュレーション時間（ms）
let lastFrameTs = null;

function fmtTime(ms) {{
  const d = new Date(ms);
  const p = n => String(n).padStart(2,'0');
  return `${{d.getUTCFullYear()}}-${{p(d.getUTCMonth()+1)}}-${{p(d.getUTCDate())}} ${{p(d.getUTCHours())}}:${{p(d.getUTCMinutes())}}:${{p(d.getUTCSeconds())}}`;
}}

function applyTick(i) {{
  const tk = TICKS[i];
  if (tk.g !== curBarId) {{
    if (curBarId >= 0) {{
      const prevBar = BARS[curBarId];
      series.update({{ time: prevBar.t, open: prevBar.o, high: prevBar.h, low: prevBar.l, close: prevBar.c }});
    }}
    curBarId = tk.g;
    o = tk.m; h = tk.m; l = tk.m; c = tk.m;
  }} else {{
    if (tk.m > h) h = tk.m;
    if (tk.m < l) l = tk.m;
    c = tk.m;
  }}
  const bar = BARS[curBarId];
  series.update({{ time: bar.t, open: o, high: h, low: l, close: c }});
}}

function renderStats(i) {{
  const tk = TICKS[i];
  document.getElementById('curTime').textContent = fmtTime(tk.t);
  document.getElementById('curBid').textContent = tk.b.toFixed(3);
  document.getElementById('curAsk').textContent = tk.a.toFixed(3);
  document.getElementById('curSpread').textContent = ((tk.a - tk.b) * 100).toFixed(1) + ' pips';
  document.getElementById('curBar').textContent = `${{o.toFixed(3)}} / ${{h.toFixed(3)}} / ${{l.toFixed(3)}} / ${{c.toFixed(3)}}`;
  document.getElementById('progressLabel').textContent = `${{(i+1).toLocaleString()}} / ${{N.toLocaleString()}}`;
  document.getElementById('seekBar').value = Math.round((i / (N-1)) * 1000);
}}

function seekTo(targetIdx) {{
  targetIdx = Math.max(0, Math.min(N-1, targetIdx));
  const targetBar = TICKS[targetIdx].g;
  const completed = BARS.slice(0, targetBar).map(b => ({{ time:b.t, open:b.o, high:b.h, low:b.l, close:b.c }}));
  series.setData(completed);
  const startTick = BARS[targetBar].s;
  o = TICKS[startTick].m; h = o; l = o; c = o;
  for (let i = startTick; i <= targetIdx; i++) {{
    const m = TICKS[i].m;
    if (i === startTick) {{ o=m; h=m; l=m; c=m; }}
    else {{ if (m>h) h=m; if (m<l) l=m; c=m; }}
  }}
  curBarId = targetBar;
  series.update({{ time: BARS[targetBar].t, open:o, high:h, low:l, close:c }});
  curIdx = targetIdx;
  simMs = TICKS[targetIdx].t - TICKS[0].t;
  renderStats(targetIdx);
}}

function step() {{
  if (!playing) return;
  const now = performance.now();
  const realDelta = lastFrameTs === null ? 0 : (now - lastFrameTs);
  lastFrameTs = now;
  const speedSel = document.getElementById('speedSel').value;

  if (speedSel === 'max') {{
    const CHUNK = 2000;
    const end = Math.min(N-1, curIdx + CHUNK);
    for (let i = curIdx+1; i <= end; i++) applyTick(i);
    curIdx = end;
  }} else {{
    const speed = parseFloat(speedSel);
    simMs += realDelta * speed;
    const targetT = TICKS[0].t + simMs;
    let i = curIdx + 1;
    while (i < N && TICKS[i].t <= targetT) {{ applyTick(i); i++; }}
    curIdx = i - 1;
  }}

  if (curIdx >= 0) renderStats(curIdx);
  if (curIdx >= N-1) {{ playing = false; document.getElementById('playBtn').textContent = '▶ 再生'; return; }}
  requestAnimationFrame(step);
}}

document.getElementById('playBtn').addEventListener('click', () => {{
  playing = !playing;
  document.getElementById('playBtn').textContent = playing ? '⏸ 一時停止' : '▶ 再生';
  if (playing) {{ lastFrameTs = null; requestAnimationFrame(step); }}
}});

document.getElementById('resetBtn').addEventListener('click', () => {{
  playing = false;
  document.getElementById('playBtn').textContent = '▶ 再生';
  curBarId = -1;
  series.setData([]);
  seekTo(0);
}});

document.getElementById('seekBar').addEventListener('input', (e) => {{
  playing = false;
  document.getElementById('playBtn').textContent = '▶ 再生';
  const idx = Math.round((e.target.value / 1000) * (N-1));
  seekTo(idx);
}});

seekTo(0);
chart.timeScale().fitContent();
</script>
</body>
</html>
"""


def main():
    args = parse_args()

    if args.tz == "jst":
        start_local = pd.Timestamp(args.start)
        end_local   = pd.Timestamp(args.end)
        start_utc = (start_local - timedelta(hours=9)).tz_localize("UTC")
        end_utc   = (end_local - timedelta(hours=9)).tz_localize("UTC")
        tz_offset = 9
        tz_label  = "JST"
    else:
        start_utc = pd.Timestamp(args.start).tz_localize("UTC")
        end_utc   = pd.Timestamp(args.end).tz_localize("UTC")
        tz_offset = 0
        tz_label  = "UTC"

    if end_utc <= start_utc:
        print("エラー: --end は --start より後にしてください")
        sys.exit(1)

    print(f"読み込み中: {PAIR}  {start_utc} 〜 {end_utc} (UTC)")
    df = load_ticks(start_utc, end_utc)
    if df.empty:
        print("エラー: 指定期間のティックデータが見つかりませんでした")
        print(f"  利用可能ファイル: {sorted(f.name for f in TICK_DIR.glob(f'{PAIR}_tick_*.parquet'))}")
        sys.exit(1)

    if len(df) > MAX_TICKS:
        print(f"エラー: 対象ティック数 {len(df):,} が上限 {MAX_TICKS:,} を超えています。期間を狭めてください。")
        sys.exit(1)

    print(f"  {len(df):,} ティック取得")
    bars, ticks = build_payload(df, tz_offset)
    print(f"  1分足 {len(bars):,} 本を構成")

    if not VENDOR_JS.exists():
        print(f"エラー: チャートライブラリが見つかりません: {VENDOR_JS}")
        print('  取得: Invoke-WebRequest -Uri "https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js" -OutFile "vendor/lightweight-charts.standalone.production.js"')
        sys.exit(1)
    chart_lib_js = VENDOR_JS.read_text(encoding="utf-8")

    start_label = args.start
    end_label   = args.end

    html = HTML_TEMPLATE.format(
        pair=PAIR,
        start_label=start_label,
        end_label=end_label,
        tz_label=tz_label,
        n_ticks=len(ticks),
        n_bars=len(bars),
        chart_lib_js=chart_lib_js,
        bars_json=json.dumps(bars, separators=(",", ":")),
        ticks_json=json.dumps(ticks, separators=(",", ":")),
    )

    if args.out:
        out_path = ROOT / args.out
    else:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        safe = lambda s: s.replace(" ", "_").replace(":", "").replace("-", "")
        out_path = OUT_DIR / f"{PAIR}_{safe(start_label)}_{safe(end_label)}.html"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")

    size_mb = out_path.stat().st_size / 1e6
    print(f"\n→ {out_path}  ({size_mb:.1f}MB)")
    print("完了！ブラウザで開いて再生してください。")


if __name__ == "__main__":
    main()
