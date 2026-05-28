from datetime import datetime

from discord import app_commands

from config import MAX_DAYS, MY_GUILD, RESULT_CHANNEL_ID
from close_service import close_schedule
from database import (
    delete_event,
    get_auto_schedule_settings,
    get_dates,
    get_event_list,
    get_schedule_settings,
    save_auto_schedule_settings,
    save_reminder_settings,
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
        guild=MY_GUILD,
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

        save_schedule_settings(event_name, days)

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
        guild=MY_GUILD,
    )
    @app_commands.describe(
        start="開始日 YYYY-MM-DD",
    )
    async def schedule(
        interaction,
        start: str,
    ):
        settings = get_schedule_settings()
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
        guild=MY_GUILD,
    )
    @app_commands.describe(
        first_start="最初に調整する開始日 YYYY-MM-DD",
        lead_days="開始日の何日前に日程調整を出すか。省略時は5日前",
    )
    async def auto_schedule_start(
        interaction,
        first_start: str,
        lead_days: int = 5,
    ):
        settings = get_schedule_settings()
        if not settings:
            await interaction.response.send_message(
                "先に /schedule_setting でイベント名と日数を設定してください。",
                ephemeral=True,
            )
            return

        try:
            first_start_date = datetime.strptime(first_start, "%Y-%m-%d")
        except ValueError:
            await interaction.response.send_message(
                "日付形式は YYYY-MM-DD で入力してください。",
                ephemeral=True,
            )
            return

        if lead_days < 0:
            await interaction.response.send_message(
                "何日前に出すかは0以上で指定してください。",
                ephemeral=True,
            )
            return

        save_auto_schedule_settings(
            interaction.channel.id,
            first_start_date.strftime("%Y-%m-%d"),
            lead_days,
        )

        await interaction.response.send_message(
            f"自動作成を開始しました。\n"
            f"最初の開始日: {first_start_date.strftime('%Y-%m-%d')}\n"
            f"投稿タイミング: 開始日の{lead_days}日前\n"
            f"投稿先: このチャンネル",
            ephemeral=True,
        )

    @app_commands.checks.has_permissions(administrator=True)
    @client.tree.command(
        name="auto_schedule_stop",
        description="日程調整の自動作成を停止",
        guild=MY_GUILD,
    )
    async def auto_schedule_stop(interaction):
        auto_settings = get_auto_schedule_settings()
        if not auto_settings or not auto_settings["active"]:
            await interaction.response.send_message(
                "自動作成は動いていません。",
                ephemeral=True,
            )
            return

        stop_auto_schedule()
        await interaction.response.send_message(
            "日程調整の自動作成を停止しました。",
            ephemeral=True,
        )

    @client.tree.command(
        name="my_icon",
        description="月間日程表で使う自分のアイコンを設定",
        guild=MY_GUILD,
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
        guild=MY_GUILD,
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

        save_reminder_settings(days_before, hour, comment.strip())

        await interaction.response.send_message(
            f"参加可能日の通知設定を保存しました。\n"
            f"通知タイミング: {days_before}日前の{hour}時\n"
            f"コメント: {comment.strip() or 'なし'}",
            ephemeral=True,
        )

    @client.tree.command(
        name="list",
        description="イベント一覧表示",
        guild=MY_GUILD,
    )
    async def list_events(interaction):
        events = get_event_list()
        if not events:
            await interaction.response.send_message("イベントが存在しません")
            return

        text = "イベント一覧\n\n" + "\n".join(f"・{event_id}" for event_id in events)
        await interaction.response.send_message(text)

    @client.tree.command(
        name="result",
        description="イベント結果表示",
        guild=MY_GUILD,
    )
    @app_commands.describe(event_id="イベントID")
    async def result(interaction, event_id: str):
        dates = get_dates(event_id)
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
        guild=MY_GUILD,
    )
    @app_commands.describe(event_id="イベントID")
    async def announce(interaction, event_id: str):
        dates = get_dates(event_id)
        if not dates:
            await interaction.response.send_message(
                "イベントが見つかりません",
                ephemeral=True,
            )
            return

        channel = client.get_channel(RESULT_CHANNEL_ID)
        if not channel:
            await interaction.response.send_message(
                "通知チャンネルが見つかりません",
                ephemeral=True,
            )
            return

        await channel.send(embed=create_result_embed(interaction.guild, event_id, dates))
        await interaction.response.send_message("通知しました", ephemeral=True)

    @app_commands.checks.has_permissions(administrator=True)
    @client.tree.command(
        name="delete",
        description="イベント削除",
        guild=MY_GUILD,
    )
    @app_commands.describe(event_id="削除するイベントID")
    async def delete(interaction, event_id: str):
        events = get_event_list()
        if event_id not in events:
            await interaction.response.send_message(
                "イベントが見つかりません",
                ephemeral=True,
            )
            return

        delete_event(event_id)
        await interaction.response.send_message(f"イベント {event_id} を削除しました")

    @app_commands.checks.has_permissions(administrator=True)
    @client.tree.command(
        name="close",
        description="募集終了",
        guild=MY_GUILD,
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
    schedule_setting.error(admin_command_error)
    schedule.error(admin_command_error)
    auto_schedule_start.error(admin_command_error)
    auto_schedule_stop.error(admin_command_error)
    reminder_setting.error(admin_command_error)
    delete.error(admin_command_error)
    close.error(admin_command_error)
