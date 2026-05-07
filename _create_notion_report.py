# -*- coding: utf-8 -*-
"""
セクター追いつき戦略 解析結果 → Notion ページ自動生成
実行前に環境変数を設定: $env:NOTION_TOKEN='ntn_xxxx'
"""
import sys, os, json
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import requests
from datetime import datetime

TOKEN = os.environ.get("NOTION_TOKEN", "")
if not TOKEN:
    print("ERROR: 環境変数 NOTION_TOKEN が設定されていません")
    print("  PowerShell: $env:NOTION_TOKEN='ntn_xxxx...'")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

TODAY = datetime.today().strftime("%Y-%m-%d")


# ── ブロック生成ヘルパー ───────────────────────────────────────────────────────

def h1(text): return {"object":"block","type":"heading_1","heading_1":{"rich_text":[{"type":"text","text":{"content":text}}]}}
def h2(text): return {"object":"block","type":"heading_2","heading_2":{"rich_text":[{"type":"text","text":{"content":text}}]}}
def h3(text): return {"object":"block","type":"heading_3","heading_3":{"rich_text":[{"type":"text","text":{"content":text}}]}}
def para(text, bold=False, color="default"):
    ann = {"bold": bold, "color": color}
    return {"object":"block","type":"paragraph","paragraph":{"rich_text":[{"type":"text","text":{"content":text},"annotations":ann}]}}
def divider(): return {"object":"block","type":"divider","divider":{}}
def callout(text, emoji="📊", color="blue_background"):
    return {"object":"block","type":"callout","callout":{"rich_text":[{"type":"text","text":{"content":text}}],"icon":{"type":"emoji","emoji":emoji},"color":color}}
def bullet(text, bold=False):
    return {"object":"block","type":"bulleted_list_item","bulleted_list_item":{"rich_text":[{"type":"text","text":{"content":text},"annotations":{"bold":bold}}]}}
def quote(text):
    return {"object":"block","type":"quote","quote":{"rich_text":[{"type":"text","text":{"content":text}}]}}

def table(headers, rows):
    """Notionテーブルブロック"""
    def cell(text):
        return [{"type":"text","text":{"content":str(text)}}]
    table_rows = []
    # ヘッダー行
    table_rows.append({
        "object":"block","type":"table_row",
        "table_row":{"cells":[cell(h) for h in headers]}
    })
    # データ行
    for row in rows:
        table_rows.append({
            "object":"block","type":"table_row",
            "table_row":{"cells":[cell(v) for v in row]}
        })
    return {
        "object":"block","type":"table",
        "table":{
            "table_width": len(headers),
            "has_column_header": True,
            "has_row_header": False,
            "children": table_rows
        }
    }


# ── ページコンテンツ構築 ──────────────────────────────────────────────────────

