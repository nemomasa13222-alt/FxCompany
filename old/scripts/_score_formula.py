"""
複合スコア計算
Score = EV × PF × √N × Omega × Tail × RecentFactor × CostTolerance
        ─────────────────────────────────────────────────────────────
                           1 + MaxDD

各項の定義:
  EV           : 期待値（pips/トレード）
  PF           : プロフィットファクター
  √N           : √トレード数（統計的信頼性の重み付け）
  Omega        : Ω比率（閾値0でのPFと等価、ここでは閾値をEVとして計算）
  Tail         : Tail Ratio = P95 / |P5|（右裾/左裾）
  RecentFactor : 直近20トレードのEV / 全体EV（直近の勢い）
  CostTolerance: EV / コスト（スプレッド）= コストに対するEVの余裕度
  MaxDD        : 最大ドローダウン（絶対値、pips）

コスト: DMMFX USDJPY 0.2pips
"""
import numpy as np
import pandas as pd
from pathlib import Path
from fx_market_classifier.features import currency_strength, log_returns
from fx_market_classifier.config import PAIRS

DATA_DIR    = Path("data/dukascopy")
PIP         = 0.01
ENTRY_COST  = 0.2   # pips
SW          = 20
IS_START    = "2022-01-01"; IS_END    = "2024-01-01"
OOS_START   = "2024-01-01"; OOS_END   = "2025-01-01"
RECENT_N    = 20    # RecentFactorの窓

TF_CONFIGS = {
    "5min":  dict(rule="5min",  rb=12, rp=10, mh=5),
    "30min": dict(rule="30min", rb=6,  rp=15, mh=3),
    "1h":    dict(rule="1h",    rb=4,  rp=25, mh=2),
}


# ── データ ────────────────────────────────────────────────────────────────────
dfs5 = {p: pd.read_parquet(DATA_DIR/f"{p}_5min.parquet")
        for p in PAIRS if (DATA_DIR/f"{p}_5min.parquet").exists()}
rd   = {p: log_returns(df["Close"]) for p, df in dfs5.items()}
st   = currency_strength(rd)
sd5  = (st["USD"].rolling(SW).sum() - st["JPY"].rolling(SW).sum())
df5  = dfs5["USDJPY"]


def resample(rule):
    if rule == "5min":
        df = df5
    else:
        df = df5.resample(rule, label="left", closed="left").agg(
            Open=("Open","first"), High=("High","max"),
            Low=("Low","min"),   Close=("Close","last"), Volume=("Volume","sum")
        ).dropna(subset=["Open"])
    sd = sd5.resample(rule, label="left", closed="left").last().reindex(df.index)
    return df, sd


def make_sig(df, sd, rb, rp):
    c  = df["Close"]
    rh = c.shift(1).rolling(rb).max()
    rl = c.shift(1).rolling(rb).min()
    ir = (rh - rl) <= rp * PIP
    s  = sd.reindex(df.index)
    return pd.DataFrame({"c":c,"o":df["Open"],
                         "ls":ir&(c>rh)&(s>0),
                         "ss":ir&(c<rl)&(s<0),
                         "rm":(rh+rl)/2})


def run_bt(sig, mh) -> np.ndarray:
    c=sig["c"].values; o=sig["o"].values; rm=sig["rm"].values
    ls=sig["ls"].values; ss=sig["ss"].values; n=len(sig)
    pnls=[]; inT=False; d=0; ep=sp=0.0; eb=-1
    for i in range(1, n-1):
        if not inT:
            if ls[i-1]:   d=1;  ep=o[i]+ENTRY_COST*PIP; sp=rm[i-1]; eb=i; inT=True
            elif ss[i-1]: d=-1; ep=o[i]-ENTRY_COST*PIP; sp=rm[i-1]; eb=i; inT=True
        else:
            held=i-eb; unr=(c[i]-ep)*d/PIP; xp=None
            if d==1  and c[i]<=sp: xp=sp
            elif d==-1 and c[i]>=sp: xp=sp
            elif held>=mh and unr>0:
                if d==1  and c[i]<c[i-1]: xp=c[i]
                elif d==-1 and c[i]>c[i-1]: xp=c[i]
            if xp is not None:
                pnls.append((xp-ep)*d/PIP); inT=False; d=0
    return np.array(pnls)


# ── スコア計算 ────────────────────────────────────────────────────────────────

def compute_score(pnls: np.ndarray, cost_pips: float = ENTRY_COST,
                  recent_n: int = RECENT_N, label: str = "") -> dict:
    if len(pnls) < 10:
        return dict(score=0, ev=0, pf=0, n=len(pnls), omega=0,
                    tail=0, recent_factor=0, cost_tol=0, max_dd=0)

    p   = pnls
    w   = p[p > 0]; l = p[p <= 0]
    n   = len(p)

    # 1. EV（期待値）
    ev = p.mean()

    # 2. PF
    pf = w.sum() / abs(l.sum()) if len(l)>0 and l.sum()!=0 else 99.0

    # 3. √N
    sqrt_n = np.sqrt(n)

    # 4. Omega（閾値 = EV で計算。全体のEVを超える利益 vs EV未満の損失）
    threshold = max(ev, 0)  # 0 or EV（正の場合）
    gains  = np.sum(np.maximum(p - threshold, 0))
    losses = np.sum(np.maximum(threshold - p, 0))
    omega  = gains / losses if losses > 0 else 99.0

    # 5. Tail Ratio
    p95  = np.percentile(p, 95)
    p05  = np.percentile(p, 5)
    tail = abs(p95 / p05) if p05 != 0 else 99.0

    # 6. RecentFactor（直近RECENT_N トレードのEV / 全体EV）
    recent_ev = p[-recent_n:].mean() if n >= recent_n else p.mean()
    recent_factor = recent_ev / ev if ev > 0 else (0.5 if recent_ev >= 0 else 0.0)
    recent_factor = np.clip(recent_factor, 0.0, 3.0)  # 上限3倍

    # 7. CostTolerance（EVのコストに対する倍率）
    cost_tol = ev / cost_pips if cost_pips > 0 else 0.0
    cost_tol = max(cost_tol, 0.0)  # 負なら0

    # 8. MaxDD（絶対値pips）
    eq      = np.cumsum(p)
    peak    = np.maximum.accumulate(np.maximum(eq, 0))
    max_dd  = abs((eq - peak).min())   # pips（正値）

    # スコア計算
    if ev <= 0 or pf <= 1.0 or cost_tol <= 0:
        score = 0.0
    else:
        score = (ev * pf * sqrt_n * omega * tail * recent_factor * cost_tol) / (1 + max_dd)

    return dict(
        score=score, ev=ev, pf=pf, n=n,
        sqrt_n=sqrt_n, omega=omega, tail=tail,
        recent_factor=recent_factor, cost_tol=cost_tol, max_dd=max_dd,
    )


