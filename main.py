from bot import create_client
from config import DISCORD_TOKEN
from operational_logging import log_info, setup_logging


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
setup_logging()
log_info("bot.starting")
client.run(DISCORD_TOKEN)
