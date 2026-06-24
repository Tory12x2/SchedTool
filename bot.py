import discord
from discord import app_commands

from auto_scheduler import auto_schedule_loop
from commands import setup_commands
from database import get_dates, get_schedule_messages
from views import OpenScheduleView


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
        self.schedule_messages_refreshed = False

    async def setup_hook(self):
        setup_commands(self)
        for schedule_message in get_schedule_messages():
            self.add_view(
                OpenScheduleView(
                    schedule_message["event_id"],
                    schedule_message["guild_id"],
                )
            )

        self.loop.create_task(auto_schedule_loop(self))

    async def on_ready(self):
        print(f"ログイン成功: {self.user}")
        if self.schedule_messages_refreshed:
            return

        self.schedule_messages_refreshed = True
        await self.sync_commands_to_guilds()
        await self.refresh_schedule_message_views()

    async def on_guild_join(self, guild):
        await self.sync_commands_to_guild(guild)

    async def sync_commands_to_guilds(self):
        for guild in self.guilds:
            await self.sync_commands_to_guild(guild)

    async def sync_commands_to_guild(self, guild):
        try:
            guild_object = discord.Object(id=guild.id)
            self.tree.copy_global_to(guild=guild_object)
            synced = await self.tree.sync(guild=guild_object)
            print(f"{guild.name}: {len(synced)} 個のコマンドを同期しました")
        except discord.DiscordException as error:
            print(f"{guild.name}: コマンド同期に失敗しました / {error}")

    async def refresh_schedule_message_views(self):
        refreshed_count = 0

        for schedule_message in get_schedule_messages():
            channel = self.get_channel(schedule_message["channel_id"])
            if not channel:
                continue

            try:
                message = await channel.fetch_message(schedule_message["message_id"])
                await message.edit(
                    view=OpenScheduleView(
                        schedule_message["event_id"],
                        schedule_message["guild_id"],
                        get_dates(
                            schedule_message["event_id"],
                            schedule_message["guild_id"],
                        ),
                    )
                )
                refreshed_count += 1
            except discord.DiscordException as error:
                print(
                    "日程調整ボタンの再登録に失敗しました: "
                    f"{schedule_message['event_id']} / {error}"
                )

        print(f"{refreshed_count} 件の日程調整ボタンを再登録しました")


def create_client():
    return ScheduleClient()
