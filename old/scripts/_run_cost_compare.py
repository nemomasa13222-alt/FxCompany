"""
コスト3パターン比較:
  A. コストなし (参照)
  B. 現実コスト（片道スプレッド＋スリッページ）← 今回の新モデル
  C. 旧モデル（固定0.02%往復）
"""
import sys, math, itertools
sys.path.insert(0, '.')
import pandas as pd
from fx_market_classifier.data_fetcher import fetch_ohlcv
from fx_market_classifier.lead_lag import LeadLagConfig, LeadLagEngine
from fx_market_classifier.pair_costs import cost_table

LOG = open("cost_compare_log.txt", "w", encoding="utf-8")
def log(m=""): print(m, flush=True); LOG.write(m+"\n"); LOG.flush()

WINDOW_GRID    = [3, 6, 12, 24]
THRESHOLD_GRID = [0.0005, 0.001, 0.0015, 0.002, 0.003]
EXIT_RATIO_GRID= [0.1, 0.2, 0.5, 0.8, 1.0]

def run_survey(price_data, label, cost_pct, use_realistic):
    rows = []
    combos = list(itertools.product(WINDOW_GRID, THRESHOLD_GRID, EXIT_RATIO_GRID))
    for w, thr, er in combos:
        cfg = LeadLagConfig(
            spread_window=w, entry_threshold=thr, exit_ratio=er,
            spread_cost_pct=cost_pct, use_case_a=False,
            use_realistic_cost=use_realistic,
        )
        eng = LeadLagEngine(price_data, cfg)
        eng.run()
        m = eng.metrics()
        if not m: continue
        rows.append({"window":w,"entry_thr":thr,"exit_ratio":er,
                     "trades":m["trades"],"win_rate":m["win_rate"],
                     "pf":m["pf"],"total_pnl":m["total_pnl"],
                     "propagation_rate":m["propagation_rate"]})
    df = pd.DataFrame(rows).sort_values("pf", ascending=False).reset_index(drop=True)
    df["cost_model"] = label
    return df

try:
    log("=== コスト3パターン比較 ===\n")
    log(cost_table(5.0))
    log()

    log("データ取得中...")
    price_data = fetch_ohlcv(lookback_days=50)
    log(f"{len(price_data)}ペア\n")

    log("A) コストなし...")
    df_a = run_survey(price_data, "No cost",         0.0,  False)
    log(f"   完了 最良PF={df_a.iloc[0]['pf']:.2f}")

    log("B) 現実コスト（片道スプレッド＋スリッページ）...")
    df_b = run_survey(price_data, "Realistic",       0.0,  True)
    log(f"   完了 最良PF={df_b.iloc[0]['pf']:.2f}")

    log("C) 旧モデル（0.02%固定往復）...")
    df_c = run_survey(price_data, "Old (0.02% fixed)", 0.02, False)
    log(f"   完了 最良PF={df_c.iloc[0]['pf']:.2f}")

    # 比較まとめ
    log("\n=== 最良パラメータ比較（各モデルTop1） ===")
    log(f"{'モデル':<28}  {'w':>4}  {'entry':>8}  {'er':>5}  {'T':>5}  {'PF':>6}  {'PnL%':>8}  {'prop%':>7}")
    log("-"*80)
    for df, label in [(df_a,"A: コストなし"),(df_b,"B: 現実コスト（新）"),(df_c,"C: 旧モデル")]:
        r = df.iloc[0]
        pf_s = f"{r['pf']:.2f}" if r['pf']<99 else "inf"
        log(f"{label:<28}  {int(r['window']):>4}  {r['entry_thr']:>8.4f}  "
            f"{r['exit_ratio']:>5.1f}  {int(r['trades']):>5}  {pf_s:>6}  "
            f"{r['total_pnl']:>8.2f}  {r['propagation_rate']*100:>7.1f}%")

    # 同一パラメータ（best from B）での3モデル比較
    best = df_b.iloc[0]
    log(f"\n=== 同一パラメータ比較（B最良: w={int(best['window'])} entry={best['entry_thr']:.4f} er={best['exit_ratio']:.1f}） ===")
    log(f"{'モデル':<28}  {'trades':>7}  {'win%':>6}  {'PF':>6}  {'PnL%':>8}")
    log("-"*60)
    for df, label in [(df_a,"A: コストなし"),(df_b,"B: 現実コスト（新）"),(df_c,"C: 旧モデル")]:
        sub = df[(df.window==best['window'])&(df.entry_thr==best['entry_thr'])&(df.exit_ratio==best['exit_ratio'])]
        if sub.empty: continue
        r = sub.iloc[0]
        pf_s = f"{r['pf']:.2f}" if r['pf']<99 else "inf"
        log(f"{label:<28}  {int(r['trades']):>7}  {r['win_rate']*100:>6.1f}  {pf_s:>6}  {r['total_pnl']:>8.2f}")

    # 全結果保存
    combined = pd.concat([df_a, df_b, df_c]).sort_values(["cost_model","pf"], ascending=[True, False])
    combined.to_csv("docs/lead_lag/cost_comparison.csv", index=False)
    log("\n保存: docs/lead_lag/cost_comparison.csv")

    # コスト削減効果
    a_best_pnl = df_a.iloc[0]['total_pnl']
    b_best_pnl = df_b.iloc[0]['total_pnl']
    c_best_pnl = df_c.iloc[0]['total_pnl']
    log(f"\n=== コスト削減効果（最良PnL比較） ===")
    log(f"コストなし  : {a_best_pnl:+.2f}% (理論上限)")
    log(f"現実コスト  : {b_best_pnl:+.2f}% (実現可能水準)")
    log(f"旧モデル    : {c_best_pnl:+.2f}%")
    log(f"コスト差    : 旧モデル - 現実 = {c_best_pnl - b_best_pnl:+.2f}%  (この分が過大評価されていたコスト)")

    log("\n=== 完了 ===")

except Exception as e:
    import traceback; log(f"\nERROR: {e}"); log(traceback.format_exc())
finally:
    LOG.close()
