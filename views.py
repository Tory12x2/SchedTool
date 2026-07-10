import asyncio
import hashlib
import discord
from datetime import datetime
from zoneinfo import ZoneInfo

from config import MAX_DAYS, STATUS_LABELS, STATUS_ORDER
from database import (
    clear_participant_role_id,
    get_dates,
    get_auto_schedule_settings,
    get_deadline_settings,
    get_event_group_settings,
    get_event_settings,
    get_notification_mention_enabled,
    get_reminder_settings,
    get_result_channel_id,
    get_schedule_settings,
    get_result_message,
    get_users,
    save_deadline_settings,
    save_notification_mention_enabled,
    save_result_channel_id,
    save_participant_role_id,
    save_reminder_settings,
    save_schedule_settings,
    set_user_status,
)
from embeds import (
    create_monthly_table_embed,
    create_personal_embed,
    create_result_embed,
    get_monthly_table_page_count,
)
from operational_logging import log_info, log_warning
from participants import (
    build_large_group_warning,
    can_member_answer,
    get_participant_members,
    get_participant_role,
    is_participant_role_missing,
)


# =========================
# ボタンUI
# =========================
# main2.py で試していた「日付 + ◎ / △ / ×」のUIです。
# ボタンの文字は config.py、押した時の動きはこのファイルで調整します。


TIMEZONE = ZoneInfo("Asia/Tokyo")


def create_setup_embed(guild):
    schedule_settings = get_schedule_settings(guild.id)
    result_channel_id = get_result_channel_id(guild.id)
    result_channel = guild.get_channel(result_channel_id) if result_channel_id else None
    reminder_settings = get_reminder_settings(guild.id)
    deadline_settings = get_deadline_settings(guild.id)
    auto_settings = get_auto_schedule_settings(guild.id)

    schedule_text = (
        f"{schedule_settings['event_name']} / {schedule_settings['days']}日"
        if schedule_settings
        else "未設定"
    )
    channel_text = result_channel.mention if result_channel else "未設定"
    role = get_participant_role(guild)
    if is_participant_role_missing(guild):
        role_text = "設定ロールが見つかりません"
        role_target_text = "再設定または解除してください"
    elif role:
        role_text = role.mention
        role_target_text = f"{role.mention} のメンバー"
    else:
        role_text = "なし"
        role_target_text = "Bot以外の全メンバー"

    embed = discord.Embed(
        title="SchedTool 設定",
        description="設定を変更すると、この画面で現在値を確認できます。",
        color=discord.Color.blue(),
    )
    embed.add_field(name="通知チャンネル", value=channel_text, inline=False)
    embed.add_field(name="イベント名・日数", value=schedule_text, inline=False)
    embed.add_field(
        name="回答締切",
        value=f"各日程の{deadline_settings['days_before']}日前{deadline_settings['hour']}時",
        inline=False,
    )
    embed.add_field(
        name="開催日通知",
        value=(
            f"{reminder_settings['days_before']}日前の{reminder_settings['hour']}時\n"
            f"コメント: {reminder_settings['comment'] or 'なし'}"
        ),
        inline=False,
    )
    embed.add_field(
        name="メンション設定",
        value="有効" if get_notification_mention_enabled(guild.id) else "無効",
        inline=False,
    )
    embed.add_field(
        name="自動作成",
        value=format_setup_auto_settings(guild, auto_settings),
        inline=False,
    )
    embed.add_field(
        name="参加予定者ロール（任意）",
        value=(
            f"現在: {role_text}\n"
            f"対象: {role_target_text}\n"
            f"対象人数: {len(get_participant_members(guild))}人"
        ),
        inline=False,
    )

    warning = build_large_group_warning(guild).strip()
    if warning:
        embed.add_field(name="注意", value=warning, inline=False)

    embed.set_footer(text="設定後、/schedule start:YYYY-MM-DD で日程調整を作成できます")
    return embed


def build_setup_status_text(guild):
    embed = create_setup_embed(guild)
    lines = [embed.title or "SchedTool 設定", embed.description or ""]
    for field in embed.fields:
        lines.append(f"{field.name}: {field.value}")
    return "\n\n".join(lines)


def format_setup_auto_settings(guild, settings):
    if not settings or not settings["active"]:
        return "停止中"

    channel = guild.get_channel(settings["channel_id"])
    channel_text = channel.mention if channel else "設定チャンネルが見つかりません"
    return (
        "動作中\n"
        f"次回開始日: {settings['next_start_date']}\n"
        f"投稿タイミング: 開始日の{settings['lead_days']}日前\n"
        f"投稿先: {channel_text}"
    )


