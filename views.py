import asyncio
import hashlib
import discord
from datetime import datetime
from zoneinfo import ZoneInfo

from config import STATUS_LABELS, STATUS_ORDER
from database import (
    get_dates,
    get_event_group_settings,
    get_event_settings,
    get_result_message,
    get_users,
    set_user_status,
)
from embeds import create_monthly_table_embed, create_personal_embed, create_result_embed


# =========================
# ボタンUI
# =========================
# main2.py で試していた「日付 + ◎ / △ / ×」のUIです。
# ボタンの文字は config.py、押した時の動きはこのファイルで調整します。


TIMEZONE = ZoneInfo("Asia/Tokyo")


def build_custom_id(prefix, guild_id, event_id, *parts):
    event_hash = hashlib.sha256(f"{guild_id}:{event_id}".encode("utf-8")).hexdigest()[:16]
    suffix = ":".join(str(part) for part in parts)
    return f"{prefix}:{event_hash}:{suffix}" if suffix else f"{prefix}:{event_hash}"


def is_event_closed(event_id, guild_id):
    settings = get_event_settings(event_id, guild_id)
    if not settings:
        return False
    if settings["closed"]:
        return True

    deadline_at = datetime.strptime(settings["deadline_at"], "%Y-%m-%d %H:%M")
    deadline_at = deadline_at.replace(tzinfo=TIMEZONE)
    return datetime.now(TIMEZONE) >= deadline_at


def is_date_group_closed(event_id, group_index, guild_id):
    if is_event_closed(event_id, guild_id):
        return True

    settings = get_event_group_settings(event_id, group_index, guild_id)
    if not settings:
        return False
    if settings["closed"]:
        return True

    deadline_at = datetime.strptime(settings["deadline_at"], "%Y-%m-%d %H:%M")
    deadline_at = deadline_at.replace(tzinfo=TIMEZONE)
    return datetime.now(TIMEZONE) >= deadline_at


def get_date_group_deadline_text(event_id, group_index, guild_id):
    settings = get_event_group_settings(event_id, group_index, guild_id)
    if not settings:
        return None
    return settings["deadline_at"]


def split_dates(dates, size=5):
    return [dates[index : index + size] for index in range(0, len(dates), size)]


def format_date_range(dates):
    if not dates:
        return "日程なし"
    if len(dates) == 1:
        return dates[0]["label"]
    return f"{dates[0]['label']}〜{dates[-1]['label']}"


class OpenScheduleButton(discord.ui.Button):
    def __init__(self, event_id, guild_id, group_index, dates):
        super().__init__(
            label=format_date_range(dates),
            style=discord.ButtonStyle.primary,
            custom_id=build_custom_id("schedule_open", guild_id, event_id, group_index),
        )
        self.event_id = event_id
        self.guild_id = guild_id
        self.group_index = group_index
        self.dates = dates

    async def callback(self, interaction):
        if is_date_group_closed(self.event_id, self.group_index, self.guild_id):
            await interaction.response.send_message(
                "この日程範囲は締切済みです。",
                ephemeral=True,
            )
            return

        if not self.dates:
            await interaction.response.send_message(
                "このイベントは見つかりませんでした。",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=create_personal_embed(
                interaction.guild,
                self.event_id,
                self.dates,
                interaction.user.id,
                get_date_group_deadline_text(self.event_id, self.group_index, self.guild_id),
            ),
            view=ScheduleView(
                self.event_id,
                self.guild_id,
                self.dates,
                group_index=self.group_index,
                selected_user_id=interaction.user.id,
            ),
            ephemeral=True,
        )


class MonthlyTableButton(discord.ui.Button):
    def __init__(self, event_id, guild_id, dates):
        super().__init__(
            label="月間日程表",
            style=discord.ButtonStyle.secondary,
            custom_id=build_custom_id("schedule_monthly", guild_id, event_id),
        )
        self.event_id = event_id
        self.guild_id = guild_id
        self.dates = dates

    async def callback(self, interaction):
        await interaction.response.send_message(
            embed=create_monthly_table_embed(
                interaction.guild,
                self.event_id,
                self.dates,
            ),
            ephemeral=True,
        )


