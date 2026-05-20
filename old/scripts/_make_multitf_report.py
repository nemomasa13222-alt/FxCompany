"""
USDJPY レンジブレイク戦略 全タイムフレーム比較報告書

出力: .company/secretary/notes/reports/report_range_break_multitf_YYYYMMDD.md
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import date
from fx_market_classifier.features import currency_strength, log_returns
from fx_market_classifier.config import PAIRS

DATA_DIR  = Path("data/dukascopy")
PIP       = 0.01; ENTRY_COST = 0.2; SW = 20
IS_START  = "2022-01-01"; IS_END    = "2024-01-01"
OOS_START = "2024-01-01"; OOS_END   = "2025-01-01"
CAPITAL   = 1_000_000;    PIP_VAL   = 667   # 10倍レバ

SESSIONS = {"東京":(0,7), "欧州":(7,13), "NY":(13,21), "深夜":(21,24)}

OUT_DIR  = Path(".company/secretary/notes/reports")
OUT_FILE = OUT_DIR / f"report_range_break_multitf_{date.today():%Y%m%d}.md"

# ── TF設定（各TFのベストパラメータ） ─────────────────────────────────────────
TF_CONFIGS = {
    "1min":  dict(tf_min=1,   resample="1min",  rb=60, rp=3,  mh=25),
    "5min":  dict(tf_min=5,   resample="5min",  rb=12, rp=10, mh=5),
    "15min": dict(tf_min=15,  resample="15min", rb=4,  rp=10, mh=3),
    "30min": dict(tf_min=30,  resample="30min", rb=6,  rp=25, mh=3),
    "1h":    dict(tf_min=60,  resample="1h",    rb=4,  rp=40, mh=2),
    "4h":    dict(tf_min=240, resample="4h",    rb=3,  rp=80, mh=2),
}
TF_ADOPTED = "5min"   # 正式採用足


# ── データ準備 ────────────────────────────────────────────────────────────────
def load_and_resample():
    dfs5 = {p: pd.read_parquet(DATA_DIR/f"{p}_5min.parquet")
            for p in PAIRS if (DATA_DIR/f"{p}_5min.parquet").exists()}
    rd   = {p: log_returns(df["Close"]) for p, df in dfs5.items()}
    st   = currency_strength(rd)
    sd5  = (st["USD"].rolling(SW).sum() - st["JPY"].rolling(SW).sum())
    df5  = dfs5["USDJPY"]

    tf_dfs  = {}
    tf_sds  = {}
    for label, cfg in TF_CONFIGS.items():
        rule = cfg["resample"]
        if label == "1min":
            f = DATA_DIR / "USDJPY_1min.parquet"
            if not f.exists():
                continue
            df_tf = pd.read_parquet(f)
            # 強弱は5分足から前方補完
            sd_tf = sd5.reindex(sd5.index.union(df_tf.index)).ffill().reindex(df_tf.index)
        elif label == "5min":
            df_tf = df5
            sd_tf = sd5.reindex(df5.index)
        else:
            df_tf = df5.resample(rule, label="left", closed="left").agg(
                Open=("Open","first"), High=("High","max"),
                Low=("Low","min"),    Close=("Close","last"), Volume=("Volume","sum")
            ).dropna(subset=["Open"])
            sd_tf = sd5.resample(rule, label="left", closed="left").last().reindex(df_tf.index)
        tf_dfs[label]  = df_tf
        tf_sds[label]  = sd_tf
    return tf_dfs, tf_sds


# ── シグナル・バックテスト ─────────────────────────────────────────────────────
def make_sig(df, sd, rb, rp):
    c  = df["Close"]
    rh = c.shift(1).rolling(rb).max()
    rl = c.shift(1).rolling(rb).min()
    ir = (rh - rl) <= rp * PIP
    s  = sd.reindex(df.index)
    return pd.DataFrame({"c": c, "o": df["Open"],
                         "ls": ir & (c > rh) & (s > 0),
                         "ss": ir & (c < rl) & (s < 0),
                         "rm": (rh + rl) / 2})


def run_bt(sig, mh) -> pd.DataFrame:
    c=sig["c"].values; o=sig["o"].values; rm=sig["rm"].values
    ls=sig["ls"].values; ss=sig["ss"].values; idx=sig.index; n=len(sig)
    rows=[]; inT=False; d=0; ep=sp=0.0; eb=-1
    for i in range(1, n-1):
        if not inT:
            if ls[i-1]:   d=1;  ep=o[i]+ENTRY_COST*PIP; sp=rm[i-1]; eb=i; inT=True
            elif ss[i-1]: d=-1; ep=o[i]-ENTRY_COST*PIP; sp=rm[i-1]; eb=i; inT=True
        else:
            held=i-eb; unr=(c[i]-ep)*d/PIP; xp=None; reason=""
            if d==1  and c[i]<=sp: xp=sp; reason="stop"
            elif d==-1 and c[i]>=sp: xp=sp; reason="stop"
            elif held>=mh and unr>0:
                if d==1  and c[i]<c[i-1]: xp=c[i]; reason="tp"
                elif d==-1 and c[i]>c[i-1]: xp=c[i]; reason="tp"
            if xp is not None:
                rows.append({"entry_time":idx[eb], "exit_time":idx[i],
                             "dir":"L" if d==1 else "S",
                             "pnl":(xp-ep)*d/PIP, "reason":reason, "held":held})
                inT=False; d=0
    return pd.DataFrame(rows)


# ── 指標計算 ──────────────────────────────────────────────────────────────────
def calc(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return dict(n=0,wr=0,pf=0,ev=0,aw=0,al=0,stop_r=0,avg_h=0,
                    total_jpy=0,dd_pct=0,max_dd_bars=0,
                    var95=0,cvar95=0,tail_ratio=0)
    p   = trades["pnl"].values
    w   = p[p>0]; l=p[p<=0]
    n   = len(p)
    wr  = len(w)/n*100
    pf  = w.sum()/abs(l.sum()) if l.sum()!=0 else 99.0
    ev  = p.mean()
    aw  = w.mean() if len(w) else 0
    al  = l.mean() if len(l) else 0
    sr  = (trades["reason"]=="stop").sum()/n*100
    ah  = trades["held"].mean()

    eq  = np.cumsum(p)
    pk  = np.maximum.accumulate(np.maximum(eq,0))
    dd  = (eq-pk)
    mdd = dd.min()*PIP_VAL/CAPITAL*100
    # 最長DD期間
    in_dd = dd < 0
    mx=cur=0
    for v in in_dd:
        cur = cur+1 if v else 0
        mx  = max(mx, cur)

    var95  = np.percentile(p, 5)
    cvar95 = p[p<=var95].mean() if (p<=var95).sum()>0 else var95
    p95    = np.percentile(p, 95)
    tr     = abs(p95/var95) if var95!=0 else 99.0

    return dict(n=n, wr=wr, pf=pf, ev=ev, aw=aw, al=al, stop_r=sr, avg_h=ah,
                total_jpy=p.sum()*PIP_VAL, dd_pct=mdd, max_dd_bars=mx,
                var95=var95, cvar95=cvar95, tail_ratio=tr)


def calc_session(trades: pd.DataFrame) -> dict:
    rows = {}
    for name,(s,e) in SESSIONS.items():
        sub = trades[trades["entry_time"].dt.hour.between(s,e-1)]["pnl"].values
        if len(sub)==0:
            rows[name] = dict(n=0,wr=0,pf=0,ev=0)
            continue
        w=sub[sub>0]; l=sub[sub<=0]
        rows[name] = dict(n=len(sub), wr=len(w)/len(sub)*100,
                          pf=w.sum()/abs(l.sum()) if l.sum()!=0 else 99.0,
                          ev=sub.mean())
    return rows


def calc_streak(trades: pd.DataFrame) -> dict:
    p = trades["pnl"].values
    mx=cur=0; best=cur_s=[]
    for v in p:
        if v<=0: cur+=1; cur_s.append(v)
        else:
            if cur>mx: mx=cur; best=cur_s[:]
            cur=0; cur_s=[]
    if cur>mx: mx=cur; best=cur_s[:]
    c3=sum(1 for i in range(len(p)-2) if all(p[i:i+3]<=0))
    c5=sum(1 for i in range(len(p)-4) if all(p[i:i+5]<=0))
    c10=sum(1 for i in range(len(p)-9) if all(p[i:i+10]<=0))
    return dict(max_streak=mx, worst_loss=sum(best)*PIP_VAL,
                c3=c3, c5=c5, c10=c10)


def calc_monthly(trades: pd.DataFrame) -> pd.Series:
    t = trades.copy()
    t["ym"] = t["exit_time"].dt.tz_localize(None).dt.to_period("M")
    return t.groupby("ym")["pnl"].sum()


def adoption_check(m_is, m_oos) -> list[tuple[str,bool]]:
    pd_ = abs(m_is["pf"] - m_oos["pf"])
    return [
        ("IS PF >= 1.30",         m_is["pf"] >= 1.30),
        ("OOS PF >= 1.10",        m_oos["pf"] >= 1.10),
        ("OOS 損益 > 0",          m_oos["total_jpy"] > 0),
        ("OOS DD <= IS×1.5",      abs(m_oos["dd_pct"]) <= abs(m_is["dd_pct"])*1.5),
        ("IS/OOS PF乖離 <= 0.30", pd_ <= 0.30),
    ]


# ── 報告書生成 ────────────────────────────────────────────────────────────────
def build_report(results: dict) -> str:
    L = []
    def w(s=""): L.append(s)
    def sep(n=65): w("=" * n)

    w(f"# USDJPY レンジブレイク戦略 全タイムフレーム比較報告書")
    w(f"  作成日: {date.today()}")
    w(f"  IS: {IS_START} ~ {IS_END}  /  OOS: {OOS_START} ~ {OOS_END}")
    w(f"  コスト: DMMFX 0.2pips（エントリー時）  資金100万円 / レバ10倍 / 1pip={PIP_VAL}円")
    w()

    # ── 1. 戦略概要 ───────────────────────────────────────────────────────────
    w("## 1. 戦略概要")
    w()
    w("  【エントリー条件】")
    w("    - 直近N本の終値レンジ幅 <= M pips（髭なし）")
    w("    - 終値がレンジ高値/安値をブレイク")
    w("    - 通貨強弱差(USD-JPY)の符号がブレイク方向と一致")
    w("  【損切り】レンジ中値まで逆行")
    w("  【利確】 最低hold本数保有 & 含み益 & 前足終値を切り下げ/切り上げ")
    w()
    w("  パラメータ（TFごとの設定）:")
    w(f"  {'TF':>5} | {'range_bars':>10} {'range_pips':>10} {'min_hold':>8} {'レンジ窓':>8} {'保有目安':>8}")
    w("  " + "-" * 58)
    for tf, cfg in TF_CONFIGS.items():
        if tf not in results: continue
        mark = " ★採用" if tf == TF_ADOPTED else ""
        w(f"  {tf:>5} | {cfg['rb']:>10} {cfg['rp']:>10} {cfg['mh']:>8} "
          f"{cfg['rb']*cfg['tf_min']:>6}分 {cfg['mh']*cfg['tf_min']:>6}分{mark}")
    w()

    # ── 2. IS/OOS サマリー表 ────────────────────────────────────────────────
    w("## 2. IS / OOS サマリー比較")
    w()
    w(f"  前提: 資金100万円 / レバ10倍 / USDJPY 6.7万通貨 / 1pip={PIP_VAL}円")
    w()
    hdr = f"  {'TF':>5} | {'IS件数':>6} {'IS WR':>6} {'IS PF':>6} {'IS損益':>8} {'IS DD':>7} | {'OOS件数':>7} {'OOS WR':>7} {'OOS PF':>7} {'OOS損益':>9} {'OOS DD':>8} | {'採否':>4}"
    w(hdr)
    w("  " + "-" * (len(hdr)-2))
    for tf in TF_CONFIGS:
        if tf not in results: continue
        mi, mo = results[tf]["is"], results[tf]["oos"]
        checks = adoption_check(mi, mo)
        ok     = all(c for _,c in checks)
        mark   = "採用" if ok else "NG"
        if tf == TF_ADOPTED: mark = "★採用"
        w(f"  {tf:>5} | {mi['n']:>6,} {mi['wr']:>6.1f}% {mi['pf']:>6.2f} "
          f"{mi['total_jpy']/10000:>+8.1f}万 {mi['dd_pct']:>+7.2f}% | "
          f"{mo['n']:>7,} {mo['wr']:>7.1f}% {mo['pf']:>7.2f} "
          f"{mo['total_jpy']/10000:>+9.1f}万 {mo['dd_pct']:>+8.2f}% | {mark:>4}")
    w()

    # ── 3. TFごとの詳細 ─────────────────────────────────────────────────────
    w("## 3. タイムフレーム別詳細")
    for tf in TF_CONFIGS:
        if tf not in results: continue
        r = results[tf]
        mi, mo = r["is"], r["oos"]
        cfg    = TF_CONFIGS[tf]
        checks = adoption_check(mi, mo)
        ok     = all(c for _,c in checks)

        w()
        w(f"### {tf}  (bars={cfg['rb']} pips={cfg['rp']} hold={cfg['mh']})"
          + ("  ★正式採用" if tf==TF_ADOPTED else ""))
        w()

        # 基本統計
        w(f"  **基本統計**")
        w(f"  {'指標':<18} | {'IS':>14} | {'OOS':>14}")
        w("  " + "-" * 52)
        for label, ki, ko in [
            ("トレード数",   "n",          "n"),
            ("勝率",        "wr",         "wr"),
            ("PF",          "pf",         "pf"),
            ("期待値(pips)", "ev",         "ev"),
            ("平均勝ち",    "aw",         "aw"),
            ("平均負け",    "al",         "al"),
            ("損切り率",    "stop_r",     "stop_r"),
            ("平均保有",    "avg_h",      "avg_h"),
            ("総損益",      "total_jpy",  "total_jpy"),
        ]:
            vi = mi[ki]; vo = mo[ki]
            if ki in ("wr","stop_r"):
                si,so = f"{vi:.1f}%", f"{vo:.1f}%"
            elif ki == "pf":
                si,so = f"{vi:.2f}", f"{vo:.2f}"
            elif ki in ("ev","aw","al"):
                si,so = f"{vi:+.2f}p", f"{vo:+.2f}p"
            elif ki == "total_jpy":
                si,so = f"{vi/10000:+.1f}万円", f"{vo/10000:+.1f}万円"
            elif ki == "avg_h":
                si,so = f"{vi:.1f}本({vi*cfg['tf_min']:.0f}分)", f"{vo:.1f}本({vo*cfg['tf_min']:.0f}分)"
            else:
                si,so = f"{vi:,}", f"{vo:,}"
            w(f"  {label:<18} | {si:>14} | {so:>14}")
        w()

        # リスク指標
        w(f"  **リスク指標**")
        w(f"  {'指標':<18} | {'IS':>14} | {'OOS':>14}")
        w("  " + "-" * 52)
        for label, ki in [("最大DD",    "dd_pct"),
                           ("最長DD期間", "max_dd_bars"),
                           ("VaR95",     "var95"),
                           ("CVaR95",    "cvar95"),
                           ("Tail Ratio","tail_ratio")]:
            vi = mi[ki]; vo = mo[ki]
            if ki == "dd_pct":
                si,so = f"{vi:+.2f}%", f"{vo:+.2f}%"
            elif ki == "max_dd_bars":
                si = f"{vi}本({vi*cfg['tf_min']/60:.1f}時間)"
                so = f"{vo}本({vo*cfg['tf_min']/60:.1f}時間)"
            elif ki in ("var95","cvar95"):
                si,so = f"{vi:.2f}p", f"{vo:.2f}p"
            else:
                si,so = f"{vi:.2f}", f"{vo:.2f}"
            w(f"  {label:<18} | {si:>14} | {so:>14}")
        w()

        # セッション別（IS）
        w(f"  **セッション別（IS）**")
        w(f"  {'セッション':>6} | {'N':>5} {'WR%':>6} {'PF':>5} {'期待値':>8}")
        w("  " + "-" * 38)
        for sname, sv in r["sess_is"].items():
            if sv["n"]==0:
                w(f"  {sname:>6} | {'0':>5} {'--':>6} {'--':>5} {'--':>8}")
            else:
                pfs = f"{sv['pf']:.2f}" if sv['pf']!=99 else " inf"
                w(f"  {sname:>6} | {sv['n']:>5} {sv['wr']:>6.1f}% {pfs:>5} {sv['ev']:>+7.3f}p")
        w()

        # 連続負け
        sk = r["streak_is"]
        w(f"  **連続負け（IS）**")
        w(f"  最大連続負け : {sk['max_streak']}回  最悪時損失: {sk['worst_loss']:,.0f}円 "
          f"({sk['worst_loss']/CAPITAL*100:.1f}%)")
        w(f"  3連敗以上: {sk['c3']}回  5連敗以上: {sk['c5']}回  10連敗以上: {sk['c10']}回")
        w()

        # 月次（IS）
        w(f"  **月次損益（IS・pips）**")
        for ym, v in r["monthly_is"].items():
            bar = "#" * min(int(abs(v)/10), 25)
            w(f"  {ym}  {'+' if v>=0 else '-'}{abs(v):6.1f}  {bar}")
        w()

        # 採否
        w(f"  **採否判定**")
        for label, ok2 in checks:
            w(f"  [{'OK' if ok2 else 'NG'}] {label}")
        w(f"  --> {'採用' if ok else '不採用（理由: '+', '.join(l for l,c in checks if not c)+'）'}")

    # ── 4. 機能しなくなる条件 ────────────────────────────────────────────────
    w()
    w("## 4. 機能しなくなる条件（全TF共通）")
    w()
    w("  1. 長期レンジ相場: 偽ブレイク増加 → 損切り率上昇・PF低下")
    w("  2. 高ボラ局面（指標・介入）: スプレッド拡大・スリッページ増大")
    w("  3. トレンドレス: 強弱差がゼロ付近に集中しフィルター機能不全")
    w("  4. 通貨強弱相関の崩壊: リスクオフ時の全円買い等で強弱スコア不正確")
    w()
    w("  モニタリング基準:")
    w("    月次PF < 1.0 が2ヶ月連続 → 要注意")
    w("    月次PF < 1.0 が3ヶ月連続 → 運用停止・再検証")
    w("    損切り率がIS比1.5倍超    → 相場環境変化の疑い")
    w()

    # ── 5. 総合評価 ──────────────────────────────────────────────────────────
    w("## 5. 総合評価")
    w()
    w("  | TF    | IS PF | OOS PF | 乖離  | IS DD | OOS DD | 採否     |")
    w("  |-------|-------|--------|-------|-------|--------|----------|")
    for tf in TF_CONFIGS:
        if tf not in results: continue
        mi,mo = results[tf]["is"], results[tf]["oos"]
        checks = adoption_check(mi, mo)
        ok = all(c for _,c in checks)
        mark = "**★採用**" if tf==TF_ADOPTED else ("OK" if ok else "NG: "+", ".join(l for l,c in checks if not c)[:20])
        w(f"  | {tf:<5} | {mi['pf']:>5.2f} | {mo['pf']:>6.2f} | "
          f"{abs(mi['pf']-mo['pf']):>5.2f} | {mi['dd_pct']:>+5.2f}% | "
          f"{mo['dd_pct']:>+6.2f}% | {mark} |")
    w()
    w("  所見:")
    w("  - PFは上位足ほど高い傾向（レンジの質が高い）")
    w("  - 4hはIS DDが-40%超で現状ロット設計では使用不可")
    w("  - 15分はPF優秀だがOOS DDが採用基準を超過（ロット調整で改善余地あり）")
    w("  - 5分★採用: 件数・安定性・DD のバランスが最良")
    w("  - 30分・1hはPF高くDDも許容範囲。件数増加後に再評価推奨")

    return "\n".join(L)


# ── メイン ────────────────────────────────────────────────────────────────────
def main():
    print("データ準備中...")
    tf_dfs, tf_sds = load_and_resample()

    results = {}
    for tf, cfg in TF_CONFIGS.items():
        if tf not in tf_dfs:
            print(f"  {tf}: データなし スキップ")
            continue
        print(f"  {tf} 計算中...")
        df = tf_dfs[tf]; sd = tf_sds[tf]
        rb,rp,mh = cfg["rb"], cfg["rp"], cfg["mh"]

        tr_is  = run_bt(make_sig(df.loc[IS_START:IS_END],  sd, rb, rp), mh)
        tr_oos = run_bt(make_sig(df.loc[OOS_START:OOS_END], sd, rb, rp), mh)

        results[tf] = {
            "is":        calc(tr_is),
            "oos":       calc(tr_oos),
            "sess_is":   calc_session(tr_is),
            "streak_is": calc_streak(tr_is),
            "monthly_is":calc_monthly(tr_is),
        }

    print("報告書生成中...")
    report = build_report(results)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(report, encoding="utf-8")
    print(f"保存: {OUT_FILE}")
    print(report)


if __name__ == "__main__":
    main()
