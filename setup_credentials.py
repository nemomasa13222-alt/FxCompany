# -*- coding: utf-8 -*-
"""
認証情報セットアップスクリプト
【初回のみ実行】 python setup_credentials.py

資格情報は Windows 資格情報マネージャーに暗号化して保存されます。
ファイルに平文で残りません。
"""

import keyring
import getpass

SERVICE = "FxCompany"


def setup():
    print("=" * 50)
    print("  FxCompany 資格情報セットアップ")
    print("  ※ Windows資格情報マネージャーに暗号化保存されます")
    print("=" * 50)
    print()

    print("【J-Quants APIキー】")
    print("  取得方法: jpx-jquants.com にログイン → マイページ → APIキー発行")
    jquants_key = getpass.getpass("  APIキー（入力は非表示）: ").strip()
    keyring.set_password(SERVICE, "jquants_api_key", jquants_key)
    print("  ✅ J-Quants APIキー保存完了")
    print()

    print("【OpenAI APIキー】")
    print("  取得方法: platform.openai.com → API keys → Create new secret key")
    openai_key = getpass.getpass("  APIキー（入力は非表示）: ").strip()
    keyring.set_password(SERVICE, "openai_api_key", openai_key)
    print("  ✅ OpenAI APIキー保存完了")
    print()

    print("✅ すべての資格情報を保存しました。")
    print("   確認: Windowsの「資格情報マネージャー」→「Windows資格情報」→「FxCompany」")
    print()


def setup_openai_only():
    """OpenAI APIキーだけを登録・更新する"""
    print("=" * 50)
    print("  OpenAI APIキー 登録")
    print("=" * 50)
    key = getpass.getpass("  APIキー（入力は非表示）: ").strip()
    keyring.set_password(SERVICE, "openai_api_key", key)
    print("  ✅ 保存完了")


def get_jquants_api_key() -> str:
    """J-Quants APIキーを取得する（環境変数 → Windows資格情報 の順で試行）"""
    import os
    # クラウド/CI環境: 環境変数から取得（GitHub Actions Secrets 等）
    key = os.environ.get("JQUANTS_API_KEY")
    if key:
        return key
    # ローカル環境: Windows資格情報マネージャーから取得
    key = keyring.get_password(SERVICE, "jquants_api_key")
    if not key:
        raise RuntimeError(
            "J-Quants APIキーが見つかりません。\n"
            "ローカル: python setup_credentials.py を実行してAPIキーを登録\n"
            "クラウド: 環境変数 JQUANTS_API_KEY を設定してください"
        )
    return key


def get_openai_api_key() -> str:
    """保存済みのOpenAI APIキーを取得する"""
    key = keyring.get_password(SERVICE, "openai_api_key")
    if not key:
        raise RuntimeError(
            "OpenAI APIキーが見つかりません。\n"
            "先に「python setup_credentials.py」を実行してAPIキーを登録してください。"
        )
    return key


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "openai":
        setup_openai_only()
    else:
        setup()
