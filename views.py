import discord
from datetime import datetime
from zoneinfo import ZoneInfo

from config import STATUS_LABELS, STATUS_ORDER
from database import (
    get_dates,
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


def is_event_closed(event_id):
    settings = get_event_settings(event_id)
    if not settings:
        return False
    if settings["closed"]:
        return True

    deadline_at = datetime.strptime(settings["deadline_at"], "%Y-%m-%d %H:%M")
    deadline_at = deadline_at.replace(tzinfo=TIMEZONE)
    return datetime.now(TIMEZONE) >= deadline_at


def split_dates(dates, size=5):
    return [dates[index : index + size] for index in range(0, len(dates), size)]


def format_date_range(dates):
    if not dates:
        return "日程なし"
    if len(dates) == 1:
        return dates[0]["label"]
    return f"{dates[0]['label']}〜{dates[-1]['label']}"


class OpenScheduleButton(discord.ui.Button):
    def __init__(self, event_id, dates):
        super().__init__(
            label=format_date_range(dates),
            style=discord.ButtonStyle.primary,
        )
        self.event_id = event_id
        self.dates = dates

    async def callback(self, interaction):
        if is_event_closed(self.event_id):
            await interaction.response.send_message(
                "この日程調整は締切済みです。",
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
            ),
            view=ScheduleView(
                self.event_id,
                self.dates,
                selected_user_id=interaction.user.id,
            ),
            ephemeral=True,
        )


class MonthlyTableButton(discord.ui.Button):
    def __init__(self, event_id, dates):
        super().__init__(
            label="月間日程表",
            style=discord.ButtonStyle.secondary,
        )
        self.event_id = event_id
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
    def __init__(self, event_id, dates=None, closed=False):
        super().__init__(timeout=None)
        if dates is None:
            dates = get_dates(event_id)

        for date_group in split_dates(dates):
            button = OpenScheduleButton(event_id, date_group)
            button.disabled = closed
            self.add_item(button)

        self.add_item(MonthlyTableButton(event_id, dates))


class ScheduleButton(discord.ui.Button):
    def __init__(self, event_id, date, status, view_dates, selected=False):
        super().__init__(
            label=STATUS_LABELS[status],
            style=self.get_style(status, selected),
            row=date["row"],
        )
        self.event_id = event_id
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
        if is_event_closed(self.event_id):
            await interaction.response.send_message(
                "この日程調整は締切済みです。",
                ephemeral=True,
            )
            return

        set_user_status(
            self.event_id,
            self.date["value"],
            interaction.user.id,
            self.status,
        )

        all_dates = get_dates(self.event_id)
        await interaction.response.edit_message(
            embed=create_personal_embed(
                interaction.guild,
                self.event_id,
                self.view_dates,
                interaction.user.id,
            ),
            view=ScheduleView(
                self.event_id,
                self.view_dates,
                selected_user_id=interaction.user.id,
            ),
        )
        await update_result_message(interaction, self.event_id, all_dates)


class ScheduleView(discord.ui.View):
    def __init__(self, event_id, dates, closed=False, selected_user_id=None):
        super().__init__(timeout=None)
        self.event_id = event_id
        self.dates = dates
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
                    )

                button = ScheduleButton(event_id, row_date, status, dates, selected)
                button.disabled = closed
                self.add_item(button)


async def update_result_message(interaction, event_id, dates):
    data = get_result_message(event_id)
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
