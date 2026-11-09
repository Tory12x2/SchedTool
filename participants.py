from database import get_participant_role_id


PARTICIPANT_PAGE_SIZE = 24
CHANNEL_PERMISSION_LABELS = {
    "view_channel": "チャンネルを見る",
    "send_messages": "メッセージを送信",
    "embed_links": "埋め込みリンク",
}


def get_channel_access_issue(guild, channel, label):
    if not channel:
        return f"{label}が見つかりません。"

    bot_member = getattr(guild, "me", None)
    if not bot_member:
        return f"{label}でBotの権限を確認できません。"

    permissions_for = getattr(channel, "permissions_for", None)
    if not callable(permissions_for):
        return f"{label}でBotの権限を確認できません。"

    permissions = permissions_for(bot_member)
    missing = [
        permission_label
        for permission_name, permission_label in CHANNEL_PERMISSION_LABELS.items()
        if not getattr(permissions, permission_name, False)
    ]
    if missing:
        return f"{label}でBotに「{'」「'.join(missing)}」権限がありません。"

    return None


def get_participant_role(guild):
    role_id = get_participant_role_id(guild.id)
    if not role_id:
        return None
    return guild.get_role(role_id)


def is_participant_role_missing(guild):
    role_id = get_participant_role_id(guild.id)
    return bool(role_id and not guild.get_role(role_id))


def get_participant_members(guild):
    role_id = get_participant_role_id(guild.id)
    if not role_id:
        return [member for member in guild.members if not member.bot]

    role = guild.get_role(role_id)
    if not role:
        return []
    return [member for member in role.members if not member.bot]


def get_participant_member_ids(guild):
    return {member.id for member in get_participant_members(guild)}


def can_member_answer(guild, member):
    if member.guild_permissions.administrator:
        return True

    role_id = get_participant_role_id(guild.id)
    if not role_id:
        return True

    role = guild.get_role(role_id)
    return bool(role and role in member.roles)


def build_large_group_warning(guild):
    role_id = get_participant_role_id(guild.id)
    member_count = len([member for member in guild.members if not member.bot])
    if role_id or member_count <= PARTICIPANT_PAGE_SIZE:
        return ""

    return (
        f"\n\n注意: 対象メンバーが{member_count}人います。"
        "24人を超える場合は、参加予定者ロールの設定を推奨します。"
    )
