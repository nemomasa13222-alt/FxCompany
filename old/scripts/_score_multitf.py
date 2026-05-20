"""全タイムフレーム 総合スコアリング"""
import numpy as np
import pandas as pd

# ── 各TFの検証済み数値（IS/OOS） ─────────────────────────────────────────────
DATA = {
    "1min":  dict(is_pf=1.15, oos_pf=1.53, diff=0.38, is_dd=2.46, oos_dd=1.26,
                  is_tr=1.93, oos_tr=2.05, oos_wr=54.9, oos_n=71,
                  is_n=117,   adopted=False, ng_reason="IS PF低・PF乖離超"),
    "5min":  dict(is_pf=1.48, oos_pf=1.56, diff=0.08, is_dd=11.27, oos_dd=7.76,
                  is_tr=1.82, oos_tr=2.04, oos_wr=56.6, oos_n=1404,
                  is_n=3807,  adopted=True,  ng_reason=""),
    "15min": dict(is_pf=1.78, oos_pf=1.63, diff=0.15, is_dd=9.17, oos_dd=15.48,
                  is_tr=2.27, oos_tr=1.88, oos_wr=52.5, oos_n=1572,
                  is_n=3900,  adopted=False, ng_reason="OOS DD超過"),
    "30min": dict(is_pf=2.13, oos_pf=2.06, diff=0.07, is_dd=16.33, oos_dd=8.43,
                  is_tr=2.41, oos_tr=2.35, oos_wr=54.6, oos_n=568,
                  is_n=1485,  adopted=True,  ng_reason=""),
    "1h":    dict(is_pf=2.09, oos_pf=2.08, diff=0.01, is_dd=20.42, oos_dd=12.99,
                  is_tr=2.41, oos_tr=2.10, oos_wr=58.2, oos_n=581,
                  is_n=1408,  adopted=True,  ng_reason=""),
    "4h":    dict(is_pf=1.66, oos_pf=1.97, diff=0.31, is_dd=40.21, oos_dd=21.31,
                  is_tr=2.00, oos_tr=2.31, oos_wr=56.1, oos_n=189,
                  is_n=442,   adopted=False, ng_reason="IS DD過大・PF乖離"),
}

# ── スコア項目・重み定義 ───────────────────────────────────────────────────────
# 各項目を0〜100に正規化後、重みを掛けて合算
CRITERIA = [
    # (名称,              キー,       方向,  重み)
    ("OOS PF",           "oos_pf",   "hi",  0.25),
    ("IS/OOS 一致性",    "diff",     "lo",  0.15),  # 乖離小=良
    ("OOS DD耐性",       "oos_dd",   "lo",  0.15),  # DD小=良
    ("IS DD",            "is_dd",    "lo",  0.10),
    ("OOS Tail Ratio",   "oos_tr",   "hi",  0.15),  # 利益裾>損失裾
    ("OOS 勝率",         "oos_wr",   "hi",  0.08),
    ("統計有効性",       "oos_n",    "hi",  0.07),  # トレード数(対数)
    ("IS PF",            "is_pf",    "hi",  0.05),
]

tfs = list(DATA.keys())
vals = {k: np.array([DATA[tf][k] for tf in tfs]) for k in ["oos_pf","diff","oos_dd","is_dd",
                                                              "oos_tr","oos_wr","oos_n","is_pf"]}
# 統計有効性は対数スケール
vals["oos_n"] = np.log1p(vals["oos_n"])

def normalize(arr, direction):
    mn, mx = arr.min(), arr.max()
    if mx == mn:
        return np.full_like(arr, 50.0)
    if direction == "hi":
        return (arr - mn) / (mx - mn) * 100
    else:
        return (mx - arr) / (mx - mn) * 100

scores = np.zeros(len(tfs))
detail = {}

for name, key, direction, weight in CRITERIA:
    norm = normalize(vals[key], direction)
    detail[name] = norm
    scores += norm * weight

# ── 表示 ─────────────────────────────────────────────────────────────────────
print("=" * 78)
print("  USDJPY レンジブレイク戦略  全タイムフレーム 総合スコアリング")
print("  (IS:2022-2024 / OOS:2024-2025 / DMMFX 0.2pips / レバ10倍)")
print("=" * 78)

