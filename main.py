from bot import create_client
from config import DISCORD_TOKEN


# =========================
# 起動ファイル
# =========================
# 通常はこのファイルは触らず、設定は config.py、
# コマンドは commands.py、UIは views.py を調整します。


if not DISCORD_TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN が設定されていません。READMEを確認して .env にBotトークンを設定してください。"
    )


client = create_client()
client.run(DISCORD_TOKEN)
