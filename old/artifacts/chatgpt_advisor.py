# -*- coding: utf-8 -*-
"""
ChatGPT 相談役モジュール

戦略・設計上の判断が必要な場面でGPT-4oに第二意見を求める。
Q&Aは .company/secretary/notes/ に自動保存する。

使い方:
    from chatgpt_advisor import ask

    answer = ask(
        question="セクター指数の構成方法として等加重平均と時価総額加重のどちらが適切か？",
        context="国内株式市場でセクター遅行株の追いつきを取る短期トレード戦略を構築中。",
    )
    print(answer)

注意:
    - APIキーはWindowsの資格情報マネージャーで管理。コードや設定ファイルには一切残らない。
    - 呼び出しのたびにOpenAIへの通信が発生する（従量課金）。
    - 回答は opinions/ フォルダにMarkdownで保存される。
"""

import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

NOTES_DIR = Path(__file__).parent / ".company" / "secretary" / "notes" / "opinions"
NOTES_DIR.mkdir(parents=True, exist_ok=True)

MODEL = "gpt-4o"

SYSTEM_PROMPT = """\
あなたはFX・株式トレードに精通した定量アナリスト兼ストラテジーコンサルタントです。
FxCompanyという新興トレーディング会社の戦略顧問として、
CEOの孫正義（AI）と創業者のMASAYAの意思決定を支援します。

回答の方針:
- 根拠を明示する（理論・実績・リスク）
- 賛否を明確に述べる（曖昧な回答は避ける）
- 実装上の注意点があれば必ず付記する
- 日本語で回答する
"""


def ask(
    question: str,
    context: str = "",
    save: bool = True,
    verbose: bool = True,
) -> str:
    """
    ChatGPT（GPT-4o）に質問して回答を返す。

    Args:
        question: 質問内容
        context:  背景情報（プロジェクト文脈など）
        save:     Q&Aをnotesに保存するか
        verbose:  コンソールに出力するか

    Returns:
        str: GPT-4oの回答
    """
    from setup_credentials import get_openai_api_key
    from openai import OpenAI

    client = OpenAI(api_key=get_openai_api_key())

    user_content = question
    if context:
        user_content = f"【背景】\n{context}\n\n【質問】\n{question}"

    if verbose:
        print(f"\n[ChatGPT 相談役] 質問中...")

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_content},
        ],
        temperature=0.3,
    )

    answer = response.choices[0].message.content.strip()

    if verbose:
        print(f"\n{'─'*60}")
        print(f"[ChatGPT 相談役の意見]")
        print(f"{'─'*60}")
        print(answer)
        print(f"{'─'*60}\n")

    if save:
        _save_opinion(question, context, answer)

    return answer


def _save_opinion(question: str, context: str, answer: str) -> None:
    """Q&Aを日付付きMarkdownファイルに追記保存する"""
    today = datetime.today().strftime("%Y-%m-%d")
    path  = NOTES_DIR / f"{today}-opinions.md"

    timestamp = datetime.now().strftime("%H:%M:%S")

    block = f"""
## {timestamp} — {question[:40]}{"..." if len(question) > 40 else ""}

**質問**
{question}

{"**背景**" + chr(10) + context + chr(10) if context else ""}
**ChatGPTの回答**
{answer}

---
"""

    if path.exists():
        with path.open("a", encoding="utf-8") as f:
            f.write(block)
    else:
        header = f"# ChatGPT 相談役ログ — {today}\n\n---\n"
        path.write_text(header + block, encoding="utf-8")

    print(f"[保存] {path.relative_to(Path(__file__).parent)}")