class SetupSettingsModal(discord.ui.Modal, title="イベント名と日数を設定"):
    event_name = discord.ui.TextInput(
        label="イベント名",
        placeholder="例: 定例会",
        max_length=80,
    )
    days = discord.ui.TextInput(
        label=f"日数（1〜{MAX_DAYS}）",
        placeholder="例: 10",
        max_length=2,
    )

    def __init__(self, guild_id):
        super().__init__()
        settings = get_schedule_settings(guild_id)
        if settings:
            self.event_name.default = settings["event_name"]
            self.days.default = str(settings["days"])

    async def on_submit(self, interaction):
        event_name = str(self.event_name.value).strip()
        days_text = str(self.days.value).strip()

        if not event_name:
            await interaction.response.send_message(
                "イベント名を入力してください。",
                ephemeral=True,
            )
            return

        try:
            days = int(days_text)
        except ValueError:
            await interaction.response.send_message(
                "日数は数字で入力してください。",
                ephemeral=True,
            )
            return

        if days < 1 or days > MAX_DAYS:
            await interaction.response.send_message(
                f"日数は1〜{MAX_DAYS}日の範囲で指定してください。",
                ephemeral=True,
            )
            return

        save_schedule_settings(event_name, days, interaction.guild.id)
        await interaction.response.send_message(
            "イベント設定を保存しました。",
            embed=create_setup_embed(interaction.guild),
            view=SetupView(),
            ephemeral=True,
        )


class SetupDeadlineModal(discord.ui.Modal, title="回答締切を設定"):
    days_before = discord.ui.TextInput(
        label="何日前に締め切るか",
        placeholder="例: 1",
        default="1",
        max_length=2,
    )
    hour = discord.ui.TextInput(
        label="締切時刻（0〜23）",
        placeholder="例: 0",
        default="0",
        max_length=2,
    )

    def __init__(self, guild_id):
        super().__init__()
        settings = get_deadline_settings(guild_id)
        self.days_before.default = str(settings["days_before"])
        self.hour.default = str(settings["hour"])

    async def on_submit(self, interaction):
        try:
            days_before = int(str(self.days_before.value).strip())
            hour = int(str(self.hour.value).strip())
        except ValueError:
            await interaction.response.send_message(
                "締切日は数字で入力してください。",
                ephemeral=True,
            )
            return

        if days_before < 0 or days_before > 30:
            await interaction.response.send_message(
                "締切日は0〜30日前の範囲で指定してください。",
                ephemeral=True,
            )
            return

        if hour < 0 or hour > 23:
            await interaction.response.send_message(
                "締切時刻は0〜23時の範囲で指定してください。",
                ephemeral=True,
            )
            return

        save_deadline_settings(days_before, hour, interaction.guild.id)
        await interaction.response.send_message(
            "回答締切を保存しました。",
            embed=create_setup_embed(interaction.guild),
            view=SetupView(),
            ephemeral=True,
        )


class SetupReminderModal(discord.ui.Modal, title="開催日通知を設定"):
    days_before = discord.ui.TextInput(
        label="何日前に通知するか",
        placeholder="例: 1",
        default="1",
        max_length=2,
    )
    hour = discord.ui.TextInput(
        label="通知時刻（0〜23）",
        placeholder="例: 21",
        default="21",
        max_length=2,
    )
    comment = discord.ui.TextInput(
        label="通知に添えるコメント",
        required=False,
        max_length=500,
    )

    def __init__(self, guild_id):
        super().__init__()
        settings = get_reminder_settings(guild_id)
        self.days_before.default = str(settings["days_before"])
        self.hour.default = str(settings["hour"])
        self.comment.default = settings["comment"]

    async def on_submit(self, interaction):
        try:
            days_before = int(str(self.days_before.value).strip())
            hour = int(str(self.hour.value).strip())
        except ValueError:
            await interaction.response.send_message(
                "通知日は数字で入力してください。",
                ephemeral=True,
            )
            return

        if days_before < 0:
            await interaction.response.send_message(
                "何日前に通知するかは0以上で指定してください。",
                ephemeral=True,
            )
            return

        if hour < 0 or hour > 23:
            await interaction.response.send_message(
                "通知時刻は0〜23時の範囲で指定してください。",
                ephemeral=True,
            )
            return

        save_reminder_settings(
            days_before,
            hour,
            str(self.comment.value).strip(),
            interaction.guild.id,
        )
        await interaction.response.send_message(
            "開催日通知を保存しました。",
            embed=create_setup_embed(interaction.guild),
            view=SetupView(),
            ephemeral=True,
        )


class SetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=900)

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        placeholder="通知チャンネルを設定",
        channel_types=[discord.ChannelType.text],
        min_values=1,
        max_values=1,
        row=0,
    )
    async def set_notification_channel(self, interaction, select):
        channel = select.values[0]
        save_result_channel_id(channel.id, interaction.guild.id)
        await interaction.response.edit_message(
            embed=create_setup_embed(interaction.guild),
            view=SetupView(),
        )

    @discord.ui.button(
        label="イベント名と日数を設定",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def open_schedule_settings(self, interaction, button):
        await interaction.response.send_modal(SetupSettingsModal(interaction.guild.id))

    @discord.ui.button(
        label="回答締切を設定",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def open_deadline_settings(self, interaction, button):
        await interaction.response.send_modal(SetupDeadlineModal(interaction.guild.id))

    @discord.ui.button(
        label="開催日通知を設定",
        style=discord.ButtonStyle.secondary,
        row=2,
    )
    async def open_reminder_settings(self, interaction, button):
        await interaction.response.send_modal(SetupReminderModal(interaction.guild.id))

    @discord.ui.button(
        label="メンション設定を切り替え",
        style=discord.ButtonStyle.secondary,
        row=2,
    )
    async def toggle_notification_mention(self, interaction, button):
        enabled = not get_notification_mention_enabled(interaction.guild.id)
        save_notification_mention_enabled(enabled, interaction.guild.id)
        await interaction.response.edit_message(
            embed=create_setup_embed(interaction.guild),
            view=SetupView(),
        )

    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="参加予定者ロールを選択（任意）",
        min_values=1,
        max_values=1,
        row=3,
    )
    async def set_participant_role(self, interaction, select):
        role = select.values[0]
        save_participant_role_id(role.id, interaction.guild.id)
        await interaction.response.edit_message(
            embed=create_setup_embed(interaction.guild),
            view=SetupView(),
        )

    @discord.ui.button(
        label="参加予定者ロールを解除",
        style=discord.ButtonStyle.secondary,
        row=4,
    )
    async def clear_participant_role(self, interaction, button):
        clear_participant_role_id(interaction.guild.id)
        await interaction.response.edit_message(
            embed=create_setup_embed(interaction.guild),
            view=SetupView(),
        )


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
        if not can_member_answer(interaction.guild, interaction.user):
            message = (
                "設定されている参加予定者ロールが見つかりません。管理者へ確認してください。"
                if is_participant_role_missing(interaction.guild)
                else "この日程調整は、参加予定者ロールのメンバーだけが回答できます。"
            )
            await interaction.response.send_message(message, ephemeral=True)
            log_warning(
                "schedule.answer.denied",
                guild_id=interaction.guild.id,
                event_id=self.event_id,
                user_id=interaction.user.id,
                reason="role",
            )
            return

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


class MonthlyTablePaginationView(discord.ui.View):
    def __init__(self, guild, event_id, dates, page=0):
        super().__init__(timeout=900)
        self.guild = guild
        self.event_id = event_id
        self.dates = dates
        self.page_count = get_monthly_table_page_count(guild)
        self.page = max(0, min(page, self.page_count - 1))
        self.previous_page.disabled = self.page == 0
        self.next_page.disabled = self.page >= self.page_count - 1

    async def show_page(self, interaction, page):
        view = MonthlyTablePaginationView(
            self.guild,
            self.event_id,
            self.dates,
            page,
        )
        await interaction.response.edit_message(
            embed=create_monthly_table_embed(
                self.guild,
                self.event_id,
                self.dates,
                page,
            ),
            view=view,
        )

    @discord.ui.button(label="前へ", style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction, button):
        await self.show_page(interaction, self.page - 1)

    @discord.ui.button(label="次へ", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction, button):
        await self.show_page(interaction, self.page + 1)


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
            view=MonthlyTablePaginationView(
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
        if not can_member_answer(interaction.guild, interaction.user):
            message = (
                "設定されている参加予定者ロールが見つかりません。管理者へ確認してください。"
                if is_participant_role_missing(interaction.guild)
                else "この日程調整は、参加予定者ロールのメンバーだけが回答できます。"
            )
            await interaction.response.send_message(message, ephemeral=True)
            return

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
        log_info(
            "schedule.answer.saved",
            guild_id=self.guild_id,
            event_id=self.event_id,
            date=self.date["value"],
            user_id=interaction.user.id,
            status=self.status,
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