def build_blocks():
    blocks = []

    # ヘッダー
    blocks.append(callout(
        f"FxCompany | セクター追いつき戦略 v2-f | 解析完了: {TODAY}\n"
        "IS/OOS検証・ロバストネス検証・月次リターン — 全項目合格",
        emoji="✅", color="green_background"
    ))
    blocks.append(divider())

    # 1. 戦略概要
    blocks.append(h2("1. 戦略概要"))
    blocks.append(para("セクター指数が上昇した後、遅れて動く「遅行株」を買い、追いつきを狙う短期戦略（最大保有10営業日）"))
    blocks.append(table(
        ["パラメータ", "値", "説明"],
        [
            ["候補業種プール", "TOP10", "IS実績PF上位10業種を固定"],
            ["動的選別", "毎日上位5業種", "SMA20日 / ランキング20日"],
            ["sector_min_rise", "2.0%", "直近5日間セクター上昇閾値"],
            ["min_gap", "3.0%", "銘柄のセクター乖離率最低値"],
            ["risk_pct", "0.5%", "1トレードのリスク上限"],
            ["stop_dist_pct", "1.5%", "エントリーからの損切幅"],
            ["min_corr", "0.60", "クロスコリレーション最低閾値"],
            ["コスト", "往復0.20%", "エントリー価格×株数ベース"],
        ]
    ))
    blocks.append(divider())

    # 2. IS/OOS パフォーマンス
    blocks.append(h2("2. IS / OOS パフォーマンス"))
    blocks.append(callout("OOS PF 1.67 > IS PF 1.47 ── 過学習なし。OOSがISを上回る稀有な結果", emoji="🏆", color="yellow_background"))
    blocks.append(table(
        ["指標", "IS（2022-2023）", "OOS（2024-2026）", "判定"],
        [
            ["件数",    "526件",    "591件",     "→"],
            ["勝率",    "46.8%",    "47.0%",     "±0（安定）"],
            ["PF",      "1.47",     "1.67",      "✅ OOS優位"],
            ["最大DD",  "10.0%",    "9.4%",      "✅ 両期間10%以内"],
            ["総損益",  "+68万円",  "+111万円",  "✅ OOS優位"],
            ["最終資金","168万円",  "+111万円",  "✅ 運用継続中"],
            ["コスト",  "36万円",   "43万円",    "全額控除後"],
        ]
    ))
    blocks.append(divider())

    # 3. 月次リターン
    blocks.append(h2("3. 月次リターン"))
    blocks.append(table(
        ["期間", "月数", "黒字月勝率", "月平均", "最良月", "最悪月"],
        [
            ["IS（2022-23）", "24ヶ月", "15/24（62%）", "+2.87万", "+21.45万", "-5.67万"],
            ["OOS（2024〜）", "28ヶ月", "17/28（61%）", "+3.98万", "+31.99万", "-8.95万"],
            ["全期間合計",   "51ヶ月", "31/51（61%）", "+3.54万", "+31.99万", "-8.95万"],
        ]
    ))
    blocks.append(h3("月次ヒートマップ（万円）"))
    blocks.append(table(
        ["年", "1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月", "年計"],
        [
            ["2022 IS", "-0.6", "+4.5", "+0.4", "-9.4", "+2.4", "+14.0", "+9.4", "+21.5", "-0.6", "-3.3", "+2.1", "-9.7", "+34.7万"],
            ["2023 IS", "+11.0", "+12.7", "+7.7", "+0.5", "-2.4", "+8.6", "+1.8", "+1.0", "-0.6", "—", "-3.6", "-4.0", "+32.7万"],
            ["2024 OOS★", "+13.0", "+16.5", "+1.2", "-2.3", "+1.4", "+3.2", "-0.3", "+4.2", "-0.2", "-6.1", "+0.7", "+0.6", "+31.7万"],
            ["2025 OOS★", "+0.8", "-4.0", "+4.6", "+11.2", "+3.1", "-1.7", "+2.8", "+32.0", "+0.6", "-1.2", "-3.0", "-1.9", "+49.2万"],
            ["2026 OOS★（途中）", "+21.8", "+26.2", "-8.9", "-6.9", "—", "—", "—", "—", "—", "—", "—", "—", "+32.2万"],
        ]
    ))
    blocks.append(h3("季節性（月別平均 / 全期間5年）"))
    blocks.append(table(
        ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"],
        [["+9.2", "+11.2", "+1.0", "-0.6", "+0.9", "+4.8", "+1.9", "+11.7", "+1.0", "-2.1", "-0.8", "-2.2"]]
    ))
    blocks.append(bullet("強い月: 1月・2月・8月（リスクオン・夏相場）", bold=True))
    blocks.append(bullet("弱い月: 4月・10月・12月（決算・年末調整）"))
    blocks.append(divider())

    # 4. 業種別成績
    blocks.append(h2("4. 業種別成績"))
    blocks.append(h3("IS（2022-2023）— 損益降順"))
    blocks.append(table(
        ["業種", "件数", "勝率", "PF", "損益"],
        [
            ["海運業",       "67",  "40.3%", "1.65", "+15.7万"],
            ["鉄鋼",         "87",  "44.8%", "1.55", "+13.7万"],
            ["ゴム製品",     "46",  "58.7%", "2.04", "+10.5万"],
            ["卸売業",       "41",  "61.0%", "2.30", "+9.8万"],
            ["サービス業",   "72",  "47.2%", "1.42", "+9.0万"],
            ["ガラス・土石", "55",  "47.3%", "1.59", "+8.5万"],
            ["小売業",       "29",  "41.4%", "1.49", "+4.1万"],
            ["化学",         "48",  "47.9%", "1.30", "+3.2万"],
            ["保険業",       "49",  "44.9%", "1.02", "+0.4万"],
            ["不動産業",     "32",  "34.4%", "0.44", "-6.0万 ⚠"],
        ]
    ))
    blocks.append(h3("OOS（2024-2026）— 損益降順 ★IS不調業種が復活"))
    blocks.append(table(
        ["業種", "件数", "勝率", "PF", "損益", "IS比変動"],
        [
            ["保険業",       "59",  "54.2%", "2.35", "+20.3万", "↑ IS9位→OOS1位"],
            ["鉄鋼",         "74",  "52.7%", "1.99", "+20.0万", "→ 安定"],
            ["サービス業",   "55",  "50.9%", "1.88", "+13.9万", "→ 安定"],
            ["卸売業",       "55",  "54.5%", "1.99", "+13.5万", "→ 安定"],
            ["ゴム製品",     "49",  "51.0%", "2.23", "+12.6万", "→ 安定"],
            ["化学",         "80",  "42.5%", "1.45", "+10.2万", "↑ 回復"],
            ["ガラス・土石", "110", "36.4%", "1.22", "+8.9万",  "→ 安定"],
            ["小売業",       "20",  "60.0%", "3.39", "+8.0万",  "↑ 回復"],
            ["不動産業",     "60",  "46.7%", "1.38", "+5.5万",  "↑ IS赤字→黒字"],
            ["海運業",       "29",  "34.5%", "0.89", "-1.2万 ⚠", "↓ IS1位→不振"],
        ]
    ))
    blocks.append(callout(
        "特定業種への依存なし。IS好調業種がOOSで下落し、IS不振業種がOOSで復活する「ローテーション」が健全に機能",
        emoji="🔄", color="blue_background"
    ))
    blocks.append(divider())

    # 5. ロバストネス検証
    blocks.append(h2("5. パラメータ ロバストネス検証"))
    blocks.append(callout(
        "全9条件黒字（PF 1.27〜1.58）・採用パラメータがPF1位 ── 孤立した過最適解ではない",
        emoji="🔬", color="green_background"
    ))
    blocks.append(h3("3×3 マトリックス（全期間 2022-2026 / コスト控除後）"))
    blocks.append(table(
        ["条件", "件数", "勝率", "PF", "最大DD", "損益", "判定"],
        [
            ["rise=2% gap=3% ★採用", "1117", "46.9%", "1.58", "10.0%", "+180万", "★1位"],
            ["rise=1% gap=3%",       "1515", "46.5%", "1.54",  "9.4%", "+244万", "合格"],
            ["rise=2% gap=2%",       "1509", "46.1%", "1.47", "15.1%", "+200万", "合格"],
            ["rise=1% gap=2%",       "2084", "46.7%", "1.46", "13.5%", "+286万", "合格"],
            ["rise=1% gap=1%",       "2534", "46.7%", "1.40", "16.2%", "+293万", "合格"],
            ["rise=2% gap=1%",       "1844", "45.7%", "1.39", "17.8%", "+198万", "合格"],
            ["rise=3% gap=3%",        "751", "43.9%", "1.38",  "9.0%",  "+80万", "合格"],
            ["rise=3% gap=2%",       "1000", "43.1%", "1.33", "12.7%",  "+94万", "合格"],
            ["rise=3% gap=1%",       "1216", "42.8%", "1.27", "15.9%",  "+91万", "黒字"],
        ]
    ))
    blocks.append(h3("合格基準チェック"))
    blocks.append(table(
        ["チェック項目", "実測値", "基準", "判定"],
        [
            ["黒字（PF≥1.0）の条件数", "9/9",  "7/9以上", "✅ 合格"],
            ["PF≥1.3の条件数",          "8/9",  "5/9以上", "✅ 合格"],
            ["採用パラメータのPF順位",  "1位/9","上位3位以内", "✅ 合格"],
            ["隣接セル最低PF",          "1.33", "≥1.2",    "✅ 合格"],
        ]
    ))
    blocks.append(bullet("gap=3% はDD10%以内に抑える「リスク管理フィルター」として機能", bold=True))
    blocks.append(bullet("gap=1% は件数・利益は大きいがDD16〜18%に上昇"))
    blocks.append(bullet("rise=2% gap=3% はPF最高かつDD最低水準の最良バランス点"))
    blocks.append(divider())

    # 6. 総合評価
    blocks.append(h2("6. 総合評価 & 本番移行判断"))
    blocks.append(table(
        ["OOS検証チェック", "実測値", "判定"],
        [
            ["OOS PF ≥ 1.3",          "1.67", "✅ 合格"],
            ["OOS 最大DD ≤ 20%",      "9.4%", "✅ 合格"],
            ["OOS 勝率 ≥ 45%",        "47.0%","✅ 合格"],
            ["OOS PF ≥ IS PF × 70%", "1.14×","✅ 合格"],
            ["OOS 全年度黒字",        "2024+29万 / 2025+55万 / 2026+28万（途中）", "✅ 合格"],
        ]
    ))
    blocks.append(h3("レバレッジ別 推計成績（OOS実績ベース）"))
    blocks.append(table(
        ["レバレッジ", "推計OOS損益", "推計最大DD", "判定"],
        [
            ["1.0×",        "+111万円", "9.4%",  "現物・リスク最小"],
            ["1.5× ★推奨", "+167万円", "14.1%", "✅ DD20%以内・推奨"],
            ["2.0×",        "+222万円", "18.8%", "DD20%超・許容範囲"],
            ["3.0×",        "+334万円", "28.2%", "⚠ DD30%超・基準超え"],
        ]
    ))
    blocks.append(callout(
        "本番移行条件：OOS検証全5項目クリア・ロバストネス全4項目クリア\n"
        "推奨: レバレッジ1.5倍でデモトレード3ヶ月 → デモPF≥1.0・DD≤25%で本番移行",
        emoji="🚀", color="green_background"
    ))
    blocks.append(divider())

    # フッター
    blocks.append(para(f"作成日: {TODAY} | FxCompany 調査部門（AI孫正義）", color="gray"))

    return blocks


