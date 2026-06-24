from datetime import datetime

import discord
from discord import app_commands

from config import MAX_DAYS
from close_service import close_schedule
from auto_scheduler import build_available_day_reminder_text, get_non_bot_member_ids
from database import (
    delete_event,
    get_auto_schedule_settings,
    get_dates,
    get_event_list,
    get_latest_event_period,
    get_notification_mention_enabled,
    get_participant_role_id,
    get_result_channel_id,
    get_reminder_settings,
    get_schedule_settings,
    get_users,
    save_auto_schedule_settings,
    save_notification_mention_enabled,
    save_participant_role_id,
    save_reminder_settings,
    save_result_channel_id,
    save_schedule_settings,
    set_member_icon,
    stop_auto_schedule,
)
from embeds import create_result_embed
from schedule_service import create_schedule


# =========================
# スラッシュコマンド
# =========================
# コマンド名や説明文を変えたい場合は、各 @client.tree.command の
# name / description を調整します。


def setup_commands(client):
    @app_commands.checks.has_permissions(administrator=True)
    @client.tree.command(
        name="schedule_setting",
        description="日程調整のイベント名と日数を設定",
    )
    @app_commands.describe(
        event_name="イベント名",
        days="1回で日程調整する日数",
    )
    async def schedule_setting(
        interaction,
        event_name: str,
        days: int,
    ):
        if days < 1 or days > MAX_DAYS:
            await interaction.response.send_message(
                f"日数は1〜{MAX_DAYS}日の範囲で指定してください。",
                ephemeral=True,
            )
            return

        save_schedule_settings(event_name, days, interaction.guild.id)

        await interaction.response.send_message(
            f"日程調整設定を保存しました。\n"
            f"イベント名: {event_name}\n"
            f"日数: {days}日",
            ephemeral=True,
        )

    @app_commands.checks.has_permissions(administrator=True)
    @client.tree.command(
        name="schedule",
        description="設定済みの日程調整を開始日から作成",
    )
    @app_commands.describe(
        start="開始日 YYYY-MM-DD",
    )
    async def schedule(
        interaction,
        start: str,
    ):
        settings = get_schedule_settings(interaction.guild.id)
        if not settings:
            await interaction.response.send_message(
                "先に /schedule_setting でイベント名と日数を設定してください。",
                ephemeral=True,
            )
            return

        try:
            start_date = datetime.strptime(start, "%Y-%m-%d")
        except ValueError:
            await interaction.response.send_message(
                "日付形式は YYYY-MM-DD で入力してください。",
                ephemeral=True,
            )
            return

        event_name = settings["event_name"]
        days = settings["days"]

        try:
            event_id, _ = await create_schedule(
                client,
                interaction.guild,
                interaction.channel,
                event_name,
                start_date,
                days,
            )
        except RuntimeError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return

        await interaction.response.send_message(
            f"日程調整を作成しました: {event_id}",
            ephemeral=True,
        )

    @app_commands.checks.has_permissions(administrator=True)
    @client.tree.command(
        name="auto_schedule_start",
        description="日程調整の自動作成を開始",
    )
    @app_commands.describe(
        event_name="自動作成するイベント名",
        lead_days="開始日の何日前に日程調整を出すか。省略時は5日前",
    )
    async def auto_schedule_start(
        interaction,
        event_name: str,
        lead_days: int = 5,
    ):
        if lead_days < 0:
            await interaction.response.send_message(
                "何日前に出すかは0以上で指定してください。",
                ephemeral=True,
            )
            return

        event_name = event_name.strip()
        if not event_name:
            await interaction.response.send_message(
                "イベント名を入力してください。",
                ephemeral=True,
            )
            return

        latest_period = get_latest_event_period(event_name, interaction.guild.id)
        if not latest_period:
            await interaction.response.send_message(
                f"{event_name} の日程調整がまだ見つかりません。\n"
                "先に手動で1回作成してから、自動作成を開始してください。",
                ephemeral=True,
            )
            return

        save_schedule_settings(
            event_name,
            latest_period["days"],
            interaction.guild.id,
        )
        save_auto_schedule_settings(
            interaction.channel.id,
            latest_period["next_start_date"],
            lead_days,
            interaction.guild.id,
        )

        await interaction.response.send_message(
            f"自動作成を開始しました。\n"
            f"イベント名: {event_name}\n"
            f"基準にした日程調整: {latest_period['event_id']}\n"
            f"1回の日数: {latest_period['days']}日\n"
            f"次回開始日: {latest_period['next_start_date']}\n"
            f"投稿タイミング: 開始日の{lead_days}日前\n"
            f"投稿先: このチャンネル",
            ephemeral=True,
        )

    @app_commands.checks.has_permissions(administrator=True)
    @client.tree.command(
        name="auto_schedule_stop",
        description="日程調整の自動作成を停止",
    )
    @app_commands.describe(
        event_name="自動作成を停止するイベント名",
    )
    async def auto_schedule_stop(interaction, event_name: str):
        event_name = event_name.strip()
        auto_settings = get_auto_schedule_settings(interaction.guild.id)
        if not auto_settings or not auto_settings["active"]:
            await interaction.response.send_message(
                "自動作成は動いていません。",
                ephemeral=True,
            )
            return

        settings = get_schedule_settings(interaction.guild.id)
        active_event_name = settings["event_name"] if settings else ""
        if event_name != active_event_name:
            await interaction.response.send_message(
                f"{event_name} の自動作成は動いていません。\n"
                f"現在動いている自動作成: {active_event_name or '不明'}",
                ephemeral=True,
            )
            return

        stop_auto_schedule(interaction.guild.id)
        await interaction.response.send_message(
            f"{event_name} の自動作成を停止しました。",
            ephemeral=True,
        )

    @client.tree.command(
        name="my_icon",
        description="月間日程表で使う自分のアイコンを設定",
    )
    @app_commands.describe(
        icon="使いたいアイコン。例: 🍎"
    )
    async def my_icon(interaction, icon: str):
        icon = icon.strip()

        if not icon:
            await interaction.response.send_message(
                "アイコンを入力してください。",
                ephemeral=True,
            )
            return

        if len(icon) > 4:
            await interaction.response.send_message(
                "アイコンは短い文字で指定してください。絵文字1つがおすすめです。",
                ephemeral=True,
            )
            return

        saved = set_member_icon(interaction.user.id, icon)
        if not saved:
            await interaction.response.send_message(
                "そのアイコンは他のメンバーが使用中です。",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"あなたのアイコンを {icon} に設定しました。",
            ephemeral=True,
        )

    @app_commands.checks.has_permissions(administrator=True)
    @client.tree.command(
        name="reminder_setting",
        description="参加可能日の通知タイミングを設定",
    )
    @app_commands.describe(
        days_before="何日前に通知するか。省略時は1日前",
        hour="何時に通知するか。0〜23で指定。省略時は21時",
        comment="通知に添える一言コメント",
    )
    async def reminder_setting(
        interaction,
        days_before: int = 1,
        hour: int = 21,
        comment: str = "",
    ):
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

        save_reminder_settings(days_before, hour, comment.strip(), interaction.guild.id)

        await interaction.response.send_message(
            f"参加可能日の通知設定を保存しました。\n"
            f"通知タイミング: {days_before}日前の{hour}時\n"
            f"コメント: {comment.strip() or 'なし'}",
            ephemeral=True,
        )

    @app_commands.checks.has_permissions(administrator=True)
    @client.tree.command(
        name="notification_channel_setting",
        description="結果や参加可能日通知を送るチャンネルを設定",
    )
    @app_commands.describe(
        channel="通知先にするテキストチャンネル",
    )
    async def notification_channel_setting(
        interaction,
        channel: discord.TextChannel,
    ):
        save_result_channel_id(channel.id, interaction.guild.id)

        await interaction.response.send_message(
            f"通知チャンネルを {channel.mention} に設定しました。",
            ephemeral=True,
        )

    @app_commands.checks.has_permissions(administrator=True)
    @client.tree.command(
        name="notification_mention_setting",
        description="参加可能日通知でメンションするか設定",
    )
    @app_commands.describe(
        enabled="メンションする場合はTrue、しない場合はFalse",
    )
    async def notification_mention_setting(
        interaction,
        enabled: bool,
    ):
        save_notification_mention_enabled(enabled, interaction.guild.id)

        await interaction.response.send_message(
            f"通知メンションを{'有効' if enabled else '無効'}にしました。",
            ephemeral=True,
        )

    @app_commands.checks.has_permissions(administrator=True)
    @client.tree.command(
        name="participant_role_setting",
        description="日程調整の参加予定者ロールを設定",
    )
    @app_commands.describe(
        role="参加予定者として扱うロール",
    )
    async def participant_role_setting(
        interaction,
        role: discord.Role,
    ):
        save_participant_role_id(role.id, interaction.guild.id)

        await interaction.response.send_message(
            f"参加予定者ロールを {role.mention} に設定しました。",
            ephemeral=True,
        )

    @app_commands.checks.has_permissions(administrator=True)
    @client.tree.command(
        name="admin_status",
        description="Bot設定と未回答者を確認",
    )
    @app_commands.describe(
        event_id="確認するイベントID。省略すると全イベントを表示",
    )
    async def admin_status(interaction, event_id: str = ""):
        events = [event_id] if event_id else get_event_list(interaction.guild.id)
        events = [event for event in events if event]

        if event_id and event_id not in get_event_list(interaction.guild.id):
            await interaction.response.send_message(
                "イベントが見つかりません",
                ephemeral=True,
            )
            return

        participant_members = get_participant_members_for_status(interaction.guild)
        participant_ids = {member.id for member in participant_members}
        lines = build_admin_status_lines(
            interaction.guild,
            events,
            participant_members,
            participant_ids,
            interaction.guild.id,
        )

        await send_chunked_status(interaction, "\n".join(lines))

    @client.tree.command(
        name="list",
        description="イベント一覧表示",
    )
    async def list_events(interaction):
        events = get_event_list(interaction.guild.id)
        if not events:
            await interaction.response.send_message(
                "イベントが存在しません",
                ephemeral=True,
            )
            return

        text = "イベント一覧\n\n" + "\n".join(f"・{event_id}" for event_id in events)
        await interaction.response.send_message(text, ephemeral=True)

    @client.tree.command(
        name="result",
        description="イベント結果表示",
    )
    @app_commands.describe(event_id="イベントID")
    async def result(interaction, event_id: str):
        dates = get_dates(event_id, interaction.guild.id)
        if not dates:
            await interaction.response.send_message("イベントが見つかりません")
            return

        await interaction.response.send_message(
            embed=create_result_embed(interaction.guild, event_id, dates)
        )

    @app_commands.checks.has_permissions(administrator=True)
    @client.tree.command(
        name="announce",
        description="結果を通知チャンネルへ投稿",
    )
    @app_commands.describe(event_id="イベントID")
    async def announce(interaction, event_id: str):
        dates = get_dates(event_id, interaction.guild.id)
        if not dates:
            await interaction.response.send_message(
                "イベントが見つかりません",
                ephemeral=True,
            )
            return

        channel = client.get_channel(get_result_channel_id(interaction.guild.id))
        if not channel:
            await interaction.response.send_message(
                "通知チャンネルが見つかりません。/notification_channel_setting で設定してください。",
                ephemeral=True,
            )
            return

        await channel.send(embed=create_result_embed(interaction.guild, event_id, dates))
        await interaction.response.send_message("通知しました", ephemeral=True)

    @app_commands.checks.has_permissions(administrator=True)
    @client.tree.command(
        name="available_day_reminder_test",
        description="参加可能日通知をテスト送信",
    )
    @app_commands.describe(
        event_id="イベントID",
        date="通知する日付 YYYY-MM-DD",
    )
    async def available_day_reminder_test(
        interaction,
        event_id: str,
        date: str,
    ):
        dates = get_dates(event_id, interaction.guild.id)
        if not dates:
            await interaction.response.send_message(
                "イベントが見つかりません",
                ephemeral=True,
            )
            return

        try:
            target_date = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            await interaction.response.send_message(
                "日付形式は YYYY-MM-DD で入力してください。",
                ephemeral=True,
            )
            return

        target_value = target_date.strftime("%Y%m%d")
        if target_value not in {schedule_date["value"] for schedule_date in dates}:
            await interaction.response.send_message(
                "指定した日付はこのイベントに含まれていません。",
                ephemeral=True,
            )
            return

        available_users = get_users(
            event_id,
            target_value,
            "available",
            interaction.guild.id,
        )
        member_ids = get_non_bot_member_ids(interaction.guild)
        available_users &= member_ids
        unavailable_users = (
            get_users(event_id, target_value, "no", interaction.guild.id) & member_ids
        )
        if unavailable_users:
            await interaction.response.send_message(
                "指定した日付に不参加の人がいるため、通知対象外です。",
                ephemeral=True,
            )
            return

        maybe_users = (
            get_users(event_id, target_value, "maybe", interaction.guild.id) & member_ids
        )
        answered_users = available_users | maybe_users | unavailable_users

        if not member_ids.issubset(answered_users):
            await interaction.response.send_message(
                "指定した日付は、まだ全員の予定が入力されていません。",
                ephemeral=True,
            )
            return

        channel = client.get_channel(get_result_channel_id(interaction.guild.id))
        if not channel:
            await interaction.response.send_message(
                "通知チャンネルが見つかりません。/notification_channel_setting で設定してください。",
                ephemeral=True,
            )
            return

        reminder_settings = get_reminder_settings(interaction.guild.id)
        await channel.send(
            "[テスト送信]\n"
            + build_available_day_reminder_text(
                event_id,
                target_date,
                available_users,
                maybe_users,
                reminder_settings["comment"],
                get_notification_mention_enabled(interaction.guild.id),
            )
        )

        await interaction.response.send_message(
            f"{channel.mention} にテスト通知を送信しました。",
            ephemeral=True,
        )

    @app_commands.checks.has_permissions(administrator=True)
    @client.tree.command(
        name="delete",
        description="イベント削除",
    )
    @app_commands.describe(event_id="削除するイベントID")
    async def delete(interaction, event_id: str):
        events = get_event_list(interaction.guild.id)
        if event_id not in events:
            await interaction.response.send_message(
                "イベントが見つかりません",
                ephemeral=True,
            )
            return

        delete_event(event_id, interaction.guild.id)
        await interaction.response.send_message(f"イベント {event_id} を削除しました")

    @app_commands.checks.has_permissions(administrator=True)
    @client.tree.command(
        name="close",
        description="募集終了",
    )
    @app_commands.describe(event_id="イベントID")
    async def close(interaction, event_id: str):
        closed = await close_schedule(client, interaction.guild, event_id)
        if not closed:
            await interaction.response.send_message(
                "イベントが見つかりません",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(f"{event_id} を終了しました")

    async def admin_command_error(interaction, error):
        if isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.response.send_message(
                "このコマンドは管理者のみ使用できます",
                ephemeral=True,
            )
            return
        raise error

    announce.error(admin_command_error)
    available_day_reminder_test.error(admin_command_error)
    schedule_setting.error(admin_command_error)
    schedule.error(admin_command_error)
    auto_schedule_start.error(admin_command_error)
    auto_schedule_stop.error(admin_command_error)
    reminder_setting.error(admin_command_error)
    notification_channel_setting.error(admin_command_error)
    notification_mention_setting.error(admin_command_error)
    participant_role_setting.error(admin_command_error)
    admin_status.error(admin_command_error)
    delete.error(admin_command_error)
    close.error(admin_command_error)


def get_participant_members_for_status(guild):
    role_id = get_participant_role_id(guild.id)
    if role_id:
        role = guild.get_role(role_id)
        if role:
            return [member for member in role.members if not member.bot]

    return [member for member in guild.members if not member.bot]


def build_admin_status_lines(guild, events, participant_members, participant_ids, guild_id):
    schedule_settings = get_schedule_settings(guild_id)
    auto_settings = get_auto_schedule_settings(guild_id)
    reminder_settings = get_reminder_settings(guild_id)
    result_channel = guild.get_channel(get_result_channel_id(guild_id))
    participant_role_id = get_participant_role_id(guild_id)
    participant_role = guild.get_role(participant_role_id) if participant_role_id else None

    lines = [
        "管理者ステータス",
        "",
        "設定",
        f"- 日程設定: {format_schedule_settings(schedule_settings)}",
        f"- 自動作成: {format_auto_settings(guild, auto_settings)}",
        f"- 通知先: {result_channel.mention if result_channel else '未設定/見つかりません'}",
        (
            f"- 参加予定者: {participant_role.mention}"
            if participant_role
            else "- 参加予定者: Bot以外の全メンバー"
        ),
        f"- 対象人数: {len(participant_members)}人",
        (
            f"- 通知: {reminder_settings['days_before']}日前の{reminder_settings['hour']}時"
            f" / メンション{'有効' if get_notification_mention_enabled(guild_id) else '無効'}"
        ),
        f"- 通知コメント: {reminder_settings['comment'] or 'なし'}",
        "",
        "未回答者",
    ]

    if not events:
        lines.append("- イベントがありません")
        return lines

    for event in events:
        dates = get_dates(event, guild_id)
        if not dates:
            lines.append(f"- {event}: イベントが見つかりません")
            continue

        lines.append(f"- {event}")
        for date in dates:
            available = get_users(event, date["value"], "available", guild_id) & participant_ids
            maybe = get_users(event, date["value"], "maybe", guild_id) & participant_ids
            unavailable = get_users(event, date["value"], "no", guild_id) & participant_ids
            answered = available | maybe | unavailable
            unanswered = participant_ids - answered

            if unanswered:
                names = format_member_names(guild, unanswered)
                lines.append(f"  {date['label']}: 未回答 {len(unanswered)}人 / {names}")
            else:
                lines.append(f"  {date['label']}: 全員回答済み")

    return lines


def format_schedule_settings(settings):
    if not settings:
        return "未設定"
    return f"{settings['event_name']} / {settings['days']}日"


def format_auto_settings(guild, settings):
    if not settings or not settings["active"]:
        return "停止中"

    channel = guild.get_channel(settings["channel_id"])
    channel_text = channel.mention if channel else f"不明なチャンネル({settings['channel_id']})"
    return (
        f"有効 / 次回開始日 {settings['next_start_date']}"
        f" / {settings['lead_days']}日前投稿 / {channel_text}"
    )


def format_member_names(guild, user_ids, limit=12):
    names = []
    for user_id in sorted(user_ids):
        member = guild.get_member(user_id)
        names.append(member.display_name if member else str(user_id))

    if len(names) > limit:
        shown = names[:limit]
        shown.append(f"ほか{len(names) - limit}人")
        return "、".join(shown)

    return "、".join(names)


async def send_chunked_status(interaction, text):
    chunks = []
    current = ""

    for line in text.splitlines():
        next_line = f"{line}\n"
        if len(current) + len(next_line) > 1900:
            chunks.append(current.rstrip())
            current = next_line
        else:
            current += next_line

    if current.strip():
        chunks.append(current.rstrip())

    if not chunks:
        chunks = ["表示する内容がありません"]

    await interaction.response.send_message(chunks[0], ephemeral=True)

    for chunk in chunks[1:]:
        await interaction.followup.send(chunk, ephemeral=True)
