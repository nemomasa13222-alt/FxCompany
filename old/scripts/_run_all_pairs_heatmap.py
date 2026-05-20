# -*- coding: utf-8 -*-
"""
12通貨ペア 散布図 × ヒートマップ生成
────────────────────────────────────────────────────────────
散布図: ブレイクダウン発生時の |強弱差| vs ATR(14)  色=時間帯
ヒートマップ: 強弱差 × ATR  → 12本後の平均対数リターン（全4セッション）
対象: 全期間（2022-2024）ブレイクダウン発生バーのみ
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.patches as mpatches
from matplotlib.colors import TwoSlopeNorm
from pathlib import Path
import warnings; warnings.filterwarnings("ignore")

FONT_PATH = r"C:\Windows\Fonts\YuGothM.ttc"
try:
    fm.fontManager.addfont(FONT_PATH)
    plt.rcParams["font.family"] = fm.FontProperties(fname=FONT_PATH).get_name()
except Exception:
    pass

BASE     = Path(__file__).parent
DATA_DIR = BASE / "data" / "dukascopy"
OUT_DIR  = BASE / "docs" / "heatmap_analysis"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── 定数 ────────────────────────────────────────────────────
STRENGTH_WINDOW = 24
ATR_PERIOD      = 14
HORIZON         = 12      # 12本後リターン
N_BINS          = 5       # グリッドビン数
JST             = pd.Timedelta(hours=9)

SESSIONS = [
    ("東京\n09-15JST",  9, 15, "#f39c12"),
    ("欧州\n15-21JST", 15, 21, "#27ae60"),
    ("NY\n21-03JST",   21,  3, "#2980b9"),
    ("深夜\n03-09JST",  3,  9, "#8e44ad"),
]

PAIR_CURRENCIES = {
    "USDJPY":("USD","JPY"), "EURJPY":("EUR","JPY"),
    "GBPJPY":("GBP","JPY"), "AUDJPY":("AUD","JPY"),
    "NZDJPY":("NZD","JPY"), "CHFJPY":("CHF","JPY"),
    "GBPUSD":("GBP","USD"), "AUDUSD":("AUD","USD"),
    "NZDUSD":("NZD","USD"), "EURGBP":("EUR","GBP"),
    "EURAUD":("EUR","AUD"), "AUDNZD":("AUD","NZD"),
}
CURRENCIES = sorted({c for v in PAIR_CURRENCIES.values() for c in v})

# ── データ読込 ──────────────────────────────────────────────
print("データ読込中...")
dfs = {}
for pair in PAIR_CURRENCIES:
    f = DATA_DIR / f"{pair}_5min.parquet"
    if not f.exists(): continue
    df = pd.read_parquet(f)
    if df.index.tz is not None:
        df.index = df.index.tz_convert("UTC").tz_localize(None)
    dfs[pair] = df[["Open","High","Low","Close"]]

common_idx = dfs["USDJPY"].index
for p in dfs: common_idx = common_idx.intersection(dfs[p].index)
for p in dfs: dfs[p] = dfs[p].reindex(common_idx)
print(f"共通バー数: {len(common_idx):,}  ({common_idx[0].date()} 〜 {common_idx[-1].date()})")

# ── 通貨強弱スコア ──────────────────────────────────────────
print("通貨強弱算出中...")
pair_lr = {p: np.log(df["Close"]/df["Close"].shift(STRENGTH_WINDOW))
           for p,df in dfs.items()}
raw_str = {c: pd.Series(0.0, index=common_idx) for c in CURRENCIES}
cnt = {c: 0 for c in CURRENCIES}
for pair,(b,q) in PAIR_CURRENCIES.items():
    if pair not in pair_lr: continue
    raw_str[b] += pair_lr[pair]; raw_str[q] -= pair_lr[pair]
    cnt[b] += 1; cnt[q] += 1
for c in CURRENCIES:
    if cnt[c]: raw_str[c] /= cnt[c]
str_df = pd.DataFrame(raw_str)

# セッションラベル
jst_hour = (common_idx + JST).hour
def get_sess(h):
    for name,s,e,_ in SESSIONS:
        if s < e:
            if s <= h < e: return name
        else:
            if h >= s or h < e: return name
    return SESSIONS[-1][0]
sess_s = pd.Series([get_sess(h) for h in jst_hour], index=common_idx)

# ── ペア別ヒートマップ生成 ──────────────────────────────────
def make_pair_figure(pair, base_c, quote_c):
    df_p = dfs[pair]

    # ATR
    hi,lo,cl = df_p["High"],df_p["Low"],df_p["Close"].shift(1)
    tr = pd.concat([hi-lo,(hi-cl).abs(),(lo-cl).abs()],axis=1).max(axis=1)
    atr = tr.rolling(ATR_PERIOD).mean()

    # 絶対強弱差（|base - quote|）
    abs_diff = (str_df[base_c] - str_df[quote_c]).abs()

    # ブレイクダウン（現在足Low < 前足Low）
    breakdown = (df_p["Low"] < df_p["Low"].shift(1)) & abs_diff.notna() & atr.notna()

    # 12本後の対数リターン（次足Open基準）
    entry_price = df_p["Open"].shift(-1)
    future_ret  = np.log(df_p["Close"].shift(-HORIZON) / entry_price) * 100  # %

    # ブレイクダウン発生時のデータ
    bd_mask = breakdown.values
    bd_idx  = common_idx[bd_mask]
    X = abs_diff.values[bd_mask]    # 強弱差
    Y = atr.values[bd_mask]          # ATR
    R = future_ret.values[bd_mask]   # 12本後リターン%
    S = sess_s.values[bd_mask]       # セッション

    valid = ~(np.isnan(X)|np.isnan(Y)|np.isnan(R))
    X,Y,R,S = X[valid],Y[valid],R[valid],S[valid]

    # ── ビン設定（分位数ベース）──────────────────────────────
    x_edges = np.percentile(X, np.linspace(0,100,N_BINS+1))
    y_edges = np.percentile(Y, np.linspace(0,100,N_BINS+1))
    # 端の重複を除去
    x_edges = np.unique(x_edges); y_edges = np.unique(y_edges)
    nx = len(x_edges)-1; ny = len(y_edges)-1

    x_mids = [(x_edges[i]+x_edges[i+1])/2 for i in range(nx)]
    y_mids = [(y_edges[i]+y_edges[i+1])/2 for i in range(ny)]
    x_labels = [f"{x_edges[i]:.3f}\n〜\n{x_edges[i+1]:.3f}" for i in range(nx)]
    y_labels = [f"{y_edges[i]:.4f}\n〜\n{y_edges[i+1]:.4f}" for i in range(ny)]

    # ── 図レイアウト ─────────────────────────────────────────
    fig = plt.figure(figsize=(22, 14))
    fig.patch.set_facecolor("#f8f9fa")
    fig.suptitle(f"{pair}  （{base_c}/{quote_c}）\n"
                 f"散布図: ブレイクダウン時 |強弱差| vs ATR(14)  /  "
                 f"ヒートマップ: 強弱差 × ATR → {HORIZON}本後リターン（全期間）",
                 fontsize=13, fontweight="bold", y=0.99)

    gs = fig.add_gridspec(2, 6, hspace=0.45, wspace=0.35,
                          height_ratios=[1.2, 1])

    # ── 散布図 ───────────────────────────────────────────────
    ax_sc = fig.add_subplot(gs[0, :4])
    ax_sc.set_facecolor("#ffffff")

    sess_colors = {s[0]: s[3] for s in SESSIONS}
    for sname, _, _, color in SESSIONS:
        mask = (S == sname)
        if mask.sum() == 0: continue
        # サンプリング（多すぎる場合）
        idx_s = np.where(mask)[0]
        if len(idx_s) > 2000:
            idx_s = np.random.choice(idx_s, 2000, replace=False)
        ax_sc.scatter(X[idx_s], Y[idx_s], c=color, alpha=0.35, s=8,
                      linewidths=0, label=sname.replace("\n"," "))

    # 楕円（各セッションの95%信頼楕円）
    from matplotlib.patches import Ellipse
    for sname,_,_,color in SESSIONS:
        mask=(S==sname)
        if mask.sum()<30: continue
        xs,ys=X[mask],Y[mask]
        mx,my=np.mean(xs),np.mean(ys)
        sx,sy=np.std(xs)*2,np.std(ys)*2
        ell=Ellipse((mx,my),sx*2,sy*2,angle=0,fill=False,
                    edgecolor=color,lw=1.8,ls="--",alpha=0.7)
        ax_sc.add_patch(ell)
        ax_sc.text(mx,my+sy*0.9,sname.replace("\n"," "),
                   fontsize=8,ha="center",color=color,fontweight="bold")

    ax_sc.set_xlabel(f"|{base_c}強さ − {quote_c}強さ|  (絶対強弱差)", fontsize=9)
    ax_sc.set_ylabel("ATR(14)", fontsize=9)
    ax_sc.set_title("散布図: ブレイクダウン発生時の市場状態分布", fontsize=10, fontweight="bold")
    ax_sc.legend(fontsize=8, markerscale=3, framealpha=0.9)
    ax_sc.grid(alpha=0.2)
    ax_sc.set_xlim(left=0)

    # ── 凡例・解説パネル ──────────────────────────────────────
    ax_leg = fig.add_subplot(gs[0, 4:])
    ax_leg.axis("off")
    ax_leg.set_facecolor("#ffffff")
    tips = [
        ("右上","強弱差大 × ATR大","トレンド継続しやすい","順張り有利"),
        ("左上","強弱差小 × ATR大","行き過ぎ・戻りやすい","逆張り有利"),
        ("左下","強弱差小 × ATR小","静かでチャンス少ない","様子見"),
        ("右下","強弱差大 × ATR小","ブレイク直後","要注意"),
    ]
    ax_leg.text(0.05, 0.97, "見方のポイント", fontsize=10, fontweight="bold",
                va="top", transform=ax_leg.transAxes)
    for i,(pos,cond,char,strat) in enumerate(tips):
        y = 0.85 - i*0.2
        ax_leg.text(0.05,y,f"・{pos}（{cond}）",fontsize=8,
                    va="top",transform=ax_leg.transAxes,fontweight="bold")
        ax_leg.text(0.05,y-0.08,f"  → {char}  [{strat}]",fontsize=7.5,
                    va="top",transform=ax_leg.transAxes,color="#555555")

    ax_leg.text(0.05,0.05,f"n={len(X):,}件（全ブレイクダウン）",
                fontsize=8,va="bottom",transform=ax_leg.transAxes,color="#888888")

    # ── ヒートマップ（4セッション）────────────────────────────
    # リターンのスケール統一
    all_means = []
    heatmap_data = {}
    for sname,s,e,color in SESSIONS:
        mask=(S==sname)
        if mask.sum()<30:
            heatmap_data[sname]=None; continue
        Xs,Ys,Rs=X[mask],Y[mask],R[mask]
        grid=np.full((ny,nx),np.nan)
        for xi in range(nx):
            for yi in range(ny):
                sel=((Xs>=x_edges[xi])&(Xs<x_edges[xi+1])&
                     (Ys>=y_edges[yi])&(Ys<y_edges[yi+1]))
                if sel.sum()>=5:
                    grid[ny-1-yi,xi]=Rs[sel].mean()
        heatmap_data[sname]=grid
        vals=grid[~np.isnan(grid)]
        if len(vals): all_means.extend(vals.tolist())

    # カラースケール（対称）
    if all_means:
        vmax = max(abs(np.percentile(all_means,5)),abs(np.percentile(all_means,95)))
        vmax = max(vmax,0.001)
    else:
        vmax = 0.1
    norm = TwoSlopeNorm(vmin=-vmax, vcenter=0, vmax=vmax)

    for col,(sname,s,e,color) in enumerate(SESSIONS):
        ax_h = fig.add_subplot(gs[1, col+1 if col<3 else col])
        ax_h = fig.add_subplot(gs[1, col+1])

        ax_h.set_facecolor("#eeeeee")
        grid=heatmap_data.get(sname)

        if grid is None or np.all(np.isnan(grid)):
            ax_h.text(0.5,0.5,"データ不足",ha="center",va="center",
                      transform=ax_h.transAxes)
        else:
            im=ax_h.imshow(grid,cmap="RdBu_r",norm=norm,aspect="auto",
                           extent=[0,nx,0,ny],origin="lower")
            # セル内に数値
            for yi in range(ny):
                for xi in range(nx):
                    val=grid[ny-1-yi,xi]
                    if not np.isnan(val):
                        ax_h.text(xi+0.5,ny-1-yi+0.5,f"{val:+.3f}",
                                  ha="center",va="center",fontsize=7,
                                  color="white" if abs(val)>vmax*0.5 else "black")

        # サンプル数の注釈
        mask_s=(S==sname)
        ax_h.set_title(f"{sname.replace(chr(10),' ')}\nn={mask_s.sum():,}",
                        fontsize=9,fontweight="bold",color=color)
        ax_h.set_xticks(range(nx)); ax_h.set_xticklabels(
            [f"{x_edges[i]:.3f}" for i in range(nx)],fontsize=6.5,rotation=30)
        ax_h.set_yticks(range(ny)); ax_h.set_yticklabels(
            [f"{y_edges[ny-i]:.4f}" for i in range(ny)],fontsize=6.5)
        if col==0:
            ax_h.set_ylabel("ATR(14)\n高  ↑", fontsize=8)
        ax_h.set_xlabel(f"|{base_c}−{quote_c}| 強弱差\n小 → 大", fontsize=7.5)

    # ヒートマップ横軸に共通カラーバー
    ax_cb = fig.add_subplot(gs[1, 0])
    ax_cb.axis("off")
    sm = plt.cm.ScalarMappable(cmap="RdBu_r", norm=norm)
    sm.set_array([])
    cb = plt.colorbar(sm, ax=ax_cb, orientation="vertical", fraction=0.8, pad=0.05)
    cb.set_label(f"{HORIZON}本後\n対数リターン(%)\n赤=上昇傾向\n青=下落傾向",
                 fontsize=8, labelpad=5)
    ax_cb.text(0.5,-0.05,
               "※赤=価格上昇（逆張りロング有利）\n青=価格下落（順張りショート有利）",
               ha="center",va="top",transform=ax_cb.transAxes,
               fontsize=7,color="#555555")

    plt.savefig(OUT_DIR/f"{pair}_heatmap.png", dpi=130,
                bbox_inches="tight", facecolor="#f8f9fa")
    plt.close(fig)
    print(f"  {pair}: n={len(X):,} 保存完了")
    return len(X)

# ── 全ペア実行 ──────────────────────────────────────────────
print("\n全ペア 散布図+ヒートマップ生成中...")
summary = []
for pair,(base_c,quote_c) in PAIR_CURRENCIES.items():
    if pair not in dfs: continue
    n = make_pair_figure(pair, base_c, quote_c)
    summary.append({"pair":pair,"base":base_c,"quote":quote_c,"n_breakdowns":n})

# ── サマリーグリッド（全12ペアのヒートマップ一覧） ──────────
print("\nサマリーグリッド生成中...")
pairs_list = [p for p in PAIR_CURRENCIES if p in dfs]
n_pairs = len(pairs_list)
n_cols = 4; n_rows = (n_pairs+n_cols-1)//n_cols

for sess_idx,(sname,s,e,color) in enumerate(SESSIONS):
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(24, n_rows*5))
    fig.patch.set_facecolor("#f8f9fa")
    fig.suptitle(f"全12ペア ヒートマップ一覧  ─  {sname.replace(chr(10),' ')}\n"
                 f"（強弱差 × ATR → {HORIZON}本後対数リターン%  /  赤=上昇 青=下落）",
                 fontsize=14, fontweight="bold", y=1.01)

    for i,pair in enumerate(pairs_list):
        base_c,quote_c = PAIR_CURRENCIES[pair]
        ax = axes[i//n_cols][i%n_cols]
        ax.set_facecolor("#dddddd")

        df_p = dfs[pair]
        hi,lo,cl = df_p["High"],df_p["Low"],df_p["Close"].shift(1)
        tr = pd.concat([hi-lo,(hi-cl).abs(),(lo-cl).abs()],axis=1).max(axis=1)
        atr = tr.rolling(ATR_PERIOD).mean()
        abs_diff = (str_df[base_c] - str_df[quote_c]).abs()
        breakdown = (df_p["Low"]<df_p["Low"].shift(1)) & abs_diff.notna() & atr.notna()
        entry_price = df_p["Open"].shift(-1)
        future_ret  = np.log(df_p["Close"].shift(-HORIZON)/entry_price)*100

        bd_mask=(breakdown & (sess_s==sname)).values
        X=abs_diff.values[bd_mask]; Y=atr.values[bd_mask]; R=future_ret.values[bd_mask]
        valid=~(np.isnan(X)|np.isnan(Y)|np.isnan(R))
        X,Y,R=X[valid],Y[valid],R[valid]

        if len(X)<30:
            ax.text(0.5,0.5,"データ不足",ha="center",va="center",
                    transform=ax.transAxes,fontsize=10)
            ax.set_title(f"{pair}",fontsize=10,fontweight="bold")
            continue

        x_edges=np.percentile(X,np.linspace(0,100,N_BINS+1))
        y_edges=np.percentile(Y,np.linspace(0,100,N_BINS+1))
        x_edges=np.unique(x_edges); y_edges=np.unique(y_edges)
        nx=len(x_edges)-1; ny=len(y_edges)-1

        grid=np.full((ny,nx),np.nan)
        for xi in range(nx):
            for yi in range(ny):
                sel=((X>=x_edges[xi])&(X<x_edges[xi+1])&
                     (Y>=y_edges[yi])&(Y<y_edges[yi+1]))
                if sel.sum()>=5: grid[ny-1-yi,xi]=R[sel].mean()

        vmax=max(abs(np.nanpercentile(grid,5) if not np.all(np.isnan(grid)) else 0.1),
                 abs(np.nanpercentile(grid,95) if not np.all(np.isnan(grid)) else 0.1),0.001)
        norm=TwoSlopeNorm(vmin=-vmax,vcenter=0,vmax=vmax)
        im=ax.imshow(grid,cmap="RdBu_r",norm=norm,aspect="auto",
                     extent=[0,nx,0,ny],origin="lower")
        plt.colorbar(im,ax=ax,fraction=0.04,pad=0.02)

        for yi in range(ny):
            for xi in range(nx):
                val=grid[ny-1-yi,xi]
                if not np.isnan(val):
                    ax.text(xi+0.5,ny-1-yi+0.5,f"{val:+.2f}",
                            ha="center",va="center",fontsize=7,
                            color="white" if abs(val)>vmax*0.5 else "black")

        ax.set_title(f"{pair}  ({base_c}/{quote_c})  n={len(X):,}",
                     fontsize=9,fontweight="bold",color=color)
        ax.set_xticks(range(nx))
        ax.set_xticklabels([f"{x_edges[i]:.3f}" for i in range(nx)],fontsize=6.5,rotation=30)
        ax.set_yticks(range(ny))
        ax.set_yticklabels([f"{y_edges[ny-i]:.4f}" for i in range(ny)],fontsize=6.5)
        ax.set_xlabel("強弱差 小→大",fontsize=7.5)
        if i%n_cols==0: ax.set_ylabel("ATR 低→高",fontsize=7.5)

    # 空のaxを非表示
    for j in range(n_pairs, n_rows*n_cols):
        axes[j//n_cols][j%n_cols].axis("off")

    plt.tight_layout()
    sess_short = sname.replace("\n","_").replace(":","").replace("-","")
    plt.savefig(OUT_DIR/f"all_pairs_{sess_short}.png", dpi=120,
                bbox_inches="tight", facecolor="#f8f9fa")
    plt.close(fig)
    print(f"  サマリーグリッド保存: all_pairs_{sess_short}.png")

pd.DataFrame(summary).to_csv(OUT_DIR/"summary.csv", index=False, encoding="utf-8-sig")
print(f"\n保存先: {OUT_DIR}")
print("完了")