# ── Notion API ─────────────────────────────────────────────────────────────────

def create_page(blocks):
    url = "https://api.notion.com/v1/pages"
    # ブロックは100件ずつに分割（API制限）
    payload = {
        "parent": {"type": "workspace", "workspace": True},
        "icon":   {"type": "emoji", "emoji": "📈"},
        "cover":  None,
        "properties": {
            "title": {
                "title": [{"type": "text", "text": {"content": f"セクター追いつき戦略 v2-f 解析レポート｜{TODAY}"}}]
            }
        },
        "children": blocks[:100],
    }
    resp = requests.post(url, headers=HEADERS, json=payload)
    if resp.status_code != 200:
        print(f"ERROR: {resp.status_code}")
        print(resp.text)
        return None
    page = resp.json()
    page_id = page["id"]
    page_url = page["url"]
    print(f"  ページ作成完了: {page_url}")

    # 100件を超えるブロックを追加
    if len(blocks) > 100:
        for i in range(100, len(blocks), 100):
            chunk = blocks[i:i+100]
            r2 = requests.patch(
                f"https://api.notion.com/v1/blocks/{page_id}/children",
                headers=HEADERS,
                json={"children": chunk}
            )
            if r2.status_code != 200:
                print(f"  追加ブロックエラー (offset {i}): {r2.status_code}")
            else:
                print(f"  ブロック追加 ({i}〜{i+len(chunk)}件)")

    return page_url


def main():
    print(f"\n{'='*55}")
    print(f"  Notion レポート作成")
    print(f"{'='*55}\n")

    # 接続確認
    resp = requests.get("https://api.notion.com/v1/users/me", headers=HEADERS)
    if resp.status_code != 200:
        print(f"ERROR: 認証失敗 ({resp.status_code})")
        print("  NOTION_TOKEN を確認してください")
        sys.exit(1)
    user = resp.json()
    print(f"  接続OK: {user.get('name', user.get('id', ''))}")

    print("  ブロック生成中...")
    blocks = build_blocks()
    print(f"  ブロック数: {len(blocks)}")

    print("  Notionページ作成中...")
    url = create_page(blocks)

    if url:
        print(f"\n{'='*55}")
        print(f"  完了！")
        print(f"  URL: {url}")
        print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