# スコア詳細
print(f"\n  {'項目':<18} {'重み':>4} | " + "  ".join(f"{tf:>6}" for tf in tfs))
print("  " + "-" * (24 + 10*len(tfs)))
for name, key, direction, weight in CRITERIA:
    row = f"  {name:<18} {int(weight*100):>3}% | "
    row += "  ".join(f"{detail[name][i]:>6.1f}" for i in range(len(tfs)))
    print(row)
print("  " + "-" * (24 + 10*len(tfs)))
print(f"  {'総合スコア':<18} {'':>4} | " + "  ".join(f"{s:>6.1f}" for s in scores))

# ランキング
rank = np.argsort(-scores)
print(f"\n{'=' * 78}")
print("  総合ランキング")
print(f"{'=' * 78}")
print(f"  {'順位':>4} {'TF':>5} | {'スコア':>7} {'OOS PF':>8} {'IS/OOS乖離':>10} "
      f"{'OOS DD':>8} {'TailR(OOS)':>10} {'OOS件数':>8} {'採否':>6}")
print("  " + "-" * 75)
for rank_i, i in enumerate(rank, 1):
    tf  = tfs[i]
    d   = DATA[tf]
    ok  = "★採用" if d["adopted"] else f"NG({d['ng_reason']})"
    bar_len = int(scores[i] / 5)
    bar = "█" * bar_len if bar_len > 0 else ""
    print(f"  #{rank_i:>2}  {tf:>5} | {scores[i]:>7.1f} {d['oos_pf']:>8.2f} "
          f"{d['diff']:>10.2f} {d['oos_dd']:>7.1f}% {d['oos_tr']:>10.2f} "
          f"{d['oos_n']:>8,} {ok}")

# ── 観点別ベスト ──────────────────────────────────────────────────────────────
print(f"\n{'=' * 78}")
print("  観点別ベスト")
print(f"{'=' * 78}")
metrics_best = [
    ("OOS PF 最高",      "oos_pf",  "hi"),
    ("IS/OOS一致性 最良", "diff",    "lo"),
    ("OOS DD 最小",      "oos_dd",  "lo"),
    ("IS DD 最小",       "is_dd",   "lo"),
    ("Tail Ratio 最高",  "oos_tr",  "hi"),
    ("トレード数 最多",   "oos_n",   "hi"),
]
for label, key, direction in metrics_best:
    raw = [DATA[tf][key] for tf in tfs]
    best_i = np.argmin(raw) if direction=="lo" else np.argmax(raw)
    print(f"  {label:<20}: {tfs[best_i]:>5}  ({raw[best_i]:.2f})")

# ── 採用可能TF の比較 ─────────────────────────────────────────────────────────
adopted = [(i, tfs[i]) for i in rank if DATA[tfs[i]]["adopted"]]
print(f"\n{'=' * 78}")
print("  採用可能TF 詳細比較")
print(f"{'=' * 78}")
print(f"  {'TF':>5} | {'スコア':>6} {'IS PF':>7} {'OOS PF':>7} {'乖離':>6} "
      f"{'IS損益':>9} {'OOS損益':>9} {'IS DD':>7} {'OOS DD':>7} {'TailR':>6}")
print("  " + "-" * 78)

# OOS損益（万円）= pips * 勝ち * 勝率 - ... → oos_pf と oos_n から近似
# 実際の損益はすでに計算済みの値を使う
oos_jpy = {
    "5min": 129.1, "30min": 212.8, "1h": 324.8
}
is_jpy = {
    "5min": 295.5, "30min": 529.4, "1h": 702.5
}

for i, tf in adopted:
    d = DATA[tf]
    print(f"  {tf:>5} | {scores[i]:>6.1f} {d['is_pf']:>7.2f} {d['oos_pf']:>7.2f} "
          f"{d['diff']:>6.2f} {is_jpy.get(tf,0):>+9.1f}万 {oos_jpy.get(tf,0):>+9.1f}万 "
          f"{d['is_dd']:>+7.2f}% {d['oos_dd']:>+7.2f}% {d['oos_tr']:>6.2f}")

print(f"\n  所見:")
print(f"  - 1h: PF最高・乖離最小（0.01）・Tail Ratio高水準。DDがやや大きい点のみ注意")
print(f"  - 30min: PF・Tail Ratio・OOS DDのバランス最良。採用3足の中で最安定")
print(f"  - 5min: 件数が圧倒的に多く統計信頼性No.1。DDも最小。安定運用の基盤")
print(f"  - 並走戦略: 5min(安定)+30min(高PF)+1h(高収益)の3足同時運用も検討余地あり")
print("=" * 78)
