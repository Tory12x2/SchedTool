import discord
from discord import app_commands

from auto_scheduler import auto_schedule_loop, send_missing_role_alert_once
from commands import setup_commands
from database import get_dates, get_participant_role_id, get_schedule_messages
from operational_logging import log_error, log_info, log_warning, timed_log
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
        log_info(
            "bot.ready",
            user=self.user,
            guilds=len(self.guilds),
            cached_members=sum(
                1 for guild in self.guilds for member in guild.members if not member.bot
            ),
        )
        if self.schedule_messages_refreshed:
            return

        self.schedule_messages_refreshed = True
        with timed_log("startup.sync_commands", guilds=len(self.guilds)):
            await self.sync_commands_to_guilds()
        with timed_log("startup.refresh_views"):
            await self.refresh_schedule_message_views()

    async def on_guild_join(self, guild):
        log_info("guild.joined", guild_id=guild.id, members=guild.member_count)
        await self.sync_commands_to_guild(guild)

    async def on_guild_role_delete(self, role):
        if get_participant_role_id(role.guild.id) != role.id:
            return
        try:
            await send_missing_role_alert_once(self, role.guild, role.id)
        except discord.DiscordException as error:
            log_error(
                "role_delete_alert.failed",
                error,
                guild_id=role.guild.id,
                role_id=role.id,
            )

    async def sync_commands_to_guilds(self):
        for guild in self.guilds:
            await self.sync_commands_to_guild(guild)

    async def sync_commands_to_guild(self, guild):
        try:
            guild_object = discord.Object(id=guild.id)
            self.tree.copy_global_to(guild=guild_object)
            synced = await self.tree.sync(guild=guild_object)
            log_info("commands.synced", guild_id=guild.id, command_count=len(synced))
        except discord.DiscordException as error:
            log_error("commands.sync_failed", error, guild_id=guild.id)

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
                log_warning(
                    "schedule_view.refresh_failed",
                    event_id=schedule_message["event_id"],
                    guild_id=schedule_message["guild_id"],
                    error_type=error.__class__.__name__,
                    error=str(error)[:300],
                )

        log_info("schedule_views.refreshed", count=refreshed_count)


def create_client():
    return ScheduleClient()
