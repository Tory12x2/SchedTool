import discord

from config import STATUS_LABELS
from database import get_member_icon, get_users
from participants import (
    PARTICIPANT_PAGE_SIZE,
    get_participant_members,
    is_participant_role_missing,
)


# =========================
# Embed表示
# =========================
# 結果表示のタイトルや文言を変えたい場合は、このファイルを調整します。


def get_all_members(guild):
    return get_participant_members(guild)


def filter_participant_users(guild, user_ids):
    participant_ids = {member.id for member in get_all_members(guild)}
    return set(user_ids) & participant_ids


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


def add_chunked_field(embed, name, lines, limit=1000):
    chunks = []
    current = []
    current_length = 0

    for line in lines:
        extra_length = len(line) + (1 if current else 0)
        if current and current_length + extra_length > limit:
            chunks.append("\n".join(current))
            current = []
            current_length = 0
        current.append(line)
        current_length += len(line) + (1 if current_length else 0)

    if current:
        chunks.append("\n".join(current))

    if not chunks:
        chunks = ["-"]

    for index, chunk in enumerate(chunks):
        field_name = name if index == 0 else f"{name}（続き）"
        embed.add_field(name=field_name, value=chunk, inline=False)


def create_result_embed(guild, event_id, dates):
    all_member_count = len(get_all_members(guild))
    perfect_dates = []
    lines = []

    embed = discord.Embed(
        title=f"📅日程調整: {event_id}",
        description="現在の回答状況",
        color=discord.Color.blue(),
    )

    if is_participant_role_missing(guild):
        embed.description = (
            "設定されている参加予定者ロールが見つかりません。"
            "管理者による再設定が必要です。"
        )
        embed.color = discord.Color.orange()
        embed.set_footer(text="Schedule Tool")
        return embed

    for date in dates:
        available_users = filter_participant_users(
            guild,
            get_users(event_id, date["value"], "available", guild.id),
        )
        maybe_users = filter_participant_users(
            guild,
            get_users(event_id, date["value"], "maybe", guild.id),
        )

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


def create_personal_embed(guild, event_id, dates, user_id, deadline_text=None):
    lines = []

    for date in dates:
        status_label = "未選択"

        for status, label in STATUS_LABELS.items():
            users = get_users(event_id, date["value"], status, guild.id)
            if user_id in users:
                status_label = label
                break

        lines.append(f"{date['label']}  {status_label}")

    embed = discord.Embed(
        title=f"📅日程調整: {event_id}",
        description="\n".join(lines) if lines else "日程がありません",
        color=discord.Color.blue(),
    )

    footer_text = "あなたの回答状況"
    if deadline_text:
        footer_text += f" / 締切: {deadline_text}"

    embed.set_footer(text=footer_text)
    return embed


def get_monthly_table_page_count(guild):
    member_count = len(get_all_members(guild))
    return max(1, (member_count + PARTICIPANT_PAGE_SIZE - 1) // PARTICIPANT_PAGE_SIZE)


def create_monthly_table_embed(guild, event_id, dates, page=0):
    members = sorted(get_all_members(guild), key=lambda member: member.id)
    page_count = get_monthly_table_page_count(guild)
    page = max(0, min(page, page_count - 1))
    start = page * PARTICIPANT_PAGE_SIZE
    page_members = members[start : start + PARTICIPANT_PAGE_SIZE]
    page_member_ids = {member.id for member in page_members}

    embed = discord.Embed(
        title=f"月間日程表: {event_id}",
        color=discord.Color.blue(),
    )

    grouped_dates = {}
    for date in dates:
        month = date["value"][:6]
        grouped_dates.setdefault(month, []).append(date)

    for month, month_dates in grouped_dates.items():
        lines = []

        for date in month_dates:
            available_users = (
                get_users(event_id, date["value"], "available", guild.id)
                & page_member_ids
            )
            maybe_users = (
                get_users(event_id, date["value"], "maybe", guild.id)
                & page_member_ids
            )
            no_users = (
                get_users(event_id, date["value"], "no", guild.id)
                & page_member_ids
            )

            lines.append(
                f"{date['label']}｜"
                f"◎{format_member_icon_inline(available_users)}｜"
                f"△{format_member_icon_inline(maybe_users)}｜"
                f"×{format_member_icon_inline(no_users)}"
            )

        add_chunked_field(
            embed,
            f"{month[:4]}年{int(month[4:])}月",
            lines,
        )

    if not grouped_dates:
        embed.description = "日程がありません"

    legend_lines = build_member_icon_legend(guild, page_member_ids).splitlines()
    add_chunked_field(
        embed,
        "アイコン",
        legend_lines,
    )
    embed.set_footer(
        text=f"押した人だけに表示されています / {page + 1}/{page_count}ページ"
    )
    return embed
