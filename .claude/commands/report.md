# /report — 報告書生成スキル

「報告書」「レポート」「PDF」という言葉が出たら、下記リストから該当するものを実行する。
カレントディレクトリ: `C:\Users\MAI\OneDrive\デスクトップ\FxCompany`

---

## 📊 株式戦略（セクター追いつき）

| # | 呼び方の例 | コマンド | 出力内容 |
|---|-----------|---------|---------|
| 1 | IS報告書・成績レポート | `python japan_stocks/make_sector_report_pdf.py` | IS期間の業種別成績・エクイティカーブ |
| 2 | OOS開封・検証結果 | `python japan_stocks/open_sector_oos.py` | OOS期間のIS vs OOS比較 |
| 3 | 総括・相談役向け | `python japan_stocks/make_advisor_report_pdf.py` | IS/OOS比較＋レバレッジ試算（4ページ） |
| 4 | バージョン比較 | `python japan_stocks/make_v2_comparison_pdf.py` | v1〜v2-f 全バージョン対比 |
| 5 | ロジック照合 | `python japan_stocks/make_logic_verification_pdf.py` | 戦略の意図 ⇔ コード 完全照合（7ページ） |
| 6 | 戦略解説書 | `python japan_stocks/make_strategy_explanation_pdf.py` | ロジック・数式から説明（8ページ） |

---

## 💹 FX戦略（USD/JPY）

| # | 呼び方の例 | コマンド | 出力内容 |
|---|-----------|---------|---------|
| 7 | FXルール解説書 | `python backtest/make_slope_rules_pdf.py` | 20SMAスロープ戦略 エントリー・エグジット説明書 |
| 8 | FXバックテスト報告書 | `python backtest/make_usdjpy_report_pdf.py` | 全バージョン結果比較（v1〜v4） |

---

## 📈 ミネルヴィニ戦略

| # | 呼び方の例 | コマンド | 出力内容 |
|---|-----------|---------|---------|
| 9 | ミネルヴィニOOS | `python japan_stocks/open_oos.py` | v4 OOS開封結果 |

---

## ⚡ クイックリファレンス（コピペ用）

```bash
# 株式 IS報告書
python japan_stocks/make_sector_report_pdf.py

# 株式 相談役向け総括
python japan_stocks/make_advisor_report_pdf.py

# 株式 ロジック照合
python japan_stocks/make_logic_verification_pdf.py

# FX ルール解説書
python backtest/make_slope_rules_pdf.py
```

---

## 📐 PDF標準フォーマット（全報告書共通）

| 項目 | 設定値 |
|------|--------|
| フォント | 游ゴシック（YuGothM.ttc） |
| 余白 | 上下左右 14mm |
| 表紙 | ネイビー背景 `(15,30,70)`、白テキスト |
| セクションヘッダー | 青背景 `(30,90,170)`、白テキスト |
| テーブルヘッダー | ネイビー `(15,30,70)`、白テキスト |
| テーブル偶数行 | ライトブルー `(235,242,255)` |
| 強調 | ティール `(0,160,120)` |
| 警告 | アンバー `(200,140,0)` |
| エラー | レッド `(190,40,40)` |

### テーブル崩れ防止ルール（必須）

`cell()` + `multi_cell()` の混在は禁止。代わりに `_match_row()` / `_row3()` を使う：

```python
# NG（崩れる）
pdf.cell(幅A, 6, text1)
pdf.multi_cell(幅B, 6, text2)   # ← heightが可変になり崩れる

# OK（崩れない）— rect()で背景 → set_xy()で座標指定 → cell()のみ
x, y = pdf.get_x(), pdf.get_y()
pdf.rect(x, y, total_width, 14, "FD")      # 固定14px
pdf.set_xy(x, y); pdf.cell(幅A, 14, text1)
pdf.set_xy(x+幅A, y); pdf.cell(幅B, 14, text2)
pdf.set_xy(x, y + 14)
```

---

## 📁 スクリプトの場所

```
FxCompany/
├── japan_stocks/               株式戦略スクリプト群
│   ├── backtest_stocks.py      バックテストエンジン本体
│   ├── run_backtest.py         バックテスト実行（パラメータ変更はここ）
│   └── results/reports/        PDFの出力先
│
├── backtest/                   FX戦略スクリプト群
│   ├── usdjpy_slope_reversal.py
│   ├── MT4/Indicators/         MT4インジケーター (.mq4)
│   └── MT4/Experts/            MT4 EA (.mq4)
│
└── .claude/commands/report.md  ← このファイル
```
