import discord
from discord import app_commands

from auto_scheduler import auto_schedule_loop
from commands import setup_commands
from config import MY_GUILD


# =========================
# Bot本体
# =========================
# IntentsなどDiscord接続まわりの設定をまとめています。


class ScheduleClient(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True

        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        setup_commands(self)
        self.loop.create_task(auto_schedule_loop(self))
        synced = await self.tree.sync(guild=MY_GUILD)
        print(f"{len(synced)} 個のコマンドを同期しました")

    async def on_ready(self):
        print(f"ログイン成功: {self.user}")


def create_client():
    return ScheduleClient()