class OpenScheduleView(discord.ui.View):
    def __init__(self, event_id, guild_id, dates=None, closed=False):
        super().__init__(timeout=None)
        if dates is None:
            dates = get_dates(event_id, guild_id)

        for group_index, date_group in enumerate(split_dates(dates)):
            button = OpenScheduleButton(event_id, guild_id, group_index, date_group)
            button.disabled = closed or is_date_group_closed(event_id, group_index, guild_id)
            self.add_item(button)

        self.add_item(MonthlyTableButton(event_id, guild_id, dates))


class ScheduleButton(discord.ui.Button):
    def __init__(self, event_id, guild_id, group_index, date, status, view_dates, selected=False):
        super().__init__(
            label=STATUS_LABELS[status],
            style=self.get_style(status, selected),
            row=date["row"],
            custom_id=build_custom_id(
                "schedule_answer",
                guild_id,
                event_id,
                group_index,
                date["value"],
                status,
            ),
        )
        self.event_id = event_id
        self.guild_id = guild_id
        self.group_index = group_index
        self.date = date
        self.status = status
        self.view_dates = view_dates

    @staticmethod
    def get_style(status, selected):
        if not selected:
            return discord.ButtonStyle.secondary
        if status == "available":
            return discord.ButtonStyle.green
        if status == "maybe":
            return discord.ButtonStyle.primary
        return discord.ButtonStyle.red

    async def callback(self, interaction):
        if is_date_group_closed(self.event_id, self.group_index, self.guild_id):
            await interaction.response.send_message(
                "この日程範囲は締切済みです。",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        set_user_status(
            self.event_id,
            self.date["value"],
            interaction.user.id,
            self.status,
            self.guild_id,
        )

        all_dates = get_dates(self.event_id, self.guild_id)
        await interaction.edit_original_response(
            embed=create_personal_embed(
                interaction.guild,
                self.event_id,
                self.view_dates,
                interaction.user.id,
                get_date_group_deadline_text(self.event_id, self.group_index, self.guild_id),
            ),
            view=ScheduleView(
                self.event_id,
                self.guild_id,
                self.view_dates,
                group_index=self.group_index,
                selected_user_id=interaction.user.id,
            ),
        )
        asyncio.create_task(
            update_result_message(interaction, self.event_id, self.guild_id, all_dates)
        )


class ScheduleView(discord.ui.View):
    def __init__(
        self,
        event_id,
        guild_id,
        dates,
        group_index=0,
        closed=False,
        selected_user_id=None,
    ):
        super().__init__(timeout=None)
        self.event_id = event_id
        self.guild_id = guild_id
        self.dates = dates
        self.group_index = group_index
        self.selected_user_id = selected_user_id

        for index, date in enumerate(dates):
            row_date = {
                "label": date["label"],
                "value": date["value"],
                "row": index,
            }

            self.add_item(
                discord.ui.Button(
                    label=row_date["label"],
                    style=discord.ButtonStyle.secondary,
                    disabled=True,
                    row=index,
                )
            )

            for status in STATUS_ORDER:
                selected = False
                if selected_user_id is not None:
                    selected = selected_user_id in get_users(
                        event_id,
                        row_date["value"],
                        status,
                        guild_id,
                    )

                button = ScheduleButton(
                    event_id,
                    guild_id,
                    group_index,
                    row_date,
                    status,
                    dates,
                    selected,
                )
                button.disabled = closed or is_date_group_closed(event_id, group_index, guild_id)
                self.add_item(button)


async def update_result_message(interaction, event_id, guild_id, dates):
    data = get_result_message(event_id, guild_id)
    if not data:
        return

    channel_id, message_id = data
    channel = interaction.client.get_channel(channel_id)
    if not channel:
        return

    try:
        message = await channel.fetch_message(message_id)
        await message.edit(
            embed=create_result_embed(interaction.guild, event_id, dates),
            view=None,
        )
    except discord.DiscordException:
        return
