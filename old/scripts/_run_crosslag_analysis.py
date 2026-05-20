# -*- coding: utf-8 -*-
"""
JPYクロスペア間 Lead-Lag 解析（IS期間のみ）
  通貨強弱・疑似ペアを使わず、リアル価格同士の情報伝播を検証

実行: python _run_crosslag_analysis.py
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import warnings; warnings.filterwarnings("ignore")

from pathlib import Path
from itertools import permutations
import time
import numpy as np
import pandas as pd
from scipy import stats

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.colors as mcolors

FONT_PATH = r"C:\Windows\Fonts\YuGothM.ttc"
try:
    fm.fontManager.addfont(FONT_PATH)
    plt.rcParams["font.family"] = fm.FontProperties(fname=FONT_PATH).get_name()
except Exception:
    pass
_p8  = fm.FontProperties(fname=FONT_PATH, size=8)
_p9  = fm.FontProperties(fname=FONT_PATH, size=9)
_p10 = fm.FontProperties(fname=FONT_PATH, size=10)

ROOT     = Path(__file__).parent
DATA_DIR = ROOT / "data" / "dukascopy"
OUT_DIR  = ROOT / "docs" / "crosslag"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PAIRS    = ["USDJPY","EURJPY","GBPJPY","AUDJPY","NZDJPY","CHFJPY"]
IS_START = "2022-01-01"
IS_END   = "2023-12-31"

MAX_LAG      = 12
MIN_CORR_ABS = 0.003
COST_PCT     = 0.0002
SMA_WIN      = 20
ADX_WIN      = 14
BB_WIN       = 20


# ══════════════════════════════════════════════════════════════════════
# 1. データ読み込み
# ══════════════════════════════════════════════════════════════════════

def load_data() -> dict:
    data = {}
    for p in PAIRS:
        f = DATA_DIR / f"{p}_5min.parquet"
        if not f.exists():
            print(f"  {p}: ファイルなし"); continue
        df = pd.read_parquet(f)
        if df.index.tz is not None:
            df.index = df.index.tz_convert("UTC").tz_localize(None)
        data[p] = df[["Open","High","Low","Close"]].dropna()
        print(f"  {p}: {len(df):,}本  {df.index[0].date()} ~ {df.index[-1].date()}")
    return data


# ══════════════════════════════════════════════════════════════════════
# 2. 市場状態分類
# ══════════════════════════════════════════════════════════════════════

def adx_series(high, low, close, n=14):
    tr  = pd.concat([(high-low), (high-close.shift()).abs(),
                      (low-close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(span=n, adjust=False).mean()
    up  = high.diff(); dn = -low.diff()
    pdm = up.where((up > dn) & (up > 0), 0.0)
    ndm = dn.where((dn > up) & (dn > 0), 0.0)
    pdi = 100 * pdm.ewm(span=n, adjust=False).mean() / atr
    ndi = 100 * ndm.ewm(span=n, adjust=False).mean() / atr
    dx  = (100 * (pdi-ndi).abs() / (pdi+ndi).replace(0, np.nan)).fillna(0)
    return dx.ewm(span=n, adjust=False).mean()


def classify_market(df: pd.DataFrame) -> pd.Series:
    close  = df["Close"]
    sma    = close.rolling(SMA_WIN).mean()
    bb_mid = close.rolling(BB_WIN).mean()
    bb_std = close.rolling(BB_WIN).std()
    bb_up  = bb_mid + 2 * bb_std
    bb_lo  = bb_mid - 2 * bb_std
    adx_v  = adx_series(df["High"], df["Low"], close, ADX_WIN)

    state = pd.Series("NO_TRADE", index=df.index)
    mr    = (adx_v < 20) & (close >= bb_lo) & (close <= bb_up)
    trend = (adx_v > 25) & ((close > sma * 1.003) | (close < sma * 0.997))
    state[mr]    = "MR"
    state[trend] = "TREND"
    return state


# ══════════════════════════════════════════════════════════════════════
# 3. クロス相関計算
# ══════════════════════════════════════════════════════════════════════

def cross_correlations(ret_a: pd.Series, ret_b: pd.Series) -> pd.DataFrame:
    """corr(ret_a(t), ret_b(t+lag)) for lag=1..MAX_LAG"""
    idx = ret_a.index.intersection(ret_b.index)
    a = ret_a.loc[idx]; b = ret_b.loc[idx]
    n = len(a)
    rows = []
    for lag in range(1, MAX_LAG+1):
        if n - lag < 30: continue
        r, p = stats.pearsonr(a.iloc[:n-lag].values, b.iloc[lag:].values)
        rows.append({"lag": lag, "corr": r, "pval": p, "n": n-lag})
    return pd.DataFrame(rows).set_index("lag") if rows else pd.DataFrame()


# ══════════════════════════════════════════════════════════════════════
# 4. バックテスト
# ══════════════════════════════════════════════════════════════════════

def backtest(ret_leader, ret_follower, lag, state=None):
    idx = ret_leader.index.intersection(ret_follower.index)
    rl  = ret_leader.loc[idx]; rf = ret_follower.loc[idx]
    n   = len(rl)
    if n - lag < 20: return pd.DataFrame()

    # 相関の符号を考慮してシグナル方向を調整（負相関なら逆方向）
    corr_sign = np.sign(rl.iloc[:n-lag].corr(rf.iloc[lag:n]))
    signals  = corr_sign * np.sign(rl.iloc[:n-lag].values)
    mask     = signals != 0
    pnl_raw  = signals * rf.iloc[lag:n].values
    pnl_net  = pnl_raw - 2 * COST_PCT
    times    = rl.index[lag:n]

    df = pd.DataFrame({
        "time":    times[:len(pnl_net)],
        "signal":  signals,
        "pnl_raw": pnl_raw,
        "pnl_net": pnl_net,
        "valid":   mask,
    })[mask].drop(columns=["valid"]).reset_index(drop=True)

    if state is not None:
        st_idx     = rl.index[:n-lag]
        df["state"] = state.reindex(st_idx).values[:len(df)]

    return df


def metrics(df: pd.DataFrame) -> dict:
    if df.empty or len(df) < 5: return {}
    pnl   = df["pnl_net"]
    wins  = pnl[pnl > 0]; loses = pnl[pnl <= 0]
    pf    = wins.sum() / abs(loses.sum()) if loses.sum() != 0 else np.inf
    cum   = pnl.cumsum()
    dd    = float((cum - cum.cummax()).min())
    return {
        "trades":    len(df),
        "win_rate":  float((pnl > 0).mean()),
        "pf":        float(min(pf, 99.0)),
        "total_pnl": float(pnl.sum() * 100),
        "max_dd":    float(dd * 100),
        "ev_bp":     float(pnl.mean() * 10000),
    }


# ══════════════════════════════════════════════════════════════════════
# 5. ヒートマップ（matplotlib版）
# ══════════════════════════════════════════════════════════════════════

def draw_heatmap(matrix: pd.DataFrame, title: str, fmt: str,
                 cmap: str, vmin, vmax, center, out_path: Path):
    fig, ax = plt.subplots(figsize=(8, 6))
    fig.patch.set_facecolor("#FAFBFF"); ax.set_facecolor("#FAFBFF")

    norm = mcolors.TwoSlopeNorm(vmin=vmin, vcenter=center, vmax=vmax) \
           if center is not None else mcolors.Normalize(vmin=vmin, vmax=vmax)
    im = ax.imshow(matrix.values.astype(float), cmap=cmap, norm=norm, aspect="auto")

    ax.set_xticks(range(len(matrix.columns)))
    ax.set_yticks(range(len(matrix.index)))
    ax.set_xticklabels(matrix.columns, fontproperties=_p9, rotation=0)
    ax.set_yticklabels(matrix.index,   fontproperties=_p9)
    ax.set_xlabel("Leader（先行ペア）", fontproperties=_p9)
    ax.set_ylabel("Follower（追随ペア）", fontproperties=_p9)

    for i in range(len(matrix.index)):
        for j in range(len(matrix.columns)):
            v = matrix.values[i, j]
            if np.isnan(v): continue
            txt = f"{v:{fmt}}"
            ax.text(j, i, txt, ha="center", va="center",
                    fontproperties=_p8,
                    color="white" if abs(v) > (vmax-vmin)*0.6 else "#222")

    plt.colorbar(im, ax=ax, shrink=0.8)
    ax.set_title(f"{title}\n行: Follower / 列: Leader",
                 fontproperties=_p10, fontsize=10, pad=10)
    plt.tight_layout()
    plt.savefig(str(out_path), dpi=140, bbox_inches="tight", facecolor="#FAFBFF")
    plt.close(fig)
    print(f"  保存: {out_path.name}")


# ══════════════════════════════════════════════════════════════════════
# 6. その他チャート
# ══════════════════════════════════════════════════════════════════════

def make_ranking_chart(df_bt: pd.DataFrame, top_n: int = 15):
    if df_bt.empty: return
    top = df_bt.head(top_n)
    names = [f"{r.leader}→{r.follower} lag={r.lag}" for _, r in top.iterrows()]

    fig, axes = plt.subplots(1, 3, figsize=(16, 6))
    fig.patch.set_facecolor("#FAFBFF")
    fig.suptitle(f"IS 上位{top_n} Lead-Lag関係",
                 fontproperties=_p10, fontsize=11)

    for ax, col, color, title, fmt in zip(
        axes,
        ["pf",      "win_rate",  "ev_bp"],
        ["#2266AA", "#22AA66",   "#AA6622"],
        ["PF",      "勝率（%）",  "期待値（bp）"],
        [".3f",     ".1f",       ".2f"],
    ):
        ax.set_facecolor("#F5F8FF")
        vals = top[col].values.copy()
        if col == "win_rate": vals = vals * 100
        bars = ax.barh(range(len(names)), vals, color=color, alpha=0.8, height=0.7)
        ref = 1.0 if col == "pf" else (50 if col == "win_rate" else 0)
        ax.axvline(ref, color="#CC3333", lw=1.2, ls="--", alpha=0.7)
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(names, fontproperties=_p8)
        ax.set_title(title, fontproperties=_p9, fontsize=9)
        ax.grid(axis="x", color="#D8E0F0", lw=0.4)
        mx = vals.max() if len(vals) else 1
        for bar, v in zip(bars, vals):
            ax.text(v + abs(mx)*0.01, bar.get_y()+bar.get_height()/2,
                    f"{v:{fmt}}", va="center", fontproperties=_p8)

    plt.tight_layout()
    out = OUT_DIR / "ranking_IS.png"
    plt.savefig(str(out), dpi=140, bbox_inches="tight", facecolor="#FAFBFF")
    plt.close(fig)
    print(f"  保存: {out.name}")


def make_lag_heatmap(df_corr: pd.DataFrame, df_bt: pd.DataFrame):
    """ラグ別相関・ラグ・PFのヒートマップ"""
    best_corr = (df_corr.assign(abs_corr=df_corr["corr"].abs())
                 .sort_values("abs_corr", ascending=False)
                 .groupby(["leader","follower"]).first().reset_index())

    # 相関・ラグは df_corr から
    for col, title, fmt, cmap, vmin, vmax, center in [
        ("corr", "最良ラグでの相関係数", ".3f", "RdBu_r", -0.05, 0.05, 0.0),
        ("lag",  "最良ラグ（5分本数）",  ".0f", "YlOrRd", 1,     12,   None),
    ]:
        pivot = best_corr.pivot(index="follower", columns="leader", values=col)
        pivot = pivot.reindex(index=PAIRS, columns=PAIRS)
        draw_heatmap(pivot, f"IS — {title}", fmt, cmap, vmin, vmax, center,
                     OUT_DIR / f"heatmap_{col}_IS.png")

    # PF は df_bt から
    if not df_bt.empty:
        best_pf = (df_bt.sort_values("pf", ascending=False)
                   .groupby(["leader","follower"]).first().reset_index())
        pivot_pf = best_pf.pivot(index="follower", columns="leader", values="pf")
        pivot_pf = pivot_pf.reindex(index=PAIRS, columns=PAIRS)
        draw_heatmap(pivot_pf, "IS — PF（バックテスト・最良ラグ）",
                     ".2f", "RdYlGn", 0.8, 1.3, 1.0,
                     OUT_DIR / "heatmap_pf_IS.png")


def make_state_chart(df_st: pd.DataFrame):
    if df_st.empty: return
    avg = df_st.groupby("state")[["pf","win_rate","ev_bp"]].mean().reset_index()

    fig, axes = plt.subplots(1, 3, figsize=(14, 5))
    fig.patch.set_facecolor("#FAFBFF")
    fig.suptitle("IS — 市場状態別平均成績",
                 fontproperties=_p10, fontsize=11)

    c = {"TREND":"#2266AA","MR":"#CC3333","NO_TRADE":"#888888"}
    sts = ["TREND","MR","NO_TRADE"]
    for ax, col, ref, title, fmt in zip(
        axes,
        ["pf",   "win_rate", "ev_bp"],
        [1.0,    0.5,        0.0],
        ["PF",   "勝率",     "期待値（bp）"],
        [".3f",  ".3f",      ".3f"],
    ):
        ax.set_facecolor("#F5F8FF")
        vals = []
        for s in sts:
            row = avg[avg.state == s]
            vals.append(float(row[col].values[0]) if not row.empty else 0.0)
        if col == "win_rate": vals = [v*100 for v in vals]
        bars = ax.bar(sts, vals, color=[c[s] for s in sts], alpha=0.8, width=0.5)
        ax.axhline(ref if col != "win_rate" else ref*100,
                   color="#333", lw=1.2, ls="--", alpha=0.7)
        ax.set_title(title, fontproperties=_p9)
        ax.set_ylabel(title, fontproperties=_p8)
        ax.grid(axis="y", color="#D8E0F0", lw=0.4)
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x()+bar.get_width()/2, v+abs(max(vals,default=0))*0.01,
                    f"{v:{fmt}}", ha="center", fontproperties=_p8)
        for tl in ax.get_xticklabels(): tl.set_fontproperties(_p8)

    plt.tight_layout()
    out = OUT_DIR / "state_IS.png"
    plt.savefig(str(out), dpi=140, bbox_inches="tight", facecolor="#FAFBFF")
    plt.close(fig)
    print(f"  保存: {out.name}")


def make_corr_by_lag(df_corr: pd.DataFrame, top_pairs: list):
    """上位ペアのラグ別相関推移"""
    if not top_pairs: return
    fig, ax = plt.subplots(figsize=(12, 5))
    fig.patch.set_facecolor("#FAFBFF"); ax.set_facecolor("#F5F8FF")
    ax.grid(color="#D8E0F0", lw=0.4)

    colors = plt.cm.tab10(np.linspace(0, 1, len(top_pairs)))
    for (leader, follower), color in zip(top_pairs, colors):
        sub = df_corr[(df_corr.leader==leader) & (df_corr.follower==follower)]
        if sub.empty: continue
        ax.plot(sub["lag"], sub["corr"], marker="o", ms=5,
                label=f"{leader}→{follower}", color=color, lw=1.5)

    ax.axhline(0, color="#888", lw=0.8, ls="--")
    ax.axhline( MIN_CORR_ABS, color="#CC3333", lw=0.8, ls=":", alpha=0.6)
    ax.axhline(-MIN_CORR_ABS, color="#CC3333", lw=0.8, ls=":", alpha=0.6)
    ax.set_xlabel("ラグ（5分本数）", fontproperties=_p9)
    ax.set_ylabel("クロス相関係数", fontproperties=_p9)
    ax.set_title("IS — ラグ別クロス相関（上位ペア）",
                 fontproperties=_p10, fontsize=10)
    ax.legend(prop=_p8, loc="upper right", ncol=2)
    ax.set_xticks(range(1, MAX_LAG+1))

    plt.tight_layout()
    out = OUT_DIR / "corr_by_lag_IS.png"
    plt.savefig(str(out), dpi=140, bbox_inches="tight", facecolor="#FAFBFF")
    plt.close(fig)
    print(f"  保存: {out.name}")


# ══════════════════════════════════════════════════════════════════════
# メイン
# ══════════════════════════════════════════════════════════════════════

def main():
    t0 = time.time()
    print("=" * 55)
    print("JPYクロスペア Lead-Lag 解析（IS期間）")
    print(f"  ペア: {PAIRS}")
    print(f"  ラグ: 1〜{MAX_LAG}本（{5}〜{MAX_LAG*5}分）")
    print(f"  IS: {IS_START} 〜 {IS_END}")
    print("=" * 55)

    data = load_data()
    if len(data) < 2:
        print("ERROR: データ不足"); return

    # ── リターンと市場状態 ─────────────────────────────────────────
    returns, states = {}, {}
    for p, df in data.items():
        sub = df.loc[IS_START:IS_END]
        if len(sub) < 100: continue
        returns[p] = np.log(sub["Close"] / sub["Close"].shift(1)).dropna()
        states[p]  = classify_market(sub)

    combos = list(permutations(list(returns.keys()), 2))
    print(f"\nペア数: {len(returns)}  組み合わせ: {len(combos)}")

    # ── クロス相関 ─────────────────────────────────────────────────
    print("\n[1] クロス相関計算中...")
    corr_rows = []
    for leader, follower in combos:
        cc = cross_correlations(returns[leader], returns[follower])
        if cc.empty: continue
        for lag, row in cc.iterrows():
            corr_rows.append({"leader":leader,"follower":follower,
                               "lag":int(lag),"corr":row["corr"],
                               "pval":row["pval"],"n":row["n"]})
    df_corr = pd.DataFrame(corr_rows)

    df_sig = df_corr[
        (df_corr["corr"].abs() >= MIN_CORR_ABS) & (df_corr["pval"] < 0.01)
    ].copy()
    print(f"  全: {len(df_corr)}件  有意: {len(df_sig)}件")

    # ── バックテスト ───────────────────────────────────────────────
    print("\n[2] バックテスト実行中...")
    bt_rows, st_rows = [], []
    for _, row in df_sig.iterrows():
        leader, follower, lag = row["leader"], row["follower"], int(row["lag"])
        df_bt = backtest(returns[leader], returns[follower], lag,
                         state=states.get(follower))
        m = metrics(df_bt)
        if not m: continue
        bt_rows.append({"leader":leader,"follower":follower,
                         "lag":lag,"corr":row["corr"],**m})
        if "state" in df_bt.columns:
            for st in ["TREND","MR","NO_TRADE"]:
                ms = metrics(df_bt[df_bt["state"]==st])
                if ms:
                    st_rows.append({"leader":leader,"follower":follower,
                                    "lag":lag,"state":st,**ms})

    df_bt = pd.DataFrame(bt_rows).sort_values("pf",ascending=False).reset_index(drop=True) \
            if bt_rows else pd.DataFrame()
    df_st = pd.DataFrame(st_rows) if st_rows else pd.DataFrame()

    if not df_bt.empty:
        print(f"  結果: {len(df_bt)}件  PF>=1.0: {(df_bt.pf>=1.0).sum()}件"
              f"  PF>=1.2: {(df_bt.pf>=1.2).sum()}件")

    # ── チャート生成 ───────────────────────────────────────────────
    print("\n[3] チャート生成中...")
    make_lag_heatmap(df_corr, df_bt)
    make_ranking_chart(df_bt)
    make_state_chart(df_st)

    # ラグ別相関：上位10ペア
    if not df_bt.empty:
        top_pairs = [(r.leader, r.follower) for _, r in df_bt.head(10).iterrows()]
        make_corr_by_lag(df_corr, top_pairs)

    # ── CSV保存 ────────────────────────────────────────────────────
    df_corr.to_csv(OUT_DIR/"corr_IS.csv",      index=False, encoding="utf-8-sig")
    df_bt.to_csv(  OUT_DIR/"backtest_IS.csv",  index=False, encoding="utf-8-sig")
    df_st.to_csv(  OUT_DIR/"state_IS.csv",     index=False, encoding="utf-8-sig")

    elapsed = time.time() - t0
    print(f"\n完了: {elapsed:.0f}秒（{elapsed/60:.1f}分）")
    print(f"出力: {OUT_DIR}")

    if not df_bt.empty:
        print("\n=== IS 上位15件（PF順）===")
        cols = ["leader","follower","lag","corr","trades","win_rate","pf","total_pnl","max_dd","ev_bp"]
        print(df_bt[cols].head(15).to_string(index=False))


if __name__ == "__main__":
    main()
