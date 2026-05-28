import os
import sys


# =========================
# 仮想環境の自動切り替え
# =========================
# `python3 main.py` で起動しても、プロジェクト内の venv があれば
# discord.py が入っている venv のPythonで起動し直します。

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(BASE_DIR, "venv", "bin", "python")

if os.path.exists(VENV_PYTHON) and os.path.abspath(sys.executable) != VENV_PYTHON:
    os.execv(VENV_PYTHON, [VENV_PYTHON, *sys.argv])


from bot import create_client
from config import DISCORD_TOKEN


# =========================
# 起動ファイル
# =========================
# 通常はこのファイルは触らず、設定は config.py、
# コマンドは commands.py、UIは views.py を調整します。


if not DISCORD_TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN が設定されていません。config.py のコメントを確認してください。"
    )


client = create_client()
client.run(DISCORD_TOKEN)
