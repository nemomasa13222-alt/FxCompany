"""
現実的なFXトレードコストモデル（国内証券基準）

コスト構造:
  スプレッド: エントリー時のみ（片道）← 国内FX業者の実態
  スリッページ: エントリー・エグジット両方（双方向）

国内FX業者（GMOクリック証券・SBI FXトレード等）の
代表スプレッドを使用。スワップポイントは日中決済を前提に無視。

単位: ポジション価値に対する % (小数)
"""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np


# ── ペアの価格帯（スプレッドのpip→%換算に使用） ──────────────────────────────

_PRICE_REF = {
    # JPY pairs: 1 pip = 0.01 JPY
    "USDJPY": 150.0, "EURJPY": 165.0, "GBPJPY": 190.0,
    "AUDJPY": 100.0, "NZDJPY": 90.0,  "CHFJPY": 168.0,
    # USD pairs: 1 pip = 0.0001 (in terms of quote ccy)
    "GBPUSD": 1.25,  "AUDUSD": 0.66,  "NZDUSD": 0.60,
    "EURGBP": 0.85,  "EURAUD": 1.70,  "AUDNZD": 1.05,
}

_JPY_PAIRS  = {"USDJPY","EURJPY","GBPJPY","AUDJPY","NZDJPY","CHFJPY"}
_USD_PAIRS  = {"GBPUSD","AUDUSD","NZDUSD","EURGBP","EURAUD","AUDNZD"}

def _pip_value(pair: str) -> float:
    """1 pip の価格単位。JPYペア=0.01、その他=0.0001"""
    return 0.01 if pair in _JPY_PAIRS else 0.0001

def _to_pct(pair: str, pips: float) -> float:
    """pips → ポジション価値に対する % (小数)"""
    pip_unit = _pip_value(pair)
    price    = _PRICE_REF.get(pair, 100.0)
    return (pips * pip_unit) / price


# ── コスト定義 ──────────────────────────────────────────────────────────────

@dataclass
class PairCostSpec:
    """
    1ペア分のコスト仕様。

    spread_pips   : ビッドアスクスプレッド（pips）
                    JPYペア: 銭単位（0.2銭 = 0.2）
                    USDペア: pips単位（0.5pips = 0.5）
    slippage_pips : スリッページ（pips）。片道分を指定。
    """
    spread_pips:   float
    slippage_pips: float = 0.3  # デフォルト: 0.3 pips 片道

    def entry_cost_pct(self, pair: str) -> float:
        """エントリー時コスト = スプレッド（片道）+ スリッページ"""
        return _to_pct(pair, self.spread_pips + self.slippage_pips)

    def exit_cost_pct(self, pair: str) -> float:
        """エグジット時コスト = スリッページのみ（スプレッドなし）"""
        return _to_pct(pair, self.slippage_pips)

    def total_cost_pct(self, pair: str) -> float:
        """往復合計コスト（参考）"""
        return self.entry_cost_pct(pair) + self.exit_cost_pct(pair)


# ── 国内証券 代表スプレッド ────────────────────────────────────────────────────
# 出典: GMOクリック証券・SBI FXトレード 2026年基準
# 通常時スプレッド。経済指標発表前後は変動する。

PAIR_COSTS: dict[str, PairCostSpec] = {
    # JPY クロス（単位: 銭 = 0.01円）
    "USDJPY": PairCostSpec(spread_pips=0.2, slippage_pips=0.2),  # 流動性最高
    "EURJPY": PairCostSpec(spread_pips=0.5, slippage_pips=0.3),
    "GBPJPY": PairCostSpec(spread_pips=1.0, slippage_pips=0.4),  # やや広め
    "AUDJPY": PairCostSpec(spread_pips=0.5, slippage_pips=0.3),
    "NZDJPY": PairCostSpec(spread_pips=0.7, slippage_pips=0.3),
    "CHFJPY": PairCostSpec(spread_pips=0.9, slippage_pips=0.4),
    # USD ペア（単位: pips = 0.0001）
    "GBPUSD": PairCostSpec(spread_pips=0.5, slippage_pips=0.3),
    "AUDUSD": PairCostSpec(spread_pips=0.4, slippage_pips=0.3),
    "NZDUSD": PairCostSpec(spread_pips=0.5, slippage_pips=0.3),
    # クロスペア
    "EURGBP": PairCostSpec(spread_pips=0.5, slippage_pips=0.4),
    "EURAUD": PairCostSpec(spread_pips=0.8, slippage_pips=0.4),
    "AUDNZD": PairCostSpec(spread_pips=0.7, slippage_pips=0.4),
}

# ── コスト一覧表（確認用） ────────────────────────────────────────────────────

def cost_table(position_ratio: float = 5.0) -> str:
    """
    各ペアのコストをポジション価値・資本に対する%で表示。

    position_ratio: ポジションサイズ倍率（risk_pct / entry_threshold）
    """
    lines = [
        f"{'ペア':<10}  {'spread':>8}  {'slip':>6}  "
        f"{'entry%pos':>10}  {'exit%pos':>9}  "
        f"{'entry%cap':>10}  {'exit%cap':>9}",
        "-" * 70,
    ]
    for pair, spec in PAIR_COSTS.items():
        e_pos = spec.entry_cost_pct(pair) * 100
        x_pos = spec.exit_cost_pct(pair)  * 100
        e_cap = e_pos * position_ratio
        x_cap = x_pos * position_ratio
        lines.append(
            f"{pair:<10}  {spec.spread_pips:>6.1f}pips  {spec.slippage_pips:>4.1f}pp  "
            f"{e_pos:>10.5f}%  {x_pos:>9.5f}%  "
            f"{e_cap:>10.5f}%  {x_cap:>9.5f}%"
        )
    return "\n".join(lines)


# ── LeadLagEngine 用コスト適用関数 ─────────────────────────────────────────

def apply_realistic_cost(
    price:    float,
    pair:     str,
    entry:    bool,
    spec:     PairCostSpec | None = None,
) -> float:
    """
    現実的コストを適用した実行価格を返す。

    entry=True  (エントリー): スプレッド（片道）+ スリッページ
    entry=False (エグジット): スリッページのみ

    LONG の場合はコスト分だけ高く買う（ask 相当）。
    SHORT の場合はコスト分だけ安く売る（bid 相当）。
    この関数では direction 引数を持たず、呼び出し元で符号を管理する。
    """
    if spec is None:
        spec = PAIR_COSTS.get(pair, PairCostSpec(spread_pips=0.5))

    cost_pct = spec.entry_cost_pct(pair) if entry else spec.exit_cost_pct(pair)
    return price * (1.0 + cost_pct)   # 呼び出し元で符号（+/-）を調整する
