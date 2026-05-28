import discord

from config import STATUS_LABELS
from database import get_member_icon, get_users


# =========================
# Embed表示
# =========================
# 結果表示のタイトルや文言を変えたい場合は、このファイルを調整します。


def get_all_members(guild):
    return [member for member in guild.members if not member.bot]


def format_member_list(guild, user_ids):
    names = []
    for user_id in user_ids:
        member = guild.get_member(user_id)
        if member:
            names.append(member.display_name)
    return "\n".join(names) if names else "なし"


def format_member_inline(guild, user_ids):
    names = []
    for user_id in user_ids:
        member = guild.get_member(user_id)
        if member:
            names.append(member.display_name)

    return "、".join(names) if names else "-"


def format_member_icon_inline(user_ids):
    icons = [get_member_icon(user_id) for user_id in sorted(user_ids)]
    return "".join(icons) if icons else "-"


def build_member_icon_legend(guild, user_ids):
    lines = []

    for user_id in sorted(user_ids):
        member = guild.get_member(user_id)
        if member:
            lines.append(f"{get_member_icon(user_id)}={member.display_name}")

    return "\n".join(lines) if lines else "入力者なし"


def create_result_embed(guild, event_id, dates):
    all_member_count = len(get_all_members(guild))
    perfect_dates = []
    lines = []

    embed = discord.Embed(
        title=f"📅日程調整: {event_id}",
        description="現在の回答状況",
        color=discord.Color.blue(),
    )

    for date in dates:
        available_users = get_users(event_id, date["value"], "available")
        maybe_users = get_users(event_id, date["value"], "maybe")

        if all_member_count and len(available_users) == all_member_count:
            perfect_dates.append(date["label"])

        lines.append(
            f"{date['label']}  ◎ {len(available_users)}人 / △ {len(maybe_users)}人"
        )

    embed.description = "\n".join(lines) if lines else "日程がありません"

    if perfect_dates:
        embed.add_field(
            name="✅全員参加可能日",
            value="\n".join(f"◎ {date}" for date in perfect_dates),
            inline=False,
        )
        embed.color = discord.Color.green()

    embed.set_footer(text="Schedule Tool")
    return embed


def create_personal_embed(guild, event_id, dates, user_id):
    lines = []

    for date in dates:
        status_label = "未選択"

        for status, label in STATUS_LABELS.items():
            users = get_users(event_id, date["value"], status)
            if user_id in users:
                status_label = label
                break

        lines.append(f"{date['label']}  {status_label}")

    embed = discord.Embed(
        title=f"📅日程調整: {event_id}",
        description="\n".join(lines) if lines else "日程がありません",
        color=discord.Color.blue(),
    )

    embed.set_footer(text="あなたの回答状況")
    return embed


def create_monthly_table_embed(guild, event_id, dates):
    embed = discord.Embed(
        title=f"月間日程表: {event_id}",
        color=discord.Color.blue(),
    )

    grouped_dates = {}
    answered_user_ids = set()

    for date in dates:
        month = date["value"][:6]
        grouped_dates.setdefault(month, []).append(date)

    for month, month_dates in grouped_dates.items():
        lines = []

        for date in month_dates:
            available_users = get_users(event_id, date["value"], "available")
            maybe_users = get_users(event_id, date["value"], "maybe")
            no_users = get_users(event_id, date["value"], "no")
            answered_user_ids.update(available_users)
            answered_user_ids.update(maybe_users)
            answered_user_ids.update(no_users)

            lines.append(
                f"{date['label']}｜"
                f"◎{format_member_icon_inline(available_users)}｜"
                f"△{format_member_icon_inline(maybe_users)}｜"
                f"×{format_member_icon_inline(no_users)}"
            )

        table_text = "\n".join(lines)

        embed.add_field(
            name=f"{month[:4]}年{int(month[4:])}月",
            value=f"```text\n{table_text}\n```",
            inline=False,
        )

    if not grouped_dates:
        embed.description = "日程がありません"

    embed.add_field(
        name="アイコン",
        value=build_member_icon_legend(guild, answered_user_ids),
        inline=False,
    )
    embed.set_footer(text="押した人だけに表示されています")
    return embed