def rolling_score(pnls: np.ndarray, window: int = 30) -> np.ndarray:
    """各時点でwindow本のローリングスコアを計算"""
    scores = []
    for i in range(len(pnls)):
        start = max(0, i - window + 1)
        s = compute_score(pnls[start:i+1])
        scores.append(s["score"])
    return np.array(scores)


# ── メイン ────────────────────────────────────────────────────────────────────
print("=" * 70)
print("  複合スコア計算")
print(f"  Score = EV × PF × √N × Omega × Tail × RecentFactor × CostTol")
print(f"          ─────────────────────────────────────────────────────")
print(f"                          1 + MaxDD")
print("=" * 70)

all_scores = {}

for tf, cfg in TF_CONFIGS.items():
    df, sd = resample(cfg["rule"])

    for period, s, e in [("IS", IS_START, IS_END), ("OOS", OOS_START, OOS_END)]:
        pnls = run_bt(make_sig(df.loc[s:e], sd, cfg["rb"], cfg["rp"]), cfg["mh"])
        m    = compute_score(pnls)
        key  = f"{tf}_{period}"
        all_scores[key] = m

        if period == "IS":
            print(f"\n  [{tf} {period}]  N={m['n']:,}")
            print(f"    EV={m['ev']:+.3f}p  PF={m['pf']:.2f}  √N={m['sqrt_n']:.1f}")
            print(f"    Omega={m['omega']:.2f}  Tail={m['tail']:.2f}  "
                  f"RecentFactor={m['recent_factor']:.2f}  CostTol={m['cost_tol']:.2f}")
            print(f"    MaxDD={m['max_dd']:.1f}pips")
            print(f"    ─── Score(IS) = {m['score']:.3f} ───")


# ── IS/OOS スコア比較表 ───────────────────────────────────────────────────────
print(f"\n{'='*70}")
print("  IS / OOS スコア比較")
print(f"{'='*70}")
print(f"  {'TF':>5} | {'IS Score':>10} {'OOS Score':>10} | "
      f"{'IS EV':>7} {'OOS EV':>8} | {'IS PF':>7} {'OOS PF':>8}")
print("  " + "-"*65)

for tf in TF_CONFIGS:
    mi  = all_scores[f"{tf}_IS"]
    mo  = all_scores[f"{tf}_OOS"]

    # OOSのスコアも計算
    df, sd = resample(TF_CONFIGS[tf]["rule"])
    cfg    = TF_CONFIGS[tf]
    pnls_oos = run_bt(make_sig(df.loc[OOS_START:OOS_END], sd, cfg["rb"], cfg["rp"]), cfg["mh"])
    mo = compute_score(pnls_oos)

    print(f"  {tf:>5} | {mi['score']:>10.3f} {mo['score']:>10.3f} | "
          f"{mi['ev']:>+7.3f}p {mo['ev']:>+8.3f}p | "
          f"{mi['pf']:>7.2f} {mo['pf']:>8.2f}")


# ── スコアの正規化（PID制御用） ───────────────────────────────────────────────
print(f"\n{'='*70}")
print("  PID制御用 正規化スコア（IS基準で0〜100に変換）")
print(f"{'='*70}")

is_scores = {tf: all_scores[f"{tf}_IS"]["score"] for tf in TF_CONFIGS}
max_s = max(is_scores.values())
min_s = min(is_scores.values())

print(f"  IS スコア範囲: {min_s:.3f} 〜 {max_s:.3f}")
print()
print(f"  {'TF':>5} | {'Raw Score':>10} {'正規化(0-100)':>14} | PID目標設定例")
print("  " + "-"*60)
for tf in TF_CONFIGS:
    raw   = is_scores[tf]
    norm  = (raw - min_s) / (max_s - min_s) * 100 if max_s != min_s else 50
    level = "フルロット(1.0×)" if norm>=70 else ("標準(0.7×)" if norm>=40 else "縮小(0.3×)")
    print(f"  {tf:>5} | {raw:>10.3f} {norm:>14.1f} | → {level}")

print(f"""
  PID制御設計案:
    目標値（Setpoint）: 正規化スコア = 60
    誤差 = 60 - 現在の正規化スコア

    Kp = 0.01  → 誤差10ポイントでロット±10%変化
    Ki = 0.002 → 5週間の累積誤差が効いてくる
    Kd = 0.005 → スコア急落に先手を打つ

    ロット倍率 = clip(1.0 + PID出力, 0.0, 2.0)

    更新頻度: 30トレードごと or 毎週月曜
""")
print("="*70)
